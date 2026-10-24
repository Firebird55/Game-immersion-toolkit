import assert from 'node:assert/strict';
import {startPreview} from './e2e-preview.mjs';
import {chromium,firefox} from 'playwright';

// Exercise the actual built CompanionClient, including its HTTP/WS bindings.
// Every account request is handled locally; no real credentials or account writes.
const preview=await startPreview('ui-state-react'),{origin}=preview;
let browser;
const started=Date.now(),phase=message=>console.log(`React fixture +${Date.now()-started}ms: ${message}`);
const requestInfo=request=>({method:request.method(),type:request.resourceType(),url:request.url()});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
try {
 for(const[name,engine] of Object.entries({chromium,firefox})) {
  phase(name+': launching browser');
  browser=await engine.launch();phase(name+': browser launched');
  for(const width of [1280,390]) {
   phase(`${name} ${width}: creating context and page`);
   const context=await browser.newContext({locale:'en-US',viewport:{width,height:900}}),page=await context.newPage();
   phase(`${name} ${width}: page created`);
   const pendingRequests=new Map(),network=[];
   const record=value=>{network.push({elapsed_ms:Date.now()-started,...value});if(network.length>80)network.shift();};
   page.on('request',request=>{const info=requestInfo(request);pendingRequests.set(request,info);record({event:'request',...info});});
   page.on('response',response=>record({event:'response',status:response.status(),url:response.url()}));
   page.on('requestfinished',request=>pendingRequests.delete(request));
   page.on('requestfailed',request=>{pendingRequests.delete(request);record({event:'requestfailed',...requestInfo(request),failure:request.failure()?.errorText});});
   page.on('domcontentloaded',()=>record({event:'domcontentloaded',url:page.url()}));
   page.on('load',()=>record({event:'load',url:page.url()}));
   page.on('crash',()=>record({event:'crash'}));
   const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));
   let socket,active='first',runtimeId='react-fixture',generation=0,revision=0,holdSnapshot=false,releaseSnapshot,extraLine=false,emptySnapshot=false,sourceText='Hello';
   const stateContext=()=>({runtime_id:runtimeId,state_version:revision,account_generation:generation});
   const region={left:.1,top:.6,width:.8,height:.25};
   const settings={preferred_game:'auto',region,tip_region:region,cinematic_region:region,hito_region:region,hito_tip_region:region,auto_start:false};
   const capture={running:true,active_game:'zzz',visible_text_ids:['fixture'],phase:'matched',message:'Ready'};
   const line=(id=1)=>({id,game:'zzz',created_at:id===1?'2026-01-01T10:00:00Z':'2026-01-01T09:00:00Z',session_id:'fixture',source_ocr:'Hello',english:id===1?'Hello':'Snapshot-only-line',chinese:id===1?'你好':'快照行',source_language:'en',source_locale:'en',source_text:id===1?sourceText:'Snapshot-only-line',translation_locale:active==='first'?'zh-Hans':'nl',translation_text:active==='first'?'你好':'Hallo',text_id:id===1?'fixture':'extra',channel:'dialogue',score:100,match_kind:'exact',voiced:true,has_audio:true,favorite:false});
   const snapshot=()=>({context:stateContext(),status:{capture,textmaps:{ready:true,entry_count:1},audio:{ready:true},settings,session:{id:'fixture',line_count:extraLine?2:1,total_line_count:extraLine?2:1},selected_languages:{zzz:{source_language:'en',source_locale:'en'}}},lines:emptySnapshot?[]:extraLine?[line(),line(2)]:[line()],lexirise:{configured:true,account:active,sent:{},decks:{}}});
   const sendEvent=(type,payload={},version=++revision)=>socket.send(JSON.stringify({type,context:{...stateContext(),state_version:version},...payload}));
   const until=async predicate=>{for(let attempt=0;attempt<100;attempt++){if(await predicate())return;await sleep(20);}throw Error('React fixture condition timed out');};
   await page.addInitScript(()=>{
    localStorage.setItem('proxy-transcript-reading-mode','migaku');
    // Capture the real React polling callback, so ordinary polls can be invoked
    // deterministically without account-reset events or ten-second sleeps.
    const nativeInterval=window.setInterval.bind(window);
    window.setInterval=(callback,delay,...args)=>{
     if(delay===10000)window.runCompanionPoll=callback;
     return nativeInterval(callback,delay,...args);
    };
   });
   await page.routeWebSocket('ws://127.0.0.1:8766/api/ws',ws=>{socket=ws;});
   await page.route('http://127.0.0.1:8766/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    requests.push({path,method:request.method(),account:request.headers()['x-proxy-transcript-account']});
    const respond=(body,status=200)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:JSON.stringify(body)});
    if(request.method()==='OPTIONS')return respond({});
    if(path==='/api/snapshot') {
     const body=snapshot();
     if(holdSnapshot){holdSnapshot=false;releaseSnapshot=()=>respond(body);return;}
     return respond(body);
    }
    if(path==='/api/setup')return respond({completed:true,version:'fixture',games:[],requirements:[],jobs:{},native:{},auto_start:false,lexirise_configured:true,free_gb:10});
    if(path==='/api/lines/1/lexirise'&&request.method()==='POST')return respond({detail:'Synthetic failure; account was inspected without exporting'},409);
    errors.push('Unexpected fixture route: '+request.method()+' '+path);return respond({},500);
   });
   try {
    // Use the same numeric address as the listener, and prove the HTTP server
    // answers before attributing a navigation stall to the browser. A readiness
    // failure stays a failure; neither the probe nor navigation is retried.
    phase(`${name} ${width}: checking HTTP readiness at ${origin}`);
    const response=await fetch(origin,{signal:AbortSignal.timeout(5000)});
    await response.arrayBuffer();assert.equal(response.status,200,'React preview HTTP readiness');
    phase(`${name} ${width}: HTTP ready; navigating`);
    await page.goto(origin,{waitUntil:'load',timeout:30000});
    phase(`${name} ${width}: navigation loaded`);
   } catch(error) {
    console.error('React fixture navigation diagnostics: '+JSON.stringify({browser:name,width,origin,
     url:page.url(),pending:[...pendingRequests.values()],network,...preview.diagnostics()},null,2));
    throw error;
   }
   const current=page.locator('.current-line'),send=current.locator('.lexirise-send');
   await send.waitFor();await until(()=>send.isEnabled());
   // Independent domains can arrive out of publication order. The older line
   // remains newer than that line's last snapshot, despite a newer capture event.
   revision=2;sendEvent('capture_status',{capture},2);
   sendEvent('line',{line:{...line(),source_text:'NEW VERSION',translation_text:'New translation',favorite:true}},1);
   await current.getByText('NEW VERSION',{exact:true}).waitFor();
   assert.equal(await current.getByRole('button',{name:'Remove current line from favorites',exact:true}).count(),1);
   revision=4;sendEvent('line',{line:{...line(),source_text:'LATEST SAME ID'}},4);
   sendEvent('line',{line:{...line(),source_text:'STALE SAME ID'}},3);
   await current.getByText('LATEST SAME ID',{exact:true}).waitFor();assert.equal(await page.getByText('STALE SAME ID',{exact:true}).count(),0);
   // A complete HTTP read overlaps later capture and line events. Commit the
   // independent snapshot rows while retaining both newer live domains.
   extraLine=true;holdSnapshot=true;releaseSnapshot=null;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await until(()=>!!releaseSnapshot);
   sendEvent('capture_status',{capture:{...capture,phase:'new_capture_phase'}});
   sendEvent('line',{line:{...line(),source_text:'AFTER HTTP READ'}});
   await releaseSnapshot();
   await current.getByText('AFTER HTTP READ',{exact:true}).waitFor();
   await page.getByText('Snapshot-only-line',{exact:true}).first().waitFor();
   await page.getByText('new capture phase',{exact:true}).first().waitFor();
   // A later deletion shares the line's ordering key; replay cannot resurrect it.
   holdSnapshot=true;releaseSnapshot=null;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await until(()=>!!releaseSnapshot);
   sendEvent('line_deleted',{line_id:2});
   await until(async()=>await page.getByText('Snapshot-only-line',{exact:true}).count()===0);
   await releaseSnapshot();await until(()=>send.isEnabled());
   assert.equal(await page.getByText('Snapshot-only-line',{exact:true}).count(),0);
   // No retry loop: continuous unrelated capture updates cannot starve a held
   // full snapshot, and successful reconciliation does not trigger extra reads.
   holdSnapshot=true;releaseSnapshot=null;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await until(()=>!!releaseSnapshot);
   const reads=requests.filter(r=>r.path==='/api/snapshot').length;
   const timer=setInterval(()=>sendEvent('capture_status',{capture}),10);
   try {await sleep(120);await releaseSnapshot();await until(()=>send.isEnabled());await sleep(100);} finally {clearInterval(timer);}
   assert.equal(requests.filter(r=>r.path==='/api/snapshot').length,reads,'Capture events must not force snapshot retries');
   // A pending audio line published after the HTTP read remains visible when
   // that older full payload is reconciled, even without an audio file yet.
   holdSnapshot=true;releaseSnapshot=null;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await until(()=>!!releaseSnapshot);
   sendEvent('capture_status',{capture:{...capture,visible_text_ids:['pending']}});
   sendEvent('line',{line:{...line(),id:3,text_id:'pending',created_at:'2026-01-01T10:01:00Z',source_text:'PENDING ORIGINAL AUDIO',has_audio:false,audio_pending:true}});
   await current.getByText('PENDING ORIGINAL AUDIO',{exact:true}).waitFor();
   await releaseSnapshot();await current.getByRole('button',{name:'Preparing original voice',exact:true}).waitFor();
   assert.equal(await current.getByText('PENDING ORIGINAL AUDIO',{exact:true}).count(),1);
   sendEvent('line_deleted',{line_id:3});sendEvent('capture_status',{capture});
   sendEvent('line',{line:line()});await until(()=>send.isEnabled());
   // Ordinary polling (without account/connection resets) is authoritative for
   // changed fields and an empty game, while keeping the account available.
   sourceText='HTTP SNAPSHOT UPDATED';revision++;
   await page.evaluate(()=>window.runCompanionPoll());
   await current.getByText('HTTP SNAPSHOT UPDATED',{exact:true}).waitFor();
   emptySnapshot=true;revision++;
   await page.evaluate(()=>window.runCompanionPoll());
   await until(async()=>await current.locator('.current-pair').count()===0);
   assert.equal(await page.locator('.transcript-line').count(),0);
   emptySnapshot=false;revision++;
   await page.evaluate(()=>window.runCompanionPoll());await until(()=>send.isEnabled());
   // Observe the account boundary in any event, even if account_changed arrives
   // later. An old A generation can never resume A after a B→A round trip.
   for(const account of ['second','first']) {
    active=account;generation++;const before=requests.filter(r=>r.path==='/api/snapshot').length;
    holdSnapshot=true;releaseSnapshot=null;
    const accountRevision=++revision;const captureRevision=++revision;
    sendEvent('capture_status',{capture},captureRevision);
    sendEvent('account_changed',{account},accountRevision);
    await until(()=>!!releaseSnapshot);assert.equal(await send.isEnabled(),false,'Account boundary retires export controls before the next snapshot');
    await releaseSnapshot();await until(()=>send.isEnabled());
    assert.equal(requests.filter(r=>r.path==='/api/snapshot').length,before+1,'One reset per account generation');
    await send.click();await until(()=>requests.filter(r=>r.path==='/api/lines/1/lexirise').at(-1)?.account===account);
    await until(()=>send.isEnabled());
   }
   const oldContext={...stateContext(),account_generation:0,state_version:revision+100};
   socket.send(JSON.stringify({type:'line',context:oldContext,line:{...line(),source_text:'PREVIOUS ACCOUNT GENERATION'}}));
   await sleep(50);assert.equal(await page.getByText('PREVIOUS ACCOUNT GENERATION',{exact:true}).count(),0);
   // A backend replacement invalidates the old HTTP response as well as all
   // old-runtime events, even when their version exceeds the new runtime's.
   holdSnapshot=true;releaseSnapshot=null;
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));await until(()=>!!releaseSnapshot);
   const releaseRetired=releaseSnapshot,retiredSocket=socket,retiredContext=stateContext();
   runtimeId='replacement';revision=0;generation=0;extraLine=false;
   retiredSocket.close();await until(()=>socket!==retiredSocket);await until(()=>send.isEnabled());
   await releaseRetired();
   socket.send(JSON.stringify({type:'line',context:{...retiredContext,state_version:1000},line:{...line(),source_text:'RETIRED RUNTIME'}}));
   await sleep(50);assert.equal(await page.getByText('RETIRED RUNTIME',{exact:true}).count(),0);
   assert.equal(await page.getByText('Snapshot-only-line',{exact:true}).count(),0);
   // The last row can be removed while this socket is disconnected. An empty
   // authoritative snapshot must remove it, including on same-runtime reconnect.
   emptySnapshot=true;revision++;
   const disconnectedSocket=socket;disconnectedSocket.close();
   await until(()=>socket!==disconnectedSocket);
   await until(async()=>await current.locator('.current-pair').count()===0);
   assert.equal(await page.locator('.transcript-line').count(),0);
   assert.deepEqual(errors,[]);await context.close();
   console.log(`${name}: actual React partial-event ordering, snapshot reconciliation and account generations ${width} passed`);
  }
  await browser.close();browser=null;
 }
}finally{
 try{await browser?.close();}finally{await preview.stop();}
}
