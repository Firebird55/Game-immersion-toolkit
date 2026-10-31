import test from 'node:test';
import assert from 'node:assert/strict';
import {validSource, validateReport, projectReport, projectObserverDiagnostic, projectFailure} from '../scripts/run-msvc-redist-census.mjs';

const head = 'a'.repeat(40), id = 'msvc-redist-1-1';
function report() {
  return {schema:'proxy-r19-msvc-redist-census-v1',status:'observed-not-approved',reason:'none',
    source_commit_label:head,source_binding:'unverified-caller-label',observation_id:id,
    observation_id_authority:'binding-only',selected_instance:{version:'18.11.12328.437',edition:'enterprise',release_state:'release'},
    query_utility:{bytes:400000,sha256:'b'.repeat(64)},requested_architecture:'x64',selection:'none',
    versions:[{version:'14.51.36231',families:[{role:'vc145-crt',files:Object.fromEntries(
      ['msvcp140.dll','msvcp140_1.dll','vcruntime140.dll','vcruntime140_1.dll'].map(name=>[name,{presence:'regular-file-present',bytes:1234}]))}]}],
    version_count:1,family_count:1,file_count:4,metadata_snapshot_stable:true,
    vendor_file_content_read:false,vendor_file_hashes_observed:false,vendor_file_versions_observed:false,
    vendor_signatures_observed:false,entitlement_probe:'not-performed',rights_review:'pending-owner-and-exact-source',
    license_eligibility:'unverified',redistribution_approved:false,source_delivery_approved:false,
    runtime_collection_allowed:false,production_execution_allowed:false,production_activation:false,
    native_closure:'unverified',native_windows_11_acceptance:'unavailable',r19_complete:false,installer:'not-built'};
}

test('caller SHA is insufficient without clean, visible, transform-free source evidence', () => {
  const snapshot={head,sourceStatus:'available',sourceIssue:null,sourceHash:'c'.repeat(64),base:{status:'not-requested',sha:null}};
  assert.equal(validSource(snapshot,head,true),true);
  for (const change of [{head:'d'.repeat(40)},{sourceStatus:'unavailable'},{sourceIssue:'hidden-index-entries'},
    {sourceIssue:'git-source-transforms'},{sourceHash:null},{sourceHash:['c'.repeat(64)]},{base:{status:'unavailable'}}]) {
    assert.equal(validSource({...snapshot,...change},head,true),false);
  }
  assert.equal(validSource(snapshot,head,false),false);
  assert.equal(validSource(snapshot,'wrong-sha',true),false);
});

test('a complete census stays observed and the caller label stays unverified', () => {
  const value=report(); assert.equal(validateReport(value,head,id),value);
  assert.equal(value.source_binding,'unverified-caller-label');
  assert.equal(value.redistribution_approved,false);
});

test('unknown metadata, origins and approval changes refuse publication', () => {
  const changes=[v=>v.private_path='PRIVATE',v=>v.source_commit_label='d'.repeat(40),v=>v.observation_id='other',
    v=>v.source_binding='verified',v=>v.requested_architecture='arm64',v=>v.selection='latest',
    v=>v.selected_instance.private_root='PRIVATE',v=>v.selected_instance.version='PRIVATE',
    v=>v.selected_instance.edition='PRIVATE',v=>v.selected_instance.release_state='PRIVATE',
    v=>v.query_utility.sha256='PRIVATE',v=>v.query_utility.bytes=0,
    v=>v.query_utility.bytes=16777217,v=>v.query_utility.extra='PRIVATE',
    v=>v.query_utility.sha256=['b'.repeat(64)],v=>v.selected_instance.version=['18.11.12328.437']];
  for(const key of ['vendor_file_content_read','vendor_file_hashes_observed','vendor_file_versions_observed',
    'vendor_signatures_observed','redistribution_approved','source_delivery_approved','runtime_collection_allowed',
    'production_execution_allowed','production_activation','r19_complete']) changes.push(v=>v[key]=true);
  for (const change of changes) {const v=report();change(v);assert.throws(()=>validateReport(v,head,id));}
});

test('missing, additional, repeated and overbound CRT metadata cannot masquerade as a complete census', () => {
  const changes=[v=>v.versions=[],v=>v.version_count=2,v=>v.family_count=2,v=>v.file_count=5,
    v=>v.versions.push(structuredClone(v.versions[0])),v=>v.versions[0].version='v145',
    v=>v.versions[0].families.push(structuredClone(v.versions[0].families[0])),
    v=>v.versions[0].families[0].role='debug-crt',v=>v.versions[0].families[0].role=['vc145-crt'],
    v=>v.versions[0].version=['14.51.36231'],v=>v.versions[0].extra='PRIVATE',
    v=>v.versions[0].families[0].extra='PRIVATE',v=>delete v.versions[0].families[0].files['msvcp140.dll'],
    v=>v.versions[0].families[0].files['other.dll']={presence:'regular-file-present',bytes:1},
    v=>v.versions[0].families[0].files['msvcp140.dll'].bytes=16777217,
    v=>v.versions[0].families[0].files['msvcp140.dll'].bytes=true,
    v=>v.versions[0].families[0].files['msvcp140.dll'].sha256='d'.repeat(64)];
  for (const change of changes) {const v=report();change(v);assert.throws(()=>validateReport(v,head,id));}
});

test('negative observations bind no partial list and accept only finite reasons', () => {
  const v=report(); Object.assign(v,{status:'unavailable',reason:'linked-path',versions:[],
    version_count:0,family_count:0,file_count:0,metadata_snapshot_stable:false});
  assert.equal(validateReport(v,head,id),v);
  for (const change of [x=>x.reason='PRIVATE',x=>x.reason='none',x=>x.file_count=4,
    x=>x.versions=report().versions,x=>x.metadata_snapshot_stable=true]) {
    const copy=structuredClone(v);change(copy);assert.throws(()=>validateReport(copy,head,id));
  }
});

test('discarded duplicate-key text cannot leak through the published JSON bytes', () => {
  const raw=Buffer.from(JSON.stringify(report()).replace('{','{"selected_instance":{"PRIVATE":"sensitive-record-never-allowed"},'));
  const projected=projectReport(raw,head,id);
  assert.equal(projected.bytes.includes(Buffer.from('PRIVATE')),false);
  assert.equal(projected.bytes.includes(Buffer.from('sensitive-record-never-allowed')),false);
  assert.deepEqual(JSON.parse(projected.bytes),report());
  assert.equal(projected.bytes.toString(),projectReport(Buffer.from(JSON.stringify(report())),head,id).bytes.toString());
  const lastUnknown=Buffer.from(JSON.stringify(report()).replace(/}$/,',"selected_instance":{"PRIVATE":"forbidden"}}'));
  assert.throws(()=>projectReport(lastUnknown,head,id));
  assert.throws(()=>projectReport(Buffer.alloc(65537),head,id));
});

function diagnostic() {
  return {schema:'proxy-r19-msvc-observer-diagnostic-v1',phase:'authored-contracts',code:'unexpected',
    contracts:37,failures:1,errors:0,skipped:0,tests:['core-13']};
}

test('fatal diagnostics publish only finite child fields and keep every admission gate closed', () => {
  const value=diagnostic();
  const error=Object.assign(new Error('PRIVATE raw exception'), {stdout:JSON.stringify(value),stderr:'PRIVATE raw stderr'});
  const projected=projectFailure('observer-child',error);
  assert.deepEqual(projected.observer,value);
  assert.equal(projected.scope,'fatal-diagnostic-not-source-bound');
  for(const key of ['raw_context_published','source_binding_established','census_receipt_published',
    'redistribution_approved','runtime_collection_allowed','production_execution_allowed','r19_complete']) assert.equal(projected[key],false);
  assert.equal(JSON.stringify(projected).includes('PRIVATE'),false);
  for(const phase of ['env','source-before','source-after','project','publish','source-final']) {
    assert.equal(projectFailure(phase,error).observer,null);
  }
  for(const phase of ['observer-identity','machine-utility','select-query','select-identity','public-root','census','utility-final']) {
    const v={...value,phase,failures:0,tests:[]};
    assert.deepEqual(projectObserverDiagnostic(Buffer.from(JSON.stringify(v))),v);
  }
});

test('unknown diagnostic metadata, overbounds, raw output and accessors cannot become public context', () => {
  const changes=[v=>v.private_path='PRIVATE',v=>v.phase='PRIVATE',v=>v.code='PRIVATE',v=>v.code='none',
    v=>v.contracts=true,v=>v.failures=1001,v=>v.skipped=-1,v=>v.errors='0',v=>v.contracts=null,
    v=>v.tests=['PRIVATE subtest id'],v=>v.tests=['core-29'],v=>v.tests=['publisher-10'],
    v=>v.tests=['core-13','core-13'],v=>v.tests=Array.from({length:9},(_,i)=>`core-0${i+1}`)];
  for(const change of changes) {
    const value=diagnostic();change(value);
    assert.throws(()=>projectObserverDiagnostic(JSON.stringify(value)));
    const projected=projectFailure('observer-child',{stdout:JSON.stringify(value),stderr:'PRIVATE'});
    assert.equal(projected.observer,null);assert.equal(JSON.stringify(projected).includes('PRIVATE'),false);
  }
  for(const raw of ['PRIVATE raw output','{',Buffer.alloc(4097),null]) {
    assert.throws(()=>projectObserverDiagnostic(raw));
    assert.equal(projectFailure('observer-child',{stdout:raw}).observer,null);
  }
  let accessed=false;
  const error={get stdout(){accessed=true;throw new Error('PRIVATE');},get stderr(){accessed=true;throw new Error('PRIVATE');}};
  assert.equal(projectFailure('observer-child',error).observer,null);assert.equal(accessed,false);
  assert.equal(projectFailure('PRIVATE unknown phase',error).phase,'unavailable');
  const raw=JSON.stringify(diagnostic()).replace('{','{"discarded":"PRIVATE",');
  assert.equal(projectFailure('observer-child',{stdout:raw}).observer,null);
  const duplicate=JSON.stringify(diagnostic()).replace('{','{"code":"PRIVATE discarded duplicate",');
  assert.equal(JSON.stringify(projectFailure('observer-child',{stdout:duplicate})).includes('PRIVATE'),false);
});
