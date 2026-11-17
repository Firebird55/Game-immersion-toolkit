import assert from 'node:assert/strict';
import test from 'node:test';
import {safeReceiverState, safeMessageMetrics} from '../scripts/android-runtime-diagnostics.mjs';

test('authored receiver diagnostics retain handoff evidence without account or frame payloads', () => {
 const privateValue = 'authored-private-value-must-not-be-serialized';
 const value = safeReceiverState({cookie: privateValue, accounts: [privateValue],
  lines: [{text_id: 'authored:bridge', source_text: privateValue}],
  status: {capture: {running: true, source_generation: 12, window_bounds: [0, 0, 1600, 240],
   last_ocr: privateValue, last_error: privateValue, viewer_url: privateValue}}});
 assert.equal(value.authored_line_present, true);
 assert.equal(value.lines, 1);
 assert.equal(value.source_generation, 12);
 assert.deepEqual(value.frame_size, [1600, 240]);
 assert.equal(value.last_ocr_present, true);
 assert.equal(value.last_ocr_matches_fixture, false);
 assert.equal(JSON.stringify(value).includes(privateValue), false);
});

test('third-party frame globals cannot inject text through numeric message metrics', () => {
 const value = safeMessageMetrics({requests: 3, received_frames: 2, png_blobs: 2,
  csp_violations: 'authored-private-value', private_url: 'authored-private-value'});
 assert.deepEqual(value, {requests: 3, received_frames: 2, png_blobs: 2, csp_violations: null});
 assert.equal(safeReceiverState(null).source_generation, null);
 assert.equal(safeMessageMetrics({requests: Infinity}).requests, null);
});
