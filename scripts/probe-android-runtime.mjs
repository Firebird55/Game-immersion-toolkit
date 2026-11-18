import {assertNativeGenshinProfile} from './android-genshin-profile-proof.mjs';
import {assertNativePublisherHash} from './android-publisher-hash-proof.mjs';
import {assertNativeZstandard} from './android-zstandard-proof.mjs';
import {assertNativePublisherCrypto} from './android-publisher-crypto-proof.mjs';
import {assertNativeWuwaBootstrap} from './android-wuwa-bootstrap-proof.mjs';
import {assertNativeZzzCatalogue} from './android-zzz-catalogue-proof.mjs';
import {waitForOwnedOriginalAudio} from './android-original-audio-readiness.mjs';
// Authored fixtures only. The APK runs the production shared Python core and UI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';
import {createAuthoredRuntimeDiagnostics, authoredReceiverLibraryReady} from './android-runtime-diagnostics.mjs';
import {nativeAccountAcceptance, verifyNativeAccountsAfterUpdate} from './android-authored-account-ui.mjs';
import {importBrowserHistoryThroughUi, verifyMigratedHistory, migrationRows} from './android-browser-migration-ui.mjs';
import {selectAuthoredAndroidDocument} from './android-authored-document-picker.mjs';
import {verifyAuthoredReaderInsets} from './android-authored-reader-insets.mjs';
import {assertNativeDataDecoder} from './android-native-decoder-proof.mjs';
import {waitForAuthoredAdbRoot} from './android-authored-adb.mjs';
import {prepareAuthoredGameData} from './android-authored-game-data-ui.mjs';

const directory = resolve(process.argv[2] ?? 'output/android-candidate');
const output = resolve(process.argv[3] ?? 'output/android-runtime');
const updateDirectory = resolve(process.argv[4] ?? 'output/android-update');
mkdirSync(output, {recursive: true});
const adb = (...args) => execFileSync('adb', args, {encoding: 'utf8', timeout: 30_000, stdio: ['ignore', 'pipe', 'pipe']}).trim();
let diagnostics = null;
async function until(operation, label, timeout = 90_000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try { const result = await operation(); if (result) return result; } catch {}
    await delay(500);
  }
  await diagnostics?.capture(label);
  throw new Error(`Android runtime did not establish ${label}`);
}
async function authoredCore(version, previousRun = null) {
  const pid = Number(await until(() => adb('shell', 'pidof', packageName).split(/\s+/)[0], 'authored app process'));
  const value = await until(() => {
    const diagnostic = JSON.parse(adb('shell', 'run-as', packageName, 'cat', 'files/android-selftest-diagnostic.json'));
    if (diagnostic.schema !== 'toolkit-android-selftest-diagnostic-v1' || diagnostic.pid !== pid
        || diagnostic.version_code !== version || diagnostic.run_id === previousRun) return null;
    if (diagnostic.state === 'failed') return {diagnostic, failed: true};
    if (diagnostic.phase !== 'complete' || diagnostic.state !== 'passed') return null;
    const core = JSON.parse(adb('shell', 'run-as', packageName, 'cat', 'files/android-core-proof.json'));
    return core.self_test_run_id === diagnostic.run_id ? {core, diagnostic} : null;
  }, 'fresh authored native core/audio/OCR proof', 150_000);
  writeFileSync(join(output, `android-selftest-version-${version}.json`), JSON.stringify(value.diagnostic, null, 2) + '\n');
  if (value.failed) throw Error(`Authored native self-test failed at ${value.diagnostic.phase}`);
  return value.core;
}
const provenance = JSON.parse(readFileSync(join(directory, 'ANDROID-PROVENANCE.json'), 'utf8'));
const packageName = provenance.application_id ?? 'io.github.firebird55.gameimmersiontoolkit.debug';
assert.ok(['io.github.firebird55.gameimmersiontoolkit.debug', 'io.github.firebird55.gameimmersiontoolkit'].includes(packageName));
const component = `${packageName}/io.github.firebird55.gameimmersiontoolkit.MainActivity`;
const apk = join(directory, 'GameImmersionToolkit-android-debug.apk');
assert.equal(createHash('sha256').update(readFileSync(apk)).digest('hex'), provenance.apk_sha256);
assert.equal(provenance.release_eligibility, false);
const update = JSON.parse(readFileSync(join(updateDirectory, 'ANDROID-PROVENANCE.json'), 'utf8'));
const updateApk = join(updateDirectory, 'GameImmersionToolkit-android-debug.apk');
assert.equal(createHash('sha256').update(readFileSync(updateApk)).digest('hex'), update.apk_sha256);
for (const field of ['source_commit', 'frontend_build_id', 'application_id', 'variant', 'signing_certificate_sha256', 'python_wheels_policy_sha256', 'native_decoder_manifest_sha256', 'publisher_source_policy_sha256']) {
  assert.ok(provenance[field], 'Both APKs must declare their actual build/signing identity');
  assert.equal(update[field], provenance[field]);
}
assert.equal(provenance.source_dirty, false);assert.equal(update.source_dirty, false);
assert.equal(update.release_eligibility, false);
assert.ok(Number.isInteger(provenance.version_code) && provenance.version_code > 0);
assert.ok(Number.isInteger(update.version_code) && update.version_code > provenance.version_code);
const expected = JSON.parse(readFileSync(join(directory, 'desktop-core-proof.json'), 'utf8'));
adb('install', '-r', apk);
const buildPolicy = JSON.parse(readFileSync(new URL('../packaging/android/build-inputs.json', import.meta.url), 'utf8'));
const deviceApi = Number(adb('shell', 'getprop', 'ro.build.version.sdk'));
const pageSize = Number(adb('shell', 'getconf', 'PAGESIZE'));
assert.ok(Number.isInteger(deviceApi) && deviceApi >= buildPolicy.min_sdk);
assert.ok([4096, 16384].includes(pageSize));
if (process.env.TOOLKIT_ANDROID_EXPECTED_API) assert.equal(deviceApi, Number(process.env.TOOLKIT_ANDROID_EXPECTED_API));
assert.match(adb('shell', 'dumpsys', 'package', packageName), new RegExp(`targetSdk=${buildPolicy.target_sdk}(?:\\s|$)`));
// Nothing in first launch may depend on a PC, model download or hosted reader.
await waitForAuthoredAdbRoot(adb, until);
adb('wait-for-device');
assert.equal(adb('shell', 'id', '-u'), '0');
// Keep root-owned ADB transport working while denying app/system-service
// egress. Bundled OCR must not acquire models through Play Services either.
adb('shell', 'iptables', '-I', 'OUTPUT', '!', '-d', '127.0.0.0/8', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'ip6tables', '-I', 'OUTPUT', '!', '-d', '::1/128', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'svc', 'wifi', 'disable');
adb('shell', 'svc', 'data', 'disable');
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitSelfTest', 'true');
const core = await authoredCore(provenance.version_code);
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
assert.equal(core.native_preview?.fixture, 'authored-native-black-bars-and-quadrants');
assert.equal(core.native_preview?.passed, true);
assert.equal(core.native_preview?.cases.length, 4);
assert.deepEqual(core.native_preview.cases.map(item => item.source), [[1600, 1200], [1600, 1200], [2400, 1080], [2400, 1080]]);
assert.ok(core.native_preview.cases.every(item => Number.isInteger(item.bytes) && item.bytes > 0 && item.bytes <= 2 * 1024 ** 2));
function assertProtectedStorage(report) {
  assert.equal(report?.fixture, 'authored-android-keystore-aes-gcm');
  for (const field of ['instance_reopened', 'tamper_rejected', 'randomized_ciphertext', 'key_nonexportable'])
    assert.equal(report[field], true);
  assert.equal(typeof report.previous_saved_blob_reopened, 'boolean');
}
assertProtectedStorage(core.native_protected_storage);
assertNativeDataDecoder(core.native_x64_decoder, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')).native_data_decoder, provenance.native_decoder_manifest_sha256);
assertNativeGenshinProfile(core.native_genshin_profile, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')), provenance, core.native_x64_decoder);
assertNativeZstandard(core.native_zstandard, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')).native_zstandard);
assertNativePublisherCrypto(core.native_publisher_crypto, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')).native_publisher_crypto, provenance);
assertNativePublisherHash(core.native_publisher_hash, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')).native_publisher_hash, provenance);
assertNativeWuwaBootstrap(core.native_wuwa_bootstrap, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')), provenance, core.native_publisher_crypto.runtime);
assertNativeZzzCatalogue(core.native_zzz_catalogue, JSON.parse(readFileSync(join(directory, 'apk-audit.json'), 'utf8')), provenance);
writeFileSync(join(output, 'android-core-proof.json'), JSON.stringify(core, null, 2) + '\n');

// Measure the normal reader in its own process after the heavy DEBUG native
// self-test. Both processes still use the same installed APK and offline rules.
adb('shell', 'am', 'force-stop', packageName);
adb('shell', 'am', 'start', '-W', '-n', component);

async function connectReader() {
  const pid = await until(() => adb('shell', 'pidof', packageName).split(/\s+/)[0], 'app process');
  adb('forward', 'tcp:9222', `localabstract:webview_devtools_remote_${pid}`);
  await until(async () => (await fetch('http://127.0.0.1:9222/json/version')).ok, 'actual Android WebView CDP');
  // Android WebView owns its default context and cannot implement browser-level
  // download/context overrides. Attach without changing that existing context.
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222', {noDefaults: true});
  const page = await until(() => browser.contexts().flatMap(context => context.pages()).find(page => page.url().startsWith('http://127.0.0.1:')), 'local shared reader');
  await page.locator('.companion-shell').waitFor({timeout: 60_000});
  diagnostics = await createAuthoredRuntimeDiagnostics(page, {output, adb, packageName, directory});
  return {browser, page};
}
// A real cross-origin iframe/WindowProxy and structured PNG Blob exercise the
// maintained receiver. The sender is authored; this is not an iOS/WebRTC claim.
const senderFixture = `<!doctype html><canvas width="1600" height="240"></canvas><script>
let sequence=0;
addEventListener('message',async event=>{
 const request=event.data;if(!request?.getVideoFrame)return;
 const canvas=document.querySelector('canvas'),context=canvas.getContext('2d');
 context.fillStyle='black';context.fillRect(0,0,1600,240);
 context.fillStyle='rgb('+(++sequence%255)+',40,80)';context.fillRect(0,0,32,32);
 context.fillStyle='white';context.font='64px sans-serif';
 context.fillText('Follow the river beyond the bridge.',40,140);
 const imageData=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
 parent.postMessage({action:'image-frame-capture',value:{imageData,imageType:'png',
  cib:request.cib,streamID:request.streamID}},event.origin);
});
</script>`;
let {browser, page} = await connectReader();
await page.route('https://vdo.ninja/**', route => route.fulfill({contentType: 'text/html', body: senderFixture}));
let originalOrigin = new URL(page.url()).origin;
assert.equal(await page.locator('meta[name="toolkit-host-platform"]').getAttribute('content'), 'android');
const normalStartup = await page.evaluate(async () => ({platform: await (await fetch('/api/platform')).json(),
  snapshot: await (await fetch('/api/snapshot')).json(), accounts: await (await fetch('/api/lexirise/accounts')).json()}));
assert.equal(normalStartup.platform.protected_accounts, true);
assert.equal(normalStartup.platform.authored_account_fixture, false);
assert.equal(normalStartup.platform.authored_game_data_fixture, false);
assert.equal(normalStartup.snapshot.lexirise.configured, false);
assert.equal(normalStartup.accounts.active, 'legacy');assert.deepEqual(normalStartup.accounts.profiles, []);
const normalAccountGeneration = normalStartup.snapshot.context.account_generation;
assert.ok(Number.isSafeInteger(normalAccountGeneration));
const insets = await verifyAuthoredReaderInsets({adb, page, until, packageName,
  report:value=>writeFileSync(join(output,'android-insets-before-restore.json'),JSON.stringify({...value,
    source_commit:provenance.source_commit,apk_sha256:provenance.apk_sha256},null,2)+'\n')});
writeFileSync(join(output, 'android-reader-insets-proof.json'), JSON.stringify({
  source_commit: provenance.source_commit, apk_sha256: provenance.apk_sha256, ...insets,
  fixture: 'authored-emulator-reader-before-personal-data', physical_device_acceptance: 'not-established',
}, null, 2) + '\n');
// Only this explicit DEBUG process installs the generated source. Normal
// startup above still used the real publisher registry and no imported data.
await browser.close();
adb('shell', 'am', 'force-stop', packageName);
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredGameData', 'true');
({browser, page} = await connectReader());
await page.route('https://vdo.ninja/**', route => route.fulfill({contentType: 'text/html', body: senderFixture}));
originalOrigin = new URL(page.url()).origin;
await prepareAuthoredGameData(page, until, {bothModes: true});
const fixtureAccountGeneration = await page.evaluate(async () => (await (await fetch('/api/snapshot')).json()).context.account_generation);
await page.evaluate(async generation => {
  const response = await fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json',
    'X-Toolkit-Account-Generation': String(generation)},
    body: JSON.stringify({region: {left: 0, top: 0, width: 1, height: 1}, stable_frames: 2})});
  if (!response.ok) throw new Error('Authored full-frame calibration failed: ' + response.status + ' ' + (await response.text()).slice(0, 512));
}, fixtureAccountGeneration);
const screenLink = page.getByLabel('Paste vdo.ninja link to start', {exact: true});
await until(() => screenLink.isEnabled(), 'actual native receiver after direct preparation');
await screenLink.fill('https://vdo.ninja/?view=authored');
const snapshot = await waitForOwnedOriginalAudio(() => page.evaluate(async () =>
  (await fetch('/api/snapshot')).json()), until, {
  accountGeneration:fixtureAccountGeneration,
  report:value => writeFileSync(join(output,'android-original-audio-readiness.json'),JSON.stringify(value,null,2)+'\n'),
});
assert.equal(snapshot.lines[0].text_id, 'authored:bridge');
assert.equal(snapshot.lines[0].has_audio, true);
assert.equal(snapshot.status.capture.running, true);
const firstGeneration = snapshot.status.capture.source_generation;
assert.ok(Number.isSafeInteger(firstGeneration));
assert.equal(await page.getByRole('button', {name: 'Stop screen', exact: true}).count(), 0);
await screenLink.fill('');
await until(() => page.evaluate(async () => !(await (await fetch('/api/snapshot')).json()).status.capture.running), 'cleared link releases actual receiver');
await screenLink.fill('https://vdo.ninja/?view=authored');
await until(() => page.evaluate(async previous => {
  const capture=(await (await fetch('/api/snapshot')).json()).status.capture;
  return capture.running && capture.source_generation > previous;
}, firstGeneration), 'fresh native scope after reconnect');
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
await page.evaluate(async ({id, generation}) => {
  const response = await fetch(`/api/lines/${id}/favorite`, {method: 'PATCH', headers: {'Content-Type': 'application/json',
    'X-Toolkit-Account-Generation': String(generation)}, body: '{"favorite":true}'});
  if (!response.ok) throw new Error('Authored favorite failed');
  const range = await fetch(`/api/lines/${id}/audio`, {headers: {Range: 'bytes=0-43'}});
  if (range.status !== 206 || (await range.arrayBuffer()).byteLength !== 44) throw new Error('Original clip range failed');
  // Preserve the production key names. These contain no account credential.
  localStorage.setItem('proxy-transcript-reading-mode', 'lexirise');
  localStorage.setItem('proxy-transcript-playback-rate', '0.75');
  localStorage.setItem('proxy-transcript-reading-options', JSON.stringify({fontSize: 31, pinyin: 'all'}));
}, {id: lineId, generation: snapshot.context.account_generation});
await page.reload();
assert.equal(await page.getByLabel('Paste vdo.ninja link to start', {exact: true}).inputValue(), '', 'Viewer links must not survive document reload');
await page.getByRole('button', {name: 'Connect Lexirise', exact: true}).waitFor();
assert.equal(await page.getByRole('combobox', {name: 'Reading', exact: true}).count(), 0);
await until(() => page.locator('select[aria-label="Voice playback speed"]').inputValue().then(value => value === '0.75'), 'production playback preference');
await page.screenshot({path: join(output, 'android-shared-reader.png')});
await browser.close();
adb('shell', 'am', 'force-stop', packageName);
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredGameData', 'true'); // No self-test rerun; actual app data must survive.
({browser, page} = await connectReader());
assert.equal(new URL(page.url()).origin, originalOrigin);
await page.getByRole('button', {name: 'Connect Lexirise', exact: true}).waitFor();
await until(() => page.locator('select[aria-label="Voice playback speed"]').inputValue().then(value => value === '0.75'), 'playback preference after process death');
const restarted = await page.evaluate(async () => ({snapshot: await (await fetch('/api/snapshot')).json(),
  font: getComputedStyle(document.querySelector('.companion-shell')).getPropertyValue('--lexirise-font-size').trim(),
  options: JSON.parse(localStorage.getItem('proxy-transcript-reading-options'))}));
assert.equal(restarted.font, '31px');assert.equal(restarted.options.pinyin, 'all');
assert.equal(restarted.snapshot.status.capture.running, false);
assert.equal(restarted.snapshot.lines.length, 1);
assert.equal(restarted.snapshot.lines[0].favorite, true);
assert.equal(restarted.snapshot.lines[0].has_audio, true);
const migratedTotal = await importBrowserHistoryThroughUi(page, until, lineId, bytes =>
  selectAuthoredAndroidDocument({adb, page, until, output, extension: 'json', bytes,
    trigger: () => page.getByLabel('Browser history backup', {exact: true}).click()}));
await browser.close();
adb('shell', 'am', 'force-stop', packageName);
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredGameData', 'true');
({browser, page} = await connectReader());
const retainedNormalSnapshot = await verifyMigratedHistory(page, until, migratedTotal, lineId);
await browser.close();
const accountAcceptance = await nativeAccountAcceptance({adb, component, packageName, connectReader, until,
  output, library: join(directory, 'authored-library.zip'), senderFixture});
// Exercise a genuine package-manager update without preparing the source again.
// Core/self-test data live in isolated authored probe folders; the real reader
// history below must survive unchanged. The signing key is temporary CI debug material;
// durable owner signing is verified separately on the protected host.
adb('shell', 'am', 'force-stop', packageName);
adb('install', '-r', updateApk);
assert.ok(new RegExp(`versionCode=${update.version_code}(?:\\s|$)`).test(adb('shell', 'dumpsys', 'package', packageName)), 'The target must actually install the newer APK');
adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitSelfTest', 'true', '--ez', 'toolkitAuthoredGameData', 'true');
const upgradedCore = await authoredCore(update.version_code, core.self_test_run_id);
({browser, page} = await connectReader());
assertProtectedStorage(upgradedCore.native_protected_storage);
assertNativeDataDecoder(upgradedCore.native_x64_decoder, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')).native_data_decoder, update.native_decoder_manifest_sha256);
assertNativeGenshinProfile(upgradedCore.native_genshin_profile, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')), update, upgradedCore.native_x64_decoder);
assertNativeZstandard(upgradedCore.native_zstandard, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')).native_zstandard);
assertNativePublisherCrypto(upgradedCore.native_publisher_crypto, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')).native_publisher_crypto, update);
assertNativePublisherHash(upgradedCore.native_publisher_hash, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')).native_publisher_hash, update);
assertNativeWuwaBootstrap(upgradedCore.native_wuwa_bootstrap, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')), update, upgradedCore.native_publisher_crypto.runtime);
assertNativeZzzCatalogue(upgradedCore.native_zzz_catalogue, JSON.parse(readFileSync(join(updateDirectory, 'apk-audit.json'), 'utf8')), update);
assert.equal(upgradedCore.native_protected_storage.previous_saved_blob_reopened, true);
assert.equal(upgradedCore.result_sha256, core.result_sha256);
assert.equal(new URL(page.url()).origin, originalOrigin);
await page.getByRole('button', {name: 'Connect Lexirise', exact: true}).waitFor();
assert.equal(await page.getByRole('combobox', {name: 'Reading', exact: true}).count(), 0);
await until(() => page.locator('select[aria-label="Voice playback speed"]').inputValue().then(value => value === '0.75'), 'playback preference after APK update');
const upgraded = await page.evaluate(async id => {
  const range = await fetch(`/api/lines/${id}/audio`, {headers: {Range: 'bytes=0-43'}});
  return {snapshot: await (await fetch('/api/snapshot')).json(), audio_status: range.status,
    audio_bytes: (await range.arrayBuffer()).byteLength,
    font: getComputedStyle(document.querySelector('.companion-shell')).getPropertyValue('--lexirise-font-size').trim(),
    options: JSON.parse(localStorage.getItem('proxy-transcript-reading-options'))};
}, lineId);
assert.equal(upgraded.snapshot.status.capture.running, false);
assert.deepEqual(upgraded.snapshot.lines, retainedNormalSnapshot.lines);
assert.equal(upgraded.audio_status, 206);assert.equal(upgraded.audio_bytes, 44);
assert.equal(upgraded.font, '31px');assert.equal(upgraded.options.pinyin, 'all');
await verifyMigratedHistory(page, until, migratedTotal, lineId);
writeFileSync(join(output, 'android-browser-migration-runtime-proof.json'), JSON.stringify({
  schema: 'toolkit-android-browser-history-runtime-v1', fixture: 'real-exporter-projection-of-authored-mixed-history',
  source_commit: provenance.source_commit, apk_sha256: provenance.apk_sha256, updated_apk_sha256: update.apk_sha256,
  normal_startup: true, native_android_execution: true, rows: migrationRows, preview_preserves_existing_rows: true,
  real_ui_import: true, paged_history: true, oldest_favorite_visible: true, repeat_idempotent: true,
  original_native_favorite_and_voice_retained: true, imported_audio_not_invented: true,
  offline_process_restart: true, apk_update_retained_data: true,
  actual_android_saf_json_selection: true,
  physical_mobile_bookmark_acceptance: 'not-established', release_eligibility: false,
}, null, 2) + '\n');
await browser.close();
await verifyNativeAccountsAfterUpdate({adb, component, packageName, connectReader, until, output}, accountAcceptance);
writeFileSync(join(output, 'android-runtime-proof.json'), JSON.stringify({schema: 'toolkit-android-runtime-proof-v1',
  fixture: 'authored-text-bitmap-and-generated-tone', apk_sha256: provenance.apk_sha256,
  source_commit: provenance.source_commit, frontend_build_id: provenance.frontend_build_id,
  application_id: packageName, version_code: provenance.version_code, variant: provenance.variant,
  android_api_level: deviceApi, native_page_size: pageSize, target_sdk: buildPolicy.target_sdk,
  updated_apk_sha256: update.apk_sha256, updated_version_code: update.version_code,
  shared_core_identical: true, native_genshin_profile_component: true, genshin_profile_only: true, native_media_completed: true, native_x64_data_decoder: core.native_x64_decoder, bundled_ocr_to_transcript: true,
  synthetic_cross_origin_receiver: true, native_receiver_stop_and_reconnect: true,
  shared_reader_audio_stopped_on_background: true, authored_fuzzy_50000_ms: core.runtime.authored_fuzzy_50000_ms,
  offline_process_restart: true, reader_preferences_retained: true, favorite_and_original_audio_retained: true,
  offline_apk_update_retained_data: true, update_signing: 'same-run-debug-identity-not-owner-key',
  native_keystore_retained_across_apk_update: true,
  normal_protected_accounts_available: true, authored_direct_game_data_flow_offline: true,
  normal_publisher_preparation_acceptance: 'not-established',
  ordinary_startup_browser_history_migration: true,
  actual_android_saf_history_json_selection: true,
  system_insets_and_rotation: true,
  physical_device_acceptance: 'not-established', release_eligibility: false}, null, 2) + '\n');
console.log('Authored shared-core, bundled OCR, original audio and reader restart accepted on the Android emulator.');
