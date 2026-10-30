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
window.fixtureMetrics={requests:0,replies:0,firstReplyDelayMs:750,lastBlobBytes:0,lastBlobType:null};
const canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d');
window.fixtureMode=value=>{mode=value;};
window.addEventListener('message',async event=>{
 const req=event.data;if(!req?.getVideoFrame)return;
 const requestNumber=++fixtureMetrics.requests;
 if(mode==='silent')return;
 if(mode==='moving')sequence++;
 canvas.width=mode==='portrait'?360:640;canvas.height=mode==='portrait'?640:360;
 ctx.fillStyle='rgb('+sequence+',80,90)';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.fillStyle='white';ctx.font='28px sans-serif';ctx.fillText('Screen '+sequence,20,80);
 const imageData=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
 fixtureMetrics.lastBlobBytes=imageData?.size??0;fixtureMetrics.lastBlobType=imageData?.type??null;
 const response={action:'image-frame-capture',value:{imageData,imageType:'png',cib:req.cib,...(req.UUID?{UUID:req.UUID}:{streamID:req.streamID})}};
 last=response;
 if(mode==='wrong-cib')response.value.cib='wrong';
 if(mode==='bad-schema')response.value.imageType='jpeg';
 if(mode==='delayed')await new Promise(resolve=>setTimeout(resolve,250));
 if(requestNumber===1)await new Promise(resolve=>setTimeout(resolve,fixtureMetrics.firstReplyDelayMs));
 fixtureMetrics.replies++;
 parent.postMessage(response,event.origin);
});
window.replay=()=>last&&parent.postMessage(last,'*');
window.announce=()=>parent.postMessage({action:'video-element-created',UUID:'whep_aaaaaaaaaaaaaaaaaaaaaaaaa',value:'videosource_whep_aaaaaaaaaaaaaaaaaaaaaaaaa'},'*');
window.fixtureReady=true;
</script>`;

async function connect(page, url = 'https://vdo.ninja/?view=synthetic&p=0') {
 await page.evaluate(async ({ adapter, url }) => {
  const { createVdoFrameSource } = await import(`./${adapter}`);
  window.source?.dispose();
  // Exercise the production deadlines (4 s request, 8 s stall). A 500 ms
  // test-only timeout confuses cold PNG encoding/decoding with a broken bridge.
  window.source = createVdoFrameSource({ container: document.querySelector('#viewer') });
  window.source.connect({ url });
 }, { adapter, url });
 const child = await (await page.locator('#viewer iframe').elementHandle()).contentFrame();
 await child.waitForFunction(() => window.fixtureReady === true, null, { timeout: 15000 });
 await page.waitForFunction(() => window.source.getState().status === 'reconnecting', null, { timeout: 15000 });
 return child;
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

async function requireFrame(page, child, label) {
 const frame = await read(page);
 if (frame) return frame;
 const receiver = await page.evaluate(() => {
  const state = source.getState();
  return { status: state.status, message: state.message, width: state.width, height: state.height, hidden: document.hidden, imageBitmapAvailable: typeof createImageBitmap === 'function', iframes: document.querySelectorAll('#viewer iframe').length, messages: window.bridgeMetrics };
 });
 const sender = await child.evaluate(() => ({ ready: window.fixtureReady, ...window.fixtureMetrics })).catch(() => ({ detached: true }));
 assert.fail(`${label}: no decoded frame within the production request deadline ${JSON.stringify({ receiver, sender })}`);
}

async function deterministic(name, type) {
 const browser = await type.launch({ headless: true });
 try {
  const context = await browser.newContext();
  await context.route('https://vdo.ninja/**', route => route.fulfill({ contentType: 'text/html', body: fixture }));
  const page = await context.newPage(); await page.goto(base);
  await page.evaluate(() => {
   window.bridgeMetrics = { frames: 0, pngBlobs: 0, currentWindow: 0, expectedOrigin: 0, announcements: 0 };
   addEventListener('message', event => {
    if (event.data?.action === 'video-element-created') bridgeMetrics.announcements++;
    if (event.data?.action !== 'image-frame-capture') return;
    bridgeMetrics.frames++;
    if (event.data.value?.imageData instanceof Blob && event.data.value.imageData.type === 'image/png') bridgeMetrics.pngBlobs++;
    if (event.source === document.querySelector('#viewer iframe')?.contentWindow) bridgeMetrics.currentWindow++;
    if (event.origin === 'https://vdo.ninja') bridgeMetrics.expectedOrigin++;
   });
  });
  let child = await connect(page);
  const first = await requireFrame(page, child, `${name}: initial delayed PNG`), second = await requireFrame(page, child, `${name}: second moving PNG`);
  assert.notDeepEqual(first.pixel, second.pixel);
  assert.equal(first.sessionId, second.sessionId, 'Cold frame delivery must not reconnect or replace the session');
  assert.deepEqual(await child.evaluate(() => ({ requests: fixtureMetrics.requests, replies: fixtureMetrics.replies })), { requests: 2, replies: 2 }, 'Both original requests must succeed; no retry may mask a dropped response');
  assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await child.evaluate(() => fixtureMode('frozen'));
  await requireFrame(page, child, 'Fresh stable observation during recent progress');
  await page.waitForFunction(() => source.getState().status === 'stalled');
  assert.equal(await read(page), null, 'A frozen frame cannot restore live status');
  await child.evaluate(() => fixtureMode('moving')); await requireFrame(page, child, 'Visible changes recover from a static screen');
  assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await child.evaluate(() => fixtureMode('portrait'));
  const portrait = await requireFrame(page, child, 'Portrait frame'); assert.equal(portrait.width, 360); assert.equal(portrait.height, 640);
  // Isolate the intentional request timeout from the older session's recovery
  // watchdog/startup grace. Automatic restart is exercised explicitly below.
  child = await connect(page);
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
  await requireFrame(page, child, 'Fresh connection after cancellation');
  await child.evaluate(() => fixtureMode('silent'));
  await page.evaluate(() => { window.pending = source.readFrame(); });
  const interruptedSession = await page.evaluate(() => source.getState().sessionId);
  const resumed = page.waitForEvent('framenavigated', { predicate: frame => frame !== child && frame.url().startsWith('https://vdo.ninja/'), timeout: 15000 });
  await child.evaluate(() => parent.postMessage({ action: 'view-connection', streamID: 'synthetic', value: false }, '*'));
  assert.equal(await page.evaluate(() => pending), null);
  child = await resumed;
  await child.waitForFunction(() => window.fixtureReady === true, null, { timeout: 15000 });
  assert.notEqual(await page.evaluate(() => source.getState().sessionId), interruptedSession);
  await requireFrame(page, child, 'Same-link native restart without a new Connect action');
  await requireFrame(page, child, 'Moving frame after same-link restart'); assert.equal(await page.evaluate(() => source.getState().status), 'live');
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  assert.equal(await page.locator('#viewer iframe').count(), 0); assert.equal(await read(page), null);
  await page.evaluate(() => { delete document.hidden; });
  child = await connect(page, 'https://vdo.ninja/?whepplay=https://de1.meshcast.io/whep/synthetic');
  assert.equal(await read(page), null); await child.evaluate(() => announce());
  await page.waitForFunction(() => bridgeMetrics.announcements > 0);
  await requireFrame(page, child, 'WHEP UUID selection reaches the same frame contract');
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
