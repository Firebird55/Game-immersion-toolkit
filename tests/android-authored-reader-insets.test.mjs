import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredReaderBounds} from '../scripts/android-authored-reader-insets.mjs';

const app = 'io.github.firebird55.gameimmersiontoolkit.debug';
const xml = (rotation, bounds) => `<hierarchy rotation="${rotation}"><node package="${app}" class="android.webkit.WebView" bounds="${bounds}" /></hierarchy>`;
test('native insets proof rejects obscured, impossible or foreign reader bounds', () => {
  assert.deepEqual(authoredReaderBounds(xml(0, '[0,60][1080,2300]'), 1080, 2400, app).reader, [0, 60, 1080, 2300]);
  assert.deepEqual(authoredReaderBounds(xml(1, '[0,60][2300,1080]'), 1080, 2400, app).reader, [0, 60, 2300, 1080]);
  for (const bounds of ['[0,0][1080,2400]', '[0,60][1080,2400]', '[0,0][1080,2300]', '[0,60][9999,2300]'])
    assert.throws(() => authoredReaderBounds(xml(0, bounds), 1080, 2400, app));
  assert.equal(authoredReaderBounds(xml(0, '[0,60][1080,2300]').replace(app, 'another.application'), 1080, 2400, app), null);
  assert.throws(() => authoredReaderBounds(xml(0, '[0,60][1080,2300]'), 1080, 2400, 'another.application'));
});
