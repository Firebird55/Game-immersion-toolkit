import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredBrowserHistoryBackup, migrationRows} from '../scripts/android-browser-migration-ui.mjs';

test('native migration fixture uses the real exporter whitelist and retains bounded mixed history', () => {
  const raw = authoredBrowserHistoryBackup(), value = JSON.parse(raw);
  assert.ok(raw.length < 65536);assert.equal(value.format, 'toolkit-browser-history-v1');
  assert.equal(value.rows.length, migrationRows);
  assert.equal(value.rows.filter(row => row.favorite).length, 1);
  assert.equal(value.rows.filter(row => row.textTruncated).length, 1);
  assert.deepEqual([...new Set(value.rows.map(row => row.source))], ['mobile-ocr', 'pc-1234567890abcdef']);
  assert.ok(value.rows.every(row => row.hadAudio === true));
  assert.doesNotMatch(raw.toString(), /rememberedKey|viewerLink|private-vault|private-stream/);
});
