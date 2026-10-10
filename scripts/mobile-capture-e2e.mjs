import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync, mkdirSync } from 'node:fs';
import { chromium, firefox } from 'playwright';

const root = new URL('../public/mobile-capture/', import.meta.url);
const files = new Map([['/', 'index.html'], ['/capture.js', 'capture.js'], ['/core.mjs', 'core.mjs'], ['/style.css', 'style.css']]);
const server = http.createServer((req, res) => {
  const file = files.get(req.url);
  if (!file) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', file.endsWith('html') ? 'text/html' : file.endsWith('css') ? 'text/css' : 'text/javascript');
  res.end(readFileSync(new URL(file, root)));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
mkdirSync('output/playwright', { recursive: true });
let browser;
try {
  for (const [name, engine] of [['chromium', chromium], ['firefox', firefox]]) {
    browser = await engine.launch({ headless: true });
    const errors = [];
    const context = await browser.newContext({ acceptDownloads: true });
    context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
    const sender = await context.newPage(), receiver = await context.newPage();
    // Synthetic capture supplies pixels only. Pairing uses real browser WebRTC.
    await sender.addInitScript(() => {
      navigator.mediaDevices.getDisplayMedia = async () => {
        if (window.denyCapture) throw new DOMException('Permission denied', 'NotAllowedError');
        const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
        const ctx = canvas.getContext('2d'); let i = 0;
        setInterval(() => {
          ctx.fillStyle = window.blackCapture ? '#000' : `rgb(${i++ % 255},100,180)`;
          ctx.fillRect(0, 0, 640, 360);
          if (!window.blackCapture) { ctx.fillStyle = '#fff'; ctx.font = '32px sans-serif'; ctx.fillText('Game subtitle fixture', 60, 280); }
        }, 100);
        return canvas.captureStream(10);
      };
    });
    await sender.goto(url); await receiver.goto(url);
    for (const [width, height, scale] of [[320, 568, 1], [390, 844, 1], [768, 1024, 1], [1920, 1080, 2]]) {
      await receiver.setViewportSize({ width, height });
      await receiver.evaluate(scale => { document.body.style.zoom = String(scale); }, scale);
      assert(await receiver.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: layout fits ${width}, zoom ${scale}`);
    }
    await receiver.evaluate(() => { document.body.style.zoom = '1'; });
    await receiver.setViewportSize({ width: 390, height: 844 });
    await receiver.selectOption('#role', 'receiver');
    await receiver.fill('#incoming', '{invalid'); await receiver.click('#apply');
    assert.match(await receiver.locator('#status').innerText(), /valid pairing/);
    await sender.evaluate(() => { window.denyCapture = true; });
    await sender.click('#start');
    await sender.getByText('Cannot start capture: Permission denied', { exact: true }).waitFor();
    assert.equal(await sender.locator('#start').isEnabled(), true);
    await sender.evaluate(() => { window.denyCapture = false; });
    await sender.click('#start');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    await receiver.fill('#incoming', await sender.locator('#outgoing').inputValue());
    await receiver.click('#apply');
    await receiver.waitForFunction(() => document.getElementById('outgoing').value.includes('"answer"'));
    await sender.fill('#incoming', await receiver.locator('#outgoing').inputValue());
    await sender.click('#apply');
    await receiver.bringToFront();
    await receiver.waitForFunction(() => document.getElementById('preview').videoWidth > 0, { timeout: 20000 });
    try {
      await receiver.waitForFunction(() => /Receiving frames/.test(document.getElementById('metrics').textContent));
    } catch (error) {
      console.error(name, await receiver.evaluate(() => ({ metrics: document.getElementById('metrics').textContent, status: document.getElementById('status').textContent, paused: document.getElementById('preview').paused, time: document.getElementById('preview').currentTime, hidden: document.hidden })));
      throw error;
    }
    await receiver.click('#begin-test');
    await receiver.waitForFunction(() => /[1-9][0-9]* visible changes/.test(document.getElementById('metrics').textContent));
    await receiver.screenshot({ path: `output/playwright/mobile-capture-${name}.png`, fullPage: true });
    await sender.evaluate(() => { window.blackCapture = true; });
    await receiver.waitForFunction(() => document.getElementById('metrics').textContent.includes('Image appears black'));
    const downloadPromise = receiver.waitForEvent('download');
    await receiver.click('#report');
    const download = await downloadPromise;
    const report = JSON.parse(readFileSync(await download.path(), 'utf8'));
    assert(report.deliveredFrames > 0 && report.visibleChanges > 0);
    assert(report.observation.frames > 0 && report.observation.darkSamples > 0);
    assert.equal(report.backgroundCaptureVerified, false);
    assert.equal(report.userObservation, 'not_verified');
    assert(!JSON.stringify(report).includes('v=0'), 'Report excludes SDP');
    await receiver.evaluate(() => document.getElementById('preview').pause());
    await receiver.waitForFunction(() => document.getElementById('metrics').textContent.includes('Frame delivery stalled'));
    await receiver.click('#stop');
    assert.match(await receiver.locator('#metrics').innerText(), /^Stopped/);
    assert.equal(await receiver.locator('#role').isEnabled(), true);
    assert.equal(await receiver.locator('#outgoing').inputValue(), '');
    assert.equal(await receiver.locator('#begin-test').isEnabled(), false);
    await sender.click('#stop');
    // A second session verifies cleanup and reconnect do not retain old metrics.
    await sender.click('#start');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    await sender.click('#stop');
    assert.equal(await sender.locator('#start').isEnabled(), true);
    assert.deepEqual(errors, [], `${name}: no uncaught browser errors`);
    await context.close(); await browser.close(); browser = null;
    console.log(`${name}: mobile layouts, denied permission, malformed pairing, real WebRTC video, black-frame report, stalls, cleanup and restart passed`);
  }
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
