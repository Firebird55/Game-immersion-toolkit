import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const baseUrl = process.env.COMPANION_URL || 'http://localhost:3000';

const fixtureLine = {
  id: 1, game: 'hito', created_at: '2026-10-03T10:00:00Z', session_id: 'browser-test',
  english: 'I see a gate', chinese: '我 看到 一个 大门', text_id: 'hito:browser-test',
  source_ocr: '', score: 100, match_kind: 'exact', channel: 'dialogue',
  voiced: false, has_audio: false, favorite: false,
};

async function installHitoFixture(page, line = fixtureLine) {
  const snapshot = {
    capture: { running: true, active_game: 'hito', phase: 'matched', message: 'Hito matched',
      visible_text_ids: [line.text_id], last_ocr: line.chinese },
    textmaps: { ready: true, entry_count: 1 },
    game_textmaps: { hito: { ready: true, entry_count: 1750 } },
    settings: { preferred_game: 'auto', region: {}, tip_region: {}, cinematic_region: {},
      hito_region: {}, hito_tip_region: {} },
    session: { id: line.session_id, line_count: 1, total_line_count: 1 },
  };
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    let json = {};
    if (url.pathname === '/api/status') json = snapshot;
    if (url.pathname === '/api/lexirise') json = { configured: true, sent: {} };
    if (url.pathname === '/api/agents') json = { lines: [], total: 0 };
    if (url.pathname.endsWith('/reading/characters')) json = { characters: [] };
    if (url.pathname.endsWith('/reading/lookup')) json = {
      translations: [], examples: [], dictionaries: [], alternateReadings: [], components: [],
    };
    if (url.pathname === '/api/lines' || url.pathname === '/api/favorites')
      json = url.pathname === '/api/lines' && url.searchParams.get('game') === 'hito' ? [line] : [];
    return route.fulfill({ json });
  });
  await page.routeWebSocket('**/api/ws', socket => {
    socket.send(JSON.stringify({ type: 'snapshot', snapshot }));
  });
}

test('companion loads offline across desktop, iPad, and mobile sizes', async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    await mkdir('output/hito-analysis', { recursive: true });
    for (const [name, width, height] of [['desktop', 1366, 900], ['ipad', 1024, 1366], ['mobile', 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const external = [];
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (['localhost', '127.0.0.1'].includes(url.hostname)) return route.continue();
        external.push(url.href);
        return route.abort();
      });
      await installHitoFixture(page);
      await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.locator('.current-chinese').waitFor({ timeout: 15000 });
      assert.deepEqual(external, []);
      assert.deepEqual(errors, []);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: `output/hito-analysis/companion-${name}.png`, fullPage: true });
      await page.close();
    }
  } finally {
    await browser.close();
  }
});

test('lookup shows only returned grammar and makes pronunciation tones readable', async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const line = { ...fixtureLine, chinese: '我 晕倒 了', english: 'I fainted' };
  const tokens = [
    { start: 0, end: 1, word: '我', pinyin: 'wǒ', zhuyin: 'ㄨㄛˇ', tones: [3], proficiency: 4, meaning: 'I' },
    { start: 2, end: 4, word: '晕倒', pinyin: 'yūndǎo', zhuyin: 'ㄩㄣ ㄉㄠˇ', tones: [1, 3], proficiency: 0, meaning: 'faint' },
    { start: 5, end: 6, word: '了', pinyin: 'le', zhuyin: 'ㄌㄜ˙', tones: [5], proficiency: 4, meaning: 'completed' },
  ];
  try {
    for (const [name, width, height] of [['desktop', 1366, 900], ['ipad', 1024, 1366], ['mobile', 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      await installHitoFixture(page, line);
      let pending = true;
      let grammar = [];
      await page.route('**/api/lines/*/reading', route => route.fulfill({ json: {
        text: line.chinese, tokens, analysisPending: pending, grammar,
      } }));
      await page.route('**/api/lines/*/reading/lookup?*', route => route.fulfill({ json: {
        translations: [{ meaning: 'faint', partOfSpeech: ['verb'], examples: [] }],
        examples: [], dictionaries: [], alternateReadings: [], components: [],
      } }));
      await page.addInitScript(() => {
        localStorage.setItem('proxy-transcript-reading-options', JSON.stringify({ pinyin: 'all', zhuyin: 'all', toneMarks: 'all' }));
      });
      await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
      await page.getByLabel('Reading source', { exact: true }).selectOption('lexirise');
      await page.getByRole('button', { name: '晕倒', exact: true }).click();
      const sheet = page.locator('.word-sheet');
      await sheet.waitFor();
      assert.equal(await sheet.getByText('Unknown grammar', { exact: true }).count(), 0);
      assert.equal(await sheet.getByText('Checking grammar…', { exact: true }).count(), 0);
      assert.equal(await sheet.getByRole('tab', { name: 'Grammar', exact: true }).count(), 0);
      assert.equal(await sheet.locator('.word-sheet-reading .pronunciation-tone').count(), 2);
      assert.equal(await sheet.locator('.word-sheet-zhuyin .pronunciation-tone').innerText(), 'ˇ');
      const sizes = await sheet.locator('.word-sheet-reading').evaluate(element => {
        const tone = element.querySelector('.pronunciation-tone');
        return { size: parseFloat(getComputedStyle(element).fontSize), weight: getComputedStyle(tone).fontWeight };
      });
      assert.ok(sizes.size >= 20);
      assert.ok(Number(sizes.weight) >= 800);
      assert.ok(await sheet.locator('.word-sheet-zhuyin .pronunciation-tone').evaluate(
        element => parseFloat(getComputedStyle(element).fontSize) >= 24));
      await page.screenshot({ path: `output/hito-analysis/lookup-tones-${name}.png`, fullPage: true });

      pending = false;
      grammar = [{ slug: 'le-completion', title: '...了', subtitle: 'Completed action or change of state',
        proficiency: 0, localOverride: false, spans: [{ start: 5, end: 6 }], examples: ['了'], level: 'HSK 1' }];
      const grammarTab = sheet.getByRole('tab', { name: 'Grammar', exact: true });
      await grammarTab.waitFor({ timeout: 10000 });
      assert.equal(await sheet.locator('.word-grammar-summary').count(), 0);
      await grammarTab.click();
      await sheet.getByText('Completed action or change of state', { exact: true }).waitFor();
      await sheet.getByRole('button', { name: 'Close word lookup', exact: true }).click();
      await page.getByRole('button', { name: '了', exact: true }).click();
      await sheet.locator('.word-grammar-summary').waitFor();
      assert.equal(await sheet.getByText('Unknown grammar', { exact: true }).count(), 1);
      assert.equal(await sheet.getByText('Checking grammar…', { exact: true }).count(), 0);
      await page.close();
    }

    const page = await browser.newPage();
    await installHitoFixture(page, line);
    await page.route('**/api/lines/*/reading', route => route.fulfill({ json: {
      text: line.chinese, tokens, analysisPending: false, grammar: [],
    } }));
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Reading source', { exact: true }).selectOption('lexirise');
    await page.getByRole('button', { name: '晕倒', exact: true }).click();
    await page.locator('.word-sheet').waitFor();
    assert.equal(await page.locator('.word-grammar-summary').count(), 0);
    assert.equal(await page.getByRole('tab', { name: 'Grammar', exact: true }).count(), 0);
  } finally {
    await browser.close();
  }
});

test('Hito transcript does not wait for failing or delayed unrelated collections', async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    await installHitoFixture(page);
    await page.route('**/api/agents', route => new Promise(resolve => {
      setTimeout(() => resolve(route.abort().catch(() => undefined)), 10000);
    }));
    await page.route('**/api/*?*game=pragmata', route => route.fulfill({ status: 500, body: 'Unavailable' }));
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.locator('.current-chinese').waitFor({ timeout: 4000 });
    assert.equal(await page.locator('[aria-busy="true"]').count(), 0);
  } finally {
    await browser.close();
  }
});

test('reading source switches both ways, restores preferences, and offers reading options for Hito', async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1024, height: 1366 } });
    await installHitoFixture(page);
    const text = fixtureLine.chinese;
    const start = text.search(/\p{Script=Han}/u);
    await page.route('**/api/lexirise', route => route.fulfill({ json: { configured: true, sent: {} } }));
    await page.route('**/api/lines/*/reading', route => route.fulfill({ json: {
      text, tokens: [{ start, end: start + 1, word: text.slice(start, start + 1),
        pinyin: 'test', zhuyin: '', tones: [1], proficiency: 0, meaning: 'test meaning', entryId: 7 }],
    } }));
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const source = page.getByLabel('Reading source', { exact: true });
    await source.selectOption('lexirise');
    await page.locator('.reading-token').first().waitFor();
    await page.getByRole('button', { name: 'Lexirise reading options', exact: true }).click();
    await page.getByLabel('Pinyin', { exact: true }).selectOption('all');
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await page.screenshot({ path: 'output/hito-analysis/companion-ipad-lexirise.png', fullPage: true });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('.reading-token').first().waitFor();
    assert.equal(await source.inputValue(), 'lexirise');
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('proxy-transcript-reading-options')).pinyin), 'all');
    await source.selectOption('migaku');
    await page.locator('.current-chinese:not(.reading-text)').waitFor();
    assert.equal(await page.locator('.reading-token').count(), 0);
  } finally {
    await browser.close();
  }
});
