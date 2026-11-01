import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve, sep } from 'node:path';
import {createHash} from 'node:crypto';
import {zipSync,strToU8} from 'fflate';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {pairingMessage} from '../public/mobile-capture/core.mjs';
import {verifyPreviewAssets} from './mobile-publication.mjs';
const { chromium, firefox, webkit } = await import(process.env.PLAYWRIGHT_MODULE_PATH ? pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href : 'playwright');

const root = process.env.MOBILE_PREVIEW_DIR ? pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR) + sep) : new URL('../public/mobile-capture/', import.meta.url);
const files = new Map(readdirSync(root).map(name => [`/${name}`, name]));
const ocr=ocrAssets();
files.set('/', 'index.html');
const expectedBuild = files.has('/build.json') ? JSON.parse(readFileSync(new URL('build.json', root), 'utf8')) : null;
const server = http.createServer((req, res) => {
  const file = files.get(new URL(req.url, 'http://localhost').pathname);
  const extra=ocr.get(new URL(req.url,'http://localhost').pathname.slice(1));
  if (!file&&!extra) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', mime(file??req.url));
  res.end(extra??readFileSync(new URL(file, root)));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
const qrModule=[...files.keys()].find(path=>/^\/qr-pairing(?:\.[a-f0-9]+)?\.mjs$/.test(path));
const captureModule=[...files.keys()].find(path=>/^\/capture(?:\.[a-f0-9]+)?\.js$/.test(path));
mkdirSync('output/playwright', { recursive: true });
const libraryId='a'.repeat(64),libraryRow={id:libraryId,textId:'reconnect-check',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:libraryId,audio:null,channels:['dialogue']},libraryRows=strToU8(JSON.stringify(libraryRow)+'\n');
const reconnectLibrary=Buffer.from(zipSync({'manifest.json':strToU8(JSON.stringify({format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic reconnect verification',revision:libraryId,coverage:{dialogue:1},catalog:[{name:'catalog/00000.ndjson',size:libraryRows.length,sha256:createHash('sha256').update(libraryRows).digest('hex')}],packs:[]})),'catalog/00000.ndjson':libraryRows},{level:0}));
async function verifyQrRendering(page){
  await page.getByRole('heading',{name:'Game immersion toolkit',exact:true}).waitFor();
  const text=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:90},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n')},'zzz',{sessionId:'qr-render-session-fixture',pairingId:'qr-render-pairing-fixture',attempt:1});
  await page.evaluate(message=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message}})),text);
  await page.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  assert.equal(await page.locator('#pairing-qr').getAttribute('data-total'),'1');
  assert(await page.locator('#qr-pause').isDisabled());
  const decoded=await page.evaluate(async modulePath=>{
    const {default:jsQR}=await import('./pairing/jsqr.mjs'),{PairingQrReader}=await import(modulePath);
    const canvas=document.querySelector('#pairing-qr'),pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height);
    const code=jsQR(pixels.data,canvas.width,canvas.height);if(!code)throw Error('Rendered QR could not decode');
    return (await new PairingQrReader().accept(code.data,'offer')).message;
  },qrModule);
  assert.equal(decoded,text);
  await page.click('#qr-enlarge');
  for(const viewport of [{width:390,height:844},{width:320,height:568},{width:568,height:320}]){
    await page.setViewportSize(viewport);
    assert(await page.locator('#qr-large-dialog').evaluate(d=>d.open&&d.scrollWidth<=d.clientWidth+1));
    const box=await page.locator('#pairing-qr').boundingBox();assert(box&&box.width>200&&box.height>200);
  }
  await page.click('#qr-enlarge');await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:''}})));
}
async function transferQr(source,target){
  await source.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  assert.equal(await source.locator('#pairing-qr').getAttribute('data-total'),'1','Typical real WebRTC offers and replies use one static compact QR');
  await source.click('#qr-enlarge');
  assert(await source.locator('#qr-large-dialog').evaluate(d=>d.open));
  for(const viewport of [{width:390,height:844},{width:320,height:568},{width:568,height:320}]){
    await source.setViewportSize(viewport);
    assert(await source.locator('#qr-large-dialog').evaluate(d=>d.scrollWidth<=d.clientWidth+1),'Large QR fits portrait and landscape without horizontal scrolling');
    const box=await source.locator('#pairing-qr').boundingBox();assert(box&&box.width>200&&box.height>200,'Large QR remains usable on a small phone');
  }
  await source.setViewportSize({width:390,height:844});
  const portrait=await source.locator('#role').inputValue()==='receiver';
  await target.evaluate(portrait=>{
    const canvas=document.createElement('canvas');canvas.width=portrait?1080:1920;canvas.height=portrait?1920:1080;window.syntheticQrCamera=canvas;
    navigator.mediaDevices.getUserMedia=async()=>{const stream=canvas.captureStream(10);window.syntheticCameraTracks=stream.getTracks();return stream;};
  },portrait);
  await target.click('#scan-pairing');
  const expected=await source.locator('#outgoing').inputValue();let complete=false;
  for(let i=0;i<50;i++){
    const image=await source.evaluate(()=>document.querySelector('#pairing-qr').toDataURL());
    if(i===20)assert((await target.locator('#qr-feedback').textContent()).includes('Use Larger QR'),'An unreadable small image gives camera-distance recovery guidance');
    await target.evaluate(async({url,size})=>{const image=new Image();image.src=url;await image.decode();const canvas=window.syntheticQrCamera,context=canvas.getContext('2d');context.fillStyle='#bbb';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,(canvas.width-size)/2,(canvas.height-size)/2,size,size);},{url:image,size:i<20?320:512});
    await target.waitForTimeout(200);
    if(await target.locator('#incoming').inputValue()===expected||await target.locator('#qr-feedback').textContent().then(v=>v.includes('Pairing QR read.'))){complete=true;break;}
  }
  if(!complete)console.error('QR scan diagnostics',await target.evaluate(()=>{const v=document.querySelector('#qr-camera');return {hidden:document.hidden,panelHidden:document.querySelector('#qr-scan-panel').hidden,width:v.videoWidth,height:v.videoHeight,time:v.currentTime,ready:v.readyState};}),await source.evaluate(async()=>{const {default:jsQR}=await import('./pairing/jsqr.mjs'),source=document.querySelector('#pairing-qr'),read=size=>{const c=document.createElement('canvas');c.width=c.height=size;const x=c.getContext('2d');x.drawImage(source,0,0,size,size);return !!jsQR(x.getImageData(0,0,size,size).data,size,size);};return {native:read(source.width),small:read(320),larger:read(384)};}));
  assert(complete,'The camera reads the complete pairing QR: '+await target.locator('#qr-feedback').textContent());
  assert(await target.evaluate(()=>window.syntheticCameraTracks.every(track=>track.readyState==='ended')),'Camera stops after reading the pairing message');
  await source.click('#qr-enlarge');
  assert(await source.locator('#qr-large-dialog').evaluate(d=>!d.open));
}
async function verifyPartialScan(source,target){
  const message=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:500},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n')},'zzz',{sessionId:'partial-session-fixture',pairingId:'partial-pairing-fixture',attempt:1});
  await source.evaluate(message=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message}})),message);
  await source.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  const total=Number(await source.locator('#pairing-qr').getAttribute('data-total'));assert(total>1);
  await source.click('#qr-pause');
  await target.evaluate(()=>{
    const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;window.syntheticQrCamera=canvas;
    navigator.mediaDevices.getUserMedia=async()=>{const stream=canvas.captureStream(10);window.syntheticCameraTracks=stream.getTracks();return stream;};
    document.querySelector('#apply').addEventListener('click',event=>{event.stopImmediatePropagation();},{capture:true,once:true}); // This transport-only fixture is not real SDP.
  });
  const show=async()=>{const image=await source.locator('#pairing-qr').evaluate(c=>c.toDataURL());await target.evaluate(async url=>{const image=new Image();image.src=url;await image.decode();const canvas=window.syntheticQrCamera,ctx=canvas.getContext('2d');ctx.fillStyle='#bbb';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,448,168,384,384);},image);};
  await target.click('#scan-pairing');await show();
  await target.waitForFunction(()=>document.querySelector('#qr-feedback').textContent.startsWith('Read 1 of '));
  assert((await target.locator('#qr-feedback').textContent()).includes('Still need QR 2'));
  await target.click('#stop-scan');assert((await target.locator('#qr-feedback').textContent()).includes('1 of '+total+' frames kept'));
  await target.click('#scan-pairing');await show();
  await target.waitForFunction(()=>document.querySelector('#qr-feedback').textContent.startsWith('Read 1 of '));
  const held=await source.locator('#pairing-qr').getAttribute('data-frame');await source.waitForTimeout(3200);
  assert.equal(await source.locator('#pairing-qr').getAttribute('data-frame'),held,'Paused QR stays still long enough for camera focus');
  for(let i=2;i<=total;i++){
    await source.click('#qr-next');await show();
    if(i<total)await target.waitForFunction(n=>document.querySelector('#qr-feedback').textContent.startsWith(`Read ${n} of `),i);
  }
  await target.waitForFunction(message=>document.querySelector('#incoming').value===message,message);
  assert(await target.evaluate(()=>window.syntheticCameraTracks.every(t=>t.readyState==='ended')));
  for(const page of [source,target])await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:''}})));
}
let browser;
try{
 for(const [name,engine] of [['chromium',chromium],['firefox',firefox],['webkit',webkit]]){
  browser=await engine.launch({headless:true});const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  await page.goto(url);await page.getByRole('heading',{name:'Game immersion toolkit',exact:true}).waitFor();
  assert.equal(await page.locator('.companion-nav > button').allTextContents().then(v=>v.join(',')),'Play,Settings');
  await page.getByText('Connect to desktop',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Open desktop transcript'}).isVisible(),false,'Connection form stays collapsed until requested');
  assert.equal(await page.locator('#frame-source,#preview,#resume-share').count(),0,'Browser screen pairing UI is removed');
  assert(!requests.some(v=>/pc-connection|qr-ui/.test(v)),'PC pairing is not loaded on Play');
  await page.click('#ocr-start');await page.waitForFunction(()=>document.querySelector('#match-status').textContent.includes('Library ZIP first'));
  await page.locator('details').filter({has:page.locator('#vdo-connect')}).locator('summary').click();await page.fill('#vdo-url','https://untrusted.example/?view=fixture');await page.click('#vdo-connect');
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent!== 'Paste a viewer link, then tap Start playing.');
  assert.equal(await page.locator('#vdo-viewer iframe').count(),0,'Invalid viewer origins cannot connect');
  for(const viewport of [{width:320,height:568},{width:390,height:844},{width:844,height:390}]){
   await page.setViewportSize(viewport);
   for(const zoom of [1,1.5,2]){
    await page.evaluate(zoom=>document.documentElement.style.zoom=String(zoom),zoom);
    const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert(layout.scroll<=layout.width+1,`${name}: Play fits phone and zoom ${JSON.stringify(layout)}`);
   }
  }
  await page.evaluate(()=>document.documentElement.style.zoom='1');await page.setViewportSize({width:390,height:844});
  await page.reload();await page.getByRole('button',{name:'Open library',exact:true}).waitFor();await page.screenshot({path:`output/playwright/mobile-play-${name}.png`,fullPage:true});
  await page.getByRole('button',{name:'Settings',exact:true}).click();await page.selectOption('#source','pc');
  await page.waitForFunction(()=>typeof document.querySelector('#scan-pairing').onclick==='function'&&typeof document.querySelector('#apply').onclick==='function');
  assert(requests.some(v=>/pc-connection/.test(v)),'Paired PC loads on demand');
  const legacy=pairingMessage({type:'offer',sdp:'v=0\r\nfixture'},'zzz');
  if(await page.locator('#apply').isEnabled()){await page.fill('#incoming',legacy);await page.click('#apply');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Screen pairing has been removed'));}
  else assert.match(await page.locator('#status').textContent(),/unavailable/);
  await verifyQrRendering(page);
  if(name!=='webkit'){
   const other=await context.newPage();await other.goto(url);await other.getByRole('heading',{name:'Game immersion toolkit',exact:true}).waitFor();await other.getByRole('button',{name:'Settings',exact:true}).click();await other.selectOption('#source','pc');await other.waitForFunction(()=>typeof document.querySelector('#scan-pairing').onclick==='function');
   await verifyPartialScan(page,other);await other.close();
  }
  assert.deepEqual(errors,[]);await context.close();await browser.close();browser=null;
  console.log(`${name}: streamlined Play, mobile zoom, VDO URL rejection, no browser capture, lazy PC pairing and QR rendering passed`);
 }
 if(expectedBuild)verifyPreviewAssets(root);
}finally{await browser?.close();await new Promise(r=>server.close(r));}
