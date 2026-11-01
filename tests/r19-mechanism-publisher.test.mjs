import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

// Execute the actual closed-value admission predicate, without spawning a
// native probe, reading an account, or exercising the surrounding publication IO.
const source = readFileSync(new URL('../.github/workflows/r19-runtime-experiment.yml', import.meta.url), 'utf8');
const start = source.indexOf("            const fixed={schema:'proxy-r19-legacy-lock-attribute-mechanism-v5'");
const end = source.indexOf('            const binding=', start);
assert.ok(start >= 0 && end > start);
const admit = new Function('value', 'child',
  "const refuse=()=>{throw new Error('refused')};\n" + source.slice(start, end) + '\nreturn true;');

function failed() {
  return {schema:'proxy-r19-legacy-lock-attribute-mechanism-v5',
    scope:'authored-local-ntfs-no-writers-mechanism',candidate_data_writers:0,
    production_allowed:false,keeper_loss_acceptance:false,rights_approval:false,
    native_windows_11_acceptance:'unavailable',r19_complete:false,
    status:'failed',phase:'fixture',failure:'unsupported-host',legacy_source_sha256:null,
    observed:[],timestamp_equalities:{},cleanup:'unconfirmed-fixture-retained',
    baseline_checkpoint:{parent_step:'not-started',script_step:'not-started',child_state:'not-created'},
    grant_conversion_failure:null};
}

function complete() {
  const value = failed();
  Object.assign(value, {status:'mechanism-observed',phase:'complete',failure:'none',
    legacy_source_sha256:'c0cb1b456c029e8cb843501ffaf17cf2b054bdfecad8e788dd35d9a85ae2d3ef',
    cleanup:'owned-handles-closed-fixture-retained',
    baseline_checkpoint:{parent_step:'cleanup',script_step:'operationresult',child_state:'signaled'},
    observed:['writable-open','exclusive-held','arm','live-clear','rearm',
      'genuine-owner-signaled-and-closed','post-loss-readonly-refused','restored-open']});
  for (const name of ['arm','live-clear','rearm','post-loss','test-restore','restored']) {
    value.timestamp_equalities[name] = {access_equal:false,change_equal:false,creation_equal:true,write_equal:true};
  }
  return value;
}

test('v5 publisher admits complete criteria and bounded failure without a native claim', () => {
  assert.equal(admit(failed(), {status:2}), true);
  // Changed access/metadata-change times remain observations, not new promises.
  assert.equal(admit(complete(), {status:0}), true);
});

test('v5 publisher refuses historical contexts, type substitutions and incomplete acceptance', () => {
  const cases = [
    [value => {value.schema='proxy-r19-legacy-lock-attribute-mechanism-v4';}, 0],
    [value => {value.grant_conversion_failure={category:'unknown',chain_end:'unknown',exceptions:[],line:'nonempty'};}, 0],
    [value => {value.candidate_data_writers=false;}, 0],
    [value => {value.production_allowed=true;}, 0],
    [value => {value.extra='unreviewed';}, 0],
    [value => {delete value.grant_conversion_failure;}, 0],
    [value => {value.observed.reverse();}, 0],
    [value => {value.timestamp_equalities.arm.creation_equal=false;}, 0],
    [value => {value.timestamp_equalities.restored.write_equal=false;}, 0],
    [value => {value.timestamp_equalities.arm.access_equal=0;}, 0],
    [value => {value.cleanup='unconfirmed-fixture-retained';}, 0],
    [value => {value.phase='post-loss';}, 0],
    [value => {value.legacy_source_sha256=null;}, 0],
    [() => {}, 2],
  ];
  for (const [mutate, status] of cases) {
    const value = complete();
    mutate(value);
    assert.throws(() => admit(value, {status}), /refused/);
  }
  assert.throws(() => admit(failed(), {status:0}), /refused/);
});
