import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {readFileSync,readdirSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {once} from 'node:events';
import {chromium,firefox,webkit} from 'playwright';
import {ocrAssets,mime} from './mobile-assets.mjs';

const root=process.env.MOBILE_PREVIEW_DIR?pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR)+sep):new URL('../public/mobile-capture/',import.meta.url);
const assets=ocrAssets(),names=readdirSync(root),relayModule='./'+names.find(n=>/^relay(?:\.[a-f0-9]+)?\.mjs$/.test(n));let endpoint='';
const server=http.createServer((req,res)=>{
 const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
 let data=/^recovery-config(?:\.[a-f0-9]+)?\.json$/.test(name)?Buffer.from(JSON.stringify({endpoint,origins:[origin]})):assets.get(name)??(names.includes(name)?readFileSync(new URL(name,root)):null);
 // Permit only this test's ephemeral signaling fixture; production CSP stays fixed.
 if(name==='index.html'&&data)data=Buffer.from(data.toString().replace("connect-src 'self'",`connect-src 'self' ${endpoint} ${endpoint.replace('http:','ws:')}`));
 if(!data){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name));res.end(data);
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
const probe=http.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));endpoint='http://127.0.0.1:'+port;
const worker=spawn(process.execPath,['node_modules/wrangler/bin/wrangler.js','dev','--config','services/pairing/wrangler.jsonc','--local','--ip','127.0.0.1','--port',String(port),'--inspector-port','0','--var','ALLOWED_ORIGINS:'+origin,'--persist-to',resolve('output/pairing-runtime-'+process.pid),'--show-interactive-dev-session=false'],{stdio:['pipe','pipe','pipe'],env:{...process.env,CI:'true',WRANGLER_SEND_METRICS:'false'}});
let workerLog='';for(const stream of [worker.stdout,worker.stderr])stream.on('data',v=>{workerLog=(workerLog+v).slice(-5000);});
let browser;
const wait=async(predicate,label)=>{for(let i=0;i<120;i++){if(worker.exitCode!==null)throw Error('Local worker exited: '+workerLog);try{if(await predicate())return;}catch{}await new Promise(r=>setTimeout(r,250));}throw Error('Timed out: '+label+'\n'+workerLog);};
try{
 await wait(async()=> (await fetch(endpoint+'/health')).ok,'worker startup');
 assert.equal((await fetch(endpoint+'/v1/rooms/'+'a'.repeat(32),{method:'POST',headers:{Origin:'https://untrusted.example','Content-Type':'application/json'},body:'{}'})).status,403);
 assert.equal((await fetch(endpoint+'/v1/rooms/'+'a'.repeat(32),{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:'x'.repeat(513)})).status,400);
 for(const [name,engine] of [['chromium',chromium],['firefox',firefox]]){
  browser=await engine.launch({headless:true});const context=await browser.newContext({acceptDownloads:true}),errors=[];
  context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
  await context.addInitScript(()=>{
   const NativePeer=RTCPeerConnection;window.testPeers=[];
   window.RTCPeerConnection=class extends NativePeer{constructor(options){super(options);window.testPeer=this;window.testPeers.push(this);}};
   window.captureRequests=0;
   if(navigator.mediaDevices)navigator.mediaDevices.getDisplayMedia=async()=>{window.captureRequests++;if(window.denyCapture)throw Error('Synthetic permission denial');const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;let i=0;const ctx=canvas.getContext('2d');setInterval(()=>{ctx.fillStyle=`rgb(${i++%255},100,180)`;ctx.fillRect(0,0,640,360);},100);window.capturedStream=canvas.captureStream(10);return window.capturedStream;};
  });
  const sender=await context.newPage(),receiver=await context.newPage();await sender.goto(origin+'?developer=1');await receiver.goto(origin+'?developer=1');await receiver.selectOption('#role','receiver');
  await sender.waitForFunction(()=>document.querySelector('#auto-recovery').checked&&!document.querySelector('#auto-recovery').disabled);
  await sender.click('#start');await sender.waitForFunction(()=>document.querySelector('#outgoing').value.includes('"relay"'));
  const offer=JSON.parse(await sender.inputValue('#outgoing'));assert.equal(await sender.locator('#pairing-qr').getAttribute('data-total'),'1','Service-assisted offer fits one static QR');
  await receiver.fill('#incoming',JSON.stringify(offer));await receiver.click('#apply');
  // The sender is never given a manual answer. One offer transfer is enough.
  await receiver.waitForFunction(()=>document.querySelector('#metrics').textContent.includes('Receiving frames'),null,{timeout:30000});
  assert.equal(await sender.evaluate(()=>window.testPeer.connectionState),'connected');
  await receiver.click('#begin-test');
  await sender.evaluate(()=>{window.firstTrack=window.capturedStream.getVideoTracks()[0];window.firstPeer=window.testPeer;});
  const recover=async()=>{
   const previous=await sender.evaluate(()=>window.testPeers.length);
   for(const p of [sender,receiver])await p.evaluate(()=>{window.testPeer.close();window.testPeer.dispatchEvent(new Event('connectionstatechange'));});
   await sender.waitForFunction(n=>window.testPeers.length>n,previous,{timeout:30000});
   await receiver.waitForFunction(()=>window.testPeer.connectionState==='connected'&&document.querySelector('#metrics').textContent.includes('Receiving frames'),null,{timeout:30000});
  };
  await recover();
  assert(await sender.evaluate(()=>window.firstTrack===window.capturedStream.getVideoTracks()[0]&&window.firstTrack.readyState==='live'),'Failed transport retains the original screen capture');
  assert.equal(await sender.evaluate(()=>window.captureRequests),1);
  assert.equal(JSON.parse(await sender.inputValue('#outgoing')).sessionId,offer.sessionId);
  await receiver.evaluate(()=>{document.querySelector('#preview').pause();window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await receiver.waitForFunction(()=>!document.querySelector('#preview').paused&&document.querySelector('#metrics').textContent.includes('Receiving frames'));
  // Let the asynchronous play result (or advancing media-time evidence) settle
  // before immediately replacing its connection in the next failure scenario.
  await receiver.waitForTimeout(500);
  // A browser suspended by switching apps must recover on visibility/resume.
  await sender.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  const before=await sender.evaluate(()=>window.testPeers.length);
  for(const p of [sender,receiver])await p.evaluate(()=>{window.testPeer.close();window.testPeer.dispatchEvent(new Event('connectionstatechange'));});
  await sender.waitForTimeout(1000);assert.equal(await sender.evaluate(()=>window.testPeers.length),before);
  await sender.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));document.dispatchEvent(new Event('resume'));});
  await receiver.waitForFunction(()=>window.testPeer.connectionState==='connected'&&document.querySelector('#metrics').textContent.includes('Receiving frames'),null,{timeout:30000});
  // An ended capture requires one permission gesture and retains pairing.
  await sender.evaluate(()=>{const t=window.capturedStream.getVideoTracks()[0];t.stop();t.dispatchEvent(new Event('ended'));});
  await sender.waitForFunction(()=>!document.querySelector('#resume-share').hidden);
  await sender.evaluate(()=>window.denyCapture=true);await sender.click('#resume-share');
  await sender.waitForFunction(()=>document.querySelector('#status').textContent.includes('could not resume'));
  assert.equal(await sender.locator('#resume-share').isEnabled(),true);
  await sender.evaluate(()=>window.denyCapture=false);await sender.click('#resume-share');
  await sender.waitForFunction(()=>document.querySelector('#outgoing').value.includes('"offer"'));
  const resumedAttempt=JSON.parse(await sender.inputValue('#outgoing')).attempt;
  await receiver.waitForFunction(attempt=>{try{return JSON.parse(document.querySelector('#outgoing').value).attempt===attempt;}catch{return false;}},resumedAttempt);
  await receiver.waitForFunction(()=>window.testPeer.connectionState==='connected'&&document.querySelector('#metrics').textContent.includes('Receiving frames'),null,{timeout:30000});
  assert.equal(JSON.parse(await sender.inputValue('#outgoing')).sessionId,offer.sessionId);
  const authResult=await receiver.evaluate(async({endpoint,room})=>new Promise((resolve,reject)=>{const ws=new WebSocket(endpoint.replace('http:','ws:')+'/v1/rooms/'+room);const timer=setTimeout(()=>{ws.close();reject(Error('Authentication timeout'));},5000);ws.onopen=()=>ws.send(JSON.stringify({kind:'auth',role:'sender',proof:'A'.repeat(43)}));ws.onclose=e=>{clearTimeout(timer);resolve(e.code);};}),{endpoint,room:offer.relay.room});
  assert.equal(authResult,4003,'An incorrect proof cannot replace a paired sender');
  assert.equal(await receiver.evaluate(()=>window.testPeer.connectionState),'connected');
  const download=receiver.waitForEvent('download');await receiver.click('#report');const report=JSON.parse(readFileSync(await(await download).path(),'utf8'));
  assert.equal(report.observation.endedAt,null);assert(report.diagnostics.recoveryAttempts>=3);
  if(!report.events.some(e=>e.kind==='preview_resumed'))console.error(name,'safe recovery diagnostics',{kinds:report.events.map(e=>e.kind),video:await receiver.evaluate(()=>({paused:document.querySelector('#preview').paused,time:document.querySelector('#preview').currentTime,ready:document.querySelector('#preview').readyState}))});
  assert(report.events.some(e=>e.kind==='preview_resumed'));
  for(const secret of [offer.relay.secret,offer.relay.room,offer.sessionId,offer.sdp])assert(!JSON.stringify(report).includes(secret),'Reports omit relay keys and connection details');
  await sender.click('#stop');await receiver.click('#stop');
  const peers=await sender.evaluate(()=>window.testPeers.length);await sender.waitForTimeout(5500);assert.equal(await sender.evaluate(()=>window.testPeers.length),peers,'Stop cancels automatic recovery');
  assert.deepEqual(errors,[]);await context.close();await browser.close();browser=null;
  console.log(name+': local Cloudflare runtime, one-way QR pairing, failed-link/foreground/recapture recovery, observation retention, authentication and Stop passed');
 }
 // WebKit validates real encrypted signaling and reconnecting sockets. Its
 // automated runtime does not establish physical iPhone capture reliability.
 browser=await webkit.launch({headless:true});const context=await browser.newContext(),sender=await context.newPage(),receiver=await context.newPage(),errors=[];
 for(const page of [sender,receiver]){page.on('pageerror',e=>errors.push(e.message));await page.goto(origin+'?developer=1');}
 const descriptor=await sender.evaluate(async({endpoint,module})=>{const {createRelay,RelayClient}=await import(module),descriptor=await createRelay(endpoint);window.relayMessages=[];window.relayTest=new RelayClient(descriptor,'sender',{onMessage:v=>window.relayMessages.push(v)});return descriptor;},{endpoint,module:relayModule});
 await receiver.evaluate(async({descriptor,module})=>{const {RelayClient}=await import(module);window.relayMessages=[];window.relayTest=new RelayClient(descriptor,'receiver',{onMessage:v=>window.relayMessages.push(v)});},{descriptor,module:relayModule});
 for(const page of [sender,receiver])await page.waitForFunction(()=>window.relayTest.ready);
 await sender.evaluate(()=>window.relayTest.send({kind:'pairing',message:'Synthetic connection fixture'}));await receiver.waitForFunction(()=>window.relayMessages.length===1);
 await receiver.evaluate(()=>{window.oldSocket=window.relayTest.socket;window.oldSocket.close();});await receiver.waitForFunction(()=>window.relayTest.socket!==window.oldSocket&&window.relayTest.ready);
 await receiver.evaluate(()=>window.relayTest.send({kind:'recover',sessionId:'synthetic-session'}));await sender.waitForFunction(()=>window.relayMessages.length===1);
 for(const page of [sender,receiver])await page.evaluate(()=>window.relayTest.close());assert.deepEqual(errors,[]);await context.close();await browser.close();browser=null;
 console.log('webkit: local Cloudflare runtime, encrypted signaling and automatic socket reconnect passed; physical iPhone capture unverified');
}finally{
 await browser?.close();worker.stdin.write('q');worker.stdin.end();const exited=once(worker,'exit');
 await Promise.race([exited,new Promise(r=>setTimeout(r,5000))]);if(worker.exitCode===null)worker.kill();
 await new Promise(r=>server.close(r));
}
