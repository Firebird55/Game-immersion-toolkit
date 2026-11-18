import test from 'node:test';
import assert from 'node:assert/strict';
import {assertNativePublisherCrypto} from '../scripts/android-publisher-crypto-proof.mjs';
import policy from '../packaging/android/publisher-crypto-native.json' with {type:'json'};

function authored() {
  const fixtures = {capi:{cases:16,bytes:100,sha256:'c'.repeat(64)},jca:{cases:41,bytes:200,sha256:'d'.repeat(64)}};
  const receipt = {schema:'toolkit-android-publisher-crypto-bundle-v1',source_sha256:policy.source.sha256,
    manifest_sha256:'a'.repeat(64),libraries:{'arm64-v8a':{sha256:'b'.repeat(64)},x86_64:{sha256:'e'.repeat(64)}},authored_fixtures:fixtures};
  const provenance = {native_publisher_crypto_manifest_sha256:receipt.manifest_sha256,publisher_crypto_authored_fixtures:fixtures};
  const runtime = {schema:'toolkit-publisher-crypto-v1',abi:'arm64-v8a',source_sha256:policy.source.sha256,
    manifest_sha256:receipt.manifest_sha256,library_sha256:receipt.libraries['arm64-v8a'].sha256,
    platform_primitives:'JCA',pointer_bits:64,key_bytes:32,nonce_bytes:12,max_bytes:policy.max_bytes,
    apk_entry_verified:true,licenses_verified:true,system_fallback:false,original_client_execution:false,account_keys_reused:false};
  const value = {fixture:'authored-packaged-publisher-crypto',passed:true,capi_cases:16,jca_cases:41,chacha_positive_cases:8,
    operations:{block:31,verify:5,decrypt:5},publisher_requests:0,account_keys_reused:false,original_client_execution:false,fixtures,runtime};
  return {value:structuredClone(value),receipt:structuredClone(receipt),provenance:structuredClone(provenance)};
}
test('actual packaged proof binds both compiled ABI receipts and fresh authored inputs', () => {
  const {value,receipt,provenance} = authored();assertNativePublisherCrypto(value,receipt,provenance);
});
for (const [name,change] of Object.entries({
  incomplete:v => {v.value.chacha_positive_cases=7;}, fallback:v => {v.value.runtime.system_fallback=true;},
  wrongLibrary:v => {v.value.runtime.library_sha256='f'.repeat(64);},
  wrongManifest:v => {v.provenance.native_publisher_crypto_manifest_sha256='f'.repeat(64);},
  missingAbi:v => {delete v.receipt.libraries.x86_64;},
  foreignFixture:v => {v.value.fixtures.capi.sha256='f'.repeat(64);},
  unknownAbi:v => {v.value.runtime.abi='linux-aarch64';},
  accountReuse:v => {v.value.runtime.account_keys_reused=true;},
  network:v => {v.value.publisher_requests=1;}, notices:v => {v.value.runtime.licenses_verified=false;},
})) test('rejects '+name, () => {
  const data=authored();change(data);assert.throws(() => assertNativePublisherCrypto(data.value,data.receipt,data.provenance));
});
