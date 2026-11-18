import assert from 'node:assert/strict';
import vectors from '../packaging/android/zstandard-authored-vectors.json' with {type:'json'};

export function assertNativeZstandard(value, receipt) {
  assert.equal(value?.fixture, 'authored-native-zstandard-manifests');
  assert.equal(value.version, vectors.version);
  assert.equal(value.backend, 'cext');
  assert.deepEqual(value.zstd, vectors.zstd);
  assert.equal(receipt?.schema, 'toolkit-android-zstandard-build-v1');
  assert.deepEqual(Object.keys(receipt.abis).sort(), ['arm64-v8a', 'x86_64']);
  assert.ok(Object.values(receipt.abis).some(row => row.native_sha256 === value.native_sha256),
    'The loaded native module must be one of the exact compiled APK ABIs');
  assert.deepEqual(value.cases, vectors.cases.map(({name, result}) => ({name, ...result})));
  assert.equal(value.sophon_context_and_offline_cache, true);
  assert.equal(value.publisher_requests, 0);
}
