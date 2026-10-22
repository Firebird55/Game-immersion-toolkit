import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import * as engines from 'playwright';
import {mime} from './mobile-assets.mjs';
if(!process.env.MOBILE_TEST_BROWSERS){
 for(const engine of ['chromium','firefox','webkit'])execFileSync(process.execPath,[fileURLToPath(import.meta.url)],{stdio:'inherit',timeout:180000,env:{...process.env,MOBILE_TEST_BROWSERS:engine}});
 process.exit(0);
}
const built=process.env.MOBILE_PREVIEW_DIR??execFileSync(process.execPath,['scripts/build-mobile-preview.mjs'],{encoding:'utf8'}).match(/Mobile preview: (.+)/)[1].trim();
const files=new Map(readdirSync(built,{recursive:true}).filter(n=>statSync(resolve(built,n)).isFile()).map(n=>[n.replaceAll('\\','/'),readFileSync(resolve(built,n))]));
let served=files;
const prefix='/Game-immersion-toolkit/';
const server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname;if(!path.startsWith(prefix)){res.writeHead(404);res.end();return;}const name=path.slice(prefix.length)||'index.html',body=served.get(name);if(!body){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',mime(name));res.setHeader('Cache-Control','no-store');res.end(body);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base='http://127.0.0.1:'+server.address().port+prefix;
const data=JSON.parse([...files].find(([name])=>/^games-data\.[a-f0-9]+\.json$/.test(name))[1]);
let browser;
try{for(const name of process.env.MOBILE_TEST_BROWSERS.split(',')){
 browser=await engines[name].launch({headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:900},locale:'en-US'}),page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',error=>errors.push(error.message));context.on('request',request=>requests.push(request.url()));
 await page.goto(base+'games.html?game=beyond&study=nl&target=zh-Hans');
 await page.getByRole('heading',{name:'BEYOND: Two Souls',exact:true}).waitFor();
 assert.equal(await page.inputValue('#guide-study'),'nl');assert.equal(await page.inputValue('#guide-target'),'zh-Hans');
 assert.match(await page.locator('.tag').textContent(),/Dutch → Simplified Chinese: Supported with installed assets/);
 await page.waitForFunction(async()=>Boolean((await navigator.serviceWorker.getRegistration())?.active&&navigator.serviceWorker.controller));
 // Public promises across every advertised source/target combination, not sampled languages.
 const claims=await page.evaluate(async()=>{const source=[...performance.getEntriesByType('resource')].find(e=>/games-data\./.test(e.name)).name;return await(await fetch(source)).json();});assert.deepEqual(claims,data);
 for(const game of data.games){await page.selectOption('#guide-game',game.id);await page.selectOption('#guide-study','all');await page.selectOption('#guide-target','all');assert.equal(await page.locator('.game-card').count(),1);await page.getByText('Compare every language',{exact:true}).click();const table=page.locator('tbody');for(const code of game.study)assert(await table.getByRole('rowheader',{name:data.languages[code],exact:true}).count());}
 for(const game of ['beyond','heavyrain']){await page.selectOption('#guide-game',game);await page.selectOption('#guide-study','nl');await page.selectOption('#guide-target','zh-Hant');assert.match(await page.locator('.tag').textContent(),/Supported with installed assets/);}
 await page.selectOption('#guide-game','heavyrain');await page.selectOption('#guide-target','pt-BR');assert.match(await page.locator('.game-card .warning').first().textContent(),/No official toolkit translation/);
 await page.selectOption('#guide-game','zzz');await page.selectOption('#guide-study','ja');await page.selectOption('#guide-target','es-419');assert.match(await page.locator('.game-card .warning').first().textContent(),/Translation locale unverified/);
 await page.selectOption('#guide-game','nte');await page.selectOption('#guide-target','fr');assert.match(await page.locator('.game-card .warning').first().textContent(),/Expected with installed assets/);
 await page.selectOption('#guide-game','all');await page.selectOption('#guide-study','all');await page.selectOption('#guide-target','all');assert.equal(await page.locator('.game-card').count(),9);assert.equal(await page.locator('#guide-game option[value="honkai3"]').count(),0);
 async function fits(message){const result=await page.evaluate(()=>({fits:document.documentElement.scrollWidth<=innerWidth+1,viewport:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,className:el.className,text:el.textContent.slice(0,80),left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right})).filter(el=>el.right>innerWidth+1||el.left< -1).slice(0,15)}));if(!result.fits){mkdirSync('output/playwright',{recursive:true});await page.screenshot({path:'output/playwright/games-guide-overflow-'+name+'.png',fullPage:true});console.error(message,result);}assert(result.fits,message);}
 for(const width of [320,390,768,1280]){await page.setViewportSize({width,height:900});await fits(name+' no horizontal overflow at '+width);}
 await page.evaluate(()=>document.body.style.zoom='2');await page.setViewportSize({width:780,height:900});await fits(name+' 200% zoom');
 // Stress wider platform font metrics as well as the system font. The hosted
 // Linux runner and Windows can wrap the same label at different widths.
 await page.evaluate(()=>{document.body.style.fontFamily='Arial,sans-serif';document.body.style.fontSize='20px';});await fits(name+' 200% zoom with enlarged Arial');await page.evaluate(()=>{document.body.style.zoom='';document.body.style.fontFamily='';document.body.style.fontSize='';});
 await page.goto(base+'games.html?game=heavyrain&study=nl&target=zh-Hans');await page.locator('.tag').waitFor();await page.locator('#guide-game').focus();await page.keyboard.press('Tab');assert(await page.locator('#guide-study').evaluate(el=>el===document.activeElement));
 const permalink=await page.locator('#selection-link').getAttribute('href');assert.match(permalink,/game=heavyrain&study=nl&target=zh-Hans/);
 assert(!requests.some(url=>!url.startsWith(base)&&!url.startsWith('blob:')),'Guide does not contact accounts, local services or storefronts automatically');
 await context.setOffline(true);await page.reload();await page.locator('.tag').waitFor();assert.equal(await page.title(),'Games & Languages — Game immersion toolkit');assert.match(await page.locator('.tag').textContent(),/Dutch → Simplified Chinese/);
 await page.getByRole('link',{name:'Open companion',exact:true}).click();await page.getByRole('button',{name:'Reader',exact:true}).waitFor();await page.locator('.public-guide a').click();await page.locator('.game-card').first().waitFor();assert.equal(await page.title(),'Games & Languages — Game immersion toolkit');
 await context.setOffline(false);await page.goto(base+'games.html?game=bad&study=bad&target=bad');await page.locator('.game-card').first().waitFor();assert.equal(await page.inputValue('#guide-game'),'all');
 if(name==='chromium'){mkdirSync('output/playwright',{recursive:true});await page.goto(base+'games.html?game=beyond&study=nl&target=zh-Hans');await page.locator('.tag').waitFor();await page.screenshot({path:'output/playwright/games-guide.png',fullPage:true});}
 await page.goto(base+'games.html?game=beyond&study=nl&target=zh-Hans');await page.locator('.tag').waitFor();
 for(const [locale,title] of [['nl','Vind een taalcombinatie'],['zh-Hans','查找语言组合'],['zh-Hant','尋找語言組合']]){
  await page.selectOption('#guide-interface',locale);await page.getByRole('heading',{name:title,exact:true}).waitFor();
  assert.equal(await page.inputValue('#guide-study'),'nl');assert.equal(await page.inputValue('#guide-target'),'zh-Hans');
  await page.setViewportSize({width:390,height:844});await fits(name+' localized '+locale);
  await page.reload();await page.getByRole('heading',{name:title,exact:true}).waitFor();
 }
 assert.deepEqual(errors,[]);await context.close();
 // Synthetic old-site cache: no guide assets, and navigation falls back to the
 // companion. Upgrading must explicitly install the new guide without clearing storage.
 const legacy=new Map(files);for(const key of legacy.keys())if(key.startsWith('games'))legacy.delete(key);
 legacy.set('index.html',Buffer.from('<!doctype html><html><title>Previous companion cache fixture</title><body>Previous companion</body></html>'));
 legacy.set('sw.js',Buffer.from(`const NAME='proxy-mobile-guide-previous';self.addEventListener('install',e=>e.waitUntil(caches.open(NAME).then(c=>c.add('./index.html'))));self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));self.addEventListener('fetch',e=>{if(e.request.mode==='navigate')e.respondWith(fetch(e.request).catch(()=>caches.open(NAME).then(c=>c.match('./index.html'))));});`));
 served=legacy;const prior=await browser.newContext({locale:'en-US'}),old=await prior.newPage();await old.goto(base);await old.evaluate(()=>navigator.serviceWorker.register('./sw.js'));await old.waitForFunction(()=>navigator.serviceWorker.controller!==null);await old.evaluate(()=>localStorage.setItem('guide-upgrade-fixture','retained'));
 served=files;await old.goto(base+'games.html?game=beyond&study=nl&target=zh-Hans');await old.locator('.tag').waitFor();await old.getByRole('button',{name:'Update guide',exact:true}).waitFor();await old.getByRole('button',{name:'Update guide',exact:true}).click();await old.locator('.tag').waitFor();await old.waitForFunction(async()=>!(await navigator.serviceWorker.getRegistration()).waiting);await prior.setOffline(true);await old.reload();await old.locator('.tag').waitFor();assert.match(await old.locator('.tag').textContent(),/Dutch → Simplified Chinese/);assert.equal(await old.evaluate(()=>localStorage.getItem('guide-upgrade-fixture')),'retained');await prior.close();
 console.log(`${name}: guide languages, regional exclusions, direct links, keyboard, mobile/zoom, offline navigation and previous-site cache upgrade passed`);await browser.close();browser=null;
}}finally{await browser?.close();await new Promise(r=>server.close(r));}
