import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import net from 'node:net';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {startOwnedServer, stopOwnedProcess} from './e2e-preview.mjs';
import {resolvePython} from './python-runtime.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';

export const ORIGIN = 'http://127.0.0.1:3000';
export const API = 'http://127.0.0.1:8766';
export const WS = 'ws://127.0.0.1:8766/api/ws';
// Fixed before observing CSR screenshots. Pixel comparisons supplement authored
// viewport/overlap/wrapping bounds; they do not make the source an error oracle.
export const PIXEL_LIMITS = Object.freeze({channelDelta: 16, changedRatio: .018, meanDelta: 1.5});
const sha256 = value => createHash('sha256').update(value).digest('hex');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function deadline(promise, milliseconds, label) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error(label + ' timed out')), milliseconds); })]); }
  finally { clearTimeout(timer); }
}
const STORAGE = Object.freeze({sentinel: 'authored-r19-continuity-v1',
  record: {kind: 'authored synthetic retained state', favorite: true, lines: ['保留原文。', 'Keep the original text.']},
  opfs: 'Authored R19 OPFS bytes — not a game library.', mode: 'lexirise', playback: '0.75'});
const SOURCE_TEXT = '你好，旅行者。欢迎来到这里。';
const TRANSLATION = 'Hello, traveler. Welcome to this place.';
const AUDIO_FAILURE_TEXT = SOURCE_TEXT + '声音不可用的测试。';

export function readDesktopManifest(root) {
  const manifest = JSON.parse(readFileSync(join(root, 'desktop-manifest.json'), 'utf8'));
  assert.equal(manifest.schema, 'proxy-desktop-frontend-v1');
  assert.equal(manifest.entry, 'index.html');
  assert.deepEqual(manifest.routes, ['/']);
  assert.equal(typeof manifest.build_id, 'string');
  assert(manifest.build_id.length > 0, 'Desktop build identity is required');
  assert(manifest.files && typeof manifest.files === 'object' && !Array.isArray(manifest.files));
  const names = new Set();
  for (const [name, entry] of Object.entries(manifest.files)) {
    assert(name && !name.includes('\\') && !name.startsWith('/') && !name.includes(':')
      && name.split('/').every(part => part && part !== '.' && part !== '..' && !/[. ]$/.test(part)), 'Unsafe built file name');
    assert(!names.has(name.toLowerCase()), 'Case-aliased built file names');
    names.add(name.toLowerCase());
    assert.match(entry.sha256, /^[a-f0-9]{64}$/);
    assert(Number.isSafeInteger(entry.bytes) && entry.bytes >= 0);
    assert.equal(typeof entry.mime, 'string');
    const bytes = readFileSync(join(root, name));
    assert.equal(bytes.length, entry.bytes, 'Built file size differs: ' + name);
    assert.equal(sha256(bytes), entry.sha256, 'Built file checksum differs: ' + name);
  }
  for (const name of ['index.html', 'mobile-capture/library-worker.mjs', 'mobile-capture/ocr/tesseract.esm.min.js',
    'mobile-capture/ocr/verified-worker.js', 'mobile-capture/ocr/core/tesseract-core.wasm', 'mobile-capture/ocr/lang/eng.traineddata.gz']) {
    assert(manifest.files[name], 'The desktop artifact lacks a required self-hosted resource: ' + name);
  }
  assert(Object.keys(manifest.files).some(name => /\.(?:woff2?|ttf)$/.test(name)), 'Desktop fonts must be local artifacts');
  return manifest;
}

export function assertStorageContinuity(actual, expected = STORAGE) {
  assert.equal(actual.origin, ORIGIN, 'The public browser origin changed');
  assert.equal(actual.sentinel, expected.sentinel, 'localStorage sentinel changed');
  assert.equal(actual.mode, expected.mode, 'The existing reading-mode key changed');
  assert.equal(actual.playback, expected.playback, 'The existing playback-rate key changed');
  assert.deepEqual(actual.record, expected.record, 'IndexedDB state changed');
  assert.equal(actual.opfs, expected.opfs, 'OPFS bytes changed');
}

export function assertLayoutBounds(metrics) {
  assert(metrics.documentWidth <= metrics.viewportWidth + 1, 'The page has horizontal overflow');
  const fits = box => box && box.width > 0 && box.height > 0 && box.x >= -1
    && box.x + box.width <= metrics.viewportWidth + 1;
  assert(fits(metrics.shell) && fits(metrics.current) && fits(metrics.source) && fits(metrics.translation), 'Transcript bounds escape the viewport');
  assert(metrics.source.y >= metrics.translation.y + metrics.translation.height - 1, 'Source and translation overlap');
  assert(metrics.actions.y >= metrics.source.y + metrics.source.height - 1, 'Voice/export controls overlap the source text');
  assert(metrics.sourceLineCount >= 1 && metrics.sourceLineCount <= 5, 'The short authored caption wraps into an implausible number of lines');
  assert(metrics.translationLineCount >= 1 && metrics.translationLineCount <= 4, 'The short authored translation is clipped or excessively wrapped');
  assert(metrics.sourceFontSize >= 22 && metrics.sourceFontSize <= 40, 'Caption font scale is outside the authored range');
  assert(metrics.fontsLoaded && metrics.localFontCount >= 2, 'The reviewed local UI fonts did not load');
}

export function assertPixelComparison(result, limits = PIXEL_LIMITS) {
  assert.equal(result.sameSize, true, 'Source/static screenshots have different dimensions');
  assert(result.changedRatio <= limits.changedRatio, 'Source/static changed-pixel ratio exceeds the fixed limit');
  assert(result.meanDelta <= limits.meanDelta, 'Source/static mean pixel difference exceeds the fixed limit');
}

function fixture() {
  let revision = 0, failedAudioLine = false;
  const context = () => ({runtime_id: 'r19-authored-fixture', state_version: revision, account_generation: 0});
  const region = {left: .1, top: .6, width: .8, height: .25};
  const settings = {preferred_game: 'zzz', region, tip_region: region, cinematic_region: region,
    hito_region: region, hito_tip_region: region, auto_start: false, capture_unvoiced: false};
  const capture = {running: true, active_game: 'zzz', visible_text_ids: ['authored-line'], phase: 'matched', message: 'Authored synthetic capture'};
  const line = () => ({id: failedAudioLine ? 2 : 1, game: 'zzz', created_at: failedAudioLine ? '2026-01-01T10:00:01Z' : '2026-01-01T10:00:00Z', session_id: 'authored-session',
    source_ocr: SOURCE_TEXT, english: TRANSLATION, chinese: SOURCE_TEXT, source_language: 'zh', source_locale: 'zh-Hans',
    source_text: failedAudioLine ? AUDIO_FAILURE_TEXT : SOURCE_TEXT, translation_locale: 'en', translation_text: TRANSLATION, text_id: 'authored-line',
    channel: 'dialogue', score: 100, match_kind: 'exact', voiced: true, has_audio: true, audio_source: 'original', favorite: false});
  const status = () => ({capture, textmaps: {ready: true, entry_count: 1}, audio: {ready: true}, settings,
    session: {id: 'authored-session', line_count: 1, total_line_count: 1}, selected_languages: {zzz: {source_language: 'zh', source_locale: 'zh-Hans'}}});
  const preferences = {languages: ['zh'], global: {effectiveTranslationLanguage: 'en', wordPopupOpenMode: 'click'},
    languageSettings: {zh: {effectiveTranslationLanguage: 'en', inlineGlossMode: 'off', readingAid: 'none',
      wordPopup: {tabs: [{id: 'definition', enabled: true}], openOn: 'first'}}}};
  const game = {id: 'zzz', title: 'Zenless Zone Zero', configured_path: null, detected_path: 'X:/Synthetic/ZZZ',
    folder_state: 'detected', folder_hint: 'Authored fixture', voice_state: 'present', voice_hint: 'Authored fixture',
    tools_missing: [], index_ready: true, indexed_lines: 1, audio_ready: true, update_state: 'ready', update_message: 'Authored fixture ready',
    progress: 100, last_checked: null, needs_attention: false};
  const setup = {completed: true, version: 'authored-r19', games: [game], requirements: [], jobs: {}, native: {},
    auto_start: false, lexirise_configured: true, free_gb: 80,
    mobile_export: {state: 'idle', scope: 'authored-scope', sourceLocale: 'zh-Hans', selectedGame: 'zzz', destinationFolder: 'X:/Synthetic/Export'}};
  const sockets = [];
  const requests = [], writes = [], unexpected = [];
  const audio = {broken: false, expectedErrors: 0};
  const serve = async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin === ORIGIN) return route.continue();
    if (url.origin !== API) {
      unexpected.push('External network: ' + url.origin);
      return route.abort('blockedbyclient');
    }
    const path = url.pathname, method = request.method();
    const linePath = path.replace(/^\/api\/lines\/2(?=\/)/, '/api/lines/1');
    requests.push({path, method});
    const respond = (json, status = 200) => route.fulfill({status, json,
      headers: {'Access-Control-Allow-Origin': ORIGIN, 'Access-Control-Allow-Methods': 'GET, HEAD, POST, PATCH, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Proxy-Transcript, X-Proxy-Transcript-Account, X-Proxy-Transcript-Export-Scope', 'Cache-Control': 'no-store'}});
    if (method === 'OPTIONS') return respond({}, 204);
    if (!['GET', 'HEAD'].includes(method)) {
      writes.push({path, method});
      if (!['PATCH /api/settings', 'POST /api/lines/1/lexirise', 'POST /api/setup/games/zzz/mobile-export/preview'].includes(method + ' ' + linePath)) {
        unexpected.push('Unrequested write: ' + method + ' ' + path);
        return respond({detail: 'Unrequested fixture write'}, 500);
      }
    }
    if (path === '/api/snapshot') return respond({context: context(), status: status(), lines: [line()], lexirise: {configured: true, account: 'authored-account', sent: {}, decks: {}}});
    if (path === '/api/status') return respond(status());
    if (path === '/api/setup') return respond(setup);
    if (path === '/api/lexirise') return respond({configured: true, account: 'authored-account', sent: {}, decks: {}});
    if (path === '/api/lexirise/accounts') return respond({active: 'authored-account', profiles: [{id: 'authored-account', name: 'Synthetic account'}]});
    if (path === '/api/lexirise/settings') return respond(preferences);
    if (path === '/api/lexirise/decks') return respond({decks: [{id: 7, title: 'Synthetic destination'}]});
    if (path === '/api/toolkit-update') return respond({installed_version: 'authored-r19', enabled: false, state: 'current', message: 'Authored fixture'});
    if (path === '/api/settings' && method === 'PATCH') { Object.assign(settings, request.postDataJSON()); revision++; return respond(settings); }
    if (path === '/api/settings') return respond(settings);
    if (path === '/api/lines' || path === '/api/favorites') return respond(path === '/api/lines' ? [line()] : []);
    if (path === '/api/setup/games/zzz/languages') return respond({context: context(), selected: 'zh-Hans', enabled_languages: ['zh'], targets: {zh: 'en'},
      translation_locales: ['en'], locales: [{locale: 'zh-Hans', language: 'zh', name: 'Simplified Chinese', reader_available: true,
        prepared: {targets: ['en'], mapped_lines: 1}, voice_state: 'present', table_bytes: 100, reclaimable_bytes: 0}]});
    if (path === '/api/setup/games/zzz/automatic-mobile-export') return respond({enabled: false, paused: false, destination: '', languages: {}, jobs: {},
      locales: [{locale: 'zh-Hans', name: 'Simplified Chinese', voice_label: 'Installed'}], translations: ['en'], browseActive: false});
    if (path === '/api/setup/games/zzz/mobile-export/preview') return respond({estimatedBytes: 2048, estimateLowBytes: 2048, estimateHighBytes: 2048, workingBytes: 4096, freeBytes: 1e9, rows: 1, basis: 'Authored fixture'});
    if (linePath === '/api/lines/1/reading') return respond({text: line().source_text,
      tokens: [{start: 0, end: 2, word: '你好', entryId: 1, proficiency: 0, pinyin: '', tones: [], meaning: 'hello'},
        {start: 3, end: 6, word: '旅行者', entryId: 2, proficiency: 0, pinyin: '', tones: [], meaning: 'traveler'}], grammar: []});
    if (linePath === '/api/lines/1/reading/lookup') return respond({translations: [{meaning: 'Authored greeting definition', partOfSpeech: [], examples: []}],
      examples: [], dictionaries: [], components: [], alternateReadings: []});
    if (linePath === '/api/lines/1/reading/characters') return respond({characters: [], partial: false});
    if (path === '/api/lines/2/audio') return route.fulfill({status: 503, body: 'Authored audio failure',
      headers: {'Access-Control-Allow-Origin': ORIGIN, 'Cache-Control': 'no-store'}});
    if (path === '/api/lines/1/audio') return route.fulfill({body: Buffer.from(TONE, 'base64'), contentType: 'audio/mpeg',
      headers: {'Access-Control-Allow-Origin': ORIGIN, 'Cache-Control': 'no-store'}});
    if (linePath === '/api/lines/1/lexirise' && method === 'POST') return respond({detail: 'Authored export failure; no remote account was written.'}, 409);
    unexpected.push(method + ' ' + path);
    return respond({detail: 'Unexpected authored fixture request'}, 500);
  };
  return {requests, writes, unexpected, sockets, settings, audio, serve,
    connect(socket) { sockets.push(socket); },
    reconnect() { const old = sockets.at(-1); assert(old, 'The production WebSocket never connected'); old.close(); return sockets.length; },
    publish() { revision++; sockets.at(-1).send(JSON.stringify({type: 'line', context: context(), line: line()})); },
    audioFailure() { failedAudioLine = true; this.publish(); },
    resetCaption() { failedAudioLine = false; revision++; sockets.at(-1).send(JSON.stringify({type: 'line_deleted', context: context(), line_id: 2})); this.publish(); }};
}

async function installFixture(context, state) {
  await context.addInitScript(() => {
    const nativePlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function(...args) {
      window.__r19LastAudio = this;
      return nativePlay.apply(this, args); // Observe the actual native decoder, without replacing it.
    };
  });
  await context.route('**/*', state.serve);
  await context.routeWebSocket(WS, socket => state.connect(socket));
}

async function seedStorage(page) {
  await page.evaluate(async expected => {
    localStorage.setItem('r19-frontend-continuity', expected.sentinel);
    localStorage.setItem('proxy-transcript-reading-mode', expected.mode);
    localStorage.setItem('proxy-transcript-playback-rate', expected.playback);
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('proxy-mobile-library', 2);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('state')) request.result.createObjectStore('state'); };
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
    });
    try { await new Promise((resolve, reject) => {
      const tx = db.transaction('state', 'readwrite'); tx.objectStore('state').put(expected.record, 'r19-frontend-continuity');
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
    }); } finally { db.close(); }
    const root = await navigator.storage.getDirectory();
    const folder = await root.getDirectoryHandle('r19-frontend-continuity', {create: true});
    const file = await folder.getFileHandle('authored.txt', {create: true});
    const writer = await file.createWritable(); await writer.write(expected.opfs); await writer.close();
  }, STORAGE);
}

async function readStorage(page) {
  return page.evaluate(async () => {
    const db = await new Promise((resolve, reject) => { const request = indexedDB.open('proxy-mobile-library', 2);
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
    let record;
    try { record = await new Promise((resolve, reject) => { const request = db.transaction('state').objectStore('state').get('r19-frontend-continuity');
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }); } finally { db.close(); }
    const folder = await (await navigator.storage.getDirectory()).getDirectoryHandle('r19-frontend-continuity');
    return {origin: location.origin, sentinel: localStorage.getItem('r19-frontend-continuity'),
      mode: localStorage.getItem('proxy-transcript-reading-mode'), playback: localStorage.getItem('proxy-transcript-playback-rate'), record,
      opfs: await (await (await folder.getFileHandle('authored.txt')).getFile()).text()};
  });
}

async function layoutMetrics(page) {
  await page.evaluate(async () => {
    await Promise.all([document.fonts.load('16px "Toolkit Geist"'), document.fonts.load('16px "Toolkit Geist Mono"')]);
    await document.fonts.ready;
  });
  return page.evaluate(() => {
    const box = selector => { const bounds = document.querySelector(selector)?.getBoundingClientRect();
      return bounds ? {x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height} : null; };
    const lineCount = selector => {
      const node = document.querySelector(selector); if (!node) return 0;
      const range = document.createRange(); range.selectNodeContents(node);
      return new Set([...range.getClientRects()].filter(rect => rect.width > 0).map(rect => Math.round(rect.y))).size;
    };
    const source = document.querySelector('.current-line .current-chinese');
    return {viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth,
      shell: box('.companion-shell'), current: box('.current-line'), source: box('.current-line .current-chinese'),
      translation: box('.current-english'), actions: box('.current-actions'), sourceLineCount: lineCount('.current-line .current-chinese'),
      translationLineCount: lineCount('.current-english'), sourceFontSize: parseFloat(getComputedStyle(source).fontSize),
      bodyFont: getComputedStyle(document.body).fontFamily, fontsLoaded: document.fonts.status === 'loaded',
      localFontCount: [...document.fonts].filter(font => font.status === 'loaded').length,
      overflowing: [...document.querySelectorAll('body *')].map(node => ({node, bounds: node.getBoundingClientRect()}))
        .filter(({bounds}) => bounds.width > 0 && bounds.right > innerWidth + 1)
        .slice(0, 8).map(({node, bounds}) => ({tag: node.tagName, class: typeof node.className === 'string' ? node.className : '',
          right: bounds.right, width: bounds.width}))};
  });
}

async function comparePixels(page, before, after) {
  return page.evaluate(async ({before, after, threshold}) => {
    const decode = async encoded => {
      const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(encoded), value => value.charCodeAt(0))], {type: 'image/png'}));
      const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
      const context = canvas.getContext('2d'); context.drawImage(bitmap, 0, 0); bitmap.close();
      return {width: canvas.width, height: canvas.height, pixels: context.getImageData(0, 0, canvas.width, canvas.height).data};
    };
    const left = await decode(before), right = await decode(after);
    if (left.width !== right.width || left.height !== right.height) return {sameSize: false};
    let changed = 0, total = 0;
    for (let offset = 0; offset < left.pixels.length; offset += 4) {
      let different = false;
      for (let channel = 0; channel < 3; channel++) { const delta = Math.abs(left.pixels[offset + channel] - right.pixels[offset + channel]);
        total += delta; if (delta > threshold) different = true; }
      if (different) changed++;
    }
    return {sameSize: true, changedRatio: changed / (left.width * left.height), meanDelta: total / (left.width * left.height * 3)};
  }, {before: before.toString('base64'), after: after.toString('base64'), threshold: PIXEL_LIMITS.channelDelta});
}

async function exercisePage(page, state, label, output) {
  await page.getByRole('heading', {name: 'Game immersion toolkit', exact: true}).waitFor();
  await page.getByLabel('Reading', {exact: true}).selectOption('migaku');
  await page.locator('.current-line .current-chinese').filter({hasText: SOURCE_TEXT}).waitFor();
  assert.equal(await page.locator('.current-line .reading-hanzi').count(), 0, 'Independent Migaku mode unexpectedly invoked the API reader');
  const screenshots = [], geometry = [];
  for (const [width, height, zoom] of [[1280, 900, 1], [800, 720, 1.25]]) {
    await page.setViewportSize({width, height});
    await page.evaluate(zoom => { document.documentElement.style.zoom = String(zoom); }, zoom);
    const metrics = await layoutMetrics(page);
    try { assertLayoutBounds(metrics); } catch (error) {
      await page.screenshot({path: join(output, label + '-bounds-failure.png'), animations: 'disabled'});
      throw new Error(label + ' ' + width + ' CSS zoom ' + zoom + ': ' + error.message + ' ' + JSON.stringify(metrics), {cause: error});
    }
    geometry.push({width, height, cssZoom: zoom, ...metrics});
    screenshots.push(await page.screenshot({path: join(output, label + '-' + width + '.png'), animations: 'disabled'}));
  }
  await page.evaluate(() => { document.documentElement.style.zoom = '1'; });
  await page.setViewportSize({width: 1280, height: 900});
  await page.getByRole('button', {name: 'Settings', exact: true}).click();
  const setup = page.getByRole('dialog', {name: 'Settings', exact: true});
  await setup.getByRole('button', {name: 'General & Updates', exact: true}).click();
  await setup.getByRole('heading', {name: 'Toolkit updates and support', exact: true}).waitFor();
  await setup.getByLabel('Interface language', {exact: true}).selectOption('en');
  await page.keyboard.press('Escape'); await setup.waitFor({state: 'hidden'});
  await page.getByRole('button', {name: 'Capture setup', exact: true}).click();
  const capture = page.getByRole('dialog', {name: 'Capture setup', exact: true});
  await capture.getByLabel('Include unvoiced dialogue', {exact: true}).check();
  await capture.getByRole('button', {name: 'Save capture settings', exact: true}).click();
  await capture.waitFor({state: 'hidden'}); assert.equal(state.settings.capture_unvoiced, true);
  await page.getByLabel('Reading', {exact: true}).selectOption('lexirise');
  const word = page.locator('.current-line .reading-hanzi').first(); await word.waitFor(); await word.click();
  const popup = page.locator('.word-sheet'); await popup.waitFor();
  await popup.getByText('Authored greeting definition', {exact: true}).waitFor();
  assert(await popup.evaluate(element => { const bounds = element.getBoundingClientRect();
    return bounds.x >= 0 && bounds.y >= 0 && bounds.right <= innerWidth + 1 && bounds.bottom <= innerHeight + 1; }), 'Lookup portal does not fit the viewport');
  assert(await popup.evaluate(element => !document.querySelector('.current-line').contains(element)), 'Shared lookup did not use its production portal');
  const lookupScreenshot = await popup.screenshot({path: join(output, label + '-lookup.png'), animations: 'disabled'});
  await page.keyboard.press('Escape');
  await page.getByRole('button', {name: 'Play current voice line', exact: true}).click();
  await page.waitForFunction(() => { const audio = window.__r19LastAudio; return audio && !audio.paused && audio.currentTime > 0; });
  state.audio.broken = true;
  try {
    // A distinct authored record gives the failed resource its own real URL;
    // Firefox may reuse decoded media for a second element with the same URL.
    state.audioFailure();
    await page.locator('.current-line .current-chinese').filter({hasText: AUDIO_FAILURE_TEXT}).waitFor();
    await page.getByRole('button', {name: 'Play current voice line', exact: true}).click();
    await page.waitForFunction(() => window.__r19LastAudio?.error?.code > 0);
    await page.locator('.current-line .current-chinese').filter({hasText: SOURCE_TEXT}).waitFor();
    // The source currently leaves a native rejected play promise unhandled.
    // Record its bounded media error separately while preserving confirmed text;
    // this is not a claim that an actionable audio-error UI has been added.
    await delay(100);
  } finally { state.audio.broken = false; }
  const send = page.locator('.current-line .lexirise-send'); await send.click();
  await page.getByText('Authored export failure; no remote account was written.', {exact: true}).waitFor();
  assert.equal(await send.isEnabled(), true, 'Failed synthetic export did not become retryable');
  const previous = state.reconnect();
  // A routine update can replace only the socket while HTTP remains healthy.
  // Production retires account writes rather than relabelling that as offline.
  await page.waitForFunction(() => document.querySelector('.current-line .lexirise-send')?.disabled === true);
  await page.locator('.current-line .current-chinese').filter({hasText: SOURCE_TEXT}).waitFor();
  for (let tries = 0; state.sockets.length === previous && tries < 150; tries++) await delay(20);
  assert(state.sockets.length > previous, 'The production WebSocket did not reconnect');
  state.publish();
  await page.locator('.current-line .reading-hanzi').first().waitFor();
  await page.waitForFunction(() => document.querySelector('.current-line .lexirise-send')?.disabled === false);
  state.resetCaption();
  await page.waitForFunction(() => !document.querySelector('.current-line')?.textContent.includes('声音不可用的测试。'));
  assert.deepEqual(state.unexpected, []);
  return {screenshots, geometry, lookupScreenshot};
}

async function probeBuiltResources(page, manifest) {
  await page.locator('.desktop-sharing > summary').click();
  const [popup] = await Promise.all([page.waitForEvent('popup', {timeout: 10000}),
    page.getByRole('link', {name: 'More connection options', exact: true}).click()]);
  const mobileErrors = []; popup.on('pageerror', error => mobileErrors.push(error.message));
  try {
    await popup.getByRole('heading', {name: 'Game immersion toolkit', exact: true}).waitFor();
    assert.equal(new URL(popup.url()).pathname, '/mobile-capture/');
    assert.deepEqual(mobileErrors, []);
  } finally { await popup.close(); }
  const names = ['mobile-capture/library-worker.mjs', 'mobile-capture/ocr/verified-worker.js',
    'mobile-capture/ocr/core/tesseract-core.wasm', ...Object.keys(manifest.files).filter(name => /\.(?:ttf|woff2?)$/.test(name))];
  for (const name of names) {
    const result = await page.evaluate(async name => { const response = await fetch('/' + name);
      const bytes = await response.arrayBuffer(); return {status: response.status, mime: response.headers.get('content-type')?.split(';')[0],
        sha256: [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('')}; }, name);
    assert.equal(result.status, 200, 'Built resource unavailable: ' + name);
    assert.equal(result.mime, manifest.files[name].mime.split(';')[0], 'Built resource MIME mismatch: ' + name);
    assert.equal(result.sha256, manifest.files[name].sha256, 'URL did not serve its own built bytes: ' + name);
  }
  const worker = await page.evaluate(() => new Promise((resolve, reject) => {
    const worker = new Worker('/mobile-capture/library-worker.mjs', {type: 'module'});
    const timer = setTimeout(() => { worker.terminate(); reject(Error('Built library worker timed out')); }, 10000);
    worker.onerror = () => { clearTimeout(timer); worker.terminate(); reject(Error('Built library worker could not load')); };
    worker.onmessage = ({data}) => { if (data.id !== 'r19-worker') return; clearTimeout(timer); worker.terminate();
      data.error ? reject(Error(data.error)) : resolve(data.result); };
    worker.postMessage({id: 'r19-worker', action: 'restore'});
  }));
  assert(Array.isArray(worker.available), 'The built module worker did not execute its actual restore action');
  const ocr = await deadline(page.evaluate(async () => {
    const {loadModel} = await import('/mobile-capture/ocr-packs.mjs');
    const {default: Tesseract} = await import('/mobile-capture/ocr/tesseract.esm.min.js');
    const model = await loadModel('eng');
    const worker = await Tesseract.createWorker([model], 1, {workerPath: new URL('/mobile-capture/ocr/verified-worker.js', location.href).href,
      corePath: new URL('/mobile-capture/ocr/core/', location.href).href, cacheMethod: 'none', workerBlobURL: false});
    try { const canvas = document.createElement('canvas'); canvas.width = 700; canvas.height = 100;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 700, 100); ctx.fillStyle = 'black';
      ctx.font = '40px Arial'; ctx.fillText('The lantern is bright.', 25, 65); return (await worker.recognize(canvas)).data.text;
    } finally { await worker.terminate(); }
  }), 45000, 'Built English OCR worker');
  assert.match(ocr, /The lantern is bright/);
  const response = await page.request.get(ORIGIN);
  const csp = response.headers()['content-security-policy'];
  assert(csp && !/(?:^|\s)'unsafe-eval'(?:\s|;|$)/.test(csp), 'Static desktop lacks its non-eval CSP');
  assert(csp.includes("'wasm-unsafe-eval'"), 'The static CSP does not explicitly permit the shipped WASM worker');
  assert.equal(response.headers()['x-content-type-options'], 'nosniff');
  assert.equal((await page.request.get(ORIGIN + '/missing-r19-module.mjs')).status(), 404);
  return {mobileProductionLink: 'passed', moduleWorker: 'passed', englishOcr: 'passed', csp: 'passed', resourceCount: names.length};
}

async function requireVacantCanonicalPort() {
  const probe = net.createServer();
  await new Promise((resolve, reject) => { probe.once('error', error => reject(Error(error.code === 'EADDRINUSE'
      ? 'Canonical port 3000 is busy; no existing process was touched.'
      : 'Canonical loopback binding is unavailable (' + error.code + '); no existing process was touched.')));
    probe.listen(3000, '127.0.0.1', resolve); });
  await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
}

function retainedFixture(temporary, template) {
  const root = join(temporary, 'retained-authored-build'); mkdirSync(root);
  const bytes = Buffer.from("export const retainedR19 = 'authored old chunk';\n");
  const name = 'assets/retained-' + sha256(bytes).slice(0, 16) + '.js';
  const files = {};
  for (const [path, content, mime] of [['index.html', Buffer.from('<!doctype html><title>Owned retired fixture</title>'), 'text/html; charset=utf-8'],
    [name, bytes, 'text/javascript; charset=utf-8']]) {
    mkdirSync(dirname(join(root, path)), {recursive: true}); writeFileSync(join(root, path), content);
    files[path] = {bytes: content.length, mime, sha256: sha256(content)};
  }
  const ordered = Object.fromEntries(Object.keys(files).sort().map(name => [name, files[name]]));
  const manifest = {...template, files, build_id: sha256(JSON.stringify(ordered))};
  writeFileSync(join(root, 'desktop-manifest.json'), JSON.stringify(manifest));
  return {root, name, bytes};
}

async function startStatic(root, retained, sourceRoot) {
  const args = ['-B', '-m', 'backend.desktop_frontend', '--root', root, '--port', '3000'];
  for (const path of retained) args.push('--retained-root', path);
  const child = spawn(resolvePython({root: sourceRoot}).command, args, {cwd: sourceRoot, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe']});
  let stopped, output = '', errors = '';
  child.stderr.on('data', value => { errors = (errors + value).slice(-4000); });
  const stop = () => stopped ??= stopOwnedProcess(child);
  try {
    const ready = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Owned static frontend startup timed out')), 15000);
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', () => { clearTimeout(timer); reject(Error('Owned static frontend exited before readiness')); });
      child.stdout.on('data', value => { output += value; if (!output.includes('\n')) return;
        clearTimeout(timer); try { resolve(JSON.parse(output.split('\n')[0])); } catch { reject(Error('Invalid static host readiness')); } });
    });
    assert.equal(ready.port, 3000); assert.equal(ready.ready, true);
    return {stop, ready};
  } catch (error) { await stop(); throw new Error(error.message + (errors ? ': ' + errors.replaceAll(root, '<built-root>') : '')); }
}

export async function runFrontendEquivalence({root = process.cwd(), desktopRoot = join(root, 'output/desktop-frontend'),
  browsers = ['chromium', 'firefox'], reportPath = join(root, 'output/checks/r19-frontend-equivalence.json')} = {}) {
  root = resolve(root); desktopRoot = resolve(desktopRoot);
  assert(browsers.length && browsers.every(name => ['chromium', 'firefox'].includes(name)), 'Only supported comparison browsers are accepted');
  const manifest = readDesktopManifest(desktopRoot);
  assert(existsSync(join(root, 'dist/server/wrangler.json')), 'Build the canonical source frontend before comparison');
  const {chromium, firefox} = await import('playwright');
  const engines = {chromium, firefox};
  const temporary = realpathSync(mkdtempSync(join(tmpdir(), 'r19-frontend-equivalence-')));
  const retained = retainedFixture(temporary, manifest);
  const screenshots = join(root, 'output/playwright/r19-frontend'); mkdirSync(screenshots, {recursive: true});
  let source, sourcePending, staticHost, staticPending, cleanupPromise, interruptedFlag = false;
  const sessions = [];
  const report = {schema: 'proxy-r19-frontend-equivalence-v1', source_commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(),
    desktop_build_id: manifest.build_id, manifest_sha256: sha256(readFileSync(join(desktopRoot, 'desktop-manifest.json'))),
    origin: ORIGIN, api: API, websocket: WS, platform: process.platform, node: process.version,
    playwright: JSON.parse(readFileSync(join(root, 'node_modules/playwright/package.json'), 'utf8')).version,
    browsers: {}, status: 'running', r19_complete: false,
    real_user_profile: 'not-accessed', extension_compatibility: 'unavailable', native_windows_11: 'unavailable'};
  const cleanup = () => cleanupPromise ??= (async () => {
    // Register pending launches before awaiting them: interruption during startup
    // must still close the eventual owned browser/server, not orphan it.
    const results = await Promise.allSettled([
      ...sessions.map(async session => (await session.pendingContext?.catch(() => null))?.close()),
      sourcePending?.then(server => server.stop()), staticPending?.then(server => server.stop()),
    ]);
    if (results.some(result => result.status === 'rejected')) throw new Error('Owned frontend/browser cleanup could not be confirmed; fixture retained');
    await rm(temporary, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
  })();
  const notInterrupted = () => assert(!interruptedFlag, 'The owned frontend probe was interrupted');
  const interrupted = () => { interruptedFlag = true; void cleanup().catch(() => { process.exitCode = 1; }); };
  process.on('SIGINT', interrupted); process.on('SIGTERM', interrupted);
  try {
    await requireVacantCanonicalPort();
    notInterrupted();
    sourcePending = startOwnedServer({name: 'r19-frontend-source', cwd: root, args: runtime => [join(root, 'node_modules/wrangler/bin/wrangler.js'),
      'dev', '--config', join(root, 'dist/server/wrangler.json'), '--ip', '127.0.0.1', '--port', '3000', '--inspector-port', '0', '--persist-to', join(runtime, 'persist')]});
    source = await sourcePending; notInterrupted();
    assert.equal(source.port, 3000, 'The canonical source host did not own the required origin');
    console.log('R19 frontend: the owned canonical source host is ready');
    for (const name of browsers) {
      const profile = join(temporary, name), state = fixture(), errors = [];
      notInterrupted();
      const session = {name, profile, state, errors, sourceChunks: new Set()}; sessions.push(session);
      session.pendingContext = engines[name].launchPersistentContext(profile, {headless: true, locale: 'en-US', viewport: {width: 1280, height: 900},
        serviceWorkers: 'block', handleSIGINT: false, handleSIGTERM: false});
      const context = session.context = await session.pendingContext; notInterrupted(); await installFixture(context, state);
      const page = session.page = context.pages()[0] ?? await context.newPage();
      page.on('response', response => {
        const url = new URL(response.url());
        if (url.origin === ORIGIN && url.pathname.startsWith('/_next/static/') && /\.(?:js|css)$/.test(url.pathname)) session.sourceChunks.add(url.pathname.slice(1));
      });
      page.on('pageerror', error => {
        if (state.audio.broken && /NotSupportedError|no supported source|media resource.*not suitable|resource.*unsupported/i.test(error.message)) state.audio.expectedErrors++;
        else errors.push(error.message);
      });
      await page.goto(ORIGIN, {timeout: 30000});
      session.before = await exercisePage(page, state, name + '-source', screenshots);
      await page.getByLabel('Voice playback speed', {exact: true}).selectOption(STORAGE.playback);
      await seedStorage(page); assertStorageContinuity(await readStorage(page));
      console.log(name + ': source UI and authored localStorage/IndexedDB/OPFS state prepared');
    }
    await source.stop(); source = null;
    notInterrupted(); staticPending = startStatic(desktopRoot, [retained.root], root);
    staticHost = await staticPending; notInterrupted();
    assert.equal(staticHost.ready.build_id, manifest.build_id);
    console.log('R19 frontend: source host replaced by the owned static host at the same origin');
    for (const session of sessions) {
      const {name, page, state} = session;
      await page.reload({timeout: 30000}); assertStorageContinuity(await readStorage(page));
      assert.equal(await page.getByLabel('Reading', {exact: true}).inputValue(), STORAGE.mode);
      const after = await exercisePage(page, state, name + '-static', screenshots), pixels = [];
      for (let index = 0; index < after.screenshots.length; index++) {
        assert.equal(after.geometry[index].bodyFont, session.before.geometry[index].bodyFont, 'Source/static UI font family changed');
        const result = await comparePixels(page, session.before.screenshots[index], after.screenshots[index]); assertPixelComparison(result); pixels.push(result);
      }
      const lookupPixels = await comparePixels(page, session.before.lookupScreenshot, after.lookupScreenshot);
      assertPixelComparison(lookupPixels);
      console.log(name + ': static UI and fixed screenshot comparison passed; checking actual built workers/WASM');
      const assets = await probeBuiltResources(page, manifest);
      assert(session.sourceChunks.size > 0, 'The source did not expose its hashed client assets');
      for (const name of session.sourceChunks) {
        assert(manifest.files[name], 'The static build omitted an old source-client chunk: ' + name);
        const response = await page.request.get(ORIGIN + '/' + name + '?r19-retained=1');
        assert.equal(response.status(), 200);
        assert.equal(sha256(await response.body()), manifest.files[name].sha256, 'Old source-client chunk changed after host replacement');
      }
      const retired = await page.request.get(ORIGIN + '/' + retained.name);
      assert.equal(retired.status(), 200); assert.equal(sha256(await retired.body()), sha256(retained.bytes));
      assert.match(retired.headers()['cache-control'], /immutable/);
      await page.getByLabel('Voice playback speed', {exact: true}).selectOption(STORAGE.playback);
      assertStorageContinuity(await readStorage(page));
      await session.context.close();
      notInterrupted();
      session.pendingContext = engines[name].launchPersistentContext(session.profile, {headless: true, locale: 'en-US', viewport: {width: 1280, height: 900},
        serviceWorkers: 'block', handleSIGINT: false, handleSIGTERM: false});
      session.context = await session.pendingContext; notInterrupted();
      await installFixture(session.context, state);
      const reopened = session.context.pages()[0] ?? await session.context.newPage(); reopened.on('pageerror', error => session.errors.push(error.message));
      await reopened.goto(ORIGIN); await reopened.getByRole('heading', {name: 'Game immersion toolkit', exact: true}).waitFor();
      assertStorageContinuity(await readStorage(reopened)); assert.deepEqual(session.errors, []); assert.deepEqual(state.unexpected, []);
      report.browsers[name] = {sourceAndStaticUi: 'passed', sameContextHostSwap: 'passed', browserRestartStorage: 'passed',
        localStorage: 'passed', indexedDB: 'passed', opfs: 'passed', cssZooms: [1, 1.25], pixels, lookupPixels, assets,
        browserVersion: session.context.browser()?.version() ?? 'unavailable', serviceWorkerPolicy: 'blocked-in-test-context',
        geometry: {source: session.before.geometry, static: after.geometry},
        audioFailureTextRetention: 'passed', sourceAudioErrorUi: 'unhandled-native-play-error-baseline', nativeAudioErrorsObserved: state.audio.expectedErrors,
        oldSourceChunks: session.sourceChunks.size, retainedImmutableChunk: 'passed',
        apiWrites: state.writes.map(({path, method}) => ({path, method})), remoteAccountWrites: 0};
      console.log(name + ': source/static UI, same-origin storage, restart, layout/pixels and built workers/WASM passed');
    }
    report.status = 'passed';
  } catch (error) { report.status = 'failed'; throw error; }
  finally {
    try { await cleanup(); report.ownedCleanup = 'passed'; }
    catch (error) { report.status = 'failed'; report.ownedCleanup = 'unconfirmed'; throw error; }
    finally { process.off('SIGINT', interrupted); process.off('SIGTERM', interrupted);
      mkdirSync(dirname(reportPath), {recursive: true}); writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n'); }
  }
  return report;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), value = key => { const index = args.indexOf(key); return index < 0 ? undefined : args[index + 1]; };
  await runFrontendEquivalence({desktopRoot: value('--desktop-root'), reportPath: value('--report'),
    ...(value('--browsers') ? {browsers: value('--browsers').split(',')} : {})});
}
