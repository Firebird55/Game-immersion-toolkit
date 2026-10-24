import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdtempSync,rmSync} from 'node:fs';
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
let browser,stage='starting';
const profiles=new Set();
const mark=value=>{stage=value;console.log(`${process.env.MOBILE_TEST_BROWSERS}: offline check — ${stage}`);};
// Print the current operation before the parent deadline, even if browser cleanup
// stalls. Ordinary failures are also printed before entering that cleanup.
const watchdog=setTimeout(()=>{console.error(`Offline test exceeded 105 seconds during: ${stage}`);process.exit(1);},105000);
watchdog.unref();
try{for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
 files=new Map(baseline);
 mark('launch browser');
 // Exercise Firefox's durable site storage in a fresh owned profile. Its
 // ephemeral test context can lose its controller and cache mid-session on
 // Windows; the restart below also verifies the actual offline-use contract.
 const profile=name==='firefox'?mkdtempSync(resolve('output/offline-firefox-')):null;
 if(profile)profiles.add(profile);
 // This fixture's text assertions require English on every host, including restart.
 let context;
 if(profile){context=await engines[name].launchPersistentContext(profile,{headless:true,locale:'en-US'});browser=context.browser();}
 else{browser=await engines[name].launch({headless:true});context=await browser.newContext({locale:'en-US'});}
 const page=await context.newPage(),errors=[],failures=[],runtimeErrors=[],offlineDiagnostics=[];let offline=false;
 // WebKit also emits browser-generated JS-source network diagnostics through
 // Playwright's pageerror event. Keep actual script errors/rejections fatal,
 // including those raised in an old document while navigation is in progress.
 await context.exposeBinding('__reportRuntimeError',(_,error)=>runtimeErrors.push(error));
 await context.addInitScript(()=>{
  addEventListener('error',event=>{if(event instanceof ErrorEvent)void globalThis.__reportRuntimeError({type:'error',message:event.message});});
  addEventListener('unhandledrejection',event=>{void globalThis.__reportRuntimeError({type:'unhandledrejection',message:String(event.reason)});});
 });
 // Playwright splits this console text at the first ':', leaving '/host/...'.
 const offlineWorkerMessage=`/${new URL(base).host}/sw.js due to access control checks.`;
 page.on('pageerror',e=>{if(name==='webkit'&&offline&&!e.stack&&e.message===offlineWorkerMessage)offlineDiagnostics.push(e.message);else errors.push({message:e.message,offline});});
 context.on('requestfailed',r=>failures.push({path:new URL(r.url()).pathname,error:r.failure()?.errorText}));mark('online navigation and service worker activation');await page.goto(base+'?developer=1');
 // clients.claim() already controls this page. Import immediately after that
 // handoff; the two offline reloads below test controlled navigations explicitly.
 await page.waitForFunction(async()=>(await navigator.serviceWorker.getRegistration())?.active?.state==='activated'&&navigator.serviceWorker.controller!=null,{},{timeout:30000}).catch(error=>{console.error(name,{errors,failures,stage:'service worker activation and control'});throw error;});
 // Worker activation can finish before the dynamically imported library UI.
 // Select the file only once its real change handler can consume the event.
 await page.waitForFunction(()=>typeof document.querySelector('#library-files').onchange==='function');
 mark('import catalog and save preferences');await page.setInputFiles('#library-files',{name:'synthetic.zip',mimeType:'application/zip',buffer:catalog});await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('1 lines')).catch(async error=>{console.error('Import fixture diagnostics',{errors,failures,runtimeErrors,state:await page.evaluate(()=>({language:navigator.language,documentLanguage:document.documentElement.lang,status:document.querySelector('#library-status').textContent,summaries:[...document.querySelectorAll('summary')].map(el=>el.textContent)}))});throw error;});
 await page.getByRole('button',{name:'Settings',exact:true}).click();await page.fill('#find-text',row.english);await page.click('#find-line');await page.getByRole('button',{name:'Favorite',exact:true}).click();
 await page.locator('summary').filter({hasText:'Capture regions and calibration'}).click();await page.fill('#crop-left','9');await page.locator('#crop-left').dispatchEvent('change');
 await page.waitForFunction(async()=>{const db=await new Promise((r,j)=>{const q=indexedDB.open('proxy-mobile-library');q.onsuccess=()=>r(q.result);q.onerror=j;});const value=await new Promise(r=>{const q=db.transaction('state').objectStore('state').get('preferences');q.onsuccess=()=>r(q.result);});db.close();return value?.zzz?.crop[0]===.09;});
 const oldBuild=await page.getAttribute('html','data-build-commit');
 const loaderCached=await page.evaluate(async base=>!!await caches.match(base+'/ocr/tesseract.esm.min.js'),base);
 if(!loaderCached){const diagnostics=await page.evaluate(async()=>({controller:navigator.serviceWorker.controller?.scriptURL,caches:await Promise.all((await caches.keys()).map(async name=>({name,requests:await Promise.all((await(await caches.open(name)).keys()).map(async request=>({url:request.url,headers:[...(await(await caches.open(name)).match(request)).headers]})))})))}));console.error('Offline cache diagnostics',name,await browser.version(),JSON.stringify(diagnostics,null,2));}
 assert(loaderCached,'The application OCR loader must be cached before the first offline visit');
 mark('first offline reload');
 offline=true;await context.setOffline(true);await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1).catch(async error=>{console.error(name,{stage:'offline restore',errors,failures,library:await page.locator('#library-status').textContent()});throw error;});await page.getByRole('button',{name:'Unfavorite',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Unfavorite',exact:true}).count(),1);await context.setOffline(false);offline=false;
 // Simulate an active capture's disabled role/update controls. Real WebRTC
 // reconnects are separately exercised by mobile-capture-e2e.
 await page.evaluate(()=>{document.querySelector('#role').disabled=true;document.querySelector('#reload-build').disabled=true;});
 const ui=[...files.keys()].find(n=>/^mobile-ui\..*\.mjs$/.test(n)),changed=Buffer.concat([files.get(ui),Buffer.from('\n// synthetic application update fixture\n')]),next='mobile-ui.'+createHash('sha256').update(changed).digest('hex').slice(0,16)+'.mjs';
 const shell=[...files.keys()].find(n=>/^companion\..*\.js$/.test(n)),changedShell=Buffer.from(files.get(shell).toString().replaceAll(ui,next)),nextShell='companion.'+createHash('sha256').update(changedShell).digest('hex').slice(0,16)+'.js';
 files.set(next,changed);files.set(nextShell,changedShell);files.delete(ui);files.delete(shell);
 files.set('index.html',Buffer.from(files.get('index.html').toString().replaceAll(ui,next).replaceAll(shell,nextShell).replace(oldBuild,'b'.repeat(40))));files.set('sw.js',Buffer.from(files.get('sw.js').toString().replaceAll(ui,next).replaceAll(shell,nextShell).replace(/proxy-mobile-([a-f0-9]{16})/,'proxy-mobile-$1-test-update')));
 mark('install waiting update');await page.evaluate(()=>navigator.serviceWorker.getRegistration().then(r=>r.update()));await page.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration()).waiting);
 assert.equal(await page.getAttribute('html','data-build-commit'),oldBuild,'Waiting update must not replace an active page');assert(await page.locator('#reload-build').isDisabled());
 mark('activate requested update');
 await page.evaluate(()=>{document.querySelector('#role').disabled=false;document.querySelector('#reload-build').disabled=false;});await page.click('#reload-build');await page.waitForFunction(()=>document.documentElement.dataset.buildCommit==='b'.repeat(40));
 await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1);await page.getByRole('button',{name:'Unfavorite',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Unfavorite',exact:true}).count(),1);assert.equal(await page.inputValue('#crop-left'),'9');
 mark('reload updated application offline');
 offline=true;await context.setOffline(true);await page.reload();await page.waitForFunction(()=>document.documentElement.dataset.buildCommit==='b'.repeat(40)).catch(async error=>{console.error('Offline update diagnostics',await page.evaluate(async()=>({build:document.documentElement.dataset.buildCommit,cache:await Promise.all((await caches.keys()).map(async name=>({name,build:(await(await(await caches.open(name)).match(new URL('./index.html',location.href)))?.text())?.match(/data-build-commit="([^"]+)/)?.[1]})))})));throw error;});await page.waitForFunction(()=>document.querySelectorAll('.transcript-line').length===1);
 assert.equal(await page.evaluate(async name=>(await fetch('./'+name)).status,ui),200,'Previously cached allowlisted modules remain readable for older open tabs');await context.setOffline(false);offline=false;
 mark('offline language guide and cache allowlist');
 offline=true;await context.setOffline(true);await page.goto(base+'/games.html?game=beyond&study=nl&target=zh-Hans');await page.locator('.tag').waitFor();assert.match(await page.locator('.tag').textContent(),/Dutch → Simplified Chinese: Supported/);await context.setOffline(false);offline=false;
 const keys=await page.evaluate(async()=>{const names=await caches.keys(),urls=[];for(const n of names)for(const r of await(await caches.open(n)).keys())urls.push(r.url);return urls;});assert(!keys.some(u=>u.endsWith('.zip')),'No selected catalog or voice files in application cache');assert.deepEqual(runtimeErrors,[],'No uncaught application errors or unhandled rejections');assert.deepEqual(errors,[]);
 if(offlineDiagnostics.length)console.log(`${name}: ${offlineDiagnostics.length} browser-only offline sw.js fetch diagnostics; no script errors or unhandled rejections`);
 mark('close browser');await context.close();await browser.close();browser=null;
 if(profile){
  mark('restart browser offline');
  context=await engines[name].launchPersistentContext(profile,{headless:true,locale:'en-US'});browser=context.browser();
  await context.setOffline(true);const reopened=await context.newPage(),restartErrors=[];reopened.on('pageerror',error=>restartErrors.push(error.message));
  await reopened.goto(base+'?developer=1');
  await reopened.waitForFunction(()=>document.documentElement.dataset.buildCommit==='b'.repeat(40)&&document.querySelectorAll('.transcript-line').length===1);
  await reopened.getByRole('button',{name:'Unfavorite',exact:true}).waitFor();assert.equal(await reopened.inputValue('#crop-left'),'9');
  assert(await reopened.evaluate(()=>caches.match(new URL('./ocr/tesseract.esm.min.js',location.href)).then(Boolean)),'OCR loader survives a real browser restart');
  assert.deepEqual(restartErrors,[]);await context.close();await browser.close();browser=null;
 }
 console.log(`${name}: offline application cache, waiting update, retained catalog/favorite/calibration and allowlist passed${profile?' including a browser restart':''}`);
}}catch(error){console.error(`Offline check failed during: ${stage}`,error);throw error;}
finally{
 let browserClosed=false;
 try{await browser?.close();browserClosed=true;}finally{
  server.closeAllConnections();await new Promise(r=>server.close(r));clearTimeout(watchdog);
  if(browserClosed)for(const profile of profiles)rmSync(profile,{recursive:true,force:true,maxRetries:3,retryDelay:100});
 }
}
