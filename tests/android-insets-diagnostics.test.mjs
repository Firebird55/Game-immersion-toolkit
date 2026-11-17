import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {numericInsetsSample, createInsetsDiagnostics} from '../scripts/android-insets-diagnostics.mjs';
const app = 'io.github.firebird55.gameimmersiontoolkit.debug';
const xml = `<hierarchy rotation="1"><node package="${app}" class="android.webkit.WebView" bounds="[0,60][2300,1080]" text="PRIVATE_SENTINEL" />
<node package="com.android.systemui" resource-id="com.android.systemui:id/navigation_bar_frame" bounds="[2300,0][2400,1080]" content-desc="PRIVATE_SENTINEL" /></hierarchy>`;
test('rotation evidence keeps numeric geometry and strict original validation only', () => {
  const sample = numericInsetsSample(xml, [1080, 2400], 1, app);
  assert.equal(sample.strict_bounds_passed, true); assert.equal(sample.hierarchy_rotation, 1);
  assert.deepEqual(sample.reader_bounds, [[0, 60, 2300, 1080]]);
  assert.deepEqual(sample.system_bar_bounds, [{kind: 'navigation', bounds: [2300, 0, 2400, 1080]}]);
  assert.equal(JSON.stringify(sample).includes('PRIVATE_SENTINEL'), false);
  assert.equal(numericInsetsSample(xml.replace('[0,60][2300,1080]', '[0,0][2400,1080]'), [1080, 2400], 1, app).strict_bounds_passed, false);
  assert.equal(numericInsetsSample(xml.replaceAll(app, 'foreign.app'), [1080, 2400], 1, app).strict_bounds_passed, false);
  const negative = numericInsetsSample(xml.replace('[0,60]', '[-10,60]'), [1080, 2400], 1, app);
  assert.deepEqual(negative.reader_bounds, [[-10, 60, 2300, 1080]]); assert.equal(negative.strict_bounds_passed, false);
});
test('observer classifies idle failures without storing UI or error text', () => {
  const output = mkdtempSync(join(tmpdir(), 'toolkit-insets-diagnostic-'));
  try {
    const observer = createInsetsDiagnostics({output, sourceCommit: 'a'.repeat(40), apkSha256: 'b'.repeat(64), packageName: app});
    observer.record(['shell', 'wm', 'size'], 'Physical size: 1080x2400');
    observer.record(['shell', 'settings', 'put', 'system', 'user_rotation', '1'], '');
    observer.failed(['shell', 'uiautomator', 'dump', '/sdcard/toolkit-authored-insets.xml'], {status: 1, stderr: 'ERROR: could not get idle state. PRIVATE_SENTINEL'});
    observer.record(['shell', 'cat', '/sdcard/toolkit-authored-insets.xml'], xml);
    observer.record(['shell', 'run-as', app, 'cat', 'unrelated'], 'PRIVATE_SENTINEL');
    const raw = readFileSync(join(output, 'android-insets-diagnostic.json'), 'utf8'), report = JSON.parse(raw);
    assert.equal(raw.includes('PRIVATE_SENTINEL'), false);
    assert.equal(report.failures[0].error_code, 'idle_timeout');
    assert.equal(report.samples[0].dump.completed, false);
    assert.equal(report.samples[0].requested_rotation, 1);
    assert.equal(report.production_fix_acceptance, false);
  } finally {rmSync(output, {recursive: true, force: true});}
});
