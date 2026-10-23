import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {zipSync,strToU8} from 'fflate';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {VIDEO,WEBM_VIDEO,CHINESE_VIDEO,CHINESE_WEBM} from '../tests/mobile-media-fixtures.mjs';
const engines=await import(process.env.PLAYWRIGHT_MODULE_PATH?pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href:'playwright');
const root=process.env.MOBILE_PREVIEW_DIR?pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR)+sep):new URL('../public/mobile-capture/',import.meta.url),ocr=ocrAssets();
const files=new Map(readdirSync(root,{recursive:true}).filter(n=>statSync(new URL(n.replaceAll('\\','/'),root)).isFile()).map(n=>['/'+n.replaceAll('\\','/'),n.replaceAll('\\','/')]));files.set('/','index.html');
const server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname,name=files.get(path),bytes=name?readFileSync(new URL(name,root)):ocr.get(path.slice(1));if(!bytes){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name??path));res.end(bytes);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
const row={id:'a'.repeat(64),textId:'synthetic-moving-source',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:null,audio:null,channels:['dialogue']},chinese={...row,id:'b'.repeat(64),textId:'synthetic-chinese-source',english:'We can keep walking.',chinese:'我们可以继续走了。'};
const rows=strToU8([row,chinese].map(value=>JSON.stringify(value)+'\n').join('')),manifest={format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic screen source',revision:'a'.repeat(64),coverage:{dialogue:2},catalog:[{name:'catalog/00000.ndjson',size:rows.length,sha256:createHash('sha256').update(rows).digest('hex')}],packs:[]};
const catalog=Buffer.from(zipSync({'manifest.json':strToU8(JSON.stringify(manifest)),'catalog/00000.ndjson':rows},{level:0}));
// Owned fixture served at the real cross-origin viewer boundary. The production
// adapter still performs its normal origin/source/cib/blob/decode validation.
const fixture=`<!doctype html><canvas id="screen"></canvas><script>
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
window.fixture={width:1280,height:720,tick:0,requests:0,video:null,available:AVAILABLE};
addEventListener('message',async event=>{
 if(!event.data?.getVideoFrame)return;
 const f=window.fixture;f.requests++;if(!f.available)return;canvas.width=f.width;canvas.height=f.height;
 ctx.fillStyle='#111';ctx.fillRect(0,0,canvas.width,canvas.height);
 if(f.video)ctx.drawImage(f.video,0,0,canvas.width,canvas.height);
 else{ctx.fillStyle='white';ctx.font=Math.round(canvas.width/1280*44)+'px Arial';ctx.fillText('The lantern is bright.',canvas.width*.14,canvas.height*.79);}
 ctx.fillStyle=++f.tick%2?'#f00':'#0f0';ctx.fillRect(20+f.tick%60,20,40,40);
 const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
 event.source.postMessage({action:'image-frame-capture',value:{cib:event.data.cib,streamID:event.data.streamID,imageType:'png',imageData:blob}},event.origin);
});
</script>`;
mkdirSync('output/playwright',{recursive:true});
let browser;
async function waitText(page,text){await page.waitForFunction(text=>document.querySelector('#transcript').textContent.includes(text),text,{timeout:45000});}
async function connect(page){await page.fill('#vdo-url','https://vdo.ninja/?view=owned_fixture&password=owned_fixture_secret');await page.click('#vdo-connect');await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('Visible screen changes'),null,{timeout:15000});}
async function hide(page,hidden){await page.evaluate(hidden=>{Object.defineProperty(document,'hidden',{configurable:true,value:hidden});document.dispatchEvent(new Event('visibilitychange'));},hidden);}
async function release(page){await page.evaluate(()=>{window.testGate=null;for(const deliver of window.testHeld.splice(0))deliver();});}
try{
 for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
  browser=await engines[name].launch({headless:true});const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  let streamAvailable=true,nativeLoads=0;
  await context.route('https://vdo.ninja/**',route=>{nativeLoads++;return route.fulfill({contentType:'text/html',body:fixture.replace('AVAILABLE',String(streamAvailable))});});
  await page.addInitScript(()=>{
   window.testHeld=[];window.testGate=null;window.testJobs=0;window.testMaxJobs=0;window.testRecognitions=0;window.testWorkers=0;window.testHistory=[];
   addEventListener('mobile-history',event=>window.testHistory.push(event.detail.map(row=>row.id)));
   const Native=window.Worker;
   window.Worker=class extends Native{
    constructor(url,options){super(url,options);this.library=String(url).includes('library-worker');this.matches=new Set();if(!this.library)window.testWorkers++;}
    postMessage(data,...rest){if(data.action==='recognize'){window.testJobs++;window.testRecognitions++;window.testMaxJobs=Math.max(window.testMaxJobs,window.testJobs);}if(data.action==='match-candidates')this.matches.add(data.id);return super.postMessage(data,...rest);}
    set onmessage(handler){super.onmessage=event=>{const data=event.data,recognition=data.action==='recognize'&&['resolve','reject'].includes(data.status),match=this.matches.delete(data.id);if(recognition)window.testJobs--;if((window.testGate==='ocr'&&recognition||window.testGate==='match'&&match)&&!window.testHeld.length){window.testHeld.push(()=>handler(event));return;}handler(event);};}
   };
  });
  await page.goto(base+'?developer=1');await page.getByRole('heading',{name:'Proxy Transcript',exact:true}).waitFor();await page.waitForFunction(()=>document.body.dataset.role==='sender');await page.selectOption('#role','receiver');await page.waitForFunction(()=>document.body.dataset.role==='receiver');
  await page.setInputFiles('#library-files',{name:'owned-catalog.zip',mimeType:'application/zip',buffer:catalog});await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('2 bilingual rows'));
  await page.selectOption('#frame-source','vdo');await connect(page);
  assert.equal(await page.inputValue('#vdo-url'),'','private link clears after connection');
  assert.equal(await page.locator('#vdo-viewer iframe').count(),1);
  const firstFrame=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
  assert((await firstFrame.evaluate(()=>fixture.requests))>=2,'status probes run before OCR starts');
  await page.locator('details').filter({has:page.locator('#preview-crop')}).locator('summary').click();
  await page.click('#preview-crop');await page.waitForFunction(()=>!document.querySelector('#crop-preview').hidden);
  assert(await page.locator('#crop-preview').evaluate(canvas=>canvas.width>0&&canvas.height>0));
  await page.click('#ocr-start');await waitText(page,row.chinese);
  assert((await page.locator('#source-status').textContent()).includes('1280 × 720'),'compact viewer retains source pixel dimensions');
  console.log(`${name}: native frames reached real OCR and catalog.`);
  await page.locator('.companion-nav button').first().click();
  assert((await page.locator('#reader-root').textContent()).includes(row.chinese),'real crop → OCR → catalog → reader');
  // Delayed real worker replies cannot publish into a changed source/session.
  for(const gate of ['ocr','match']){
   await page.click('#ocr-pause');await page.click('#clear-history');
   await page.evaluate(gate=>{window.testGate=gate;window.testHistory=[];},gate);await page.click('#ocr-start');
   await page.waitForFunction(()=>window.testHeld.length===1,null,{timeout:30000});
   const before=await page.evaluate(()=>window.testRecognitions);await page.waitForTimeout(800);assert.equal(await page.evaluate(()=>window.testRecognitions),before,'no queued OCR while a reply is delayed');
   if(gate==='ocr'){await page.click('#vdo-stop');assert.equal(await page.locator('#vdo-viewer iframe').count(),0);}
   else await hide(page,true);
   await release(page);await page.waitForTimeout(800);
   assert.equal(await page.locator('#transcript .transcript-line').count(),0,'old reply cannot publish');
   assert(!(await page.evaluate(()=>window.testHistory)).some(rows=>rows.length),'no transient stale reader event');
   if(gate==='ocr')await connect(page);else{await hide(page,false);await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('Visible screen changes'));}
   await page.click('#ocr-start');await waitText(page,row.chinese);
  }
  // Sender lock/stop is modeled by missing frames; a manual native restart on
  // the same private link must recover the receiver AND existing OCR intent.
  await page.click('#clear-history');streamAvailable=false;const beforeRecovery=nativeLoads;
  await page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/')).evaluate(()=>fixture.available=false);
  await page.waitForFunction(()=>/stalled|fresh|Retry|retry|reconnect|Waiting/i.test(document.querySelector('#source-status').textContent),null,{timeout:15000});
  for(let i=0;i<120&&nativeLoads===beforeRecovery;i++)await page.waitForTimeout(250);
  assert(nativeLoads>beforeRecovery,'lost native stream triggers bounded automatic viewer reconnect');
  assert.equal(await page.locator('#transcript .transcript-line').count(),0,'nothing stale while source is unavailable');
  streamAvailable=true;
  await page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/')).evaluate(()=>fixture.available=true).catch(()=>{});
  await waitText(page,row.chinese);
  assert(await page.evaluate(()=>document.body.classList.contains('ocr-running')),'same-link restart resumes OCR without another Start click');
  console.log(`${name}: same-link sender restart resumed OCR automatically.`);
  // Session restart, rotation and zoom preserve bounded normalized calibration.
  await page.click('#ocr-pause');
  for(const [width,height]of [[720,1280],[1920,1080],[1280,720]]){
   const frame=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
   await frame.evaluate(({width,height})=>{fixture.width=width;fixture.height=height;},{width,height});
   await page.waitForFunction(({width,height})=>document.querySelector('#source-status').textContent.includes(width+' × '+height),{width,height});
   await page.click('#preview-crop');await page.waitForFunction(()=>!document.querySelector('#crop-preview').hidden);
   assert.equal(await page.inputValue('#crop-left'),'8');assert.equal(await page.inputValue('#crop-top'),'67');
   assert(await page.locator('#crop-preview').evaluate(canvas=>canvas.width<=2304&&canvas.height<=1024));
  }
  for(const viewport of [{width:320,height:568},{width:844,height:390}]){
   await page.setViewportSize(viewport);await page.evaluate(()=>document.documentElement.style.zoom='1.25');
   const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(element=>{const rect=element.getBoundingClientRect();return rect.width&&rect.right>innerWidth+1;}).map(element=>({tag:element.tagName,id:element.id,text:element.tagName==='BUTTON'?element.textContent:null,parent:element.parentElement.className,right:element.getBoundingClientRect().right})).slice(0,12)}));
   assert(layout.scroll<=layout.width+1,`native setup fits mobile and zoom: ${JSON.stringify(layout)}`);
  }
  await page.evaluate(()=>document.documentElement.style.zoom='1');await page.setViewportSize({width:390,height:844});
  for(let cycle=0;cycle<3;cycle++){await hide(page,true);assert.equal(await page.locator('#vdo-viewer iframe').count(),0);await hide(page,false);await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('Visible screen changes'));await page.click('#vdo-stop');await connect(page);}
  // Existing video adapter remains interchangeable without a second connection.
  await page.selectOption('#frame-source','browser');
  await page.evaluate(async sources=>{const video=document.querySelector('#preview');video.loop=true;for(const [base64,type]of sources){video.src=URL.createObjectURL(new Blob([Uint8Array.from(atob(base64),c=>c.charCodeAt(0))],{type}));try{await video.play();window.dispatchEvent(new CustomEvent('mobile-stream',{detail:{generation:200,role:'receiver',state:'connected',live:true,game:'zzz'}}));return;}catch{}}throw Error('Fixture video decoding unavailable.');},[[VIDEO,'video/mp4'],[WEBM_VIDEO,'video/webm']]);
  await page.click('#clear-history');await page.click('#ocr-start');await waitText(page,row.chinese);await page.click('#ocr-pause');
  await page.selectOption('#frame-source','vdo');await connect(page);
  const frame=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
  await frame.evaluate(async sources=>{const video=document.createElement('video');video.loop=true;video.muted=true;video.playsInline=true;document.body.append(video);for(const [base64,type]of sources){video.src=URL.createObjectURL(new Blob([Uint8Array.from(atob(base64),c=>c.charCodeAt(0))],{type}));try{await video.play();fixture.video=video;return;}catch{}}throw Error('Chinese fixture decoding unavailable.');},[[CHINESE_VIDEO,'video/mp4'],[CHINESE_WEBM,'video/webm']]);
  await page.selectOption('#ocr-language','chi_sim');await page.click('#clear-history');await page.click('#ocr-start');await waitText(page,chinese.chinese);
  assert.equal(await page.evaluate(()=>window.testMaxJobs),1,'one real OCR worker job at a time');
  const privateState=await page.evaluate(async()=>{const keys=await indexedDB.databases(),result={localStorage:{...localStorage},stores:[]};for(const entry of keys){const db=await new Promise(resolve=>{const request=indexedDB.open(entry.name);request.onsuccess=()=>resolve(request.result);});for(const name of db.objectStoreNames){const rows=await new Promise(resolve=>{const request=db.transaction(name).objectStore(name).getAll();request.onsuccess=()=>resolve(request.result);});result.stores.push(rows);}db.close();}return JSON.stringify(result);});
  assert(!privateState.includes('owned_fixture_secret'),'viewer credentials never enter persisted storage');
  await page.click('#vdo-stop');assert.equal(await page.locator('#vdo-viewer iframe').count(),0);await page.screenshot({path:`output/playwright/mobile-source-${name}.png`,fullPage:true});assert.deepEqual(errors,[]);
  await context.close();await browser.close();browser=null;console.log(`${name}: moving native fixture, real OCR/catalog/reader, stale replies, source replacement, lifecycle, Chinese and mobile zoom passed.`);
 }
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
