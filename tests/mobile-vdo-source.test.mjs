import test from 'node:test';
import assert from 'node:assert/strict';
import { createVdoFrameSource, parseVdoViewerUrl } from '../public/mobile-capture/vdo-source.mjs';

const link = 'https://vdo.ninja/?view=synthetic&p=0';
function png(width = 2, height = 2) {
 const bytes = new Uint8Array(33); bytes.set([137, 80, 78, 71, 13, 10, 26, 10]);
 const data = new DataView(bytes.buffer); data.setUint32(8, 13); data.setUint32(12, 0x49484452); data.setUint32(16, width); data.setUint32(20, height);
 return new Blob([bytes], { type: 'image/png' });
}
function fixture(options = {}) {
 const listeners = new Set(), frames = [], calls = [], decoded = [];
 const window = { Blob, addEventListener(type, listener) { if (type === 'message') listeners.add(listener); }, removeEventListener(type, listener) { if (type === 'message') listeners.delete(listener); } };
 const document = new EventTarget(); document.hidden = false;
 const container = { children: [], appendChild(frame) { this.children.push(frame); } };
 document.createElement = type => {
  if (type === 'iframe') {
   const frame = new EventTarget(); Object.assign(frame, { attributes: {}, setAttribute(key, value) { this.attributes[key] = value; }, remove() { container.children = container.children.filter(child => child !== this); }, contentWindow: { postMessage(data, origin) { calls.push({ data, origin, frame }); } } }); frames.push(frame); return frame;
  }
  const canvas = { getContext() { return { drawImage(image) { canvas.pixel = image.pixel; }, getImageData() { return { data: Uint8Array.of(canvas.pixel, 0, 0, 255) }; } }; } }; return canvas;
 };
 let pixel = 1;
 const decodeImage = options.decodeImage ?? (async () => { const image = { width: 2, height: 2, pixel: pixel++, closed: 0, close() { this.closed++; } }; decoded.push(image); return image; });
 const source = createVdoFrameSource({ container, window, document, decodeImage, requestTimeoutMs: 100, ...options });
 function emit(data, extras = {}) { for (const listener of [...listeners]) listener({ data, origin: 'https://vdo.ninja', source: frames.at(-1)?.contentWindow, ...extras }); }
 function reply(overrides = {}, extras = {}, request = calls.at(-1)?.data) { emit({ action: 'image-frame-capture', value: { imageType: 'png', imageData: png(), cib: request.cib, ...(request.UUID ? { UUID: request.UUID } : { streamID: 'synthetic' }), ...overrides } }, extras); }
 return { source, calls, frames, document, container, listeners, decoded, emit, reply };
}

test('viewer URL allowlist preserves password, room, server and route values', () => {
 const original = 'https://vdo.ninja/?view=synthetic&password=synthetic%2Btest&room=test&wss=wss.vdo.ninja%3A443&codec=h264&buffer=500';
 assert.equal(parseVdoViewerUrl(original).url, original);
 assert.equal(parseVdoViewerUrl('https://vdo.ninja/?pull=synthetic&p=0').streamId, 'synthetic');
 const whep = 'https://vdo.ninja/?whepplay=https%3A%2F%2Fde1.meshcast.io%2Fwhep%2Fsynthetic&whepplaytoken=synthetic';
 assert.equal(parseVdoViewerUrl(whep).url, whep); assert.equal(parseVdoViewerUrl(whep).route, 'whep');
 const meshcast = 'https://meshcast.io/view.html?geo=de1&id=synthetic&muted';
 const normalized = parseVdoViewerUrl(meshcast);
 assert.equal(normalized.originalUrl, meshcast);
 assert.equal(new URL(normalized.url).searchParams.get('whepplay'), 'https://de1.meshcast.io/synthetic/whep');
 assert(new URL(normalized.url).searchParams.has('muted'));
});

test('unsupported routes and endpoint interpretations fail explicitly without echoing secrets', () => {
 for (const invalid of [
  'https://evil.example/?view=test', 'http://vdo.ninja/?view=test', 'https://vdo.ninja.evil.example/?view=test',
  'https://user:synthetic@vdo.ninja/?view=test', 'https://vdo.ninja:9443/?view=test', 'https://vdo.ninja/alpha/?view=test',
  'https://vdo.ninja/?push=test', 'https://vdo.ninja/?room=test', 'https://vdo.ninja/?view=test,test2',
  'https://vdo.ninja/?view=test&view=other', 'https://vdo.ninja/?view=test&password=one&password=two',
  'https://vdo.ninja/?view=test&css=https://evil.example/', 'https://vdo.ninja/?view=test&wss=evil.example',
  'https://vdo.ninja/?view=test&whepplay=https://de1.meshcast.io/whep/test',
  'https://vdo.ninja/?whepplay=https://de1.meshcast.io.evil.example/whep/test',
  'https://vdo.ninja/?whepplay=https://de1.meshcast.io/whep/test%252Fother',
  'https://vdo.ninja/?whepplay=https://de1.meshcast.io/whep/test%3Fredirect=evil',
  'https://vdo.ninja/?whepplay=https://127.0.0.1/whep/test',
  'https://meshcast.io/?view=test', 'https://meshcast.io/view.html?id=test',
  'https://meshcast.io/view.html?geo=evil&id=test', 'https://meshcast.io/view.html?geo=de1&id=test&auth=synthetic',
  'https://meshcast.io/view.html?geo=de1&id=test&server=synthetic',
  'https://app.meshcast.io/watch/test', `${link}#synthetic`,
 ]) assert.throws(() => parseVdoViewerUrl(invalid), error => !error.message.includes('synthetic'), invalid);
});

test('strict origin, window, cib, stream and blob schema checks precede bounded decoding', async () => {
 const f = fixture(); f.source.connect({ url: link }); const waiting = f.source.readFrame();
 assert.equal(await f.source.readFrame(), null); assert.equal(f.calls.length, 1);
 f.reply({}, { origin: 'https://evil.example' }); f.reply({}, { source: {} }); f.reply({ cib: 'wrong' }); f.reply({ streamID: 'other' });
 f.emit({ action: 'image-frame-capture', value: null });
 assert.equal(f.decoded.length, 0);
 f.reply(); const frame = await waiting; assert(frame); assert.equal(frame.sequence, 1); assert.equal(f.calls[0].origin, 'https://vdo.ninja');
 assert.equal(f.source.getState().status, 'connecting');
 assert.equal(await f.source.readFrame(), null); frame.release(); frame.release(); assert.equal(f.decoded[0].closed, 1);
 const second = f.source.readFrame(); f.reply(); (await second).release(); assert.equal(f.source.getState().status, 'live');
 const iframe = f.frames[0]; assert.match(iframe.allow, /camera 'none'/); assert.equal(iframe.attributes.sandbox, 'allow-scripts allow-same-origin');
 f.source.dispose(); assert.equal(f.listeners.size, 0); assert.equal(f.container.children.length, 0);
});

test('WHEP selects only an announced official generated UUID', async () => {
 const f = fixture(); f.source.connect({ url: 'https://vdo.ninja/?whep=https://de1.meshcast.io/whep/synthetic' });
 assert.equal(await f.source.readFrame(), null);
 const UUID = `whep_${'a'.repeat(25)}`;
 f.emit({ action: 'video-element-created', UUID, value: `videosource_${UUID}` }, { source: {} }); assert.equal(await f.source.readFrame(), null);
 f.emit({ action: 'video-element-created', UUID, value: `videosource_${UUID}` });
 f.frames[0].dispatchEvent(new Event('load'));
 const waiting = f.source.readFrame(); assert.equal(f.calls.at(-1).data.UUID, UUID); f.reply(); (await waiting).release(); f.source.dispose();
});

test('timeout, abort, reconnect and visibility discard late frames and remove listeners', async () => {
 const f = fixture({ requestTimeoutMs: 15 }); f.source.connect({ url: link });
 assert.equal(await f.source.readFrame(), null); assert.equal(f.source.getState().status, 'stalled');
 const abort = new AbortController(), wait = f.source.readFrame({ signal: abort.signal }), old = f.calls.at(-1).data;
 abort.abort(); assert.equal(await wait, null); f.reply({}, {}, old); assert.equal(f.decoded.length, 0);
 const id = f.source.getState().sessionId, pending = f.source.readFrame();
 f.source.connect({ url: link }); assert.equal(await pending, null); assert.notEqual(f.source.getState().sessionId, id);
 const next = f.source.readFrame(); f.reply({}, {}, old); f.reply(); (await next).release();
 const hidden = f.source.readFrame(); f.document.hidden = true; f.document.dispatchEvent(new Event('visibilitychange'));
 assert.equal(await hidden, null); assert.equal(f.source.getState().status, 'paused'); assert.equal(f.listeners.size, 0); assert.equal(f.container.children.length, 0);
 f.source.dispose();
});

test('malformed headers, decompression bombs and oversized blobs never reach decoder', async () => {
 for (const imageData of [new Blob(['oops'], { type: 'image/png' }), png(65535, 65535), new Blob([new Uint8Array(16777217)], { type: 'image/png' }), new Blob([new Uint8Array(33)], { type: 'image/png' })]) {
  const f = fixture(); f.source.connect({ url: link }); const waiting = f.source.readFrame(); f.reply({ imageData });
  assert.equal(await waiting, null); assert.equal(f.decoded.length, 0); assert.equal(f.source.getState().status, 'reconnecting'); f.source.dispose();
 }
});

test('cancel during decode holds the single decode slot and closes late decoded resources', async () => {
 let complete; const image = { width: 2, height: 2, closed: 0, close() { this.closed++; } };
 const f = fixture({ decodeImage: () => new Promise(resolve => { complete = resolve; }) }); f.source.connect({ url: link });
 const abort = new AbortController(), waiting = f.source.readFrame({ signal: abort.signal }); f.reply();
 await new Promise(resolve => setImmediate(resolve)); assert(complete);
 abort.abort(); assert.equal(await waiting, null); assert.equal(await f.source.readFrame(), null);
 f.source.connect({ url: link }); assert.equal(await f.source.readFrame(), null);
 complete(image); await new Promise(resolve => setImmediate(resolve)); assert.equal(image.closed, 1); f.source.dispose();
});

test('iframe reload changes session identity and rejects an old cib on the same WindowProxy', async () => {
 const f = fixture(); f.source.connect({ url: link }); f.frames[0].dispatchEvent(new Event('load'));
 const id = f.source.getState().sessionId, waiting = f.source.readFrame(), old = f.calls.at(-1).data;
 f.frames[0].dispatchEvent(new Event('load')); assert.equal(await waiting, null); assert.notEqual(f.source.getState().sessionId, id);
 const fresh = f.source.readFrame(); f.reply({}, {}, old); assert.equal(f.decoded.length, 0); f.reply(); (await fresh).release(); f.source.dispose();
});

const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
test('native stop and restart on the same link reconnects automatically with one viewer', async () => {
 const f = fixture({ reconnectBaseMs: 10, reconnectMaxMs: 30 }); f.source.connect({ url: link });
 const first = f.source.readFrame(); f.reply(); (await first).release();
 const id = f.source.getState().sessionId, oldWindow = f.frames[0].contentWindow;
 const pending = f.source.readFrame(), oldRequest = f.calls.at(-1).data;
 f.emit({ action: 'view-connection', value: false, streamID: 'other' }); assert.equal(f.container.children.length, 1);
 f.emit({ action: 'view-connection', value: false, streamID: 'synthetic' });
 assert.equal(await pending, null); assert.equal(f.container.children.length, 0); assert.equal(f.source.getState().status, 'reconnecting');
 assert.notEqual(f.source.getState().sessionId, id); await sleep(20);
 assert.equal(f.container.children.length, 1); assert.equal(f.frames.length, 2);
 assert.equal(new URL(f.frames.at(-1).src).searchParams.get('view'), 'synthetic');
 assert.equal(new URL(f.frames.at(-1).src).searchParams.get('scale'), '100');
 const fresh = f.source.readFrame(); f.reply({}, { source: oldWindow }, oldRequest); assert.equal(f.decoded.length, 1);
 f.reply(); (await fresh).release(); const moving = f.source.readFrame(); f.reply(); (await moving).release();
 assert.equal(f.source.getState().status, 'live'); f.source.dispose();
});

test('frozen PNG replies cannot block recovery and repeated failures use bounded backoff', async t => {
 t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
 const f = fixture({ reconnectBaseMs: 15, reconnectMaxMs: 40, freezeReconnectMs: 45, decodeImage: async () => ({ width: 2, height: 2, pixel: 1, close() {} }) });
 t.after(() => f.source.dispose());
 f.source.connect({ url: link });
 const first = f.source.readFrame(); f.reply(); (await first).release();
 for (let i = 0; i < 3; i++) { t.mock.timers.tick(10); const repeat = f.source.readFrame(); f.reply(); assert.equal(await repeat, null); }
 t.mock.timers.tick(15); assert.equal(f.source.getState().status, 'reconnecting'); assert.equal(f.container.children.length, 0);
 t.mock.timers.tick(14); assert.equal(f.frames.length, 1);
 t.mock.timers.tick(1); assert.equal(f.frames.length, 2);
 f.frames.at(-1).dispatchEvent(new Event('error'));
 t.mock.timers.tick(29); assert.equal(f.frames.length, 2, 'Second failure waits for the doubled backoff');
 t.mock.timers.tick(1); assert.equal(f.frames.length, 3);
 f.frames.at(-1).dispatchEvent(new Event('error'));
 t.mock.timers.tick(39); assert.equal(f.frames.length, 3, 'Further failures use the maximum delay');
 t.mock.timers.tick(1); assert.equal(f.frames.length, 4);
 f.frames.at(-1).dispatchEvent(new Event('error'));
 f.source.disconnect(); const count = f.frames.length; t.mock.timers.tick(100);
 assert.equal(f.frames.length, count, 'Manual stop cancels retries'); assert.equal(f.container.children.length, 0); f.source.dispose();
});

test('timeout retries after startup grace; hide and dispose cancel queued retries', async () => {
 for (const action of ['hidden', 'dispose']) {
  const f = fixture({ requestTimeoutMs: 10, startupGraceMs: 0, reconnectBaseMs: 20 }); f.source.connect({ url: link });
  assert.equal(await f.source.readFrame(), null); assert.equal(f.source.getState().status, 'reconnecting');
  if (action === 'hidden') { f.document.hidden = true; f.document.dispatchEvent(new Event('visibilitychange')); }
  else f.source.dispose();
  await sleep(40); assert.equal(f.frames.length, 1); assert.equal(f.listeners.size, 0); assert.equal(f.container.children.length, 0); f.source.dispose();
 }
});

test('explicit viewer scale is preserved', () => {
 const f = fixture(); f.source.connect({ url: `${link}&scale=50` });
 assert.equal(new URL(f.frames[0].src).searchParams.get('scale'), '50'); f.source.dispose();
});

test('synchronous stop/dispose subscribers cannot create a viewer or retry after cleanup', async () => {
 for (const status of ['connecting', 'reconnecting']) {
  const f = fixture({ reconnectBaseMs: 10 });
  f.source.subscribe(state => { if (state.status === status) f.source.disconnect(); });
  f.source.connect({ url: link });
  if (status === 'reconnecting') f.frames[0].dispatchEvent(new Event('error'));
  assert.equal(f.source.getState().status, 'ended'); await sleep(30);
  assert.equal(f.container.children.length, 0); assert.equal(f.listeners.size, 0); assert.equal(f.source.getState().status, 'ended'); f.source.dispose();
 }
});
