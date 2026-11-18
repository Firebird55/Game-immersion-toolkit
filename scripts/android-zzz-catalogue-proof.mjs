import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const asset = name => readFileSync(new URL('../packaging/android/zzz-catalogue/' + name, import.meta.url));
const pin = JSON.parse(asset('manifest-pin.json'));
const fixtureBytes = Buffer.from(asset('authored-operation.json').toString('utf8').replaceAll('\r\n', '\n'));
const fixture = JSON.parse(fixtureBytes);
const fixtureSha256 = createHash('sha256').update(fixtureBytes).digest('hex');
const inputs = Object.fromEntries(Object.entries(fixture.files).map(([name, row]) => [name, row.sha256]));

export function assertNativeZzzCatalogue(value, audit, provenance, {required = true} = {}) {
  assert.equal(value?.schema, 'toolkit-android-authored-zzz-catalogue-proof-v1');
  const component = audit.zzz_catalogue_component;
  assert.deepEqual(component, provenance.zzz_catalogue_component);
  if (!required && component?.present === false) {
    assert.equal(value.present, false);
    assert.equal(value.passed, false);
    assert.equal(value.status, 'unverified-not-packaged');
    return false;
  }
  assert.deepEqual(component, {present:true, manifest_sha256:pin.manifest_sha256, runtime_files:pin.modules + 3,
    source_files:pin.sources, corresponding_source_bundle_sha256:pin.corresponding_source_bundle_sha256,
    authored_fixture_sha256:fixtureSha256});
  assert.equal(value.present, true);
  assert.equal(value.passed, true);
  assert.equal(value.manifest_sha256, component.manifest_sha256);
  assert.equal(value.fixture_sha256, fixtureSha256);
  assert.equal(value.mode, fixture.mode);
  assert.deepEqual(value.input_sha256, inputs);
  assert.equal(value.output_sha256, fixture.output.sha256);
  assert.equal(value.ranges, fixture.output.data.ranges.length);
  assert.equal(value.bad_input_digest_rejected, true);
  assert.equal(value.retained_data, true);
  assert.equal(value.original_game_bytes, false);
  assert.equal(value.snapshot_ready, false);
  return true;
}
