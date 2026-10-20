import assert from 'node:assert/strict';
import http from 'node:http';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {chromium,firefox} from 'playwright';
const bytes=Buffer.from('Synthetic OCR model transport fixture');
const model={bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),url:'./fixture.gz',builtin:false};
let downloads=0,broken=false;
const server=http.createServer((req,res)=>{
 const name=new URL(req.url,'http://localhost').pathname.slice(1);
 if(!name){res.setHeader('Content-Type','text/html');return res.end('<!doctype html><title>OCR storage test</title>');}
 if(name==='ocr-models.json'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify({models:{nld:model},locales:{nl:'nld'}}));}
 if(name==='fixture.gz'){downloads++;return res.end(broken?Buffer.alloc(bytes.length):bytes);}
 if(['ocr-packs.mjs','storage.mjs'].includes(name)){res.setHeader('Content-Type','text/javascript');return res.end(readFileSync('public/mobile-capture/'+name));}
 res.writeHead(404).end();
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 for(const [name,engine] of [['chromium',chromium],['firefox',firefox]]){
  browser=await engine.launch();const context=await browser.newContext(),page=await context.newPage();
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.evaluate(async()=>{window.packs=await import('./ocr-packs.mjs');window.storage=await import('./storage.mjs');await storage.put('history',[{text:'keep'}]);await storage.put('lexirise-vault',{fixture:true});});
  assert.equal(await page.evaluate(async()=>(await packs.modelStatus('nld')).installed),false);
  assert.match(await page.evaluate(async()=>{try{await packs.loadModel('nld');}catch(e){return e.message;}}),/Download/);
  const before=downloads;
  await page.evaluate(()=>packs.loadModel('nld',{download:true}));
  assert.equal(downloads,before+1);
  assert.equal(await page.evaluate(async()=>(await packs.modelStatus('nld')).storedBytes),bytes.length);
  await context.setOffline(true);
  assert.equal(await page.evaluate(async()=>(await packs.loadModel('nld')).data.length),bytes.length);
  assert.equal(downloads,before+1,'Offline reuse makes no network request');
  await page.evaluate(()=>packs.removeModel('nld'));
  assert.equal(await page.evaluate(async()=>(await packs.modelStatus('nld')).installed),false);
  assert.deepEqual(await page.evaluate(()=>storage.get('history')),[{text:'keep'}]);
  assert.deepEqual(await page.evaluate(()=>storage.get('lexirise-vault')),{fixture:true});
  await context.setOffline(false);broken=true;
  assert.match(await page.evaluate(async()=>{try{await packs.loadModel('nld',{download:true});}catch(e){return e.message;}}),/checksum/);
  assert.equal(await page.evaluate(async()=>(await packs.modelStatus('nld')).installed),false,'Corrupt downloads never become installed');
  broken=false;await context.close();await browser.close();browser=null;
  console.log(name+': explicit OCR download, verified bytes, offline reuse and isolated removal passed');
 }
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
