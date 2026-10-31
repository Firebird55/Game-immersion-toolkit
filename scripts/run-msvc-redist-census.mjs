// Build-host observation only; never an input to the runtime collector.
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {captureSourceSnapshot} from './check-evidence.mjs';

const sha256 = value => createHash('sha256').update(value).digest('hex');
const hex = value => typeof value === 'string' && /^[0-9a-f]{40}$/.test(value);
const integer = value => Number.isSafeInteger(value) && value >= 0;
const failure = () => { throw new Error('Census evidence unavailable.'); };
const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort());
const reportKeys = ['schema','status','reason','source_commit_label','source_binding','observation_id',
  'observation_id_authority','selected_instance','query_utility','requested_architecture','selection','versions',
  'version_count','family_count','file_count','metadata_snapshot_stable','vendor_file_content_read',
  'vendor_file_hashes_observed','vendor_file_versions_observed','vendor_signatures_observed','entitlement_probe',
  'rights_review','license_eligibility','redistribution_approved','source_delivery_approved','runtime_collection_allowed',
  'production_execution_allowed','production_activation','native_closure','native_windows_11_acceptance','r19_complete','installer'];
const reasons = new Set(['none','invalid-input','platform-unavailable','linked-path','missing-layout','nonregular-layout',
  'metadata-unavailable','version-limit','family-limit','unknown-version-entry','unknown-family-entry','ambiguous-entry',
  'required-file-unavailable','member-size-limit','instance-unavailable','instance-ambiguous','instance-version-mismatch',
  'instance-metadata-unavailable','instance-limit','vswhere-origin','vswhere-changed','query-unavailable','query-limit',
  'query-cleanup-unconfirmed','layout-changed','deadline','output-unavailable','output-limit','observation-failed']);
const files = ['msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'];
const falseFields = ['vendor_file_content_read', 'vendor_file_hashes_observed',
  'vendor_file_versions_observed', 'vendor_signatures_observed', 'redistribution_approved',
  'source_delivery_approved', 'runtime_collection_allowed', 'production_execution_allowed',
  'production_activation', 'r19_complete'];

export function validSource(snapshot, head, clean) {
  return hex(head) && clean === true && snapshot?.head === head
    && snapshot.sourceStatus === 'available' && snapshot.sourceIssue === null
    && typeof snapshot.sourceHash === 'string' && /^[0-9a-f]{64}$/.test(snapshot.sourceHash)
    && snapshot.base?.status === 'not-requested';
}

export function validateReport(value, head, id) {
  if (!exactKeys(value, reportKeys) || value.schema !== 'proxy-r19-msvc-redist-census-v1'
      || value.source_commit_label !== head || value.observation_id !== id
      || value.source_binding !== 'unverified-caller-label' || value.observation_id_authority !== 'binding-only'
      || value.requested_architecture !== 'x64' || value.selection !== 'none'
      || value.entitlement_probe !== 'not-performed' || value.license_eligibility !== 'unverified'
      || value.rights_review !== 'pending-owner-and-exact-source' || value.native_closure !== 'unverified'
      || value.native_windows_11_acceptance !== 'unavailable' || value.installer !== 'not-built'
      || falseFields.some(key => value[key] !== false)
      || !['observed-not-approved', 'unavailable'].includes(value.status)
      || !Array.isArray(value.versions) || value.versions.length > 16
      || !exactKeys(value.selected_instance, ['version','edition','release_state'])
      || value.selected_instance.version !== null && (typeof value.selected_instance.version !== 'string'
        || !/^18(?:\.[0-9]{1,6}){3}$/.test(value.selected_instance.version))
      || !['unknown','enterprise','professional','community','build-tools'].includes(value.selected_instance.edition)
      || !['unknown','release','prerelease'].includes(value.selected_instance.release_state)
      || value.query_utility !== null && (!exactKeys(value.query_utility,['bytes','sha256'])
        || !integer(value.query_utility.bytes) || value.query_utility.bytes < 1 || value.query_utility.bytes > 16777216
        || typeof value.query_utility.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.query_utility.sha256))) failure();
  if (value.status === 'unavailable') {
    if (value.versions.length || value.version_count !== 0 || value.family_count !== 0
        || value.file_count !== 0 || value.metadata_snapshot_stable !== false
        || !reasons.has(value.reason) || value.reason === 'none') failure();
    return value;
  }
  if (value.reason !== 'none' || value.metadata_snapshot_stable !== true
      || !/^18(?:\.[0-9]{1,6}){3}$/.test(value.selected_instance?.version ?? '')
      || !['enterprise', 'professional', 'community', 'build-tools'].includes(value.selected_instance.edition)
      || !['release', 'prerelease'].includes(value.selected_instance.release_state)
      || !integer(value.query_utility?.bytes) || value.query_utility.bytes < 1 || value.query_utility.bytes > 16777216
      || !/^[0-9a-f]{64}$/.test(value.query_utility.sha256 ?? '') || !value.versions.length) failure();
  let families = 0, members = 0;
  const versions = new Set();
  for (const row of value.versions) {
    if (!exactKeys(row,['version','families']) || typeof row.version !== 'string'
        || !/^(?:0|[1-9][0-9]{0,5})(?:\.(?:0|[1-9][0-9]{0,5})){1,3}$/.test(row.version)
        || versions.has(row.version) || !Array.isArray(row.families) || !row.families.length || row.families.length > 6) failure();
    versions.add(row.version);
    const roles = new Set();
    for (const family of row.families) {
      if (!exactKeys(family,['role','files']) || typeof family.role !== 'string'
          || !/^vc14[0-5]-crt$/.test(family.role) || roles.has(family.role)
          || JSON.stringify(Object.keys(family.files ?? {}).sort()) !== JSON.stringify([...files].sort())) failure();
      roles.add(family.role); families++;
      for (const name of files) {
        const member = family.files[name];
        if (member?.presence !== 'regular-file-present' || !integer(member.bytes)
            || member.bytes < 1 || member.bytes > 16777216 || Object.keys(member).length !== 2) failure();
        members++;
      }
    }
  }
  if (value.version_count !== versions.size || value.family_count !== families || value.file_count !== members) failure();
  return value;
}

export function projectReport(input, head, id) {
  if (!Buffer.isBuffer(input) || input.length > 65536) failure();
  const report = validateReport(JSON.parse(input.toString('utf8')), head, id);
  // Publish only this checked value, never original text with duplicate keys,
  // discarded values, whitespace or other private serialization artifacts.
  const canonical = value => Array.isArray(value) ? value.map(canonical)
    : value !== null && typeof value === 'object'
      ? Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])) : value;
  const bytes = Buffer.from(JSON.stringify(canonical(report))+'\n');
  if (bytes.length > 65536) failure();
  return {report, bytes};
}

// This fixed Python program imports only the reviewed stdlib census and its
// authored tests. No user command/root input, PATH tool search or package setup.
const program = String.raw`
import importlib.util,io,json,os,re,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]); head=sys.argv[2]; oid=sys.argv[3]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
try:
 if os.name!='nt' or sys.version_info[:3]!=(3,12,10): raise ValueError()
 import struct
 if struct.calcsize('P')!=8: raise ValueError()
 probe=load('msvc_census',root/'scripts/probe-msvc-redist.py')
 suite=unittest.TestSuite()
 for name in ('test_msvc_redist_probe','test_msvc_redist_ci_boundary'):
  tests=load(name,root/'backend/tests'/(name+'.py'))
  suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(tests))
 result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
 if not result.wasSuccessful() or result.skipped or not result.testsRun: raise ValueError()
 budget=probe.Budget(); machine=probe.canonical_path(probe.known_program_files_x86())
 utility=machine/'Microsoft Visual Studio/Installer/vswhere.exe'
 initial=probe.utility_identity(utility,budget)
 raw=probe.bounded_capture([str(utility),'-all','-prerelease','-products','*','-version','[18.0,19.0)',
  '-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-format','json','-utf8','-nologo'],budget)
 def unique(items):
  value={}
  for key,item in items:
   if key in value: raise ValueError()
   value[key]=item
  return value
 values=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
 if type(values) is not list or len(values)!=1 or type(values[0]) is not dict: raise ValueError()
 selected=probe.canonical_path(values[0].get('installationPath','')); version=values[0].get('installationVersion')
 if type(version) is not str or not probe.VS_VERSION.fullmatch(version): raise ValueError()
 probe.directory(selected,budget)
 public=probe.canonical_path(root/'output/checks')
 if any(probe.path_within(public,p,budget) for p in (selected,utility.parent)): raise ValueError()
 if probe.utility_identity(utility,budget)!=initial: raise ValueError()
 report=probe.observe(selected,version,utility,head,oid,budget=budget)
 if report['status']=='observed-not-approved' and report['query_utility']!=initial: raise ValueError()
 if probe.utility_identity(utility,budget)!=initial: raise ValueError()
 print(json.dumps({'contracts':result.testsRun,'skipped':len(result.skipped),'python':'3.12.10','census_performed':True,'report':report}))
except BaseException:
 print('MSVC census unavailable; no source admitted.',file=sys.stderr); sys.exit(2)
`;

// Reuse the census's raw root-first Windows/reparse guards for every sink.
// Preflight BOTH fixed leaves before either write; never delete old files.
const publish = String.raw`
import hashlib,importlib.util,json,stat,sys
from pathlib import Path
try:
 root=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('msvc_census',root/'scripts/probe-msvc-redist.py')
 probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
 budget=probe.Budget(); probe.directory(probe.canonical_path(root),budget)
 for path in (root/'output',root/'output/checks'):
  path=probe.canonical_path(path); value=probe.info(path,budget,missing=True)
  if value is None: path.mkdir()
  probe.directory(path,budget)
 targets=[probe.canonical_path(root/'output/checks'/name) for name in ('MSVC-REDIST-CENSUS.json','MSVC-REDIST-CI-BINDING.json')]
 if any(probe.info(path,budget,missing=True) is not None for path in targets): raise ValueError()
 raw=sys.stdin.buffer.read(131073)
 if len(raw)>131072: raise ValueError()
 values=json.loads(raw)
 if type(values) is not list or len(values)!=2 or any(type(v) is not dict for v in values): raise ValueError()
 for path,value in zip(targets,values): probe.write_report(path,value,budget=budget)
 for path,value in zip(targets,values):
  entry=probe.info(path,budget)
  if not stat.S_ISREG(entry.st_mode) or entry.st_size>65536: raise ValueError()
  with path.open('rb') as stream: actual=stream.read(65537)
  if len(actual)!=entry.st_size or actual!=probe.serialized(value): raise ValueError()
  if path==targets[0] and (len(actual)!=values[1]['census']['bytes'] or hashlib.sha256(actual).hexdigest()!=values[1]['census']['sha256']): raise ValueError()
 print('PAIR_WRITTEN')
except BaseException:
 print('MSVC metadata publication unavailable.',file=sys.stderr);sys.exit(2)
`;

export function main(environment = process.env) {
  const head = environment.GITHUB_SHA;
  const id = `msvc-redist-${environment.GITHUB_RUN_ID}-${environment.GITHUB_RUN_ATTEMPT}`;
  if (process.platform !== 'win32' || environment.GITHUB_ACTIONS !== 'true'
      || environment.GITHUB_EVENT_NAME !== 'workflow_dispatch' || !hex(head)
      || !/^\d+$/.test(environment.GITHUB_RUN_ID ?? '') || !/^\d+$/.test(environment.GITHUB_RUN_ATTEMPT ?? '')
      || !environment.R19_CENSUS_PYTHON) failure();
  const cwd = process.cwd();
  const gitClean = () => execFileSync('git', ['status', '--porcelain=v1', '--untracked-files=all'],
    {cwd, encoding:'utf8', stdio:['ignore','pipe','pipe'], maxBuffer:1048576, timeout:10000}).length === 0;
  const before = captureSourceSnapshot({cwd});
  // Snapshot checks effective attributes before status can invoke Git filters.
  if (!validSource(before, head, true) || !gitClean()) failure();
  const rawSummary = execFileSync(environment.R19_CENSUS_PYTHON,
    ['-I','-B','-c',program,cwd,head,id],
    {cwd, encoding:'utf8', stdio:['ignore','pipe','pipe'], maxBuffer:131072, timeout:150000});
  const summary = JSON.parse(rawSummary);
  if (!exactKeys(summary,['contracts','skipped','python','census_performed','report'])
      || !integer(summary.contracts) || !summary.contracts || summary.contracts > 1000 || summary.skipped !== 0
      || summary.python !== '3.12.10' || summary.census_performed !== true) failure();
  const after = captureSourceSnapshot({cwd});
  if (!validSource(after, head, true) || !gitClean() || JSON.stringify(before) !== JSON.stringify(after)) failure();
  const {report, bytes:raw} = projectReport(Buffer.from(JSON.stringify(summary.report)), head, id);
  const binding = {schema:'proxy-r19-msvc-redist-ci-binding-v1',
    status:report.status === 'observed-not-approved' ? 'source-bound-observed-not-approved' : 'source-bound-unavailable',
    provider:'github', event:'workflow_dispatch', source_commit:head,
    run_id:environment.GITHUB_RUN_ID, run_attempt:environment.GITHUB_RUN_ATTEMPT, observation_id:id,
    source_before:before, source_after:after, clean_source:true,
    selector:'all-vs18-vc-tools-exact-single-instance', contracts:summary.contracts, skipped:0,
    observer_python:'3.12.10', observer_role:'build-host-only-not-runtime-supplier',
    census:{filename:'MSVC-REDIST-CENSUS.json',bytes:raw.length,sha256:sha256(raw),status:report.status},
    redistribution_approved:false,runtime_collection_allowed:false,production_execution_allowed:false,
    native_windows_11_acceptance:'unavailable',r19_complete:false,installer:'not-built'};
  const pairWritten = execFileSync(environment.R19_CENSUS_PYTHON,['-I','-B','-c',publish,cwd],
    {cwd,input:JSON.stringify([JSON.parse(raw),binding]),encoding:'utf8',stdio:['pipe','pipe','pipe'],maxBuffer:8192,timeout:45000});
  if (pairWritten !== 'PAIR_WRITTEN\r\n' && pairWritten !== 'PAIR_WRITTEN\n') failure();
  const final = captureSourceSnapshot({cwd});
  if (!validSource(final,head,true) || !gitClean() || JSON.stringify(before) !== JSON.stringify(final)) failure();
  console.log('MSVC_METADATA_PAIR_VALIDATED');
  return report.status === 'observed-not-approved' ? 0 : 2;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode=main(); }
  catch { console.error('MSVC census evidence unavailable; no source admitted.'); process.exitCode=2; }
}
