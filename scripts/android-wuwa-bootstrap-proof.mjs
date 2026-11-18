import assert from 'node:assert/strict';

/** Authored carrier only: packaged JNI and mmap execution, never game Ready. */
export function assertNativeWuwaBootstrap(value, audit, provenance, cryptoRuntime) {
  const fixture = audit.wuwa_authored_fixture;
  assert.equal(value?.schema, 'toolkit-android-authored-wuwa-bootstrap-v1');
  assert.equal(value.passed, true);
  for (const name of ['actual_network', 'original_game_bytes', 'snapshot_ready']) assert.equal(value[name], false);
  assert.deepEqual(fixture, provenance.wuwa_authored_fixture);
  assert.equal(fixture.original_game_bytes, false);
  assert.ok(Number.isSafeInteger(fixture.apk_bytes) && fixture.apk_bytes >= 1024 && fixture.apk_bytes <= 32768);
  assert.equal(value.fixture_sha256, fixture.sha256);assert.equal(value.apk_sha256, fixture.apk_sha256);
  assert.deepEqual(value.crypto_proof, cryptoRuntime);
  assert.equal(value.mmap_runtime?.android_extension, true);
  assert.ok(Number.isSafeInteger(value.mmap_runtime.bytes) && value.mmap_runtime.bytes > 0 && value.mmap_runtime.bytes <= 131072);
  const entry = `assets/chaquopy/bootstrap-native/${cryptoRuntime.abi}/mmap.cpython-312.so`;
  assert.match(value.mmap_runtime.sha256, /^[a-f0-9]{64}$/);
  assert.equal(value.mmap_runtime.sha256, audit.native_files[entry]?.sha256);
  assert.equal(audit.native_files[entry]?.minimum_load_alignment, 16384);
  assert.deepEqual(value.cases.map(row => row.case), ['text', 'text-audio', 'corrupt', 'cancel']);
  for (const row of value.cases.slice(0, 2)) {
    assert.equal(row.stage, 'manifest-format');assert.equal(row.downloaded_bytes, fixture.apk_bytes);
    assert.equal(row.module_sha256, fixture.module_sha256);
    for (const key of ['full_apk_verified', 'mmap_data_parser', 'offline_restart', 'retained_data']) assert.equal(row[key], true);
    assert.equal(row.snapshot_activated, false);
  }
  for (const row of value.cases.slice(2)) {
    assert.equal(row.rejected, true);assert.equal(row.retained_data, true);
    assert.ok(Number.isSafeInteger(row.charged_bytes) && row.charged_bytes > 0 && row.charged_bytes <= fixture.apk_bytes);
  }
}
