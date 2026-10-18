import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {zipSync,strToU8} from 'fflate';
import {createHash} from 'node:crypto';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {TONE,VIDEO,WEBM_VIDEO,CHINESE_VIDEO,CHINESE_WEBM} from '../tests/mobile-media-fixtures.mjs';
const engines=await import(process.env.PLAYWRIGHT_MODULE_PATH?pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href:'playwright');
const root=process.env.MOBILE_PREVIEW_DIR?pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR)+sep):new URL('../public/mobile-capture/',import.meta.url),ocr=ocrAssets();
const files=new Map(readdirSync(root,{recursive:true}).filter(n=>statSync(new URL(n.replaceAll('\\','/'),root)).isFile()).map(n=>['/'+n.replaceAll('\\','/'),n.replaceAll('\\','/')]));files.set('/','index.html');
const server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname,name=files.get(path),bytes=name?readFileSync(new URL(name,root)):ocr.get(path.slice(1));if(!bytes){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name??path));res.end(bytes);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}`,hash=value=>createHash('sha256').update(value).digest('hex'),tone=Buffer.from(TONE,'base64'),sha=hash(tone),id='a'.repeat(64);
const row={id,textId:'dialogue-test',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:id,audio:sha,channels:['dialogue','cinematic','gameplay']},chineseRow={...row,id:'b'.repeat(64),textId:'dialogue-chinese',english:'We can keep walking.',chinese:'我们可以继续走了。'},quietRow={...row,id:'c'.repeat(64),textId:'quiet-synthetic',english:'A quiet unvoiced sentence.',chinese:'无声的句子。',sourceVoice:null,audio:null},segment=Buffer.from([row,chineseRow,quietRow].map(r=>JSON.stringify(r)+'\n').join(''));
const manifest={format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic device verification',revision:id,coverage:{dialogue:3,exportedVoices:2},catalog:[{name:'catalog/00000.ndjson',sha256:hash(segment),size:segment.length}],packs:[{id,clips:[sha]}]};
const encode=entries=>Buffer.from(zipSync(Object.fromEntries(Object.entries(entries).map(([k,v])=>[k,Buffer.isBuffer(v)?v:strToU8(JSON.stringify(v))])),{level:0}));
const catalog=encode({'manifest.json':manifest,'catalog/00000.ndjson':segment}),voices=encode({'manifest.json':{format:manifest.format,kind:'voices',game:'zzz',id,clips:{[sha]:{size:tone.length,sha256:sha}}},['audio/'+sha+'.mp3']:tone});
const input=(name,buffer)=>({name,mimeType:'application/zip',buffer});
mkdirSync('output/playwright',{recursive:true});
const pipelinePath=[...files.keys()].find(p=>/\/ocr-pipeline(?:\.[a-f0-9]+)?\.mjs$/.test(p));
const libraryWorkerPath=[...files.keys()].find(p=>/\/library-worker(?:\.[a-f0-9]+)?\.mjs$/.test(p));
async function verifyBeyondContext(page){
 const first={...row,id:'d'.repeat(64),textId:'beyond:ONE:1',sourceVoice:'d'.repeat(64),sourceLanguage:'nl',sourceLocale:'nl',audioLocale:'nl',sourceText:'Goed.',translationLocale:'zh-Hans',translationText:'好的'};
 const other={...first,id:'e'.repeat(64),textId:'beyond:OTHER:1',sourceVoice:'e'.repeat(64)};
 const paired={...first,id:'f'.repeat(64),textId:'beyond:ONE:context-100-900',sourceVoice:'f'.repeat(64),sourceText:'Goed. We gaan naar huis.',translationText:'好的 我们回家吧。',anchorsSource:['We gaan naar huis.'],anchorsTranslation:['我们回家吧。'],memberTextIds:['beyond:ONE:1','beyond:ONE:2']};
 const collision={...other,id:'9'.repeat(64),sourceText:'Een andere tekst.',translationText:'我们回家吧。'};
 const rows=[first,other,paired,collision],segment=Buffer.from(rows.map(value=>JSON.stringify(value)+'\n').join(''));
 const bytes=encode({'manifest.json':{...manifest,game:'beyond',coverage:{dialogue:rows.length},catalog:[{name:'catalog/00000.ndjson',size:segment.length,sha256:hash(segment)}]},'catalog/00000.ndjson':segment});
 const result=await page.evaluate(async({url,bytes})=>{
  const worker=new Worker(url,{type:'module'});let id=0;const pending=new Map();
  worker.onmessage=({data})=>{if(data.stage||data.progress!=null)return;const request=pending.get(data.id);if(!request)return;pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data.result);};
  const request=(action,body={})=>new Promise((resolve,reject)=>{const token=++id;pending.set(token,{resolve,reject});worker.postMessage({id:token,action,...body});});
  try{
   await request('open',{files:[new File([Uint8Array.from(bytes)],'synthetic-context.zip')]});
   const first=await request('match-candidates',{values:['好的']}),last=await request('match-candidates',{values:['我们回家吧。']});
   const previous=await request('context-fragments',{values:['好的']});
   const paired=await request('match-context',{previous,values:['我们回家吧。']});
   const isolated=await request('match-context',{previous:[],values:['我们回家吧。']});
   return {first:first.state,last:last.state,paired,isolated:isolated.state};
  }finally{worker.terminate();}
 },{url:base+libraryWorkerPath,bytes:[...bytes]});
 assert.equal(result.first,'ambiguous');assert.equal(result.last,'ambiguous');assert.equal(result.isolated,'unmatched');
 assert.equal(result.paired.row.textId,paired.textId);assert.equal(result.paired.row.sourceLocale,'nl');assert.equal(result.paired.row.audioLocale,'nl');
 assert.deepEqual(result.paired.row.memberTextIds,paired.memberTextIds);
}
async function verifyHeavyRainPages(page){
 const source={...row,textId:'heavyrain:100:00000003',sourceLanguage:'nl',sourceLocale:'nl',audioLocale:'nl',sourceText:'We vertrekken morgen samen vroeg. Neem de blauwe koffer mee naar het station.',translationLocale:'zh-Hans',translationText:'我们明天一起出发。请把蓝色行李箱带到车站去。'};
 const child={...source,id:'b'.repeat(64),sourceVoice:'b'.repeat(64),textId:'heavyrain:100:00000001',sourceText:'Pap!',translationText:'爸爸！'},other={...child,id:'c'.repeat(64),sourceVoice:'c'.repeat(64),textId:'heavyrain:200:00000002'};
 const segment=Buffer.from([source,child,other].map(value=>JSON.stringify(value)+'\n').join('')),bytes=encode({'manifest.json':{...manifest,game:'heavyrain',coverage:{dialogue:3,exportedVoices:3},catalog:[{name:'catalog/00000.ndjson',sha256:hash(segment),size:segment.length}]},'catalog/00000.ndjson':segment});
 const result=await page.evaluate(async({url,bytes})=>{
  const worker=new Worker(url,{type:'module'});let id=0;const pending=new Map();
  worker.onmessage=({data})=>{if(data.stage||data.progress!=null)return;const request=pending.get(data.id);if(!request)return;pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data.result);};
  const request=(action,body={})=>new Promise((resolve,reject)=>{const token=++id;pending.set(token,{resolve,reject});worker.postMessage({id:token,action,...body});});
  try{
   await request('open',{files:[new File([Uint8Array.from(bytes)],'synthetic-heavy-rain.zip')]});
   const values=['Pap!','Neem de blauwe koffer mee naar het station.'],initial=await request('scene-matches',{values}),contextual=await request('scene-matches',{values,groups:initial.groups});
   return {initial,contextual,dutch:await request('match-candidates',{values:['Neem de blauwe koffer mee naar het station.']}),chinese:await request('match-candidates',{values:['请把蓝色行李箱带到车站去。']}),short:await request('match-candidates',{values:['koffer mee']})};
  }finally{worker.terminate();}
 },{url:base+libraryWorkerPath,bytes:[...bytes]});
 for(const hit of [result.dutch,result.chinese]){assert.equal(hit.state,'matched');assert.equal(hit.row.sourceLocale,'nl');assert.equal(hit.row.audioLocale,'nl');assert.equal(hit.row.translationLocale,'zh-Hans');}
 assert.equal(result.short.state,'unmatched');
 assert.equal(result.initial.matches.length,1);assert.equal(result.contextual.matches.length,2);assert.deepEqual(result.initial.groups,['heavyrain:100']);
}
async function diagnoseOcr(page,name,stage){
 await page.screenshot({path:`output/playwright/mobile-library-${name}-failure.png`,fullPage:true});
 const data=await page.evaluate(async({base,pipelinePath})=>{
  const video=document.querySelector('#preview'),{crops,cropFrame,recognizeRegion,candidates}=await import(base+pipelinePath),{default:Tesseract}=await import(base+'/ocr/tesseract.esm.min.js'),language=document.querySelector('#ocr-language').value;
  const worker=await Tesseract.createWorker(language,1,{workerPath:base+'/ocr/worker.min.js',corePath:base+'/ocr/core/',langPath:base+'/ocr/lang/',workerBlobURL:false}),canvas=document.createElement('canvas'),region={crop:crops.zzz,channel:'dialogue',ink:'white'};
  cropFrame(video,canvas,region.crop);const data=await recognizeRegion(worker,canvas,region,language);await worker.terminate();
  return {width:video.videoWidth,height:video.videoHeight,readyState:video.readyState,paused:video.paused,time:video.currentTime,text:data?.text,confidence:data?.confidence,candidates:data?candidates(data,region,canvas.width,canvas.height,'zzz'):null};
 },{base,pipelinePath});console.error({name,stage,...data});
}
let browser;
try{
 for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
  browser=await engines[name].launch({headless:true});
  const context=await browser.newContext({acceptDownloads:true,viewport:{width:390,height:844}}),page=await context.newPage(),errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));context.on('request',request=>{if(!request.url().startsWith(base)&&!request.url().startsWith('blob:')&&!request.url().startsWith('data:'))external.push(request.url());});
  await page.goto(base+'?developer=1');await verifyBeyondContext(page);await verifyHeavyRainPages(page);await page.selectOption('#role','receiver');
  await page.setInputFiles('#library-files',[input('catalog.zip',catalog),input('voices.zip',voices)]);
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('1 unique voice clips accessible'),{},{timeout:30000}).catch(async error=>{console.error({errors,status:await page.locator('#library-status').textContent(),storage:await page.locator('#storage-status').textContent()});throw error;});
  await page.fill('#find-text',quietRow.english+'\n'+quietRow.chinese);await page.click('#find-line');await page.getByRole('button',{name:'No verified original voice',exact:true}).waitFor();assert(await page.getByRole('button',{name:'No verified original voice',exact:true}).isDisabled());await page.click('#clear-history');
  if(name==='webkit'&&process.platform==='win32'){
   const recognized=await page.evaluate(async base=>{const {default:Tesseract}=await import(base+'/ocr/tesseract.esm.min.js');const worker=await Tesseract.createWorker('eng',1,{workerPath:base+'/ocr/worker.min.js',corePath:base+'/ocr/core/',langPath:base+'/ocr/lang/',workerBlobURL:false});const canvas=document.createElement('canvas');canvas.width=900;canvas.height=100;const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,900,100);ctx.fillStyle='black';ctx.font='40px Arial';ctx.fillText('The lantern is bright.',30,65);const result=await worker.recognize(canvas);await worker.terminate();return result.data.text;},base);
   assert(recognized.includes(row.english));assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
   await page.screenshot({path:'output/playwright/mobile-library-webkit.png',fullPage:true});
   console.log('webkit Windows: file opening and real canvas OCR passed; video/MP3 decoding unavailable in this test runtime. Full media checks run on Linux CI.');
   await context.close();await browser.close();browser=null;continue;
  }
  const videoSource=async sources=>page.evaluate(async sources=>{const video=document.querySelector('#preview');video.loop=true;for(const [base64,type] of sources){const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));video.src=URL.createObjectURL(new Blob([bytes],{type}));try{await video.play();window.dispatchEvent(new CustomEvent('mobile-stream',{detail:{generation:1,state:'connected',live:true,game:'zzz',role:'receiver'}}));return;}catch{}}throw new Error('Test browser cannot decode MP4 or WebM.');},sources);
  await videoSource([[VIDEO,'video/mp4'],[WEBM_VIDEO,'video/webm']]);
  await page.click('#ocr-start');
  await page.waitForFunction(()=>document.body.classList.contains('ocr-running'));
  assert(await page.evaluate(()=>{const r=document.querySelector('#preview').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth;}),'The live preview stays visible while reading the transcript');
  await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1,{},{timeout:30000}).catch(async error=>{console.error({stage:'English OCR',status:await page.locator('#match-status').textContent(),errors});await diagnoseOcr(page,name,'English OCR');throw error;});
  assert.equal(await page.locator('.transcript-chinese').textContent(),row.chinese);
  await page.getByRole('button',{name:'Play original voice',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0,{},{timeout:15000});
  await page.getByRole('button',{name:'Favorite',exact:true}).click();
  await page.click('#ocr-pause');
  await page.click('#clear-history');
  await page.selectOption('#ocr-language','chi_sim');
  await videoSource([[CHINESE_VIDEO,'video/mp4'],[CHINESE_WEBM,'video/webm']]);
  await page.click('#ocr-start');
  await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1,{},{timeout:15000}).catch(async error=>{const diagnosis=await page.evaluate(async base=>{const {default:T}=await import(base+'/ocr/tesseract.esm.min.js'),w=await T.createWorker('chi_sim',1,{workerPath:base+'/ocr/worker.min.js',corePath:base+'/ocr/core/',langPath:base+'/ocr/lang/',workerBlobURL:false});await w.setParameters({tessedit_pageseg_mode:'6'});const v=document.querySelector('#preview'),c=document.createElement('canvas');c.width=1800;c.height=301;c.getContext('2d').drawImage(v,v.videoWidth*.08,v.videoHeight*.67,v.videoWidth*.84,v.videoHeight*.25,0,0,1800,301);const r=await w.recognize(c);await w.terminate();return r.data.text;},base);console.error({stage:'Chinese OCR',status:await page.locator('#match-status').textContent(),diagnosis,errors});throw error;});
  assert.equal(await page.locator('.transcript-chinese').textContent(),chineseRow.chinese);
  await page.click('#ocr-pause');
  const offline=files.has('/sw.js');
  if(offline){await page.waitForFunction(()=>navigator.serviceWorker.controller!=null);await context.setOffline(true);}
  await page.reload();
  await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1,{},{timeout:30000});
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('0 unique voice clips accessible'),{},{timeout:30000}).catch(async error=>{console.error({stage:'catalog restore',errors,status:await page.locator('#library-status').textContent(),storage:await page.locator('#storage-status').textContent(),cache:await page.locator('#cache-status').textContent()});throw error;});
  assert(await page.getByRole('button',{name:'Reselect voice pack',exact:true}).isDisabled());
  assert.equal(await page.locator('#library-status').textContent().then(v=>v.includes('0 unique voice clips accessible')),true);
  await page.setInputFiles('#library-files',[input('voices.zip',voices)]);
  await page.waitForFunction(()=>!document.querySelector('.transcript-line button').disabled,{},{timeout:15000});
  await page.getByRole('button',{name:'Play original voice',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0,{},{timeout:15000});
  if(offline){
   await page.selectOption('#role','receiver');await page.click('#clear-history');await videoSource([[CHINESE_VIDEO,'video/mp4'],[CHINESE_WEBM,'video/webm']]);await page.click('#ocr-start');
   await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1,{},{timeout:30000}).catch(async error=>{console.error({stage:'Offline OCR',status:await page.locator('#match-status').textContent(),errors});throw error;});
   assert.equal(await page.locator('.transcript-chinese').textContent(),chineseRow.chinese);await page.click('#ocr-pause');await context.setOffline(false);
  }
  // A malformed file must preserve the existing accessible library.
  await page.setInputFiles('#library-files',[input('broken.zip',Buffer.from('broken'))]);
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('512 MiB')||document.querySelector('#library-status').textContent.includes('complete'),{},{timeout:15000});
  assert(await page.getByRole('button',{name:'Play original voice',exact:true}).isEnabled());
  const download=page.waitForEvent('download');await page.click('#library-report');const report=JSON.parse(readFileSync(await(await download).path(),'utf8'));
  assert.equal(report.availableVoices,1);assert.equal(report.physicalDeviceVerified,false);assert(report.samples.some(v=>v.kind==='playback'));assert(!JSON.stringify(report).includes(row.english));assert(!JSON.stringify(report).includes('catalog.zip'));
  if(name==='chromium'&&process.env.MOBILE_STORAGE_DIR){
   const directory=resolve(process.env.MOBILE_STORAGE_DIR),paths=readdirSync(directory).filter(n=>n.endsWith('.zip')).map(n=>resolve(directory,n)),total=paths.reduce((n,p)=>n+statSync(p).size,0);assert(total>=2*1024**3);
   const start=Date.now();await page.setInputFiles('#library-files',paths);
   await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('50 unique voice clips accessible'),{},{timeout:60000});
   await page.fill('#find-text','Storage test line 0');await page.click('#find-line');await page.getByRole('button',{name:'Play original voice',exact:true}).first().click();await page.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0);
   await page.reload();await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('50 bilingual rows'));assert(await page.getByRole('button',{name:'Reselect voice pack',exact:true}).first().isDisabled());
   await page.setInputFiles('#library-files',paths.filter(p=>!p.endsWith('.catalog.zip')));await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('50 unique voice clips accessible'));
   const saved=page.waitForEvent('download');await page.click('#library-report');const state=JSON.parse(readFileSync(await(await saved).path(),'utf8'));assert.equal(state.selectedBytes,total-statSync(paths.find(p=>p.endsWith('.catalog.zip'))).size);assert.equal(state.selectedPacks,5);assert(state.storage.usage<64*1024**2,'Voice packs must not be copied into browser storage');
   console.log(`chromium: ${(total/1024**3).toFixed(2)} GiB in five Files packs opened, played and reselected in ${Date.now()-start} ms; browser cache below 64 MiB`);
  }
  await page.screenshot({path:`output/playwright/mobile-library-${name}.png`,fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[],'No third-party OCR/library requests');
  console.log(`${name}: real OCR, MP3 playback, file recovery, history/favorites and private reporting passed`);
  await context.close();await browser.close();browser=null;
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
