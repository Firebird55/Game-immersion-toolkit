// Authored fixtures only. The APK runs the production shared Python core and UI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';

const directory = resolve(process.argv[2] ?? 'output/android-candidate');
const output = resolve(process.argv[3] ?? 'output/android-runtime');
mkdirSync(output, {recursive: true});
const packageName = 'io.github.firebird55.gameimmersiontoolkit.debug';
const component = `${packageName}/io.github.firebird55.gameimmersiontoolkit.MainActivity`;
const adb = (...args) => execFileSync('adb', args, {encoding: 'utf8', timeout: 30_000, stdio: ['ignore', 'pipe', 'pipe']}).trim();
async function until(operation, label, timeout = 90_000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try { const result = await operation(); if (result) return result; } catch {}
    await delay(500);
  }
  throw new Error(`Android runtime did not establish ${label}`);
}
const provenance = JSON.parse(readFileSync(join(directory, 'ANDROID-PROVENANCE.json'), 'utf8'));
const apk = join(directory, 'GameImmersionToolkit-android-debug.apk');
assert.equal(createHash('sha256').update(readFileSync(apk)).digest('hex'), provenance.apk_sha256);
assert.equal(provenance.release_eligibility, false);
const expected = JSON.parse(readFileSync(join(directory, 'desktop-core-proof.json'), 'utf8'));
adb('install', '-r', apk);
// Nothing in first launch may depend on a PC, model download or hosted reader.
adb('root');adb('wait-for-device');
assert.equal(adb('shell', 'id', '-u'), '0');
// Keep root-owned ADB transport working while denying app/system-service
// egress. Bundled OCR must not acquire models through Play Services either.
adb('shell', 'iptables', '-I', 'OUTPUT', '!', '-d', '127.0.0.0/8', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'ip6tables', '-I', 'OUTPUT', '!', '-d', '::1/128', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'svc', 'wifi', 'disable');
adb('shell', 'svc', 'data', 'disable');
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitSelfTest', 'true');
const core = await until(() => JSON.parse(adb('shell', 'run-as', packageName, 'cat', 'files/android-core-proof.json')), 'authored native core/audio/OCR proof', 150_000);
assert.equal(core.result_sha256, expected.result_sha256);
assert.deepEqual(core.results, expected.results);
assert.equal(core.native_media_completed, true);
assert.equal(core.native_ocr.confirmed_text_id, 'authored:bridge');
assert.equal(core.native_ocr.original_audio_available, true);
assert.equal(core.runtime.pydantic_core, '2.50.1');
assert.equal(core.runtime.rapidfuzz, '3.14.6');
assert.match(core.runtime.fuzzy_scorer, /rapidfuzz\.fuzz_cpp/);
assert.equal(core.runtime.fuzzy_extractor, 'rapidfuzz.process_cpp_impl');
assert.ok(core.runtime.authored_fuzzy_50000_ms < 250, 'Native fuzzy lookup must remain bounded on the target');
writeFileSync(join(output, 'android-core-proof.json'), JSON.stringify(core, null, 2) + '\n');

async function connectReader() {
  const pid = await until(() => adb('shell', 'pidof', packageName).split(/\s+/)[0], 'app process');
  adb('forward', 'tcp:9222', `localabstract:webview_devtools_remote_${pid}`);
  await until(async () => (await fetch('http://127.0.0.1:9222/json/version')).ok, 'actual Android WebView CDP');
  // Android WebView owns its default context and cannot implement browser-level
  // download/context overrides. Attach without changing that existing context.
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222', {noDefaults: true});
  const page = await until(() => browser.contexts().flatMap(context => context.pages()).find(page => page.url().startsWith('http://127.0.0.1:')), 'local shared reader');
  await page.locator('.companion-shell').waitFor({timeout: 60_000});
  return {browser, page};
}
let {browser, page} = await connectReader();
const originalOrigin = new URL(page.url()).origin;
assert.equal(await page.locator('meta[name="toolkit-host-platform"]').getAttribute('content'), 'android');
const library = readFileSync(join(directory, 'authored-library.zip')).toString('base64');
const imported = await page.evaluate(async encoded => {
  const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
  const response = await fetch('/api/library/import', {method: 'POST', headers: {
    'Content-Type': 'application/zip', 'X-Toolkit-Import-Id': crypto.randomUUID()}, body: bytes});
  return {status: response.status, data: await response.json()};
}, library);
assert.equal(imported.status, 200);
assert.equal(imported.data.game, 'zzz');
await page.evaluate(async () => {
  const response = await fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({zzz_region: {left: 0, top: 0, width: 1, height: 1}, stable_frames: 2})});
  if (!response.ok) throw new Error('Authored full-frame calibration failed');
});
const generation = await page.evaluate(async () => (await (await fetch('/api/capture/start', {method: 'POST'})).json()).generation);
for (let sequence = 1; sequence <= 4; sequence++) {
  const status = await page.evaluate(async ({generation, sequence}) => {
    const canvas = document.createElement('canvas');canvas.width = 1600;canvas.height = 240;
    const context = canvas.getContext('2d');context.fillStyle = 'black';context.fillRect(0, 0, 1600, 240);
    context.fillStyle = 'white';context.font = '64px sans-serif';
    context.fillText('Follow the river beyond the bridge.', 40, 140);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    return (await fetch('/api/capture/frame', {method: 'POST', headers: {'Content-Type': 'image/png',
      'X-Toolkit-Generation': String(generation), 'X-Toolkit-Frame': String(sequence)}, body: blob})).status;
  }, {generation, sequence});
  assert.equal(status, 202);
  await delay(1200);
}
const snapshot = await until(() => page.evaluate(async () => {
  const value = await (await fetch('/api/snapshot')).json();return value.lines.length ? value : null;
}), 'native frame OCR into the actual reader transcript');
assert.equal(snapshot.lines[0].text_id, 'authored:bridge');
assert.equal(snapshot.lines[0].has_audio, true);
const lineId = snapshot.lines[0].id;
await page.evaluate(() => {
  // Observe real WebView media objects created by the production play button.
  // No fake media implementation, timing or completion signal is substituted.
  const NativeAudio = window.Audio;
  window.__toolkitObservedAudio = [];
  const ObservedAudio = function(...args) {
    const element = new NativeAudio(...args);window.__toolkitObservedAudio.push(element);return element;
  };
  ObservedAudio.prototype = NativeAudio.prototype;Object.setPrototypeOf(ObservedAudio, NativeAudio);
  window.Audio = ObservedAudio;
});
await page.getByRole('button', {name: 'Play current voice line', exact: true}).first().click();
await until(() => page.evaluate(() => window.__toolkitObservedAudio.some(audio => !audio.paused && !audio.ended)), 'actual shared reader clip playback');
adb('shell', 'input', 'keyevent', 'KEYCODE_HOME');
await delay(1200);
adb('shell', 'am', 'start', '-W', '-n', component);
assert.equal(await page.evaluate(() => window.__toolkitObservedAudio.length > 0 &&
  window.__toolkitObservedAudio.every(audio => audio.paused && !audio.getAttribute('src'))), true,
  'Backgrounding must stop and release the actual detached shared reader Audio');
await page.evaluate(async id => {
  const response = await fetch(`/api/lines/${id}/favorite`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: '{"favorite":true}'});
  if (!response.ok) throw new Error('Authored favorite failed');
  const range = await fetch(`/api/lines/${id}/audio`, {headers: {Range: 'bytes=0-43'}});
  if (range.status !== 206 || (await range.arrayBuffer()).byteLength !== 44) throw new Error('Original clip range failed');
  // Preserve the production key names. These contain no account credential.
  localStorage.setItem('proxy-transcript-reading-mode', 'lexirise');
  localStorage.setItem('proxy-transcript-playback-rate', '0.75');
  localStorage.setItem('proxy-transcript-reading-options', JSON.stringify({fontSize: 31, pinyin: 'all'}));
}, lineId);
await page.reload();
await until(() => page.locator('select[aria-label="Reading"]').inputValue().then(value => value === 'lexirise'), 'production reading mode bootstrap');
await until(() => page.locator('select[aria-label="Voice playback speed"]').inputValue().then(value => value === '0.75'), 'production playback preference');
await page.screenshot({path: join(output, 'android-shared-reader.png')});
await browser.close();
adb('shell', 'am', 'force-stop', packageName);
adb('shell', 'am', 'start', '-W', '-n', component); // No self-test rerun; actual app data must survive.
({browser, page} = await connectReader());
assert.equal(new URL(page.url()).origin, originalOrigin);
await until(() => page.locator('select[aria-label="Reading"]').inputValue().then(value => value === 'lexirise'), 'reading mode after process death');
await until(() => page.locator('select[aria-label="Voice playback speed"]').inputValue().then(value => value === '0.75'), 'playback preference after process death');
const restarted = await page.evaluate(async () => ({snapshot: await (await fetch('/api/snapshot')).json(),
  font: getComputedStyle(document.querySelector('.companion-shell')).getPropertyValue('--lexirise-font-size').trim(),
  options: JSON.parse(localStorage.getItem('proxy-transcript-reading-options'))}));
assert.equal(restarted.font, '31px');assert.equal(restarted.options.pinyin, 'all');
assert.equal(restarted.snapshot.status.capture.running, false);
assert.equal(restarted.snapshot.lines.length, 1);
assert.equal(restarted.snapshot.lines[0].favorite, true);
assert.equal(restarted.snapshot.lines[0].has_audio, true);
await browser.close();
writeFileSync(join(output, 'android-runtime-proof.json'), JSON.stringify({schema: 'toolkit-android-runtime-proof-v1',
  fixture: 'authored-text-bitmap-and-generated-tone', apk_sha256: provenance.apk_sha256,
  source_commit: provenance.source_commit, frontend_build_id: provenance.frontend_build_id,
  shared_core_identical: true, native_media_completed: true, bundled_ocr_to_transcript: true,
  shared_reader_audio_stopped_on_background: true, authored_fuzzy_50000_ms: core.runtime.authored_fuzzy_50000_ms,
  offline_process_restart: true, reader_preferences_retained: true, favorite_and_original_audio_retained: true,
  physical_device_acceptance: 'not-established', release_eligibility: false}, null, 2) + '\n');
console.log('Authored shared-core, bundled OCR, original audio and reader restart accepted on the Android emulator.');
