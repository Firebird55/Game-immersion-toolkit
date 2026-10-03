import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const baseUrl = process.env.COMPANION_URL || 'http://localhost:3000';

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
