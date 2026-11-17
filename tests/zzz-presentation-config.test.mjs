import test from 'node:test';
import assert from 'node:assert/strict';
import {AUTO_CONFIG_FIELDS, autoPresentationConfig, presentationDictionary, timelineOwners} from '../scripts/zzz-presentation-config.mjs';

const u32 = value => { const b = Buffer.alloc(4); b.writeUInt32LE(value >>> 0); return b; };
const u64 = value => { const b = Buffer.alloc(8); b.writeBigUInt64LE(BigInt(value)); return b; };
const aligned = bytes => Buffer.concat([bytes, Buffer.alloc((4 - bytes.length % 4) % 4)]);
const unityString = text => aligned(Buffer.concat([u32(Buffer.byteLength(text)), Buffer.from(text)]));
const odinString = text => Buffer.concat([Buffer.from([1]), u32(text.length), Buffer.from(text, 'utf16le')]);
const namedString = (name, value) => Buffer.concat([Buffer.from([0x27]), odinString(name), odinString(value)]);
const namedNull = name => Buffer.concat([Buffer.from([0x2d]), odinString(name)]);
const header = name => Buffer.concat([Buffer.alloc(28), unityString(name)]);
const typeName = (id, name) => Buffer.concat([Buffer.from([0x2f]), u32(id), odinString(name)]);
function timelinePayload({alias = false} = {}) {
  const value = Buffer.concat([Buffer.from([1]), odinString('$v'), typeName(1, 'MoleMole.RuntimeTimelineData, Logic'), u32(1),
    namedString('_resPath', 'Assets/Future/Scene.prefab'), namedString('_audioResPath', 'Assets/Future/OriginalAudio.playable'),
    namedNull('timelineResPath'), namedString('timelineResPathFemale', 'Assets/Future/OtherPlayer.prefab'), Buffer.from([5])]);
  const pair = (key, value) => Buffer.concat([Buffer.from([4, 0x2e]), namedString('$k', key), value, Buffer.from([5])]);
  return Buffer.concat([Buffer.from([1]), odinString('timelineDatas'), typeName(0,
    'System.Collections.Generic.Dictionary`2[[System.String, mscorlib],[MoleMole.TimelineData, Logic]], mscorlib'), u32(0),
  Buffer.from([6]), u64(alias ? 2 : 1), pair('FutureReleasedKey', value),
  ...(alias ? [pair('FutureAlias', Buffer.concat([Buffer.from([9]), odinString('$v'), u32(1)]))] : []), Buffer.from([7,5])]);
}
function timelineObject(payload, priority = 0) {
  return Buffer.concat([header('AuthoredSyntheticTimeline'), u32(0), u32(payload.length), aligned(payload), Buffer.alloc(32), u32(priority)]);
}

test('typed timeline dictionaries retain original player/audio paths and shared Odin references without inventing captions', () => {
  const result = presentationDictionary(timelineObject(timelinePayload({alias:true}), -3), 'timeline');
  assert.equal(result.priority, -3);
  assert.deepEqual(result.entries.map(row => row.key), ['FutureReleasedKey', 'FutureAlias']);
  assert.deepEqual(result.entries[0].paths, result.entries[1].paths);
  assert.equal(result.entries[0].paths._audioResPath, 'Assets/Future/OriginalAudio.playable');
  assert.equal(result.entries[0].paths.timelineResPathFemale, 'Assets/Future/OtherPlayer.prefab');
  assert.equal(Object.hasOwn(result.entries[0], 'text_id'), false);
  const object = timelineObject(timelinePayload());
  assert.throws(() => presentationDictionary(object.subarray(0, object.length - 1), 'timeline'), /Truncated/);
  assert.throws(() => presentationDictionary(Buffer.concat([object, u32(0)]), 'timeline'), /Trailing/);
  assert.throws(() => presentationDictionary(object, 'video'), /dictionary/);
});

test('lowest original config order wins and ambiguous equal-priority sources stay unresolved in any input order', () => {
  const base = presentationDictionary(timelineObject(timelinePayload()), 'timeline').entries[0];
  const high = {...base, priority:12}, low = {...base, priority:2, paths:{...base.paths, _audioResPath:'Assets/Other.playable'}};
  assert.equal(timelineOwners([high, low], [base.key]).owners[0].paths._audioResPath, low.paths._audioResPath);
  const tie = {...high, paths:low.paths};
  for (const rows of [[high, tie], [tie, high]]) {
    const r = timelineOwners(rows, [base.key, 'NewMissingKey']);
    assert.deepEqual(r.owners, []);
    assert.deepEqual(r.coverage.ambiguous_equal_priority_keys, [base.key]);
    assert.deepEqual(r.coverage.unresolved_keys, ['NewMissingKey']);
    assert.equal(r.coverage.subtitle_audio_acquisition, 'not-implemented');
  }
  assert.equal(timelineOwners([high, tie, low], [base.key]).owners.length, 1);
});

test('future config groups are read from variable AssetPath arrays and changed layouts fail closed', () => {
  const scalars = new Set(['abilityRegistryConfigPath', 'graphRegistryConfigPath', 'levelGroupRegistryConfigPath', 'voSeqRegistryConfigPath']);
  const ref = value => Buffer.concat([unityString(''), u64(value)]);
  const chunks = [header('NewAutoConfigMetaConfig'), Buffer.alloc(40)];
  for (const field of AUTO_CONFIG_FIELDS) chunks.push(scalars.has(field) ? ref(0) :
    field === 'timelineDataPathes' ? Buffer.concat([u32(2), ref(101), ref(702)]) :
    field === 'languageVideoDataPaths' ? Buffer.concat([u32(1), ref(999)]) : u32(0));
  const object = Buffer.concat(chunks), parsed = autoPresentationConfig(object);
  assert.deepEqual(parsed.timelineDataPathes.map(row => row.hash), ['101','702']);
  assert.deepEqual(parsed.languageVideoDataPaths.map(row => row.hash), ['999']);
  assert.throws(() => autoPresentationConfig(Buffer.concat([object, u32(0)])), /schema/);
  assert.throws(() => autoPresentationConfig(object.subarray(0, object.length - 1)), /Truncated/);
});
