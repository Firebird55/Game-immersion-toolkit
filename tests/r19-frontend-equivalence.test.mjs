import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';
import test from 'node:test';
import {ORIGIN, readDesktopManifest, assertStorageContinuity, assertLayoutBounds, assertPixelComparison} from '../scripts/r19-frontend-equivalence.mjs';

// These acceptance-gate negatives are cheaper than rerunning two browser engines
// just to prove that the comparison cannot report missing state/assets as green.
test('desktop comparison refuses missing or altered built resources', t => {
  const root = mkdtempSync(join(tmpdir(), 'r19-manifest-fixture-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  const names = ['index.html', 'mobile-capture/library-worker.mjs', 'mobile-capture/ocr/tesseract.esm.min.js',
    'mobile-capture/ocr/verified-worker.js', 'mobile-capture/ocr/core/tesseract-core.wasm',
    'mobile-capture/ocr/lang/eng.traineddata.gz', 'assets/authored-font.ttf'];
  const files = {};
  for (const name of names) {
    const bytes = Buffer.from('Owned synthetic manifest fixture: ' + name);
    mkdirSync(dirname(join(root, name)), {recursive: true}); writeFileSync(join(root, name), bytes);
    files[name] = {sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length, mime: 'application/octet-stream'};
  }
  const manifest = {schema: 'proxy-desktop-frontend-v1', entry: 'index.html', routes: ['/'], build_id: 'synthetic', files};
  const save = () => writeFileSync(join(root, 'desktop-manifest.json'), JSON.stringify(manifest));
  save(); assert.equal(readDesktopManifest(root).build_id, 'synthetic');
  writeFileSync(join(root, 'assets/authored-font.ttf'), 'altered');
  assert.throws(() => readDesktopManifest(root), /size differs|checksum differs/);
  delete files['assets/authored-font.ttf']; delete files['mobile-capture/ocr/lang/eng.traineddata.gz']; save();
  assert.throws(() => readDesktopManifest(root), /required self-hosted resource/);
});

test('browser continuity needs the actual OPFS bytes and IndexedDB record, not only localStorage', () => {
  const expected = {sentinel: 'owned fixture', record: {favorite: true}, opfs: 'owned bytes', mode: 'lexirise', playback: '0.75'};
  const complete = {origin: ORIGIN, ...expected};
  assert.doesNotThrow(() => assertStorageContinuity(complete, expected));
  assert.throws(() => assertStorageContinuity({...complete, opfs: ''}, expected), /OPFS bytes/);
  assert.throws(() => assertStorageContinuity({...complete, record: undefined}, expected), /IndexedDB state/);
  assert.throws(() => assertStorageContinuity({...complete, origin: 'http://localhost:3000'}, expected), /origin changed/);
});

test('independent geometry and pixel limits reject clipped, overlapping and visibly changed pages', () => {
  const metrics = {viewportWidth: 800, documentWidth: 800, shell: {x: 0, y: 0, width: 800, height: 720},
    current: {x: 20, y: 200, width: 760, height: 200}, translation: {x: 40, y: 230, width: 720, height: 32},
    source: {x: 40, y: 280, width: 720, height: 46}, actions: {x: 40, y: 340, width: 720, height: 36},
    sourceLineCount: 1, translationLineCount: 1, sourceFontSize: 32, fontsLoaded: true, localFontCount: 2};
  assert.doesNotThrow(() => assertLayoutBounds(metrics));
  assert.throws(() => assertLayoutBounds({...metrics, source: {...metrics.source, y: 240}}), /overlap/);
  assert.throws(() => assertLayoutBounds({...metrics, documentWidth: 900}), /overflow/);
  assert.throws(() => assertLayoutBounds({...metrics, localFontCount: 0}), /fonts/);
  assert.doesNotThrow(() => assertPixelComparison({sameSize: true, changedRatio: .001, meanDelta: .1}));
  assert.throws(() => assertPixelComparison({sameSize: false, changedRatio: 0, meanDelta: 0}), /dimensions/);
  assert.throws(() => assertPixelComparison({sameSize: true, changedRatio: .2, meanDelta: .1}), /pixel ratio/);
  assert.throws(() => assertPixelComparison({sameSize: true, changedRatio: .001, meanDelta: 2}), /mean pixel/);
});
