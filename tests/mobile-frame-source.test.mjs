import test from 'node:test';
import assert from 'node:assert/strict';
import { createFrameLifecycle, validFrameSize } from '../public/mobile-capture/frame-source.mjs';

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
