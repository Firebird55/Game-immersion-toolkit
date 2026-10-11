// Read-only local verification using the owner's private two-line exports.
// CI uses synthetic media instead. No voice files are served or uploaded.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
import {openZip,readCatalog} from '../public/mobile-capture/library.mjs';
import {ocrAssets,mime} from './mobile-assets.mjs';
const allowed=new Set(['index.html','capture.js','core.mjs','style.css','library.mjs','library-worker.mjs','mobile-ui.mjs','ocr-pipeline.mjs','storage.mjs','manifest.webmanifest','icon.svg','icon.png']);
const root=resolve(process.env.MOBILE_PRIVATE_EXPORT_ROOT??'output/mobile-library-voice-check'),assets=ocrAssets(),server=http.createServer((req,res)=>{const path=new URL(req.url,'http://localhost').pathname,name=path==='/'?'index.html':path.slice(1);try{if(!allowed.has(name)&&!assets.has(name))throw Error();const bytes=assets.get(name)??readFileSync(resolve('public/mobile-capture',name));res.setHeader('Content-Type',mime(name));res.end(bytes);}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{browser=await chromium.launch({headless:true});for(const game of ['nte','honkai3','pragmata','cyberpunk','witcher3','wuwa']){
 const pointer=JSON.parse(readFileSync(resolve(root,game,'latest.json'))),folder=resolve(root,game,pointer.revision),paths=readdirSync(folder).filter(n=>n.endsWith('.zip')).map(n=>resolve(folder,n)),catalog=await readCatalog(await openZip(new File([readFileSync(resolve(folder,game+'.catalog.zip'))],'catalog.zip'))),row=catalog.rows[0];
 const context=await browser.newContext(),page=await context.newPage();await page.goto('http://127.0.0.1:'+server.address().port);await page.setInputFiles('#library-files',paths);await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('Audio packs are open.'));if(row.playerVoice)await page.selectOption('#player-voice',row.playerVoice);await page.fill('#find-text',row.english);await page.click('#find-line');await page.getByRole('button',{name:'Play original voice',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#voice-player').currentTime>0);const duration=await page.evaluate(()=>document.querySelector('#voice-player').duration);assert(duration>0&&Number.isFinite(duration));console.log(`${game}: verified private ZIP/MP3 round trip and original playback (${duration.toFixed(2)} s)`);await context.close();
 }}finally{await browser?.close();await new Promise(r=>server.close(r));}
