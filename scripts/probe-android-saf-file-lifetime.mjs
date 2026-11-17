// Causal diagnostic for unchanged c423 APK, not an acceptance or fix claim.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright';
import {selectAuthoredAndroidDocument} from './android-authored-document-picker.mjs';
import {waitForAuthoredAdbRoot} from './android-authored-adb.mjs';
import {authoredBrowserHistoryBackup} from './android-browser-migration-ui.mjs';

const root = resolve('output/android-downloaded/android-candidate'), output = resolve('output/android-saf-diagnostic');
mkdirSync(output, {recursive: true});
const expectedSource = 'c42312cbc403425f965e89d38284c9d8aae93ee7';
const provenance = JSON.parse(readFileSync(join(root, 'ANDROID-PROVENANCE.json')));
assert.equal(provenance.source_commit, expectedSource);assert.equal(provenance.source_dirty, false);
assert.equal(provenance.application_id, 'io.github.firebird55.gameimmersiontoolkit.debug');
assert.equal(provenance.apk_sha256, '41be9bc58227bed245a25df93a524bf0f33357feb50ab29a8c119eb3a674e7c2');
const apk = join(root, 'GameImmersionToolkit-android-debug.apk');
assert.equal(createHash('sha256').update(readFileSync(apk)).digest('hex'), provenance.apk_sha256);
const library = readFileSync(join(root, 'authored-library.zip'));
assert.ok(library.length > 0 && library.length < 1024 * 1024);
const expectedHash = createHash('sha256').update(library).digest('hex');
const adb = (...args) => execFileSync('adb', args, {encoding: 'utf8', timeout: 30000}).trim();
async function until(read, label, timeout = 90000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {try {const value = await read();if (value) return value;} catch {} await delay(500);}
  throw Error('Authored SAF diagnostic did not establish ' + label);
}
assert.equal(adb('shell', 'getprop', 'ro.kernel.qemu'), '1');
const api = Number(adb('shell', 'getprop', 'ro.build.version.sdk'));
assert.ok([34, 36].includes(api));assert.equal(api, Number(process.env.TOOLKIT_ANDROID_EXPECTED_API));
adb('install', '-r', apk);
await waitForAuthoredAdbRoot(adb, until);
adb('shell', 'iptables', '-I', 'OUTPUT', '!', '-d', '127.0.0.0/8', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'ip6tables', '-I', 'OUTPUT', '!', '-d', '::1/128', '-m', 'owner', '!', '--uid-owner', '0', '-j', 'REJECT');
adb('shell', 'am', 'start', '-W', '-n', provenance.application_id + '/io.github.firebird55.gameimmersiontoolkit.MainActivity');
const pid = await until(() => adb('shell', 'pidof', provenance.application_id), 'actual app process');
adb('forward', 'tcp:9222', 'localabstract:webview_devtools_remote_' + pid);
await until(async () => (await fetch('http://127.0.0.1:9222/json/version')).ok, 'WebView CDP');
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222', {noDefaults: true});
const page = await until(() => browser.contexts().flatMap(context => context.pages()).find(page => page.url().startsWith('http://127.0.0.1:')), 'local reader');
const codes = {}, responses = [];
page.on('requestfailed', request => {
  if (new URL(request.url()).pathname !== '/api/library/import') return;
  const text = request.failure()?.errorText ?? '';
  const code = ['ERR_UPLOAD_FILE_CHANGED', 'ERR_ACCESS_DENIED', 'ERR_FILE_NOT_FOUND', 'ERR_ABORTED', 'ERR_FAILED'].find(code => text.includes(code)) ?? 'OTHER';
  codes[code] = (codes[code] ?? 0) + 1;
});
page.on('response', response => {if (new URL(response.url()).pathname === '/api/library/import') responses.push(response.status());});
const reports = [];
let jsonSaf = false;
function save() {
  writeFileSync(join(output, 'authored-saf-file-lifetime.json'), JSON.stringify({
    schema: 'toolkit-authored-saf-file-lifetime-diagnostic-v1', apk_source_commit: expectedSource,
    apk_sha256: provenance.apk_sha256, api, fixture_bytes: library.length, reports,
    ordinary_json_saf_preview_and_commit: jsonSaf,
    native_android_execution: true, production_fix_acceptance: false, real_account_writes: false,
  }, null, 2) + '\n');
}
try {
  await page.getByRole('button', {name: 'Open library', exact: true}).waitFor();
  for (const preserve of [false, true]) {
    const beforeOutcomes = responses.length + Object.values(codes).reduce((sum, value) => sum + value, 0);
    await page.evaluate(({preserve, expectedSize}) => {
      const input = document.querySelector('[aria-label="Private toolkit library"]');
      const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
      window.__authoredSaf = {reset_requested: 0, selected: false};
      Object.defineProperty(input, 'value', {configurable: true, get() {return descriptor.get.call(this);},
        set(value) {if (value === '') {window.__authoredSaf.reset_requested++;if (preserve) return;}descriptor.set.call(this, value);}});
      const selected = event => {
        if (event.target !== input) return;
        document.removeEventListener('change', selected, true);
        const file = input.files?.[0];
        window.__authoredSaf.file = file;window.__authoredSaf.selected = !!file;
        window.__authoredSaf.name_matches = file?.name === 'toolkit-authored.zip';
        window.__authoredSaf.size_matches = file?.size === expectedSize;
        window.__authoredSaf.mime_zip = file?.type === 'application/zip';
      };
      document.addEventListener('change', selected, true);
    }, {preserve, expectedSize: library.length});
    await selectAuthoredAndroidDocument({adb, page, until, output, extension: 'zip', bytes: library,
      trigger: () => page.getByRole('button', {name: 'Open library', exact: true}).click()});
    let completionTimeout = false;
    try {
      await until(async () => {
        const state = await page.evaluate(async () => ({selected: window.__authoredSaf.selected,
          reset: window.__authoredSaf.reset_requested, snapshot: await (await fetch('/api/snapshot')).json()}));
        const busy = await page.getByRole('button', {name: 'Cancel import', exact: true}).count();
        const outcomes = responses.length + Object.values(codes).reduce((sum, value) => sum + value, 0);
        return state.selected && state.reset > 0 && (state.snapshot.status.textmaps.ready || !busy && outcomes > beforeOutcomes);
      }, 'actual import handler completion');
    } catch {completionTimeout = true;}
    const report = await page.evaluate(async expected => {
      const value = window.__authoredSaf;
      const result = {selected: value.selected, reset_requested: value.reset_requested,
        name_matches: value.name_matches === true, size_matches: value.size_matches === true, mime_zip: value.mime_zip === true,
        retained_input: document.querySelector('[aria-label="Private toolkit library"]').files.length === 1};
      const status = document.querySelector('.android-library-card > [role="status"]')?.textContent?.trim();
      result.account_scope_wait = status === 'Wait for the selected account to load before retrying.';
      try {
        if (!value.name_matches || !value.size_matches) throw new TypeError();
        const bytes = await value.file.arrayBuffer();
        const digest = await crypto.subtle.digest('SHA-256', bytes);
        result.read_hash_matches = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('') === expected;
      } catch (error) {result.read_error = ['NotReadableError', 'NotFoundError', 'AbortError', 'SecurityError', 'TypeError'].includes(error.name) ? error.name : 'OTHER';}
      const snapshot = await (await fetch('/api/snapshot')).json();
      result.library_ready = snapshot.status.textmaps.ready;result.entries = snapshot.status.textmaps.entry_count;
      return result;
    }, expectedHash);
    reports.push({preserve_original_file_input: preserve, ...report, handler_completion_timeout: completionTimeout,
      import_http_statuses: [...responses], network_error_codes: {...codes}});
    save();
    await page.evaluate(() => {delete document.querySelector('[aria-label="Private toolkit library"]').value;delete window.__authoredSaf;});
    if (report.library_ready) break;
  }
  assert.equal(reports[0].library_ready, true, 'The unchanged normal input must work while its source document remains present');
  assert.equal(reports[0].preserve_original_file_input, false);
  assert.equal(reports[0].read_hash_matches, true);
  const setup = page.locator('details.android-device-setup');
  if (!await setup.evaluate(element => element.open)) await setup.locator(':scope > summary').click();
  await page.getByText('Import old browser history', {exact: true}).click();
  await selectAuthoredAndroidDocument({adb, page, until, output, extension: 'json', bytes: authoredBrowserHistoryBackup(),
    trigger: () => page.getByLabel('Browser history backup', {exact: true}).click()});
  await page.getByText('22 lines · 1 favorites · 1 excerpts.', {exact: false}).waitFor();
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/snapshot')).json()).status.session.total_line_count), 0);
  await page.getByRole('button', {name: 'Import history and favorites', exact: true}).click();
  await page.getByText('History imported: 22 new lines, 0 already imported. Original browser data is unchanged.', {exact: true}).waitFor();
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/snapshot')).json()).status.session.total_line_count), 22);
  jsonSaf = true;save();
} finally {await browser.close();}
console.log('Bounded unchanged-APK SAF diagnostic completed; see authored boolean/hash evidence.');
