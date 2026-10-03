import { test } from 'node:test';
import assert from 'node:assert/strict';
import { appliesToWord, unknownWordGrammar, grammarUrl } from '../app/grammar-rules.ts';

const rule = (slug, proficiency, spans) => ({ slug, proficiency, spans });
test('Definition includes unknown rules anchored to the pressed occurrence, not another copy of the word', () => {
  const rules = [rule('unknown', 0, [{ start: 3, end: 4 }]),
    rule('learning', 2, [{ start: 3, end: 4 }]),
    rule('known', 4, [{ start: 3, end: 4 }]),
    rule('elsewhere', 0, [{ start: 8, end: 9 }])];
  assert.deepEqual(unknownWordGrammar(rules, 3, 4).map(value => value.slug), ['unknown', 'learning']);
  assert.equal(appliesToWord(rules[0], 4, 5), false);
  assert.equal(appliesToWord(rules[0], 2, 4), true);
});
test('rule links use the official Chinese grammar pages and escape path content', () => {
  assert.equal(grammarUrl('de-hua'), 'https://lexirise.app/learn/zh/grammar/de-hua');
  assert.equal(grammarUrl('bad/path?'), 'https://lexirise.app/learn/zh/grammar/bad%2Fpath%3F');
});
