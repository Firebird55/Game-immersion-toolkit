import assert from 'node:assert/strict';
import test from 'node:test';
import {gzipSync} from 'node:zlib';
import { sceneAssetPaths, sceneBundleRangesFromCatalog } from '../scripts/scene-catalog.mjs';

test('comic and dialogue references use their authored namespaces across table field changes', () => {
  const table = { changingKey: [{ otherKey: 'Data/ScriptConfig/Comic/Test_Comic.asset' },
    { nested: ['Data/ScriptConfig/Perform/Data/GalGame/Test.asset', 'data/scriptconfig/comic/test_comic.asset'] }] };
  assert.deepEqual(sceneAssetPaths(table, 'comic'), ['assets/napresources/data/scriptconfig/comic/test_comic.asset']);
  assert.deepEqual(sceneAssetPaths(table, 'galgame'), ['assets/napresources/data/scriptconfig/perform/data/galgame/test.asset']);
});

function catalog({dependency=1, truncated=false}={}) {
  const data=Buffer.alloc(52+12+18+56+12);
  data.writeUInt32LE(1,8);data.writeUInt32LE(2,12);data.writeUInt32LE(2,16);
  data.writeUInt32LE(52,20);data.writeBigUInt64LE(64n,28);data.writeBigUInt64LE(82n,36);data.writeBigUInt64LE(138n,44);
  data.writeUInt32LE(0,52);data.writeBigUInt64LE(42n,56);
  data.writeUInt32LE(100,65);data.writeUInt32LE(200,74);
  data.writeUInt32LE(0,82);data.writeUInt32LE(500,102);data.writeUInt32LE(50,106);
  data.writeUInt32LE(1,110);data.writeUInt32LE(700,130);data.writeUInt32LE(60,134);
  data.writeUInt32LE(1,138);data.writeUInt32LE(dependency,142);data.writeUInt32LE(0,146);
  return gzipSync(truncated?data.subarray(0,-1):data);
}

test('comic voice dictionaries in another block follow authored bundle dependencies',()=>{
  assert.deepEqual(sceneBundleRangesFromCatalog(catalog(),new Set([42n])),{matchedHashes:[42n],ranges:[
    {block:'Blocks/100.blk',offset:500,size:50},{block:'Blocks/200.blk',offset:700,size:60},
  ]});
  assert.deepEqual(sceneBundleRangesFromCatalog(catalog(),new Set([99n])),{matchedHashes:[],ranges:[]});
  assert.throws(()=>sceneBundleRangesFromCatalog(catalog({dependency:3}),new Set([42n])),/outside catalog/);
  assert.throws(()=>sceneBundleRangesFromCatalog(catalog({truncated:true}),new Set([42n])),/Truncated scene dependencies/);
});

test('unrelated strings and unsafe resource paths cannot enter the scene lookup', () => {
  assert.deepEqual(sceneAssetPaths([
    'Data/ScriptConfig/Comic/../Other.asset', 'Data/ScriptConfig/Comic/./Other.asset',
    'Data/ScriptConfig/Comic//Other.asset', 'Data/ScriptConfig/Comic/Other.asset?url',
    'Data/ScriptConfig/ComicExtra/Other.asset', 'Data/ScriptConfig/Comic/C:\\Other.asset',
    'https://example.invalid/Data/ScriptConfig/Comic/Other.asset',
    'Data/ScriptConfig/Perform/Data/GalGame/Comic.asset', null, 123,
  ], 'comic'), []);
  assert.throws(() => sceneAssetPaths({}, 'guess'), /Unknown scene category/);
});
