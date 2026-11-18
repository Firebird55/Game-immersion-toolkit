import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {assertNativeZzzCatalogue} from '../scripts/android-zzz-catalogue-proof.mjs';

function fixture() {
  const asset = name => readFileSync(new URL('../packaging/android/zzz-catalogue/' + name, import.meta.url));
  const pin = JSON.parse(asset('manifest-pin.json'));
  const raw = asset('authored-operation.json').toString('utf8').replaceAll('\r\n', '\n');
  const operation = JSON.parse(raw);
  const hash = createHash('sha256').update(raw).digest('hex');
  const component = {present:true, manifest_sha256:pin.manifest_sha256, runtime_files:16, source_files:20,
    corresponding_source_bundle_sha256:pin.corresponding_source_bundle_sha256, authored_fixture_sha256:hash};
  const report = {schema:'toolkit-android-authored-zzz-catalogue-proof-v1', present:true, passed:true,
    manifest_sha256:pin.manifest_sha256, fixture_sha256:hash, mode:'comic-plan',
    input_sha256:Object.fromEntries(Object.entries(operation.files).map(([name, row]) => [name, row.sha256])),
    output_sha256:operation.output.sha256, ranges:1, bad_input_digest_rejected:true, retained_data:true,
    original_game_bytes:false, snapshot_ready:false};
  return {report, audit:{zzz_catalogue_component:component}, provenance:{zzz_catalogue_component:structuredClone(component)}};
}

test('the installed ZZZ worker receipt is bound to the audited exact APK component and authored output', () => {
  const {report, audit, provenance} = fixture();
  assert.equal(assertNativeZzzCatalogue(report, audit, provenance), true);
  for (const [key, value] of Object.entries({fixture_sha256:'0'.repeat(64), output_sha256:'0'.repeat(64),
    manifest_sha256:'0'.repeat(64), snapshot_ready:true, retained_data:false, bad_input_digest_rejected:false})) {
    assert.throws(() => assertNativeZzzCatalogue({...report, [key]:value}, audit, provenance));
  }
  assert.throws(() => assertNativeZzzCatalogue(report, audit,
    {zzz_catalogue_component:{...provenance.zzz_catalogue_component, source_files:0}}));
});

test('an APK without ZZZ software is unverified and fails the hosted required check', () => {
  const absent = {zzz_catalogue_component:{present:false}};
  const report = {schema:'toolkit-android-authored-zzz-catalogue-proof-v1', present:false, passed:false, status:'unverified-not-packaged'};
  assert.equal(assertNativeZzzCatalogue(report, absent, absent, {required:false}), false);
  assert.throws(() => assertNativeZzzCatalogue(report, absent, absent));
  assert.throws(() => assertNativeZzzCatalogue({...report, passed:true}, absent, absent, {required:false}));
});
