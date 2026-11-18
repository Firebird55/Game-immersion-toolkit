// Acceptance fixtures only. Never enable production accounts or write real services.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {authoredLibraryIdentity} from './android-authored-library-check.mjs';
import {authoredReceiverLibraryReady, createAuthoredRuntimeDiagnostics} from './android-runtime-diagnostics.mjs';
import {prepareAuthoredGameData} from './android-authored-game-data-ui.mjs';
import {observeRecoveryForm, observeRecoveryPredicate} from './android-authored-recovery-observation.mjs';

const firstKey = 'lx_first_authored_account_fixture_only';
const secondKey = 'lx_second_authored_account_fixture_only';
const corruptBytes = Buffer.from('authored-corrupt-credential-fixture');

export function authoredCredentialPath(packageName, platform) {
  if (packageName !== 'io.github.firebird55.gameimmersiontoolkit.debug'
      || platform?.platform !== 'android' || platform.authored_account_fixture !== true
      || platform.protected_accounts !== true || platform.account_protocol !== 'scoped-accounts-v1')
    throw Error('Only an explicitly isolated DEBUG account fixture may be modified');
  return 'files/authored-account-ui/credentials/accounts.gcm';
}

const snapshot = page => page.evaluate(async () => (await fetch('/api/snapshot')).json());
const platform = page => page.evaluate(async () => (await fetch('/api/platform')).json());

async function openAccountSettings(page) {
  const connect = page.getByRole('button', {name: 'Connect Lexirise', exact: true});
  if (await connect.count()) await connect.click();
  else await page.getByRole('button', {name: 'Account settings', exact: true}).click();
}

async function audioHash(page, id) {
  return page.evaluate(async id => {
    const response = await fetch(`/api/lines/${id}/audio`);
    if (!response.ok) throw Error('The retained authored recording is unavailable');
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > 4 * 1024 ** 2) throw Error('Authored audio exceeds its bound');
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
  }, id);
}

export async function verifyAuthoredOwner(page, identity, expectedAudio, until) {
  assert.equal((await platform(page)).authored_account_fixture, true);
  await until(() => page.evaluate(async identity => (await (await fetch('/api/lexirise/accounts')).json()).active === identity, identity),
    'authored protected owner reopened');
  await page.locator('.transcript-line').filter({hasText: 'Follow the river beyond the bridge.'}).first().waitFor();
  await until(async () => (await snapshot(page)).status.textmaps.ready, 'restored original direct-source index');
  const value = await snapshot(page);
  assert.equal(value.lines.length, 1);assert.equal(value.lines[0].favorite, true);
  assert.equal(value.status.textmaps.ready, true);assert.equal(value.status.settings.capture_unvoiced, true);
  assert.equal(value.status.settings.stable_frames, 2);
  assert.equal(await audioHash(page, value.lines[0].id), expectedAudio);
  assert.ok(Object.hasOwn(value.lexirise.sent, 'line:' + value.lines[0].id));
}

// Shared UI steps can run against the desktop authored harness or a real WebView.
// Storage, frame acquisition and controlled corruption are explicit host adapters.
export async function exerciseAccountUi(page, {library, until, capture, corrupt, preserved, recoveryObservation}) {
  const expectedLibrary = authoredLibraryIdentity(library);
  assert.equal((await platform(page)).authored_account_fixture, true);
  await openAccountSettings(page);
  const register = async (key, label) => {
    await page.getByRole('button', {name: 'Add account securely', exact: true}).click();
    await page.getByLabel('Lexirise API key', {exact: true}).fill(key);
    await page.getByLabel('Account label (optional)', {exact: true}).fill(label);
    await page.getByRole('button', {name: 'Verify and save', exact: true}).click();
    await page.waitForFunction(label => document.querySelector('select[aria-label="Active Lexirise account"]')?.selectedOptions[0]?.textContent === label, label);
    return page.getByRole('combobox', {name: 'Active Lexirise account', exact: true}).inputValue();
  };
  const first = await register(firstKey, 'First authored owner');
  await page.getByRole('button', {name: 'Close Lexirise settings', exact: true}).click();
  await prepareAuthoredGameData(page, until, {bothModes: true});
  await capture(page);
  await page.getByRole('button', {name: 'Play current voice line', exact: true}).waitFor();
  const initial = await snapshot(page);assert.equal(initial.lines.length, 1);
  const generation = initial.context.account_generation, oldLine = initial.lines[0].id;
  const expectedAudio = await audioHash(page, oldLine);
  assert.equal(expectedAudio, expectedLibrary.audio_sha256);
  await page.getByRole('button', {name: 'Favorite current line', exact: true}).click();
  await until(async () => (await snapshot(page)).lines[0]?.favorite, 'authored native favorite');
  await page.getByRole('button', {name: 'Capture setup', exact: true}).click();
  const settings = page.getByRole('dialog', {name: 'Capture setup', exact: true});
  await settings.getByLabel('Include unvoiced dialogue', {exact: true}).check();
  assert.equal(await settings.getByRole('button', {name: 'Update TextMaps', exact: true}).count(), 0);
  await settings.getByRole('button', {name: 'Save capture settings', exact: true}).click();
  await settings.waitFor({state: 'hidden'});
  await until(async () => (await snapshot(page)).status.settings.capture_unvoiced, 'authored scoped preferences');
  await page.getByRole('button', {name: 'Account settings', exact: true}).click();
  await page.getByRole('button', {name: 'Find or create game deck', exact: true}).click();
  await until(async () => !!(await snapshot(page)).lexirise.decks?.zzz, 'authored mock export destination');
  await page.getByRole('button', {name: 'Close Lexirise settings', exact: true}).click();
  await page.locator('.current-line .lexirise-send').click();
  await page.getByText('Sentence and voice saved in Lexirise · Zenless Zone Zero.', {exact: true}).waitFor();
  await until(async () => Object.keys((await snapshot(page)).lexirise.sent).length === 1, 'authored original-audio mock export');
  await page.evaluate(() => {
    const RealAudio = window.Audio;window.__toolkitAccountAudio = [];
    const TrackedAudio = function(...args) {const element = new RealAudio(...args);window.__toolkitAccountAudio.push(element);return element;};
    TrackedAudio.prototype = RealAudio.prototype;Object.setPrototypeOf(TrackedAudio, RealAudio);window.Audio = TrackedAudio;
  });
  await page.getByRole('button', {name: 'Play current voice line', exact: true}).click();
  await until(() => page.evaluate(() => window.__toolkitAccountAudio.some(audio => !audio.paused && !audio.ended)), 'authored real WebView playback');
  await page.getByRole('button', {name: 'Account settings', exact: true}).click();
  const second = await register(secondKey, 'Second authored owner');assert.notEqual(first, second);
  const other = await snapshot(page);
  assert.equal(other.lines.length, 0);assert.equal(other.status.textmaps.ready, false);
  assert.equal(other.status.settings.capture_unvoiced, false);assert.deepEqual(other.lexirise.sent, {});
  assert.ok(other.context.account_generation > generation);
  assert.equal(await page.getByRole('button', {name: 'Play current voice line', exact: true}).count(), 0);
  assert.equal(await page.evaluate(() => window.__toolkitAccountAudio.length > 0 && window.__toolkitAccountAudio.every(audio => audio.paused && !audio.getAttribute('src'))), true);
  const stale = await page.evaluate(async ({generation, oldLine, library}) => {
    const headers = {'Content-Type': 'application/json', 'X-Toolkit-Account-Generation': String(generation)};
    const values = [
      await fetch('/api/settings', {method: 'PATCH', headers, body: JSON.stringify({stable_frames: 9})}),
      await fetch('/api/library/import/cancel', {method: 'POST', headers, body: JSON.stringify({import_id: crypto.randomUUID()})}),
      await fetch('/api/library/import', {method: 'POST', headers: {...headers, 'Content-Type': 'application/zip',
        'X-Toolkit-Import-Id': crypto.randomUUID()}, body: Uint8Array.from(atob(library), c => c.charCodeAt(0))}),
      await fetch('/api/capture/receiver', {method: 'POST', headers: {...headers,
        'X-Toolkit-Document-Epoch': document.querySelector('meta[name="toolkit-document-epoch"]').content},
        body: JSON.stringify({id: crypto.randomUUID(), revision: 1, action: 'start', expected_generation: 1})}),
      await fetch(`/api/lines/${oldLine}/audio`),
    ];
    return values.map(response => response.status);
  // The guard must reject before parsing an archive. Keep this rejected body
  // within the server's 64-KiB drain bound so its exact 409 can reach Firefox.
  }, {generation, oldLine, library: readFileSync(library).subarray(0, 4096).toString('base64')});
  assert.deepEqual(stale, [409, 409, 409, 409, 409]);
  assert.equal((await snapshot(page)).lines.length, 0);
  assert.equal((await snapshot(page)).status.textmaps.ready, false);
  await page.getByRole('combobox', {name: 'Active Lexirise account', exact: true}).selectOption(first);
  await until(() => page.evaluate(async identity => (await (await fetch('/api/lexirise/accounts')).json()).active === identity, first), 'authored A-B-A restoration');
  await page.getByRole('button', {name: 'Close Lexirise settings', exact: true}).click();
  await verifyAuthoredOwner(page, first, expectedAudio, until);
  assert.notEqual((await snapshot(page)).lines[0].id, oldLine);
  assert.equal(await page.evaluate(async generation => (await fetch('/api/settings', {method: 'PATCH', headers: {
    'Content-Type': 'application/json', 'X-Toolkit-Account-Generation': String(generation)},
    body: JSON.stringify({stable_frames: 9})})).status, generation), 409, 'Returning to A must not revive its old request scope');
  await corrupt(page);
  await until(async () => (await platform(page)).capture_source === 'unavailable', 'locked native capture capability');
  await until(async () => await page.locator('.transcript-line').count() === 0, 'locked native history hidden');
  await openAccountSettings(page);
  const recoveryInput = recoveryObservation ? await page.getByLabel('Lexirise API key', {exact: true}).elementHandle() : null;
  await observeRecoveryForm(page, recoveryObservation, 'before-fill', recoveryInput);
  await page.getByLabel('Lexirise API key', {exact: true}).fill(firstKey);
  await observeRecoveryForm(page, recoveryObservation, 'after-fill', recoveryInput);
  await observeRecoveryForm(page, recoveryObservation, 'before-submit', recoveryInput);
  await page.getByRole('button', {name: 'Verify and restore local data', exact: true}).click();
  await until(() => observeRecoveryPredicate(page, first, recoveryObservation), 'explicit native verified-owner recovery');
  await recoveryInput?.dispose();
  await page.getByRole('button', {name: 'Close Lexirise settings', exact: true}).click();
  await verifyAuthoredOwner(page, first, expectedAudio, until);
  assert.equal(await preserved(page), true);
  return {first, expectedAudio};
}

export async function connectAuthoredReceiver(page, until) {
  const generation = (await snapshot(page)).context.account_generation;
  assert.equal(await page.evaluate(async generation => (await fetch('/api/settings', {method: 'PATCH', headers: {
    'Content-Type': 'application/json', 'X-Toolkit-Account-Generation': String(generation)},
    body: JSON.stringify({region: {left: 0, top: 0, width: 1, height: 1}})})).status, generation), 200);
  await until(() => authoredReceiverLibraryReady(page), 'authored native library activation');
  const link = page.getByLabel('Paste vdo.ninja link to start', {exact: true});
  await until(() => link.isEnabled(), 'authored native account receiver');
  await link.fill('https://vdo.ninja/?view=authored');
  await until(async () => (await snapshot(page)).lines.length === 1, 'authored account native OCR transcript');
}

export async function nativeAccountAcceptance({adb, component, packageName, connectReader, until, output, library, senderFixture}) {
  adb('shell', 'am', 'force-stop', packageName);
  adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredAccounts', 'true');
  const {browser, page} = await connectReader();
  const path = authoredCredentialPath(packageName, await platform(page));
  await page.route('https://vdo.ninja/**', route => route.fulfill({contentType: 'text/html', body: senderFixture}));
  const diagnostics = await createAuthoredRuntimeDiagnostics(page, {output, adb, packageName});
  let result;
  try {
    result = await exerciseAccountUi(page, {library, until, recoveryObservation: diagnostics.recovery,
      capture: page => connectAuthoredReceiver(page, until),
      corrupt: async page => {
        assert.equal(authoredCredentialPath(packageName, await platform(page)), path);
        const local = join(output, 'authored-corrupt-credentials.bin');writeFileSync(local, corruptBytes);
        adb('push', local, '/data/local/tmp/toolkit-authored-corrupt-credentials.bin');
        adb('shell', 'run-as', packageName, 'cp', '/data/local/tmp/toolkit-authored-corrupt-credentials.bin', path);
        await until(async () => (await snapshot(page)).lexirise.account === 'recovery', 'native corrupt-store locked state');
      },
      preserved: async page => {
        assert.equal(authoredCredentialPath(packageName, await platform(page)), path);
        return adb('shell', 'run-as', packageName, 'sha256sum', path).split(/\s+/)[0] === createHash('sha256').update(corruptBytes).digest('hex');
      }});
  } catch (error) {
    await diagnostics.capture('authored-account-ui acceptance');throw error;
  } finally {await browser.close();}
  // Reopen the same isolated Android store with the actual Keystore provider.
  adb('shell', 'am', 'force-stop', packageName);
  adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredAccounts', 'true');
  const reopened = await connectReader();
  try {await verifyAuthoredOwner(reopened.page, result.first, result.expectedAudio, until);}
  finally {await reopened.browser.close();}
  adb('shell', 'am', 'force-stop', packageName);
  adb('shell', 'am', 'start', '-W', '-n', component);
  const normal = await connectReader();
  try {
    const capabilities = await platform(normal.page);
    assert.equal(capabilities.protected_accounts, true);assert.equal(capabilities.authored_account_fixture, false);
    assert.equal((await snapshot(normal.page)).lexirise.configured, false);
  }
  finally {await normal.browser.close();}
  return result;
}

export async function verifyNativeAccountsAfterUpdate({adb, component, packageName, connectReader, until, output}, result) {
  adb('shell', 'am', 'force-stop', packageName);
  adb('shell', 'am', 'start', '-W', '-n', component, '--ez', 'toolkitAuthoredAccounts', 'true');
  const {browser, page} = await connectReader();
  try {
    authoredCredentialPath(packageName, await platform(page));
    await verifyAuthoredOwner(page, result.first, result.expectedAudio, until);
  } finally {await browser.close();}
  writeFileSync(join(output, 'android-account-runtime-proof.json'), JSON.stringify({
    schema: 'toolkit-android-authored-account-runtime-v1', fixture: 'two-immutable-mock-owners-and-generated-tone',
    account_switch: 'A-B-A', native_android_execution: true, credential_protection: 'actual-isolated-android-keystore',
    remote_transport: 'immutable-authored-mock', shared_ui_direct_game_preparation: true, native_ocr_capture: true,
    favorite_and_preferences_retained: true, original_audio_hash_retained: true, mock_audio_export: true,
    stale_account_requests_rejected: true, detached_audio_retired_on_switch: true,
    corrupt_original_store_preserved: true, explicit_verified_owner_recovery: true,
    process_restart_retained_data: true, apk_update_retained_recovered_data: true,
    normal_protected_accounts_available: true, real_account_writes: false,
    physical_device_acceptance: 'not-established', release_eligibility: false,
  }, null, 2) + '\n');
}
