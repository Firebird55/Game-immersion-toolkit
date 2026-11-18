import assert from 'node:assert/strict';
import policy from '../packaging/android/publisher-hash-native.json' with {type:'json'};

/** Require actual Python→Java→own APK JNI proof, including upgrade startup. */
export function assertNativePublisherHash(value, receipt, provenance) {
  assert.equal(value?.schema, 'toolkit-authored-publisher-hash-proof-v1');
  assert.equal(value.passed, true);assert.equal(value.cases, 47);
  assert.equal(value.native_boundary_rejections, 2);assert.equal(value.original_game_bytes, false);
  assert.equal(receipt?.schema, 'toolkit-android-publisher-hash-bundle-v1');
  assert.equal(receipt.contract, policy.contract);
  assert.equal(receipt.source_sha256, policy.source.sha256);
  assert.equal(receipt.header_sha256, policy.source.members['deps/xxhash/xxhash.h']);
  assert.deepEqual(Object.keys(receipt.libraries).sort(), ['arm64-v8a', 'x86_64']);
  assert.match(receipt.manifest_sha256, /^[a-f0-9]{64}$/);
  assert.equal(receipt.manifest_sha256, provenance?.native_publisher_hash_manifest_sha256);
  assert.equal(receipt.authored_fixture?.cases, 47);
  assert.match(receipt.authored_fixture.sha256, /^[a-f0-9]{64}$/);
  assert.ok(Number.isSafeInteger(receipt.authored_fixture.bytes) && receipt.authored_fixture.bytes > 0 && receipt.authored_fixture.bytes <= 65536);
  assert.deepEqual(receipt.authored_fixture, provenance.publisher_hash_authored_fixture);
  assert.equal(value.fixture_sha256, receipt.authored_fixture.sha256);
  const runtime = value.runtime;
  assert.equal(runtime?.schema, policy.contract);assert.equal(runtime.algorithm, 'XXH3-64');
  assert.equal(runtime.version, policy.source.xxhash_version);
  assert.ok(['arm64-v8a', 'x86_64'].includes(runtime.abi));
  assert.equal(runtime.library_sha256, receipt.libraries[runtime.abi].sha256);
  assert.match(runtime.library_sha256, /^[a-f0-9]{64}$/);
  assert.equal(runtime.manifest_sha256, receipt.manifest_sha256);
  assert.equal(runtime.source_sha256, receipt.source_sha256);assert.equal(runtime.header_sha256, receipt.header_sha256);
  assert.equal(runtime.pointer_bits, 64);assert.equal(runtime.max_bytes, 4096);assert.equal(runtime.seed, 0);
  for (const field of ['apk_entry_verified', 'licenses_verified']) assert.equal(runtime[field], true);
  for (const field of ['custom_secret', 'system_fallback', 'original_client_execution']) assert.equal(runtime[field], false);
}
