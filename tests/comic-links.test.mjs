import assert from 'node:assert/strict';
import test from 'node:test';
import { comicVoicePairs, uniqueComicLinks } from '../scripts/comic-links.mjs';

// Synthetic Odin records only; no game assets, dialogue or voice data.
const guid = 'a'.repeat(32);
const source = 'VO_Comic/VO_Test/Comic_Test_001';
function string(value, width = 2) {
  const header = Buffer.alloc(5);
  header[0] = width - 1;
  header.writeUInt32LE(value.length, 1);
  return Buffer.concat([header, Buffer.from(value, width === 2 ? 'utf16le' : 'latin1')]);
}
const named = (name, value, width) => Buffer.concat([Buffer.from([0x27]), string(name, width), string(value, width)]);
function dictionary(pairs, width = 2, field = 'guidToData') {
  const count = Buffer.alloc(9); count[0] = 0x06; count.writeBigUInt64LE(BigInt(pairs.length), 1);
  return Buffer.concat([
    Buffer.from([0x01]), string(field, width), Buffer.from([0x2f, 0, 0, 0, 0]),
    string('System.Collections.Generic.Dictionary`2[[System.String, mscorlib],[System.String, mscorlib]], mscorlib', width),
    Buffer.alloc(4), count,
    ...pairs.flatMap(([key, value]) => [Buffer.from([0x04, 0x2e]), named('$k', key, width), named('$v', value, width), Buffer.from([0x05])]),
    Buffer.from([0x07, 0x05]),
  ]);
}

test('comic links come from complete explicit dictionary entries in either string encoding', () => {
  for (const width of [1, 2]) {
    assert.deepEqual(comicVoicePairs(dictionary([[guid, source], ['b'.repeat(32), 'unvoiced']], width)), [{ text_id: `Comic_${guid}`, source }]);
  }
});

test('unrelated, partial and malformed dictionaries never supply links', () => {
  assert.deepEqual(comicVoicePairs(dictionary([[guid, source]], 2, 'unrelated')), []);
  assert.deepEqual(comicVoicePairs(Buffer.concat([string(guid), string(source)])), []);
  const valid = dictionary([[guid, source]]);
  for (const end of [valid.length - 1, valid.length - 2, valid.length - 10]) assert.deepEqual(comicVoicePairs(valid.subarray(0, end)), []);
  assert.deepEqual(comicVoicePairs(dictionary([[guid, source], ['invalid', source]])), []);
  assert.deepEqual(comicVoicePairs(dictionary([[guid, '../Comic_Test']])), []);
  const corrupt = Buffer.from(valid); corrupt.writeUInt32LE(0xffffffff, 2);
  assert.deepEqual(comicVoicePairs(corrupt), []);
});

test('conflicting text or voice associations are rejected across blocks, duplicates deduplicated', () => {
  const pair = { text_id: `Comic_${guid}`, source };
  assert.deepEqual(uniqueComicLinks([pair, { ...pair, source: source.toLowerCase() }]), [{ ...pair, source: source.toLowerCase() }]);
  assert.deepEqual(uniqueComicLinks([pair, { ...pair, source: 'VO_Comic/VO_Test/Comic_Test_002' }]), []);
  assert.deepEqual(uniqueComicLinks([pair, { ...pair, text_id: `Comic_${'b'.repeat(32)}` }]), []);
});

test('authored protagonist variants survive dictionary extraction without choosing a voice',()=>{
  const variants='{M#'+source+'}{F#VO_Comic/VO_Other/Comic_Test_001}';
  assert.deepEqual(comicVoicePairs(dictionary([[guid,variants]])),[{text_id:`Comic_${guid}`,source:variants}]);
  assert.deepEqual(comicVoicePairs(dictionary([[guid,variants+'unrelated']])),[]);
  assert.deepEqual(comicVoicePairs(dictionary([[guid,'{M#'+source+'}{M#'+source+'}']])),[]);
});
