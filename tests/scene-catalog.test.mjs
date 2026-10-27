import assert from 'node:assert/strict';
import test from 'node:test';
import {gzipSync} from 'node:zlib';
import { sceneAssetPaths, sceneBundleRangesFromCatalog, unityResourceCatalog, resourceCatalogBytes } from '../scripts/scene-catalog.mjs';

function unityCatalog(blockCount=2) {
  // A catalog root in block 100 depends on a voice dictionary in block 200.
  const blockBytes=blockCount*9,padding=(4-blockBytes%4)%4,dependencies=120+blockBytes+padding;
  const raw=Buffer.alloc(dependencies+4+4+4);
  raw.writeUInt32LE(3,0);raw.write('Res',4);raw.writeUInt32LE(1,8);raw.writeBigUInt64LE(42n,16);
  raw.writeUInt32LE(2,24);
  raw.writeUInt32LE(500,48);raw.writeUInt32LE(1,56);raw.writeUInt32LE(50,68);
  raw.writeUInt32LE(1,72);raw.writeUInt32LE(700,92);raw.writeUInt32LE(1,96);raw.writeUInt32LE(1,100);raw.writeUInt32LE(60,112);
  raw.writeUInt32LE(blockCount,116);raw.writeUInt32LE(100,120);raw.writeUInt32LE(200,129);
  raw.writeUInt32LE(1,dependencies);raw.writeUInt32LE(1,dependencies+4);
  const cab=Buffer.alloc(128+raw.length);
  cab.writeUInt32BE(100,0);cab.writeUInt32BE(cab.length,4);cab.writeUInt32BE(21,8);cab.writeUInt32BE(128,12);
  cab.write('2019.4.40f1',20);let p=32;cab.writeUInt32LE(19,p);p+=5;
  cab.writeUInt32LE(1,p);p+=4;cab.writeInt32LE(6776977,p);p+=7+16;
  cab.writeUInt32LE(1,p);p+=4;p=(p+3)&~3;
  cab.writeBigInt64LE(1n,p);cab.writeUInt32LE(raw.length,p+12);raw.copy(cab,128);
  return cab;
}

test('Unity-wrapped resource catalogs preserve exact scene ranges and dependencies',()=>{
  const cab=unityCatalog(),decoded=unityResourceCatalog(cab);
  const expected={matchedHashes:[42n],ranges:[{block:'Blocks/100.blk',offset:500,size:50},{block:'Blocks/200.blk',offset:700,size:60}]};
  assert.deepEqual(sceneBundleRangesFromCatalog(decoded,new Set([42n]),true),expected);
  // Exercise all four packed-block alignment cases without changing authored ranges.
  for(const blocks of [3,4,5])assert.deepEqual(sceneBundleRangesFromCatalog(unityResourceCatalog(unityCatalog(blocks)),new Set([42n]),true),expected);
  const bundle=Buffer.from('mhy1synthetic');
  assert.deepEqual(resourceCatalogBytes(bundle,()=>({end:bundle.length,files:[cab]})),decoded);
  assert.throws(()=>resourceCatalogBytes(bundle,()=>({end:1,files:[cab]})),/bundle sequence/);
  assert.throws(()=>resourceCatalogBytes(bundle,()=>({end:bundle.length,files:[cab,cab]})),/Ambiguous/);
  const bad=Buffer.from(cab);bad.writeUInt32LE(99999,128+56);
  assert.throws(()=>unityResourceCatalog(bad),/dependency slice/);
  const outside=Buffer.from(cab);outside.writeUInt32LE(999999,68+12);
  assert.throws(()=>unityResourceCatalog(outside),/object bounds/);
  const padding=Buffer.from(cab);padding[128+138]=1;
  assert.throws(()=>unityResourceCatalog(padding),/alignment padding/);
});

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
