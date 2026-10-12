import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync,statSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import * as engines from 'playwright';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';
const root=resolve(process.env.MOBILE_PREVIEW_DIR??'public/mobile-capture'),assets=ocrAssets();
const server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';if(name.includes('..')){res.writeHead(404).end();return;}try{const bytes=assets.get(name)??readFileSync(resolve(root,name));res.setHeader('Content-Type',mime(name));res.end(bytes);}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
const fixture=Array.from({length:12},(_,i)=>({id:12-i,game:'zzz',created_at:new Date(1700000000000+(12-i)*1000).toISOString(),chinese:'你好，旅行者。'+(12-i),english:'Hello, traveler. '+(12-i),speaker_chinese:'向导',speaker_english:'Guide',has_audio:true,audio_source:'original',favorite:true}));
const api='http://127.0.0.1:8766',gateway='https://game-immersion-lexirise.boazbrak.workers.dev';
mkdirSync('output/playwright',{recursive:true});
let browser;
try{for(const name of (process.env.MOBILE_TEST_BROWSERS??'chromium,firefox,webkit').split(',')){
 browser=await engines[name].launch();const context=await browser.newContext({viewport:{width:1280,height:900}}),errors=[],writes=[];
 await context.addInitScript(()=>{window.captureRequests=0;if(navigator.mediaDevices)navigator.mediaDevices.getDisplayMedia=async()=>{window.captureRequests++;throw Error('Transcript sharing must not capture');};});
 await context.route(api+'/**',route=>{const u=new URL(route.request().url());if(u.pathname==='/api/lines'){const before=Number(u.searchParams.get('before_id')??Infinity);return route.fulfill({json:fixture.filter(r=>r.id<before).slice(0,8),headers:{'Access-Control-Allow-Origin':'*'}});}if(/^\/api\/lines\/\d+\/audio$/.test(u.pathname))return route.fulfill({body:Buffer.from(TONE,'base64'),contentType:'audio/mpeg',headers:{'Access-Control-Allow-Origin':'*'}});throw Error('Unexpected local API access: '+u.pathname);});
 const sockets=[];await context.routeWebSocket('ws://127.0.0.1:8766/api/ws',socket=>sockets.push(socket));
 await context.route(gateway+'/**',async route=>{const request=route.request();if(request.method()==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type'}});const body=request.postDataJSON();if(['PATCH','POST'].includes(body.method)&&!body.path.startsWith('/v1/analyze')&&!body.path.startsWith('/v1/dictionary'))writes.push(body);let data={};if(body.path==='/v1/settings')data={languages:['zh'],global:{},languageSettings:{zh:{}}};if(body.path==='/v1/analyze/text')data={occurrences:[],stateByEntryId:{}};if(body.path==='/v1/vocabulary')data={item:{id:99}};return route.fulfill({json:data,headers:{'Access-Control-Allow-Origin':'*','Cache-Control':'no-store'}});});
 const receiver=await context.newPage();receiver.on('pageerror',e=>errors.push(e.message));await receiver.goto(base);await receiver.getByRole('heading',{name:'Your next line belongs here.'}).waitFor();
 assert.equal(await receiver.locator('#library-files').isVisible(),false);assert.equal(await receiver.locator('#report').isVisible(),false);
 for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:320,height:568},{width:844,height:390}]){await receiver.setViewportSize(viewport);assert(await receiver.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
 await receiver.setViewportSize({width:390,height:844});await receiver.screenshot({path:'output/playwright/companion-'+name+'-phone.png',fullPage:true});
 await receiver.getByRole('button',{name:'Settings',exact:true}).click();await receiver.locator('input[name=key]').fill('mock-key');await receiver.locator('input[name=pass]').fill('a safe mock passphrase');await receiver.locator('input[name=confirm]').fill('a safe mock passphrase');await receiver.getByRole('button',{name:'Connect Lexirise',exact:true}).click();await receiver.getByRole('button',{name:'Lock',exact:true}).waitFor();assert.equal(writes.length,0);
 const saved=await receiver.evaluate(async()=>{const db=await new Promise(r=>{const q=indexedDB.open('proxy-mobile-library');q.onsuccess=()=>r(q.result);});const record=await new Promise(r=>{const q=db.transaction('state').objectStore('state').get('lexirise-vault');q.onsuccess=()=>r(q.result);});db.close();return {version:record.version,iterations:record.iterations,keys:Object.keys(record)};});assert.equal(saved.iterations,600000);assert(!saved.keys.includes('key'));
 await receiver.reload();await receiver.getByRole('button',{name:'Settings',exact:true}).click();await receiver.getByRole('button',{name:'Unlock',exact:true}).waitFor();assert.equal(writes.length,0);
 await receiver.locator('input[name=pass]').fill('incorrect passphrase');await receiver.getByRole('button',{name:'Unlock',exact:true}).click();await receiver.getByRole('alert').filter({hasText:'Cannot unlock'}).waitFor();
 await receiver.locator('input[name=pass]').fill('a safe mock passphrase');await receiver.getByRole('button',{name:'Unlock',exact:true}).click();await receiver.getByRole('button',{name:'Lock',exact:true}).waitFor();await receiver.getByRole('button',{name:'Lock',exact:true}).click();
 await receiver.selectOption('#source','pc');await receiver.getByRole('button',{name:'Connection',exact:true}).click();
 if(name==='webkit'&&process.platform==='win32'){
  console.log(name+': role/layout/vault verified; Windows WebKit WebRTC unavailable, transcript transport covered in other engines.');
 }else{
  const sender=await context.newPage();sender.on('pageerror',e=>errors.push(e.message));await sender.goto(base+'?pc=1');await sender.getByRole('button',{name:'Share transcript & create offer',exact:true}).waitFor();assert.equal(await sender.locator('#library-files').isVisible(),false);
  await sender.click('#start');await sender.waitForFunction(()=>document.querySelector('#outgoing').value.includes('"offer"'));
  const pair=async()=>{await receiver.fill('#incoming',await sender.inputValue('#outgoing'));await receiver.click('#apply');await receiver.waitForFunction(()=>document.querySelector('#outgoing').value.includes('"answer"'));await sender.fill('#incoming',await receiver.inputValue('#outgoing'));await sender.click('#apply');};await pair();
  await receiver.getByRole('button',{name:'Reader',exact:true}).click();await receiver.locator('.current-card').filter({hasText:'Hello, traveler. 12'}).waitFor({timeout:20000});assert.equal(await sender.evaluate(()=>window.captureRequests),0);
  assert.equal(await receiver.getByRole('button',{name:'★ Favorited',exact:true}).count(),0,'Receiver favorites do not copy PC favorites');await receiver.locator('.current-card').getByRole('button',{name:'☆ Favorite',exact:true}).click();await receiver.locator('.current-card').getByRole('button',{name:'★ Favorited',exact:true}).waitFor();
  await receiver.getByRole('button',{name:'Load older PC history'}).click();await receiver.waitForFunction(()=>document.querySelectorAll('.history-list .dialogue').length===12);assert.equal(await receiver.locator('.history-list .dialogue').count(),12);
  if(name==='chromium'){await receiver.locator('.current-card').getByRole('button',{name:'▶ Original voice'}).click();await receiver.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0);}
  const newer={...fixture[0],id:13,english:'The next chapter.',created_at:new Date(1700000020000).toISOString()};for(const socket of sockets)socket.send(JSON.stringify({type:'line',line:newer}));await receiver.locator('.current-card').filter({hasText:'The next chapter.'}).waitFor();for(const socket of sockets)socket.send(JSON.stringify({type:'line',line:newer}));await receiver.waitForTimeout(100);assert.equal(await receiver.locator('.history-list .dialogue').count(),13);
  await sender.click('#reconnect');await sender.waitForFunction(()=>JSON.parse(document.querySelector('#outgoing').value||'{}').attempt===2);await receiver.getByRole('button',{name:'Connection',exact:true}).click();await pair();await receiver.getByRole('button',{name:'Reader',exact:true}).click();await receiver.waitForTimeout(300);assert.equal(await receiver.locator('.history-list .dialogue').count(),13);
  await sender.click('#stop');await receiver.waitForFunction(()=>document.querySelector('.connection-badge').textContent.includes('Not connected'));assert.equal(await receiver.locator('.history-list .dialogue').count(),13);
  await receiver.getByRole('button',{name:'Favorites',exact:true}).click();assert.equal(await receiver.locator('.history-list .dialogue').count(),1);await sender.close();
  console.log(name+': transcript-only pairing, history pagination, local favorites, updates/deduplication, reconnect, stop and vault passed.');
 }
 assert.deepEqual(errors,[]);assert.equal(writes.length,0);await context.close();await browser.close();browser=null;
}}
finally{await browser?.close();server.close();}
