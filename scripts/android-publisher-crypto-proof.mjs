import assert from 'node:assert/strict';
import policy from '../packaging/android/publisher-crypto-native.json' with {type:'json'};

/** Actual APK/JNI execution, distinct from compilation or standalone probes. */
export function assertNativePublisherCrypto(value, receipt, provenance) {
  assert.equal(value?.fixture, 'authored-packaged-publisher-crypto');
  assert.equal(value.passed, true);
  assert.equal(value.capi_cases, 16);assert.equal(value.jca_cases, 41);
  assert.equal(value.chacha_positive_cases, 8);
  assert.deepEqual(value.operations, {block:31,verify:5,decrypt:5});
  assert.equal(value.publisher_requests, 0);
  assert.equal(value.account_keys_reused, false);assert.equal(value.original_client_execution, false);
  assert.equal(receipt?.schema, 'toolkit-android-publisher-crypto-bundle-v1');
  assert.equal(receipt.source_sha256, policy.source.sha256);
  assert.deepEqual(Object.keys(receipt.libraries).sort(), ['arm64-v8a','x86_64']);
  assert.equal(receipt.manifest_sha256, provenance?.native_publisher_crypto_manifest_sha256);
  assert.match(receipt.manifest_sha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(value.fixtures, receipt.authored_fixtures);
  assert.deepEqual(value.fixtures, provenance.publisher_crypto_authored_fixtures);
  for (const [kind,count] of [['capi',16],['jca',41]]) {
    const fixture = value.fixtures[kind];
    assert.equal(fixture.cases, count);assert.match(fixture.sha256, /^[a-f0-9]{64}$/);
    assert.ok(Number.isSafeInteger(fixture.bytes) && fixture.bytes >= 8 && fixture.bytes <= 65536);
  }
  const runtime = value.runtime;
  assert.equal(runtime?.schema, 'toolkit-publisher-crypto-v1');
  assert.ok(['arm64-v8a','x86_64'].includes(runtime.abi));
  assert.equal(runtime.library_sha256, receipt.libraries[runtime.abi].sha256);
  assert.equal(runtime.manifest_sha256, receipt.manifest_sha256);
  assert.equal(runtime.source_sha256, policy.source.sha256);
  assert.equal(runtime.platform_primitives, 'JCA');
  assert.equal(runtime.pointer_bits, 64);assert.equal(runtime.key_bytes, 32);assert.equal(runtime.nonce_bytes, 12);
  assert.equal(runtime.max_bytes, policy.max_bytes);
  for (const field of ['apk_entry_verified','licenses_verified']) assert.equal(runtime[field], true);
  for (const field of ['system_fallback','original_client_execution','account_keys_reused']) assert.equal(runtime[field], false);
}
