import test from 'node:test';
import assert from 'node:assert/strict';
import {assertNativePublisherHash} from '../scripts/android-publisher-hash-proof.mjs';
import policy from '../packaging/android/publisher-hash-native.json' with {type:'json'};

function authored() {
  const fixture = {cases:47, bytes:4096, sha256:'c'.repeat(64)};
  const receipt = {schema:'toolkit-android-publisher-hash-bundle-v1',contract:policy.contract,
    source_sha256:policy.source.sha256,header_sha256:policy.source.members['deps/xxhash/xxhash.h'],
    manifest_sha256:'a'.repeat(64),libraries:{'arm64-v8a':{sha256:'b'.repeat(64)},x86_64:{sha256:'d'.repeat(64)}},authored_fixture:fixture};
  const runtime = {schema:policy.contract,algorithm:'XXH3-64',version:'0.8.4',abi:'arm64-v8a',pointer_bits:64,
    max_bytes:4096,seed:0,custom_secret:false,system_fallback:false,original_client_execution:false,
    apk_entry_verified:true,licenses_verified:true,source_sha256:receipt.source_sha256,
    header_sha256:receipt.header_sha256,library_sha256:receipt.libraries['arm64-v8a'].sha256,manifest_sha256:receipt.manifest_sha256};
  return {value:{schema:'toolkit-authored-publisher-hash-proof-v1',passed:true,cases:47,native_boundary_rejections:2,
    original_game_bytes:false,fixture_sha256:fixture.sha256,runtime},receipt,
    provenance:{native_publisher_hash_manifest_sha256:receipt.manifest_sha256,publisher_hash_authored_fixture:structuredClone(fixture)}};
}
for (const abi of ['arm64-v8a', 'x86_64']) test('binds actual APK/JNI '+abi+' identity and authored inputs', () => {
  const data = authored();data.value.runtime.abi=abi;data.value.runtime.library_sha256=data.receipt.libraries[abi].sha256;
  assertNativePublisherHash(data.value, data.receipt, data.provenance);
});
for (const [name, change] of Object.entries({
  cases:d => {d.value.cases=46;}, rejection:d => {d.value.native_boundary_rejections=1;},
  nativeOnly:d => {delete d.value.fixture_sha256;}, source:d => {d.value.runtime.source_sha256='f'.repeat(64);},
  header:d => {d.receipt.header_sha256='f'.repeat(64);}, fallback:d => {d.value.runtime.system_fallback=true;},
  secret:d => {d.value.runtime.custom_secret=true;}, algorithm:d => {d.value.runtime.algorithm='XXH64';},
  architecture:d => {d.value.runtime.abi='linux-arm64';}, missingAbi:d => {delete d.receipt.libraries.x86_64;},
  library:d => {d.value.runtime.library_sha256='f'.repeat(64);}, manifest:d => {d.provenance.native_publisher_hash_manifest_sha256='f'.repeat(64);},
  notices:d => {d.value.runtime.licenses_verified=false;}, bits:d => {d.value.runtime.pointer_bits=32;},
  limit:d => {d.value.runtime.max_bytes=8192;}, gameBytes:d => {d.value.original_game_bytes=true;},
  fixture:d => {d.provenance.publisher_hash_authored_fixture.sha256='f'.repeat(64);},
})) test('rejects '+name, () => {
  const data=authored();change(data);assert.throws(() => assertNativePublisherHash(data.value,data.receipt,data.provenance));
});
