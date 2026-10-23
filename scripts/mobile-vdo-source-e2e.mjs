import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium, firefox, webkit } = await import(process.env.PLAYWRIGHT_MODULE_PATH ? pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href : 'playwright');
const root = process.env.MOBILE_PREVIEW_DIR ? pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR) + sep) : new URL('../public/mobile-capture/', import.meta.url);
const files = readdirSync(root), adapter = files.find(name => /^vdo-source(?:\.[a-f0-9]+)?\.mjs$/.test(name));
assert(adapter, 'The published receiver must contain its reviewed VDO adapter');
const server = http.createServer((request, response) => {
 const name = new URL(request.url, 'http://localhost').pathname.slice(1);
 if (!name) { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><div id="viewer"></div>'); return; }
 if (!files.includes(name) || !name.endsWith('.mjs')) { response.writeHead(404); response.end(); return; }
 response.setHeader('Content-Type', 'text/javascript'); response.end(readFileSync(new URL(name, root)));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}/`;

// Exact hosted getVideoFrame shape. Real cross-origin WindowProxy + structured
// Blob cloning + browser PNG decoding; no VDO network or account in normal CI.
const fixture = `<!doctype html><canvas width="640" height="360"></canvas><script>
let sequence=0, mode='moving', last=null;
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
window.fixtureMode=value=>{mode=value;};
window.addEventListener('message',async event=>{
 const req=event.data;if(!req?.getVideoFrame)return;
 if(mode==='silent')return;
 if(mode==='moving')sequence++;
 canvas.width=mode==='portrait'?360:640;canvas.height=mode==='portrait'?640:360;
 ctx.fillStyle='rgb('+sequence+',80,90)';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.fillStyle='white';ctx.font='28px sans-serif';ctx.fillText('Screen '+sequence,20,80);
 const imageData=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
 const response={action:'image-frame-capture',value:{imageData,imageType:'png',cib:req.cib,...(req.UUID?{UUID:req.UUID}:{streamID:req.streamID})}};
 last=response;
 if(mode==='wrong-cib')response.value.cib='wrong';
 if(mode==='bad-schema')response.value.imageType='jpeg';
 if(mode==='delayed')await new Promise(resolve=>setTimeout(resolve,250));
 parent.postMessage(response,event.origin);
});
window.replay=()=>last&&parent.postMessage(last,'*');
window.announce=()=>parent.postMessage({action:'video-element-created',UUID:'whep_aaaaaaaaaaaaaaaaaaaaaaaaa',value:'videosource_whep_aaaaaaaaaaaaaaaaaaaaaaaaa'},'*');
</script>`;

async function connect(page, url = 'https://vdo.ninja/?view=synthetic&p=0') {
 await page.evaluate(async ({ adapter, url }) => {
  const { createVdoFrameSource } = await import(`./${adapter}`);
  window.source?.dispose();
  window.source = createVdoFrameSource({ container: document.querySelector('#viewer'), requestTimeoutMs: 500, stallAfterMs: 600, reconnectBaseMs: 50, reconnectMaxMs: 200 });
  window.source.connect({ url });
 }, { adapter, url });
 await page.waitForFunction(() => window.source.getState().status === 'reconnecting');
 return page.frames().find(frame => frame.url().startsWith('https://vdo.ninja/'));
}
async function read(page) {
 return page.evaluate(async () => {
  const frame = await window.source.readFrame(); if (!frame) return null;
  try {
   const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
   const context = canvas.getContext('2d'); context.drawImage(frame.image, 0, 0);
   return { sessionId: frame.sessionId, sequence: frame.sequence, width: frame.width, height: frame.height, pixel: [...context.getImageData(0, 0, 1, 1).data] };
  } finally { frame.release(); }
 });
}

async function deterministic(name, type) {
 const browser = await type.launch({ headless: true });
 try {
  const context = await browser.newContext();
  await context.route('https://vdo.ninja/**', route => route.fulfill({ contentType: 'text/html', body: fixture }));
  const page = await context.newPage(); await page.goto(base);
  let child = await connect(page);
  const first = await read(page), second = await read(page);
  assert(first && second, `${name}: decoded frames arrive`); assert.notDeepEqual(first.pixel, second.pixel);
  assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await child.evaluate(() => fixtureMode('frozen'));
  assert(await read(page), 'A fresh stable observation can confirm OCR during recent progress');
  await page.waitForFunction(() => source.getState().status === 'stalled');
  assert.equal(await read(page), null, 'A frozen frame cannot restore live status');
  await child.evaluate(() => fixtureMode('moving')); assert(await read(page));
  assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await child.evaluate(() => fixtureMode('portrait'));
  const portrait = await read(page); assert.equal(portrait.width, 360); assert.equal(portrait.height, 640);
  await child.evaluate(() => fixtureMode('silent'));
  await page.evaluate(() => { window.pending = source.readFrame(); });
  // A message from the parent window (wrong source and origin) must be ignored.
  await page.evaluate(() => window.postMessage({ action: 'image-frame-capture', value: { cib: 'forged' } }, '*'));
  assert.equal(await page.evaluate(() => source.readFrame()), null, 'Concurrent reads are not queued');
  assert.equal(await page.evaluate(() => pending), null, 'No matching response times out');
  await child.evaluate(() => fixtureMode('delayed'));
  await page.evaluate(() => { window.abort = new AbortController(); window.pending = source.readFrame({ signal: abort.signal }); abort.abort(); });
  assert.equal(await page.evaluate(() => pending), null);
  const oldSession = await page.evaluate(() => source.getState().sessionId);
  child = await connect(page);
  assert.notEqual(await page.evaluate(() => source.getState().sessionId), oldSession);
  assert(await read(page));
  await child.evaluate(() => fixtureMode('silent'));
  await page.evaluate(() => { window.pending = source.readFrame(); });
  const interruptedSession = await page.evaluate(() => source.getState().sessionId);
  const resumed = page.waitForEvent('framenavigated', { predicate: frame => frame !== child && frame.url().startsWith('https://vdo.ninja/'), timeout: 5000 });
  await child.evaluate(() => parent.postMessage({ action: 'view-connection', streamID: 'synthetic', value: false }, '*'));
  assert.equal(await page.evaluate(() => pending), null);
  child = await resumed;
  await child.waitForFunction(() => typeof fixtureMode === 'function');
  assert.notEqual(await page.evaluate(() => source.getState().sessionId), interruptedSession);
  assert(await read(page), 'Same-link native restart recovers without a new Connect action');
  assert(await read(page)); assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  assert.equal(await page.locator('#viewer iframe').count(), 0); assert.equal(await read(page), null);
  await page.evaluate(() => { delete document.hidden; });
  child = await connect(page, 'https://vdo.ninja/?whepplay=https://de1.meshcast.io/whep/synthetic');
  assert.equal(await read(page), null); await child.evaluate(() => announce());
  assert(await read(page), 'WHEP UUID selection reaches the same frame contract');
  await child.evaluate(() => fixtureMode('bad-schema')); assert.equal(await read(page), null);
  assert.equal(await page.evaluate(() => source.getState().status), 'reconnecting');
  await page.evaluate(() => source.dispose()); assert.equal(await page.locator('iframe').count(), 0);
  await context.close(); console.log(`${name}: VDO frame bridge, moving PNGs, bounds, stall, rotation, cancellation and cleanup passed`);
 } finally { await browser.close(); }
}

// Private, explicitly authorized device acceptance. The link is held only in
// the process environment; never print upstream errors, URLs, IDs or pixels.
async function probe() {
 if (!process.env.VDO_VIEWER_URL) throw new Error('Supply VDO_VIEWER_URL privately for device acceptance.');
 const browser = await chromium.launch({ headless: true });
 try {
  const page = await browser.newPage(); await page.goto(base);
  await page.evaluate(async ({ adapter, url }) => {
   const { createVdoFrameSource } = await import(`./${adapter}`);
   window.source = createVdoFrameSource({ container: document.querySelector('#viewer') });
   source.connect({ url });
  }, { adapter, url: process.env.VDO_VIEWER_URL });
  const duration = Math.min(180, Math.max(5, Number(process.env.VDO_PROBE_SECONDS) || 35)) * 1000;
  const started = Date.now(), deadline = started + duration;
  let frames = 0, liveObservations = 0, sessions = 0, previousSession = null, width = 0, height = 0, nextSummary = started + 5000;
  while (Date.now() < deadline) {
   const frame = await read(page);
   const state = await page.evaluate(() => ({ status: source.getState().status, sessionId: source.getState().sessionId }));
   if (state.sessionId !== previousSession) { sessions++; previousSession = state.sessionId; }
   if (frame) { frames++; width = frame.width; height = frame.height; if (state.status === 'live') liveObservations++; }
   if (Date.now() >= nextSummary) { console.log(JSON.stringify({ elapsedSeconds: Math.round((Date.now() - started) / 1000), frames, liveObservations, sessions, width, height, status: state.status })); nextSummary = Date.now() + 5000; }
   await new Promise(resolve => setTimeout(resolve, 400));
  }
  const status = await page.evaluate(() => source.getState().status);
  await page.evaluate(() => source.dispose());
  console.log(JSON.stringify({ complete: true, frames, liveObservations, sessions, width, height, status }));
 } catch (error) { console.log(JSON.stringify({ probeFailure: error.name })); process.exitCode = 1; }
 finally { await browser.close(); }
}

try {
 if (process.argv.includes('--probe')) await probe();
 else for (const name of (process.env.MOBILE_TEST_BROWSERS ?? 'chromium,firefox,webkit').split(',')) {
  const type = { chromium, firefox, webkit }[name];
  assert(type, 'MOBILE_TEST_BROWSERS must select chromium, firefox or webkit');
  await deterministic(name, type);
 }
} finally { await new Promise(resolve => server.close(resolve)); }
