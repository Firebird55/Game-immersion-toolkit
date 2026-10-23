import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {zipSync,strToU8} from 'fflate';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {VIDEO,WEBM_VIDEO} from '../tests/mobile-media-fixtures.mjs';
const engines=await import(process.env.PLAYWRIGHT_MODULE_PATH?pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href:'playwright');
const root=process.env.MOBILE_PREVIEW_DIR?pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR)+sep):new URL('../public/mobile-capture/',import.meta.url),ocr=ocrAssets();
const files=new Map(readdirSync(root,{recursive:true}).filter(n=>statSync(new URL(n.replaceAll('\\','/'),root)).isFile()).map(n=>['/'+n.replaceAll('\\','/'),n.replaceAll('\\','/')]));files.set('/','index.html');
const server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname,name=files.get(path),bytes=name?readFileSync(new URL(name,root)):ocr.get(path.slice(1));if(!bytes){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name??path));res.end(bytes);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
const row={id:'a'.repeat(64),textId:'synthetic-moving-source',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:null,audio:null,channels:['dialogue']},chinese={...row,id:'b'.repeat(64),textId:'synthetic-chinese-source',english:'We can keep walking.',chinese:'我们可以继续走了。'};
const rows=strToU8([row,chinese].map(value=>JSON.stringify(value)+'\n').join('')),manifest={format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic screen source',revision:'a'.repeat(64),coverage:{dialogue:2},catalog:[{name:'catalog/00000.ndjson',size:rows.length,sha256:createHash('sha256').update(rows).digest('hex')}],packs:[]};
const catalog=Buffer.from(zipSync({'manifest.json':strToU8(JSON.stringify(manifest)),'catalog/00000.ndjson':rows},{level:0}));
// Lossless raster of the authored Chinese subtitle card in mobile-media-fixtures.
// Native transport sends PNGs: testing it must not require a second H264/WebM
// decoder inside the viewer, nor depend on the runner's installed CJK fonts.
const chinesePng=readFileSync(new URL('../tests/fixtures/mobile-native-chinese.png',import.meta.url)).toString('base64');
// Owned fixture served at the real cross-origin viewer boundary. The production
// adapter still performs its normal origin/source/cib/blob/decode validation.
const fixture=`<!doctype html><canvas id="screen"></canvas><script>
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
window.fixture={width:1280,height:720,tick:0,requests:0,image:null,available:AVAILABLE};
addEventListener('message',async event=>{
 if(!event.data?.getVideoFrame)return;
 const f=window.fixture;f.requests++;if(!f.available)return;canvas.width=f.width;canvas.height=f.height;
 ctx.fillStyle='#111';ctx.fillRect(0,0,canvas.width,canvas.height);
 if(f.image)ctx.drawImage(f.image,0,0,canvas.width,canvas.height);
 else{ctx.fillStyle='white';ctx.font=Math.round(canvas.width/1280*44)+'px Arial';ctx.fillText('The lantern is bright.',canvas.width*.14,canvas.height*.79);}
 ctx.fillStyle=++f.tick%2?'#f00':'#0f0';ctx.fillRect(20+f.tick%60,20,40,40);
 const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
 event.source.postMessage({action:'image-frame-capture',value:{cib:event.data.cib,streamID:event.data.streamID,imageType:'png',imageData:blob}},event.origin);
});
</script>`;
mkdirSync('output/playwright',{recursive:true});
let browser,activePage,activeName,stage='startup';
async function diagnoseFailure(page,name,error){
 const state=await page.evaluate(()=>({sourceStatus:document.querySelector('#source-status')?.textContent,matchStatus:document.querySelector('#match-status')?.textContent,language:document.querySelector('#ocr-language')?.value,hidden:document.hidden,ocrRunning:document.body.classList.contains('ocr-running'),ocrJobs:window.testJobs,maxOcrJobs:window.testMaxJobs,recognitions:window.testRecognitions,heldReplies:window.testHeld?.length,ocrResults:window.testOcrResults,matchResults:window.testMatchResults,transcriptRows:document.querySelectorAll('#transcript .transcript-line').length})).catch(()=>({pageUnavailable:true}));
 const child=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
 state.fixture=await child?.evaluate(()=>({width:fixture.width,height:fixture.height,requests:fixture.requests,tick:fixture.tick,available:fixture.available,imageLoaded:Boolean(fixture.image?.complete),imageWidth:fixture.image?.naturalWidth??0,imageHeight:fixture.image?.naturalHeight??0})).catch(()=>({unavailable:true}));
 const report={browser:name,stage,error:error.name,...state};
 console.error('Mobile source fixture failure:',JSON.stringify(report));
 writeFileSync(`output/playwright/mobile-source-${name}-failure.json`,JSON.stringify(report,null,2)+'\n');
 await page.screenshot({path:`output/playwright/mobile-source-${name}-failure.png`,fullPage:true}).catch(()=>{});
}
async function waitText(page,text){await page.waitForFunction(text=>document.querySelector('#transcript').textContent.includes(text),text,{timeout:45000});}
async function connect(page){await page.fill('#vdo-url','https://vdo.ninja/?view=owned_fixture&password=owned_fixture_secret');await page.click('#vdo-connect');await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('Visible screen changes'),null,{timeout:15000});}
async function hide(page,hidden){await page.evaluate(hidden=>{Object.defineProperty(document,'hidden',{configurable:true,value:hidden});document.dispatchEvent(new Event('visibilitychange'));},hidden);}
async function release(page){await page.evaluate(()=>{window.testGate=null;for(const deliver of window.testHeld.splice(0))deliver();});}
try{
 for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
  browser=await engines[name].launch({headless:true});const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[];
  activePage=page;activeName=name;stage='initial native screen and English OCR';
  page.on('pageerror',error=>errors.push(error.message));
  let streamAvailable=true,nativeLoads=0;
  await context.route('https://vdo.ninja/**',route=>{nativeLoads++;return route.fulfill({contentType:'text/html',body:fixture.replace('AVAILABLE',String(streamAvailable))});});
  await page.addInitScript(()=>{
   window.testHeld=[];window.testGate=null;window.testJobs=0;window.testMaxJobs=0;window.testRecognitions=0;window.testWorkers=0;window.testHistory=[];window.testOcrResults=[];window.testMatchResults=[];
   addEventListener('mobile-history',event=>window.testHistory.push(event.detail.map(row=>row.id)));
   const Native=window.Worker;
   window.Worker=class extends Native{
    constructor(url,options){super(url,options);this.library=String(url).includes('library-worker');this.matches=new Set();if(!this.library)window.testWorkers++;}
    postMessage(data,...rest){if(data.action==='recognize'){window.testJobs++;window.testRecognitions++;window.testMaxJobs=Math.max(window.testMaxJobs,window.testJobs);}if(data.action==='match-candidates')this.matches.add(data.id);return super.postMessage(data,...rest);}
    set onmessage(handler){super.onmessage=event=>{const data=event.data,recognition=data.action==='recognize'&&['resolve','reject'].includes(data.status),match=this.matches.delete(data.id);if(recognition){window.testJobs--;window.testOcrResults.push({status:data.status,text:data.data?.text?.slice(0,160),confidence:data.data?.confidence});window.testOcrResults=window.testOcrResults.slice(-6);}if(match){window.testMatchResults.push({state:data.result?.state,score:data.result?.score});window.testMatchResults=window.testMatchResults.slice(-6);}if((window.testGate==='ocr'&&recognition||window.testGate==='match'&&match)&&!window.testHeld.length){window.testHeld.push(()=>handler(event));return;}handler(event);};}
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
  // A real OCR/catalog reply delayed beyond the production 8-second progress
  // window must still count as the first sighting; later fast scans cannot mask
  // its loss. Hold further frames until that exact result has been accepted.
  stage='slow same-session OCR result';
  await page.click('#ocr-pause');await page.click('#clear-history');
  await page.evaluate(()=>{window.testGate='match';});await page.click('#ocr-start');
  await page.waitForFunction(()=>window.testHeld.length===1,null,{timeout:30000});
  const slowViewer=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
  const slowLoads=nativeLoads,slowRecognitions=await page.evaluate(()=>window.testRecognitions);
  await page.waitForTimeout(9000);
  assert((await page.locator('#source-status').textContent()).includes('No visible frame changes'));
  assert.equal(nativeLoads,slowLoads);assert.equal(await page.evaluate(()=>window.testRecognitions),slowRecognitions);
  await slowViewer.evaluate(()=>fixture.available=false);
  await release(page);
  await page.waitForFunction(()=>document.querySelector('#match-status').textContent.includes('confirming'),null,{timeout:2500});
  assert.equal(await page.evaluate(()=>window.testRecognitions),slowRecognitions,'The delayed result itself is accepted without another recognition');
  assert.equal(await page.locator('#transcript .transcript-line').count(),0,'The second fresh sighting is still required');
  await slowViewer.evaluate(()=>fixture.available=true);await waitText(page,row.chinese);
  console.log(`${name}: slow same-session OCR survives the progress timeout and confirms from fresh frames.`);
  // Delayed real worker replies cannot publish into a changed source/session.
  for(const gate of ['ocr','match']){
   stage=`late ${gate} response invalidation`;
   await page.click('#ocr-pause');await page.click('#clear-history');
   await page.evaluate(gate=>{window.testGate=gate;window.testHistory=[];},gate);await page.click('#ocr-start');
   await page.waitForFunction(()=>window.testHeld.length===1,null,{timeout:30000});
   const before=await page.evaluate(()=>window.testRecognitions);await page.waitForTimeout(800);assert.equal(await page.evaluate(()=>window.testRecognitions),before,'no queued OCR while a reply is delayed');
   if(gate==='ocr'){await page.click('#vdo-stop');assert.equal(await page.locator('#vdo-viewer iframe').count(),0);}
   else await hide(page,true);
   await release(page);await page.waitForTimeout(800);
   assert.equal(await page.locator('#transcript .transcript-line').count(),0,'old reply cannot publish');
   assert(!(await page.evaluate(()=>window.testHistory)).some(rows=>rows.length),'no transient stale reader event');
   if(gate==='ocr'){
    const stoppedRecognitions=await page.evaluate(()=>window.testRecognitions);
    await connect(page);await page.waitForTimeout(1500);
    assert.equal(await page.evaluate(()=>window.testRecognitions),stoppedRecognitions,'Reconnecting after explicit Stop must not restart OCR');
    assert.equal(await page.locator('#transcript .transcript-line').count(),0);
    assert.equal(await page.evaluate(()=>document.body.classList.contains('ocr-running')),false,'OCR intent stays stopped until Start');
    console.log(`${name}: explicit native Stop cancels OCR intent across reconnect.`);
   }else{await hide(page,false);await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('Visible screen changes'));}
   await page.click('#ocr-start');await waitText(page,row.chinese);
  }
  // Sender lock/stop is modeled by missing frames; a manual native restart on
  // the same private link must recover the receiver AND existing OCR intent.
  stage='same-link native restart';
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
  stage='rotation, zoom and repeated lifecycle';
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
  stage='existing browser video adapter';
  await page.selectOption('#frame-source','browser');
  await page.evaluate(async sources=>{const video=document.querySelector('#preview');video.loop=true;for(const [base64,type]of sources){video.src=URL.createObjectURL(new Blob([Uint8Array.from(atob(base64),c=>c.charCodeAt(0))],{type}));try{await video.play();window.dispatchEvent(new CustomEvent('mobile-stream',{detail:{generation:200,role:'receiver',state:'connected',live:true,game:'zzz'}}));return;}catch{}}throw Error('Fixture video decoding unavailable.');},[[VIDEO,'video/mp4'],[WEBM_VIDEO,'video/webm']]);
  await page.click('#clear-history');await page.click('#ocr-start');await waitText(page,row.chinese);await page.click('#ocr-pause');
  await page.selectOption('#frame-source','vdo');await connect(page);
  stage='native Chinese PNG and real OCR';
  const frame=page.frames().find(frame=>frame.url().startsWith('https://vdo.ninja/'));
  const imageSize=await frame.evaluate(async png=>{const image=new Image();image.src='data:image/png;base64,'+png;await image.decode();fixture.image=image;return{width:image.naturalWidth,height:image.naturalHeight};},chinesePng);
  assert.deepEqual(imageSize,{width:1280,height:720},'The owned native Chinese PNG decodes before OCR starts');
  await page.evaluate(()=>{window.testOcrResults=[];window.testMatchResults=[];});
  await page.selectOption('#ocr-language','chi_sim');await page.click('#clear-history');await page.click('#ocr-start');await waitText(page,chinese.chinese);
  assert((await page.locator('#source-status').textContent()).includes('1280 × 720'),'Chinese PNG reaches the bounded source frame envelope');
  assert((await page.locator('#reader-root').textContent()).includes(chinese.chinese),'Real Chinese OCR reaches the reader');
  stage='privacy and final cleanup';
  assert.equal(await page.evaluate(()=>window.testMaxJobs),1,'one real OCR worker job at a time');
  const privateState=await page.evaluate(async()=>{const keys=await indexedDB.databases(),result={localStorage:{...localStorage},stores:[]};for(const entry of keys){const db=await new Promise(resolve=>{const request=indexedDB.open(entry.name);request.onsuccess=()=>resolve(request.result);});for(const name of db.objectStoreNames){const rows=await new Promise(resolve=>{const request=db.transaction(name).objectStore(name).getAll();request.onsuccess=()=>resolve(request.result);});result.stores.push(rows);}db.close();}return JSON.stringify(result);});
  assert(!privateState.includes('owned_fixture_secret'),'viewer credentials never enter persisted storage');
  await page.click('#vdo-stop');assert.equal(await page.locator('#vdo-viewer iframe').count(),0);await page.screenshot({path:`output/playwright/mobile-source-${name}.png`,fullPage:true});assert.deepEqual(errors,[]);
  await context.close();await browser.close();browser=null;activePage=null;console.log(`${name}: moving native fixture, real OCR/catalog/reader, stale replies, source replacement, lifecycle, Chinese and mobile zoom passed.`);
 }
}catch(error){if(activePage)await diagnoseFailure(activePage,activeName,error).catch(()=>{});throw error;}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
