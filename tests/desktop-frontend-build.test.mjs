import assert from 'node:assert/strict';
import {createHash, randomUUID} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import {buildDesktopFrontend, desktopBuildId, inventoryDesktopPayload, MANIFEST_NAME, safeDesktopName, verifyDesktopOutput} from '../scripts/build-desktop-frontend.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
function put(root, name, data) { const path = join(root, name); mkdirSync(dirname(path), {recursive: true}); writeFileSync(path, data); return path; }
function fixture(t) { const path = realpathSync(mkdtempSync(join(tmpdir(), 'desktop-build-'))); t.after(() => rmSync(path, {recursive: true, force: true})); return path; }

// The source build tests always serve a Worker. These cases prevent accepting
// undeclared/private assets or an altered static directory as a frozen payload.
test('portable names and canonical manifest identity reject unsafe output', t => {
  for (const name of ['../data.db', '/index.html', 'assets\\app.js', 'assets/x.js:stream', 'assets/CON.txt', 'assets/font.ttf.', 'assets/./app.js', 'assets/漢字.js']) {
    assert.throws(() => safeDesktopName(name), /Unsafe/);
  }
  const directory = fixture(t);
  put(directory, 'index.html', '<p>fixture</p>');
  put(directory, 'assets/app-12345678.js', 'export {};');
  const files = inventoryDesktopPayload(directory);
  const canonical = JSON.stringify(Object.fromEntries(Object.keys(files).sort().map(name => [name, {bytes: files[name].bytes, mime: files[name].mime, sha256: files[name].sha256}])));
  assert.equal(desktopBuildId(files), sha256(canonical));
  const manifest = {schema: 'proxy-desktop-frontend-v1', entry: 'index.html', routes: ['/'], source_commit: 'a'.repeat(40),
    source_fingerprint: 'b'.repeat(64), lock_sha256: 'c'.repeat(64), frontend_origin: 'http://127.0.0.1:3000',
    api_base: 'http://127.0.0.1:8766', websocket_url: 'ws://127.0.0.1:8766/api/ws', files, build_id: desktopBuildId(files)};
  put(directory, MANIFEST_NAME, JSON.stringify(manifest));
  assert.equal(verifyDesktopOutput(directory).build_id, manifest.build_id);
  put(directory, 'assets/app-12345678.js', 'changed');
  assert.throws(() => verifyDesktopOutput(directory), /exact manifest/);
  put(directory, 'data/private.db', 'must not ship');
  assert.throws(() => inventoryDesktopPayload(directory), /Unreviewed/);
});

test('empty directories and linked assets cannot enter the static inventory', t => {
  const empty = fixture(t);
  put(empty, 'index.html', '<p>fixture</p>');
  mkdirSync(join(empty, 'data'));
  assert.throws(() => inventoryDesktopPayload(empty), /directory/);
  const linked = fixture(t);
  put(linked, 'index.html', '<p>fixture</p>');
  put(linked, 'outside.txt', 'outside');
  mkdirSync(join(linked, 'assets'));
  try { symlinkSync(join(linked, 'outside.txt'), join(linked, 'assets/linked.js')); }
  catch (error) { if (['EPERM', 'EACCES'].includes(error.code)) return; throw error; }
  assert.throws(() => inventoryDesktopPayload(linked), /links/);
});

test('intentional CSR build is self-contained, pinned, inventoried and reused only while unchanged', async t => {
  const outputDirectory = join(root, 'output/desktop-build-test-' + randomUUID());
  t.after(() => rmSync(outputDirectory, {recursive: true, force: true}));
  const result = await buildDesktopFrontend({outputDirectory});
  const manifest = verifyDesktopOutput(outputDirectory);
  assert.equal(manifest.runtime, 'static-local-no-node');
  assert.equal(manifest.desktop_service_worker, false);
  assert.equal(manifest.browser_profile, 'existing-selected-profile');
  assert.equal(manifest.files['index.html'].mime, 'text/html; charset=utf-8');
  const html = readFileSync(join(outputDirectory, 'index.html'), 'utf8');
  assert.match(html, /<div id="root"><\/div>/);
  assert.match(html, /src="\/assets\/[^"/]+\.js"/);
  assert.doesNotMatch(html, /main\.tsx|wrangler|\/node_modules\//);
  for (const name of ['mobile-capture/library-worker.mjs', 'mobile-capture/ocr/core/tesseract-core.wasm',
    'mobile-capture/ocr/lang/chi_sim.traineddata.gz', 'mobile-capture/pairing/fflate.mjs', 'proxy-transcript.png',
    'notices/GEIST-OFL.txt', 'notices/THIRD_PARTY_LICENSES.txt']) assert(manifest.files[name], 'Required served resource: ' + name);
  assert(Object.keys(manifest.files).some(name => name.startsWith('_next/static/') && name.endsWith('.js')));
  assert(Object.keys(manifest.files).every(name => !name.endsWith('.map') && !name.endsWith('.py') && !name.startsWith('node_modules/')));
  for (const font of Object.values(manifest.fonts.files)) assert(Object.entries(manifest.files).some(([name, item]) => name.startsWith('assets/') && name.endsWith('.ttf') && item.sha256 === font.sha256));
  assert.equal(manifest.lock_sha256, sha256(readFileSync(join(root, 'package-lock.json'))));
  assert(!JSON.stringify(manifest).includes(root), 'Public manifest must not contain the build checkout path.');
  const repeated = await buildDesktopFrontend({outputDirectory});
  assert.equal(repeated.reused, true);
  assert.equal(repeated.manifest.build_id, result.manifest.build_id);
  const alteredMetadata = {...manifest, source_fingerprint: '0'.repeat(64)};
  put(outputDirectory, MANIFEST_NAME, JSON.stringify(alteredMetadata));
  const repairedMetadata = await buildDesktopFrontend({outputDirectory});
  assert.equal(repairedMetadata.reused, false, 'An altered source identity cannot reuse an otherwise unchanged payload.');
  assert.equal(repairedMetadata.manifest.source_fingerprint, manifest.source_fingerprint);
  if (repairedMetadata.retainedDirectory) rmSync(repairedMetadata.retainedDirectory, {recursive: true, force: true});
  const chunk = Object.keys(manifest.files).find(name => name.startsWith('assets/') && name.endsWith('.js'));
  put(outputDirectory, chunk, 'modified');
  assert.throws(() => verifyDesktopOutput(outputDirectory), /exact manifest/);
  assert(existsSync(join(outputDirectory, MANIFEST_NAME)), 'Rejected output is retained for recovery.');
});
