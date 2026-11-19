// Actual shared React + real scoped Android HTTP/lease server. Sizing/download
// provider responses and PNG admission are authored mocks, not provider/OCR proof.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync, mkdirSync, readFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium, firefox} from 'playwright';
import {authoredReceiverLibraryReady} from './android-runtime-diagnostics.mjs';

const frontend = resolve(process.argv[2] ?? 'output/game-data-ui-frontend');
const output = resolve('output/checks/game-data-ui'); mkdirSync(output, {recursive: true});
async function until(read, label) {
 const end = Date.now() + 30000;
 while (Date.now() < end) {if (await read()) return; await delay(100);}
 throw Error('Authored shared UI did not establish ' + label);
}
const initial = () => ({id:'zzz', title:'Zenless Zone Zero',state:'not_downloaded',revision:null,installed_revision:null,can_activate:false,region:'global',content_mode:'text',source_locale:'ja',target_locales:['en'],
 installed_bytes:0,deletable_bytes:0,retained_bytes:0,download_bytes:null,download_is_upper_bound:false,required_disk_bytes:null,plan_id:null,
 job:null,can_plan:true,can_download:false,can_delete:false,message:'Check size first.'});
const sender = `<!doctype html><canvas width="1600" height="240"></canvas><script>
let n=0;addEventListener('message',async e=>{if(!e.data?.getVideoFrame)return;
const c=document.querySelector('canvas'),x=c.getContext('2d');x.fillStyle='black';x.fillRect(0,0,1600,240);
x.fillStyle='rgb('+(++n%255)+',40,80)';x.fillRect(0,0,32,32);x.fillStyle='white';x.font='64px sans-serif';
x.fillText('Follow the river beyond the bridge.',40,140);const imageData=await new Promise(r=>c.toBlob(r,'image/png'));
parent.postMessage({action:'image-frame-capture',value:{imageData,imageType:'png',cib:e.data.cib,streamID:e.data.streamID}},e.origin);});</script>`;

for (const [name, engine] of Object.entries({chromium, firefox})) {
 const root = mkdtempSync(join(output, name + '-'));
 const service = spawn(process.env.PYTHON ?? 'python', ['-u','-m','scripts.android-account-ui-fixture',root,frontend], {stdio:['pipe','pipe','inherit']});
 const lines = createInterface({input:service.stdout})[Symbol.asyncIterator]();
 let browser;
 try {
  const item = await lines.next(); assert.equal(item.done,false);
  const {origin,library,cookie} = JSON.parse(item.value);
  browser = await engine.launch({headless:true}); const page = await browser.newPage({viewport:{width:390,height:844}});
  await page.context().addCookies([{name:'toolkit_session',value:cookie,url:origin,httpOnly:true,sameSite:'Strict'}]);
  let row=initial(), transfers=0, stops=0, deletes=0, frames=0, textOnlyLine=false, unverifiedLine=false, audioRequests=0, activations=0;
  page.on('request',request=>{if(/^\/api\/lines\/[0-9]+\/audio$/.test(new URL(request.url()).pathname))audioRequests++;});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route(origin+'/api/game-data**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname,body=request.postDataJSON();
   assert.equal(request.headers()['x-toolkit-account-generation'],'0');
   if(request.method()==='POST'&&path.endsWith('/start')){
    transfers++;assert.deepEqual(body,{region:'global',source_locale:'ja',target_locales:['en'],content_mode:'text-audio'});
    const job = row.job ?? {downloaded_bytes:0,total_bytes:null,progress_percent:0,completed_stages:0};
    row={...row,...body,revision:'authored-revision',state:'downloading',can_plan:false,message:'Checking game files…',
     job:{...job,id:'authored-job',status:'running',phase:'planning',stop_requested:false,message:'Checking game files…'}};
   }else if(request.method()==='POST'&&path.endsWith('/stop')){
    stops++;assert.deepEqual(body,{job_id:'authored-job'});
    row={...row,state:'not_downloaded',can_plan:true,job:{...row.job,status:'stopped',phase:'stopped',stop_requested:true}};
   }else if(request.method()==='DELETE'){
    deletes++;assert.deepEqual(body,{revision:'authored-revision'});row={...initial(),revision:'authored-revision',retained_bytes:4096};
   }else if(request.method()==='POST'&&path.endsWith('/activate')){
    activations++;assert.equal(path,'/api/game-data/zzz/activate');
    assert.deepEqual(body,{revision:'authored-installed'});
   }else assert.equal(request.method(),'GET');
   await route.fulfill({status:request.method()==='POST'&&path.endsWith('/start')?202:200,contentType:'application/json',
    body:JSON.stringify(request.method()==='GET'?{schema:'game-data-v1',games:[row]}:{game:row,freed_bytes:8192})});
  });
  await page.route('https://vdo.ninja/**', route=>route.fulfill({contentType:'text/html',body:sender}));
  await page.route(origin+'/api/snapshot',async route=>{
   if(!textOnlyLine&&!unverifiedLine)return route.continue();
   const response=await route.fetch(),value=await response.json();
   value.lines=[{id:9000001,game:'zzz',created_at:new Date().toISOString(),session_id:value.status.session.id,text_id:'authored:only-text',
    source_ocr:'A verified text-only caption remains readable.',english:'Official authored translation.',chinese:'已验证的纯文字对白。',
    source_text:'A verified text-only caption remains readable.',source_locale:'en',source_language:'en',texts:{en:'A verified text-only caption remains readable.'},
    translation_locale:'zh-Hans',translation_text:'已验证的纯文字对白。',audio_locale:'en',voice_status:'unknown',voiced:false,has_audio:false,
    audio_omitted_by_request:!unverifiedLine,source_voice_binding:null,text_capture_verified:!unverifiedLine,audio_pending:false,channel:'dialogue',match_kind:'exact',score:100,favorite:false}];
   value.status.capture.visible_text_ids=['authored:only-text'];
   value.context.state_version++;value.status.session.line_count++;value.status.session.total_line_count++;
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.route(origin+'/api/capture/frame',async route=>{
   const request=route.request();assert.equal(request.headers()['content-type'],'image/png');
   assert.equal(request.headers()['x-toolkit-account-generation'],'0');
   assert.match(request.headers()['x-toolkit-document-epoch'],/^[a-f0-9]{32}$/);
   assert.deepEqual([...request.postDataBuffer().subarray(0,8)],[137,80,78,71,13,10,26,10]); frames++;
   await route.fulfill({status:202,contentType:'application/json',body:'{}'});
  });
  await page.goto(origin); await page.getByRole('button',{name:'Settings',exact:true}).waitFor();
  assert.equal(await page.getByRole('combobox',{name:'Reading',exact:true}).count(),0);
  assert.equal(await page.getByText('Private library on this device',{exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'Connect screen',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'Stop screen',exact:true}).count(),0);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  const panel=page.getByRole('dialog',{name:'Zenless Zone Zero settings',exact:true});
  await panel.getByText('Available after starting',{exact:true}).waitFor();
  const layout=await panel.evaluate(element=>{const r=element.getBoundingClientRect();return {
   fits:element.scrollWidth<=element.clientWidth+1,inside:r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1};});
  assert.deepEqual(layout,{fits:true,inside:true});
  assert.equal(await panel.getByRole('button',{name:'Download',exact:true}).isEnabled(),true);
  assert.equal(await panel.getByRole('button',{name:'Check download size',exact:true}).count(),0);
  assert.equal(transfers,0);
  assert.equal(await panel.getByLabel('Game data content',{exact:true}).inputValue(),'text');
  await panel.getByLabel('Game data content',{exact:true}).selectOption('text-audio');
  await panel.getByRole('button',{name:'Download',exact:true}).click();
  const stop=panel.getByRole('button',{name:'Stop download',exact:true});
  await stop.waitFor();
  const bar=panel.getByRole('progressbar',{name:'Game data download progress'});
  assert.equal(await bar.getAttribute('value'),'0');
  row={...row,message:'Downloading game files…',job:{...row.job,phase:'transfer',downloaded_bytes:2048,total_bytes:8192,progress_percent:25}};
  await panel.getByText('2.0 KiB / 8.0 KiB currently estimated',{exact:true}).waitFor();
  assert.equal(await bar.getAttribute('value'),'25');
  row={...row,message:'Reading the ZZZ dialogue catalogue…',job:{...row.job,phase:'catalogue',downloaded_bytes:4096,total_bytes:16384,completed_stages:1}};
  await panel.getByText('Reading the ZZZ dialogue catalogue…',{exact:true}).waitFor();
  await panel.getByText(/4.0 KiB \/ 16.0 KiB currently estimated/).waitFor();
  assert.equal(await bar.getAttribute('value'),'25');
  await stop.click();
  await panel.getByRole('button',{name:'Continue download',exact:true}).click();
  await stop.waitFor();
  assert.equal(await bar.getAttribute('value'),'25');
  row={...row,state:'ready',installed_bytes:8192,deletable_bytes:8192,can_delete:true,can_plan:true,message:'Authored data ready.',
   job:{...row.job,status:'complete',phase:'ready',downloaded_bytes:7168,total_bytes:7168}};
  await panel.getByText('7.0 KiB',{exact:true}).waitFor();
  assert.equal(await bar.getAttribute('value'),'100');assert.equal(transfers,2);assert.equal(stops,1);
  await panel.getByRole('button',{name:'Delete downloaded data',exact:true}).waitFor({state:'visible'});
  await until(async()=>!(await panel.getByRole('button',{name:'Delete downloaded data',exact:true}).isDisabled()),'download completion polling');
  await panel.getByRole('button',{name:'Delete downloaded data',exact:true}).click();assert.equal(deletes,0);
  await panel.getByRole('button',{name:'Confirm delete',exact:true}).click();
  await panel.getByText('Available after starting',{exact:true}).waitFor();assert.equal(deletes,1);
  await page.keyboard.press('Escape');
  textOnlyLine=true;
  await page.locator('.current-line .current-chinese').getByText('A verified text-only caption remains readable.',{exact:true}).waitFor();
  await page.locator('.current-line').getByText('Text only',{exact:true}).waitFor();
  assert.equal(await page.locator('.current-line').getByRole('button',{name:'Original voice unavailable',exact:true}).count(),0);
  assert.equal(audioRequests,0);
  textOnlyLine=false;unverifiedLine=true;
  await until(async()=>await page.locator('.current-line .current-chinese').getByText('A verified text-only caption remains readable.',{exact:true}).count()===0,'unknown non-dialogue remains hidden despite audio_pending false');
  unverifiedLine=false;
  textOnlyLine=false;await page.reload();
  const link=page.getByLabel('VDO.Ninja link or stream code',{exact:true});
  await link.fill('authored-first');
  assert.equal(await link.inputValue(),'authored-first');
  assert.equal(await authoredReceiverLibraryReady(page),false);
  await delay(400);
  assert.equal(frames,0,'Unprepared game data must not start capture');
  assert.equal(await page.locator('.android-screen-viewer iframe').count(),0);
  // Seed an authored library through the maintained HTTP seam. This is test
  // setup; production download/activation is tested with real providers later.
  const imported=await page.request.post(origin+'/api/library/import',{headers:{'Origin':origin,'Content-Type':'application/zip',
   'X-Toolkit-Account-Generation':'0','X-Toolkit-Import-Id':crypto.randomUUID(),'X-Proxy-Transcript':'setup'},data:readFileSync(library)});
  assert.equal(imported.status(),200);
  await until(()=>page.evaluate(async()=>!!(await(await fetch('/api/snapshot')).json()).status.textmaps.ready),'authored prepared seed');
  assert.equal(activations,0);
  await until(()=>authoredReceiverLibraryReady(page),'actual keyed receiver ready after library activation');
  await until(()=>frames>=2,'draft stream code automatically connects after preparation');
  await link.fill('');
  await until(()=>page.evaluate(async()=>!(await(await fetch('/api/snapshot')).json()).status.capture.running),'clear draft native stop');
  const beforeSelection = frames;
  row={...row,state:'error',revision:'authored-new-estimate',installed_revision:'authored-installed',can_activate:true};
  await page.getByRole('combobox',{name:'Game',exact:true}).selectOption('wuwa');
  await delay(500);assert.equal(activations,0);
  await page.getByRole('combobox',{name:'Game',exact:true}).selectOption('zzz');
  await until(()=>activations===1,'explicit installed revision activation');
  assert.equal(frames,beforeSelection);  // Choosing a game never starts a private screen link.
  await page.getByRole('button',{name:'Instructions',exact:true}).click();
  await page.getByRole('dialog',{name:'Game screen instructions',exact:true}).waitFor();await page.keyboard.press('Escape');
  await until(()=>authoredReceiverLibraryReady(page),'actual keyed receiver ready for pasted link');
  await link.fill('https://vdo.ninja/?view=authored-first');
  await until(()=>frames>=beforeSelection+2,'automatic pasted-link receiver frames');
  await link.fill('');
  await until(()=>page.evaluate(async()=>!(await(await fetch('/api/snapshot')).json()).status.capture.running),'clear-link native stop');
  const stopped=frames;await delay(1000);assert.equal(frames,stopped);
  await link.fill('https://vdo.ninja/?view=authored-second');await until(()=>frames>stopped,'new link fresh lease');
  await page.evaluate(()=>window.dispatchEvent(new Event('toolkit-host-pause')));
  await until(()=>page.evaluate(async()=>!(await(await fetch('/api/snapshot')).json()).status.capture.running),'background stop');
  const paused=frames;await delay(1000);assert.equal(frames,paused);
  await page.evaluate(()=>window.dispatchEvent(new Event('toolkit-host-resume')));await until(()=>frames>paused,'foreground fresh lease');
  assert.deepEqual(errors,[]);
  console.log(name+': actual shared UI explicit installed-source selection, text/audio mode consent, size/update/delete, readable omitted-unknown text with no audio request, plain reader and paste/clear/background passed (mocked provider/PNG admission).');
 } finally {
  await browser?.close();service.stdin.write(JSON.stringify({action:'close'})+'\n');
  await new Promise(resolve=>service.once('exit',resolve));
 }
}
