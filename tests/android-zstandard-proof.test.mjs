import assert from 'node:assert/strict';
import {test} from 'node:test';
import vectors from '../packaging/android/zstandard-authored-vectors.json' with {type:'json'};
import {assertNativeZstandard} from '../scripts/android-zstandard-proof.mjs';

const receipt = {schema:'toolkit-android-zstandard-build-v1', abis:{'arm64-v8a':{native_sha256:'a'.repeat(64)},x86_64:{native_sha256:'b'.repeat(64)}}};
const proof = {fixture:'authored-native-zstandard-manifests', version:vectors.version, backend:'cext', zstd:vectors.zstd,
  native_sha256:'a'.repeat(64), cases:vectors.cases.map(({name,result}) => ({name,...result})),
  sophon_context_and_offline_cache:true,publisher_requests:0};

test('The target proof requires actual pinned compiled bytes and every bounded result', () => {
  assertNativeZstandard(proof, receipt);
  for (const change of [
    {backend:'cffi'}, {native_sha256:'c'.repeat(64)}, {version:'0.24.0'}, {cases:proof.cases.slice(1)},
    {publisher_requests:1}, {sophon_context_and_offline_cache:false},
    {cases:proof.cases.map((value,index) => index === 0 ? {...value,sha256:'d'.repeat(64)} : value)},
  ]) assert.throws(() => assertNativeZstandard({...proof,...change}, receipt));
  assert.throws(() => assertNativeZstandard(proof,{...receipt,abis:{'arm64-v8a':receipt.abis['arm64-v8a']}}));
});
