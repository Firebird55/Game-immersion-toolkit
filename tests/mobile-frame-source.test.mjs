import test from 'node:test';
import assert from 'node:assert/strict';
import { createVideoFrameSource, createFrameLifecycle, validFrameSize } from '../public/mobile-capture/frame-source.mjs';

function fixture({ callbacks = false } = {}) {
 const document = new EventTarget(); document.hidden = false;
 const video = new EventTarget();
 Object.assign(video, { ownerDocument: document, videoWidth: 2, videoHeight: 2, currentTime: 0, paused: false, ended: false, readyState: 2, pixel: 1 });
 const canvases = [], pending = new Map(); let next = 0;
 document.createElement = () => {
  const canvas = { width: 0, height: 0, pixel: 0, getContext() { return { drawImage(image) { canvas.pixel = image.pixel; }, getImageData() { return { data: Uint8Array.of(canvas.pixel, 0, 0, 255) }; } }; } };
  canvases.push(canvas); return canvas;
 };
 if (callbacks) {
  video.requestVideoFrameCallback = callback => { pending.set(++next, callback); return next; };
  video.cancelVideoFrameCallback = id => pending.delete(id);
 }
 function frame(time, pixel = time) { video.currentTime = time; video.pixel = pixel; for (const [id, fn] of [...pending]) { pending.delete(id); fn(0, { mediaTime: time }); } }
 return { document, video, canvases, pending, frame };
}

test('video source owns snapshots, bounds retention, and does not own the transport', async () => {
 const f = fixture(), states = [], source = createVideoFrameSource({ video: f.video, now: () => 42 });
 f.video.srcObject = { getTracks() { throw new Error('Adapter must not access track ownership.'); } };
 f.video.play = f.video.pause = () => { throw new Error('Adapter must not control existing video.'); };
 const unsubscribe = source.subscribe(state => states.push(state));
 source.connect(); f.frame(1);
 const first = await source.readFrame();
 assert.equal(first.timestamp, 42); assert.equal(first.sequence, 1); assert.equal(first.width, 2);
 assert.equal(source.getState().status, 'connecting');
 f.frame(2); assert.equal(await source.readFrame(), null, 'A held consumer frame blocks another allocation');
 first.release(); first.release(); assert.equal(first.image.width, 1);
 const second = await source.readFrame(); assert.equal(second.sequence, 2); assert.equal(source.getState().status, 'live');
 const id = second.sessionId; source.disconnect(); assert.equal(second.image.width, 1);
 assert.equal(source.getState().status, 'ended'); source.connect(); assert.notEqual(source.getState().sessionId, id);
 unsubscribe(); source.dispose(); assert.equal(await source.readFrame(), null); assert.throws(() => source.connect(), /disposed/);
 assert(states.some(state => state.status === 'live'));
});

test('delivered but unchanged pixels never establish live status and recover on visible change', async () => {
 const f = fixture(), source = createVideoFrameSource({ video: f.video, stallAfterMs: 20 }); source.connect();
 f.frame(1, 9); (await source.readFrame()).release();
 f.frame(2, 9); assert.equal(await source.readFrame(), null);
 await new Promise(resolve => setTimeout(resolve, 30)); assert.equal(source.getState().status, 'stalled');
 f.frame(3, 10); const fresh = await source.readFrame(); assert.equal(source.getState().status, 'live'); fresh.release();
 f.frame(4, 10); const stable = await source.readFrame(); assert(stable, 'A fresh stable observation can confirm OCR during recent progress'); stable.release();
 await new Promise(resolve => setTimeout(resolve, 30)); assert.equal(source.getState().status, 'stalled');
 f.frame(5, 10); assert.equal(await source.readFrame(), null, 'Stable observations never extend live status'); source.dispose();
});

test('visibility requires a new session and real video callback after resume', async () => {
 const f = fixture({ callbacks: true }), source = createVideoFrameSource({ video: f.video }); source.connect();
 const oldCallback = [...f.pending.values()][0], id = source.getState().sessionId;
 f.document.hidden = true; f.document.dispatchEvent(new Event('visibilitychange'));
 assert.equal(source.getState().status, 'paused'); assert.equal(f.pending.size, 0);
 oldCallback(0, { mediaTime: 10 }); assert.equal(await source.readFrame(), null);
 f.document.hidden = false; f.document.dispatchEvent(new Event('visibilitychange'));
 assert.notEqual(source.getState().sessionId, id); assert.equal(await source.readFrame(), null);
 f.frame(11); const frame = await source.readFrame(); assert(frame); frame.release();
 source.dispose(); assert.equal(f.pending.size, 0);
});

test('aborted calls, paused/invalid video and ended events cannot produce frames', async () => {
 const f = fixture(), source = createVideoFrameSource({ video: f.video }); source.connect(); f.frame(1);
 const controller = new AbortController(); controller.abort(); assert.equal(await source.readFrame({ signal: controller.signal }), null);
 f.video.paused = true; assert.equal(await source.readFrame(), null); f.video.paused = false;
 f.video.videoWidth = 0; assert.equal(await source.readFrame(), null);
 f.video.dispatchEvent(new Event('ended')); assert.equal(source.getState().status, 'ended'); source.dispose();
 assert.equal(validFrameSize(1080, 1920), true); assert.equal(validFrameSize(4096, 4096), false);
});

test('4K, ultrawide and portrait captures retain aspect ratio within bounded snapshot dimensions', async () => {
 for (const [width, height] of [[3840, 2160], [7680, 2160], [2160, 3840]]) {
  const f = fixture(), source = createVideoFrameSource({ video: f.video });
  f.video.videoWidth = width; f.video.videoHeight = height; source.connect(); f.frame(1);
  const frame = await source.readFrame(); assert(frame); assert(validFrameSize(frame.width, frame.height));
  assert(Math.abs(frame.width / frame.height - width / height) < 0.002);
  assert.equal(f.video.videoWidth, width); assert.equal(f.video.videoHeight, height); frame.release(); source.dispose();
 }
});

test('a synthetic replacement uses the same consumer-owned envelope without video or VDO internals', () => {
 const state = createFrameLifecycle(); let released = 0;
 state.start();
 const frame = state.accept({ image: { synthetic: true }, width: 2, height: 2, fingerprint: 'synthetic-1', release: () => released++ });
 assert.equal(frame.image.synthetic, true); assert.equal(frame.sessionId, state.getState().sessionId);
 state.stop(); frame.release(); assert.equal(released, 1); state.dispose();
});

test('synchronous subscriber stop cannot leave a new stall timer or released frame behind', async () => {
 const lifecycle = createFrameLifecycle({ stallAfterMs: 10 });
 let stop = true, releases = 0;
 lifecycle.subscribe(state => { if (stop && state.status === 'connecting') lifecycle.stop(); });
 lifecycle.start(); await new Promise(resolve => setTimeout(resolve, 20));
 assert.equal(lifecycle.getState().status, 'ended');
 stop = false; lifecycle.start(); stop = true;
 const frame = lifecycle.accept({ image: {}, width: 1, height: 1, fingerprint: 'first', release() { releases++; } });
 assert.equal(frame, null); assert.equal(releases, 1);
 await new Promise(resolve => setTimeout(resolve, 20)); assert.equal(lifecycle.getState().status, 'ended'); lifecycle.dispose();
});
