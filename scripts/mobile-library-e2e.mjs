import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {zipSync,strToU8} from 'fflate';
import {createHash} from 'node:crypto';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';
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
const storagePath=[...files.keys()].find(p=>/\/storage(?:\.[a-f0-9]+)?\.mjs$/.test(p));
async function verifyZzzProxy(page){
 const female={...row,id:'7'.repeat(64),textId:'GalGame_fixture:F',sourceVoice:'7'.repeat(64),playerVoice:'female',sourceLanguage:'ja',sourceLocale:'ja',audioLocale:'ja',sourceText:'私の言葉です。',translationLocale:'zh-Hans',translationText:'这句话的字幕相同。',memberTextIds:['GalGame_fixture']},
 male={...female,id:'6'.repeat(64),textId:'GalGame_fixture:M',sourceVoice:'6'.repeat(64),playerVoice:'male',sourceText:'僕の言葉です。',memberTextIds:['GalGame_fixture']};
 const segment=Buffer.from([female,male].map(value=>JSON.stringify(value)+'\n').join('')),bytes=encode({'manifest.json':{...manifest,game:'zzz',coverage:{dialogue:2},catalog:[{name:'catalog/00000.ndjson',size:segment.length,sha256:hash(segment)}]},'catalog/00000.ndjson':segment});
 const result=await page.evaluate(async({url,bytes})=>{
  const worker=new Worker(url,{type:'module'});let id=0;const pending=new Map();
  worker.onmessage=({data})=>{if(data.stage||data.progress!=null)return;const request=pending.get(data.id);if(!request)return;pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data.result);};
  const request=(action,body={})=>new Promise((resolve,reject)=>{const token=++id;pending.set(token,{resolve,reject});worker.postMessage({id:token,action,...body});});
  try{
   await request('open',{files:[new File([Uint8Array.from(bytes)],'synthetic-zzz-proxy.zip')]});
   return {unique:await request('match-candidates',{values:['私の言葉です。']}),ambiguous:await request('match-candidates',{values:['这句话的字幕相同。']}),male:await request('match-candidates',{values:['这句话的字幕相同。'],player:'male'})};
  }finally{worker.terminate();}
 },{url:base+libraryWorkerPath,bytes:[...bytes]});
 assert.equal(result.unique.row.textId,female.textId);assert.equal(result.unique.row.sourceLocale,'ja');assert.equal(result.unique.row.audioLocale,'ja');assert.equal(result.unique.row.memberTextIds,undefined);
 assert.notEqual(result.ambiguous.state,'matched');assert.equal(result.male.row.textId,male.textId);
}
async function verifyBeyondContext(page){
 const first={...row,id:'d'.repeat(64),textId:'beyond:ONE:1',sourceVoice:'d'.repeat(64),sourceLanguage:'nl',sourceLocale:'nl',audioLocale:'nl',sourceText:'Goed.',translationLocale:'zh-Hans',translationText:'好的'};
 const other={...first,id:'e'.repeat(64),textId:'beyond:OTHER:1',sourceVoice:'e'.repeat(64)};
 const paired={...first,id:'f'.repeat(64),textId:'beyond:ONE:context-100-900',sourceVoice:'f'.repeat(64),sourceText:'Goed. We gaan naar huis.',translationText:'好的 我们回家吧。',anchorsSource:['We gaan naar huis.'],anchorsTranslation:['我们回家吧。'],memberTextIds:['beyond:ONE:1','beyond:ONE:2']};
 const collision={...other,id:'9'.repeat(64),sourceText:'Een andere tekst.',translationText:'我们回家吧。'};
 const background={...first,id:'8'.repeat(64),textId:'beyond:BACKGROUND:complete',sourceVoice:'8'.repeat(64),sourceText:'Ik zei dat het bijna klaar is!',translationText:'我说快准备好了！'};
 const rows=[first,other,paired,collision,background],segment=Buffer.from(rows.map(value=>JSON.stringify(value)+'\n').join(''));
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
   const simultaneous=await request('simultaneous-matches',{values:['我们回家吧。','我说快准备好了！'],primary:paired});
   const unresolved=await request('simultaneous-matches',{values:['好的','我说快准备好了！']});
   return {first:first.state,last:last.state,paired,isolated:isolated.state,simultaneous,unresolved};
  }finally{worker.terminate();}
 },{url:base+libraryWorkerPath,bytes:[...bytes]});
 assert.equal(result.first,'ambiguous');assert.equal(result.last,'ambiguous');assert.equal(result.isolated,'unmatched');
 assert.equal(result.paired.row.textId,paired.textId);assert.equal(result.paired.row.sourceLocale,'nl');assert.equal(result.paired.row.audioLocale,'nl');
 assert.deepEqual(result.paired.row.memberTextIds,paired.memberTextIds);
 assert.deepEqual(new Set(result.simultaneous.map(hit=>hit.row.id)),new Set([paired.id,background.id]));
 assert.deepEqual(result.unresolved.map(hit=>hit.row.id),[background.id]);
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
let browser;
const bundle=encode({'manifest.json':{format:'proxy-mobile-bundle-v1',kind:'bundle',game:'zzz',revision:id,catalog:'library/catalog.zip',voices:[`library/voices/${id}.zip`]},'library/catalog.zip':catalog,[`library/voices/${id}.zip`]:voices});
try{
 for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
  browser=await engines[name].launch({headless:true});const context=await browser.newContext({viewport:{width:390,height:844},acceptDownloads:true}),page=await context.newPage(),errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('blob:')&&!r.url().startsWith('data:'))external.push(r.url());});
  await page.goto(base+'?developer=1');await page.getByRole('heading',{name:'Game immersion toolkit',exact:true}).waitFor();
  await page.setInputFiles('#library-files',input('retained-test.zip',bundle));
  await page.waitForFunction(()=>!document.querySelector('#library-files').disabled&&document.querySelector('#cache-status').textContent.includes('on this device'));
  const retention=await page.locator('#cache-status').textContent();
  if(name==='webkit'&&process.platform==='win32'&&retention.includes('could not be kept')){
   assert.match(retention,/works this session/);
   console.log('Windows WebKit OPFS unavailable: session-only fallback verified; retained reopening UNVERIFIED on this runtime.');
  }else{
   assert.match(retention,/^Library kept on this device/);
   await page.reload();await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready'));
   assert.equal(await page.locator('#saved-libraries option').count(),2);
   await page.setInputFiles('#library-files',input('bad-update.zip',Buffer.from('broken')));
   await page.waitForFunction(()=>!document.querySelector('#library-files').disabled);
   await page.reload();await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready'));
   await page.click('#remove-retained-library');await page.waitForFunction(()=>document.querySelector('#saved-libraries').options.length===1);
  }
  await page.click('#forget-library');await page.locator('#keep-library').uncheck();
  await verifyZzzProxy(page);await verifyBeyondContext(page);await verifyHeavyRainPages(page);
  assert.equal(await page.locator('.companion-nav button').count(),2);
  await page.setInputFiles('#library-files',input('old-voices.zip',voices));
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('voice-only'));
  const chooser=page.waitForEvent('filechooser');await page.click('#open-library');await(await chooser).setFiles(input('Synthetic Game - Mandarin - Mobile Library.zip',bundle));
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready'));
  assert.match(await page.locator('#selected-library').textContent(),/Mandarin - Mobile Library/);
  await page.waitForFunction(()=>!document.querySelector('#library-files').disabled);
  assert.equal(await page.inputValue('#library-files'),'','Resetting the picker permits retry without losing the visible selected file');
  assert(await page.getByRole('button',{name:'Change library',exact:true}).isVisible());
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.fill('#find-text',row.english);await page.click('#find-line');
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.locator('.current-card').filter({hasText:row.chinese}).waitFor();
  if(!(name==='webkit'&&process.platform==='win32')){
   await page.locator('.current-card').getByRole('button',{name:'▶ Play voice',exact:true}).click();
   await page.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0,null,{timeout:15000});
  }else console.log('Windows WebKit audio decoding is unavailable; bundle bytes and clip checksum are still verified.');
  await page.locator('.current-card').getByRole('button',{name:'☆ Favorite',exact:true}).click();
  await page.locator('.current-card').getByRole('button',{name:'★ Favorited',exact:true}).waitFor();
  await page.setInputFiles('#library-files',input('broken.zip',Buffer.from('broken')));
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('incomplete'));
  assert(await page.locator('.current-card').getByRole('button',{name:'▶ Play voice',exact:true}).isEnabled(),'A bad replacement preserves working voices');
  await page.evaluate(async path=>{const storage=await import(path),history=await storage.get('history');await storage.put('history',history.map(row=>({...row,audio:'f'.repeat(64)})));},storagePath);
  await page.reload();await page.locator('#keep-library').uncheck();await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Reopen library for voices'));
  await page.getByRole('button',{name:'Reopen voice library',exact:true}).waitFor();
  assert(await page.locator('.current-card').getByRole('button',{name:'▶ Play voice',exact:true}).isDisabled());
  await page.locator('.current-card').getByRole('button',{name:'★ Favorited',exact:true}).waitFor();
  const reopen=page.waitForEvent('filechooser');await page.locator('.current-card').getByRole('button',{name:'Open voice library',exact:true}).click();await(await reopen).setFiles(input('Synthetic Game - Mandarin - Mobile Library.zip',bundle));
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready'));
  await page.waitForFunction(()=>!document.querySelector('.current-card .line-actions button').disabled);
  assert(await page.locator('.current-card').getByRole('button',{name:'▶ Play voice',exact:true}).isEnabled(),'Reopening repairs an old saved audio hash');
  // Older catalog + voice files remain usable, including voice-only reselection with a remembered catalog.
  await page.setInputFiles('#library-files',[input('catalog.zip',catalog),input('voices.zip',voices)]);
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready'));
  await page.setInputFiles('#library-files',input('voices.zip',voices));
  await page.waitForFunction(()=>!document.querySelector('#library-files').disabled);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  const download=page.waitForEvent('download');await page.click('#library-report');const report=JSON.parse(readFileSync(await(await download).path(),'utf8'));
  assert.equal(report.availableVoices,1);assert.equal(report.physicalDeviceVerified,false);assert(!JSON.stringify(report).includes(row.english));
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.screenshot({path:`output/playwright/mobile-library-${name}.png`,fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[],'No third-party library requests');
  if(name==='chromium'&&process.env.MOBILE_REAL_BUNDLE){const start=Date.now();await page.setInputFiles('#library-files',process.env.MOBILE_REAL_BUNDLE);await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Voices ready')&&!document.querySelector('#library-files').disabled,null,{timeout:120000});console.log(`chromium: owner-local large bundle opened through the actual UI in ${Date.now()-start} ms; no game text or audio was uploaded`);}
  console.log(`${name}: one-file import, actionable missing catalog, persistent file status, manual voice playback, favorites, reload, legacy files and failure recovery passed`);
  await context.close();await browser.close();browser=null;
 }
}finally{await browser?.close();await new Promise(r=>server.close(r));}
