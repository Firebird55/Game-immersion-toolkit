import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countUnknownWords, restoreTranslationLimit, shouldHideTranslation } from '../app/translation-visibility.ts';

test('each threshold includes its boundary and excludes the next unknown word', () => {
  for (const limit of [0, 1, 2, 3]) {
    for (let count = 0; count <= 4; count++) {
      assert.equal(shouldHideTranslation(limit, count), count <= limit);
    }
    assert.equal(shouldHideTranslation(limit, null), false);
  }
  assert.equal(shouldHideTranslation('off', 0), false);
});

test('tracked, learning, fresh and unsaved occurrences count; Known and punctuation do not', () => {
  const text = '我我我我我，123！';
  const tokens = [0, 1, 2, 3, 4].map((proficiency, start) => ({ start, end: start + 1, proficiency }));
  tokens.push({ start: 5, end: 6, proficiency: 0 }, { start: 6, end: 9, proficiency: 0 });
  assert.equal(countUnknownWords(text, tokens), 4);
  assert.equal(countUnknownWords('你好！', [{ start: 0, end: 2, proficiency: 4 }]), 0);
  assert.equal(countUnknownWords('你好！', [{ start: 0, end: 2, proficiency: 3 }]), 1);
});

test('missing or incomplete analysis never hides English as an all-known line', () => {
  assert.equal(countUnknownWords('你好！', []), null);
  assert.equal(countUnknownWords('你好！', [{ start: 0, end: 1, proficiency: 4 }]), null);
  assert.equal(countUnknownWords('你好！', [{ start: 1, end: 2, proficiency: 4 }]), null);
  assert.equal(countUnknownWords('你好！', [{ start: 0, end: 9, proficiency: 4 }]), null);
  assert.equal(countUnknownWords('...123!', []), null);
});

test('saved zero survives restoration while old or invalid settings default to Always show', () => {
  for (const limit of [0, 1, 2, 3]) assert.equal(restoreTranslationLimit(limit), limit);
  for (const invalid of [undefined, null, 'off', '0', -1, 4, 1.5, true]) {
    assert.equal(restoreTranslationLimit(invalid), 'off');
  }
});
