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

async function installHitoFixture(page) {
  const snapshot = {
    capture: { running: true, active_game: 'hito', phase: 'matched', message: 'Hito matched',
      visible_text_ids: [fixtureLine.text_id], last_ocr: fixtureLine.chinese },
    textmaps: { ready: true, entry_count: 1 },
    game_textmaps: { hito: { ready: true, entry_count: 1750 } },
    settings: { preferred_game: 'auto', region: {}, tip_region: {}, cinematic_region: {},
      hito_region: {}, hito_tip_region: {} },
    session: { id: fixtureLine.session_id, line_count: 1, total_line_count: 1 },
  };
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    let json = {};
    if (url.pathname === '/api/status') json = snapshot;
    if (url.pathname === '/api/lexirise') json = { configured: true, sent: {} };
    if (url.pathname === '/api/agents') json = { lines: [], total: 0 };
    if (url.pathname === '/api/lines' || url.pathname === '/api/favorites')
      json = url.pathname === '/api/lines' && url.searchParams.get('game') === 'hito' ? [fixtureLine] : [];
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
