import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {zipSync,strToU8} from 'fflate';
import * as engines from 'playwright';
import {mime} from './mobile-assets.mjs';
// Give each engine a fresh origin and process, with bounded startup and teardown.
if(!process.env.MOBILE_TEST_BROWSERS){
 for(const engine of ['chromium','firefox','webkit'])execFileSync(process.execPath,[fileURLToPath(import.meta.url)],{stdio:'inherit',timeout:120000,env:{...process.env,MOBILE_TEST_BROWSERS:engine}});
 process.exit(0);
}
const built=process.env.MOBILE_PREVIEW_DIR??execFileSync(process.execPath,['scripts/build-mobile-preview.mjs'],{encoding:'utf8'}).match(/Mobile preview: (.+)/)[1].trim();
const baseline=new Map(readdirSync(built,{recursive:true}).filter(n=>statSync(resolve(built,n)).isFile()).map(n=>[n.replaceAll('\\','/'),readFileSync(resolve(built,n))]));
let files=baseline;
const server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html',bytes=files.get(name);if(!bytes){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name));res.setHeader('Cache-Control','no-store');res.end(bytes);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const id='a'.repeat(64),row={id,textId:'update-check',english:'The lantern is bright.',chinese:'灯笼很亮。',audio:null,sourceVoice:id,channels:['dialogue']},segment=strToU8(JSON.stringify(row)+'\n'),sha=createHash('sha256').update(segment).digest('hex');
const manifest={format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic update verification',revision:id,coverage:{dialogue:1},catalog:[{name:'catalog/00000.ndjson',size:segment.length,sha256:sha}],packs:[]};
const catalog=Buffer.from(zipSync({'manifest.json':strToU8(JSON.stringify(manifest)),'catalog/00000.ndjson':segment},{level:0}));
let browser;
try{for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
 files=new Map(baseline);browser=await engines[name].launch({headless:true});const context=await browser.newContext(),page=await context.newPage(),errors=[],failures=[];page.on('pageerror',e=>errors.push(e.message));context.on('requestfailed',r=>failures.push({path:new URL(r.url()).pathname,error:r.failure()?.errorText}));await page.goto(base);
 await page.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration())?.active,{},{timeout:30000}).catch(error=>{console.error(name,{errors,failures,stage:'service worker activation'});throw error;});await page.reload();await page.waitForFunction(()=>navigator.serviceWorker.controller!=null);
 await page.setInputFiles('#library-files',{name:'synthetic.zip',mimeType:'application/zip',buffer:catalog});await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('1 bilingual rows'));
 await page.fill('#find-text',row.english);await page.click('#find-line');await page.getByRole('button',{name:'Favorite',exact:true}).click();
 await page.locator('summary').filter({hasText:'Capture regions and calibration'}).click();await page.fill('#crop-left','9');await page.locator('#crop-left').dispatchEvent('change');
 await page.waitForFunction(async()=>{const db=await new Promise((r,j)=>{const q=indexedDB.open('proxy-mobile-library');q.onsuccess=()=>r(q.result);q.onerror=j;});const value=await new Promise(r=>{const q=db.transaction('state').objectStore('state').get('preferences');q.onsuccess=()=>r(q.result);});db.close();return value?.zzz?.crop[0]===.09;});
 const oldBuild=await page.getAttribute('html','data-build-commit');
 assert(await page.evaluate(async base=>!!await caches.match(base+'/ocr/tesseract.esm.min.js'),base),'The application OCR loader must be cached before the first offline visit');
 await context.setOffline(true);await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1).catch(async error=>{console.error(name,{stage:'offline restore',errors,failures,library:await page.locator('#library-status').textContent()});throw error;});assert.equal(await page.getByRole('button',{name:'Unfavorite',exact:true}).count(),1);await context.setOffline(false);
 // Simulate an active capture's disabled role/update controls. Real WebRTC
 // reconnects are separately exercised by mobile-capture-e2e.
 await page.evaluate(()=>{document.querySelector('#role').disabled=true;document.querySelector('#reload-build').disabled=true;});
 const ui=[...files.keys()].find(n=>/^mobile-ui\..*\.mjs$/.test(n)),changed=Buffer.concat([files.get(ui),Buffer.from('\n// synthetic application update fixture\n')]),next='mobile-ui.'+createHash('sha256').update(changed).digest('hex').slice(0,16)+'.mjs';
 files.set(next,changed);files.set('index.html',Buffer.from(files.get('index.html').toString().replaceAll(ui,next).replace(oldBuild,'b'.repeat(40))));files.set('sw.js',Buffer.from(files.get('sw.js').toString().replaceAll(ui,next).replace(/proxy-mobile-([a-f0-9]{16})/,'proxy-mobile-$1-test-update')));
 await page.evaluate(()=>navigator.serviceWorker.getRegistration().then(r=>r.update()));await page.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration()).waiting);
 assert.equal(await page.getAttribute('html','data-build-commit'),oldBuild,'Waiting update must not replace an active page');assert(await page.locator('#reload-build').isDisabled());
 await page.evaluate(()=>{document.querySelector('#role').disabled=false;document.querySelector('#reload-build').disabled=false;});await page.click('#reload-build');await page.waitForFunction(()=>document.documentElement.dataset.buildCommit==='b'.repeat(40));
 await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1);assert.equal(await page.getByRole('button',{name:'Unfavorite',exact:true}).count(),1);assert.equal(await page.inputValue('#crop-left'),'9');
 const keys=await page.evaluate(async()=>{const names=await caches.keys(),urls=[];for(const n of names)for(const r of await(await caches.open(n)).keys())urls.push(r.url);return urls;});assert(!keys.some(u=>u.endsWith('.zip')),'No selected catalog or voice files in application cache');assert.deepEqual(errors,[]);
 console.log(`${name}: offline application cache, waiting update, retained catalog/favorite/calibration and allowlist passed`);await context.close();await browser.close();browser=null;
}}finally{await browser?.close();await new Promise(r=>server.close(r));}
