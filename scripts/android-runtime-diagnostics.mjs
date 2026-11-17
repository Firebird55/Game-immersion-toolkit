// Authored runtime acceptance only. Never serialize URLs, cookies, OCR text,
// provider payloads, account details or arbitrary browser console messages.
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {authoredLibraryIdentity, inspectAuthoredLibrary} from './android-authored-library-check.mjs';

const paths = new Set(['/api/snapshot', '/api/platform', '/api/library/import', '/api/settings',
 '/api/capture/receiver', '/api/capture/frame']);
const states = new Set(['receiver_frame_stale', 'receiver_document_changed', 'receiver_document_retired',
 'receiver_revision_stale', 'receiver_generation_changed', 'receiver_dimensions_changed', 'receiver_owned',
 'receiver_registry_full', 'account_generation_changed', 'account_recovery_required']);
const number = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
async function bounded(promise, milliseconds) {
 let timer;
 try {return await Promise.race([promise, new Promise((_, reject) => {
  timer = setTimeout(() => reject(Error('Authored diagnostic read exceeded its bound')), milliseconds);
 })]);} finally {clearTimeout(timer);}
}

export function safeMessageMetrics(value) {
 return Object.fromEntries(['requests', 'received_frames', 'png_blobs', 'csp_violations']
  .map(key => [key, number(value?.[key])]));
}

export async function authoredReceiverLibraryReady(page) {
 const message = await page.locator('[aria-label="Receive game screen"] [role="status"]').textContent();
 // This status is rendered from the actual libraryReady prop. HTTP import
 // completion alone does not prove React committed its new keyed receiver.
 return ['Connect the game device to begin.', 'Screen source stopped.'].includes(message?.trim());
}

export function safeReceiverState(value) {
 const capture = value?.status?.capture;
 const settings = value?.status?.settings, maps = value?.status?.textmaps;
 const region = name => {
  const result = ['left', 'top', 'width', 'height'].map(key => settings?.[name]?.[key]);
  return result.every(item => typeof item === 'number' && Number.isFinite(item) && item >= 0 && item <= 1) ? result : null;
 };
 return {lines: Array.isArray(value?.lines) ? value.lines.length : null,
  authored_line_present: Array.isArray(value?.lines) && value.lines.some(line => line.text_id === 'authored:bridge'),
  running: capture?.running === true, source_generation: number(capture?.source_generation),
  state_version: number(value?.context?.state_version),
  stable_frames: number(settings?.stable_frames),
  fuzzy_threshold: typeof settings?.fuzzy_threshold === 'number' && Number.isFinite(settings.fuzzy_threshold)
   && settings.fuzzy_threshold >= 0 && settings.fuzzy_threshold <= 100 ? settings.fuzzy_threshold : null,
  region: region('region'), cinematic_region: region('cinematic_region'),
  textmap_ready: maps?.ready === true, textmap_entries: number(maps?.entry_count),
  textmap_voices: number(maps?.audio_count), audio_ready: value?.status?.audio?.ready === true,
  last_ocr_present: typeof capture?.last_ocr === 'string' && capture.last_ocr.length > 0,
  last_ocr_matches_fixture: capture?.last_ocr === 'Follow the river beyond the bridge.',
  frame_size: Array.isArray(capture?.window_bounds) && capture.window_bounds.length === 4
   && capture.window_bounds.every(Number.isSafeInteger) ? capture.window_bounds.slice(2) : null};
}

function messageMetrics() {
 if (window.__toolkitAuthoredReceiverMetrics) return;
 window.__toolkitAuthoredReceiverMetrics = {requests: 0, received_frames: 0, png_blobs: 0, csp_violations: 0};
 addEventListener('message', event => {
  const value = window.__toolkitAuthoredReceiverMetrics;
  if (event.data?.getVideoFrame === true) value.requests++;
  if (event.data?.action === 'image-frame-capture') {
   value.received_frames++;
   if (event.data?.value?.imageData instanceof Blob && event.data.value.imageData.type === 'image/png') value.png_blobs++;
  }
 });
 addEventListener('securitypolicyviolation', () => window.__toolkitAuthoredReceiverMetrics.csp_violations++);
}

export async function createAuthoredRuntimeDiagnostics(page, {output, adb, packageName, directory}) {
 let expectedLibrary = null;
 try {if (directory) expectedLibrary = authoredLibraryIdentity(join(directory, 'authored-library.zip'));} catch {}
 const requests = new Map(), controls = [];
 let browserErrors = 0, consoleErrors = 0, cspConsoleErrors = 0;
 page.on('pageerror', () => browserErrors++);
 page.on('console', value => {
  if (value.type() === 'error') consoleErrors++;
  if (/Content Security Policy|content security policy/.test(value.text())) cspConsoleErrors++;
 });
 page.on('response', response => {
  let path;
  try {path = new URL(response.url()).pathname;} catch {return;}
  if (!paths.has(path)) return;
  const status = response.status(), key = path + ':' + status;
  requests.set(key, (requests.get(key) ?? 0) + 1);
  if (path === '/api/capture/receiver' || path === '/api/capture/frame') {
   void response.json().then(value => {
    controls.push({path, status, running: value?.running === true,
     generation: number(value?.generation), frame: number(value?.frame),
     state: states.has(value?.state) ? value.state : null});
    if (controls.length > 32) controls.shift();
   }).catch(() => {});
  }
 });
 let newDocumentMetrics = true;
 try {await page.addInitScript(messageMetrics);} catch {newDocumentMetrics = false;}
 await page.evaluate(messageMetrics);
 return {async capture(label, filename = 'android-authored-runtime-failure.json') {
  if (!['android-authored-runtime-failure.json', 'android-receiver-before-library-ready.json',
    'android-receiver-after-library-ready.json'].includes(filename)) throw Error('Unknown authored diagnostic filename');
  const report = {schema: 'toolkit-android-authored-runtime-failure-v1',
   // Labels are authored probe literals, never user errors.
   checkpoint: String(label).slice(0, 160), new_document_metrics: newDocumentMetrics,
   browser_errors: browserErrors, console_errors: consoleErrors, csp_console_errors: cspConsoleErrors,
   requests: [...requests].map(([key, count]) => ({key, count})), controls: controls.slice()};
  if (directory) report.authored_library = {expected_fixture_valid: expectedLibrary !== null, inspected: false};
  try {
   const value = await bounded(page.evaluate(async () => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 3000);
    let snapshot = null;
    try {const response = await fetch('/api/snapshot', {signal: controller.signal});if (response.ok) snapshot = await response.json();}
    catch {} finally {clearTimeout(timer);}
    const message = document.querySelector('[aria-label="Receive game screen"] [role="status"]')?.textContent?.trim();
    return {snapshot, hidden: document.hidden, iframe_count: document.querySelectorAll('.android-screen-viewer iframe').length,
     library_ready: ['Connect the game device to begin.', 'Screen source stopped.'].includes(message),
     viewer_link_present: !!document.querySelector('#android-screen-link')?.value,
     image_bitmap_available: typeof createImageBitmap === 'function', metrics: window.__toolkitAuthoredReceiverMetrics};
   }), 5000);
   report.reader = {...safeReceiverState(value.snapshot), hidden: value.hidden === true,
    iframe_count: number(value.iframe_count), viewer_link_present: value.viewer_link_present === true,
    library_ready: value.library_ready === true,
    image_bitmap_available: value.image_bitmap_available === true};
   report.parent_messages = safeMessageMetrics(value.metrics);
   const account = value.snapshot?.lexirise?.account;
   if (expectedLibrary && (account === undefined || account === 'legacy') && value.snapshot?.status?.capture?.active_game === 'zzz')
    report.authored_library = inspectAuthoredLibrary(adb, packageName, expectedLibrary);
   report.senders = [];
   for (const frame of page.frames()) {
    if (frame === page.mainFrame()) continue;
    let official = false;
    try {official = new URL(frame.url()).origin === 'https://vdo.ninja';} catch {}
    if (!official || report.senders.length >= 4) continue;
    const value = await bounded(frame.evaluate(() => ({hidden: document.hidden,
     metrics: window.__toolkitAuthoredReceiverMetrics})), 1500).catch(() => null);
    if (value) report.senders.push({hidden: value.hidden === true, metrics: safeMessageMetrics(value.metrics)});
   }
  } catch {report.reader_unavailable = true;}
  try {
   const pid = adb('shell', 'pidof', packageName).split(/\s+/)[0];
   if (/^[0-9]+$/.test(pid)) {
    const logs = adb('logcat', '--pid', pid, '-d', '-t', '200', 'ToolkitAndroid:W', 'AndroidRuntime:E', '*:S');
    report.native_log = {ocr_failures: logs.split('\n').filter(line => line.includes('A frame could not be recognized locally')).length,
     startup_failure: logs.includes('Local host startup failed'), fatal_exception: logs.includes('FATAL EXCEPTION')};
   }
  } catch {report.native_log_unavailable = true;}
  writeFileSync(join(output, filename), JSON.stringify(report, null, 2) + '\n');
 }};
}
