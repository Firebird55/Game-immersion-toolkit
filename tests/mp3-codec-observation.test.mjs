// Authored metadata/process/filesystem fixtures only; no codec/native execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,readdirSync,realpathSync,mkdtempSync,rmSync,existsSync,writeFileSync,symlinkSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {canonical,validateNative,validateFailure,runObservation,projectNames,flags,baseCommit,root} from '../scripts/run-mp3-codec-observation.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex'), rec=b=>({bytes:b.length,sha256:sha(b)}), zero='0'.repeat(64), h='1'.repeat(40), sourceHash='2'.repeat(64);
const pin=JSON.parse(readFileSync(join(root,'packaging/codecs/ffmpeg-mp3-replay.json')));
const four=['packaging/codecs/ffmpeg-mp3-replay.json','scripts/replay-mp3-codec.py','scripts/build-mp3-codec-replay.ps1','scripts/fixtures/mp3-codec-origin.c'];
const libs=['avcodec-r19-audio-lame-63.dll','avformat-r19-audio-lame-63.dll','avutil-r19-audio-lame-61.dll','swresample-r19-audio-lame-7.dll','avfilter-r19-audio-lame-12.dll','libmp3lame.dll'];
const approved={
 'packaging/codecs/ffmpeg-mp3-replay.json':{bytes:15933,sha256:'8274d8842d05596f49f644f313dd0f885b19b37240fa21dc877fd3b3ff36f4e4'},
 'scripts/replay-mp3-codec.py':{bytes:48280,sha256:'615ea978748aa692381bb592628743fbf4b9a4c9ad449be51d929c796a3f4db7'},
 'scripts/build-mp3-codec-replay.ps1':{bytes:35311,sha256:'a0d6f92af1bf7e7377b6eafba902f1c16e120bbee7edd770dcfc76e46676d638'},
 'scripts/fixtures/mp3-codec-origin.c':{bytes:1571,sha256:'c26d6d6c5285c73934fbe214d528b8efea2d5596a65cb8ab57578eb93f1853c3'}};
function fixture(){
 const p=structuredClone(pin);
 const inputs=Object.fromEntries(projectNames.map(n=>{const b=readFileSync(join(root,n));return[n,{raw:rec(b),canonical_lf:rec(Buffer.from(b.toString('utf8').replaceAll('\r\n','\n')))}];}));
 const originals=Object.fromEntries([...p.sources,...p.original_recipes].map(r=>[r.filename,{bytes:r.bytes,sha256:r.sha256}]));
 const kit={...Object.fromEntries(Object.entries(originals).map(([n,r])=>['original-inputs/'+n,r])),...Object.fromEntries(projectNames.map(n=>['project-orchestration/'+n,inputs[n].raw])),...Object.fromEntries(['BASE-BSD-COPIES.json','FUNCTIONAL-LICENSE-BOUNDARY.json','MP3-BSD-COPIES.json'].map(n=>[n,{bytes:1,sha256:zero}]))};
 const candidate={...Object.fromEntries([...libs,'ffmpeg.exe','mp3-codec-origin.exe'].map(n=>[n,{bytes:4,sha256:zero}])),...Object.fromEntries(p.notices.map(n=>['notices/'+n.component+'/'+n.path,{bytes:n.bytes,sha256:n.sha256}])),'notices/project/MP3-BUILD-RECIPES-LICENSE.txt':{"bytes":11978,"sha256":"011cccd64fe949708b7e554df8a54089edaffcadd2ae500d4299178310ecbbc7"}};
 const cp=JSON.parse(readFileSync(join(root,'packaging/build-tools/cmake-4.4.5-windows-x64.json'))),pick=(r,n)=>Object.fromEntries(n.map(k=>[k,r[k]]));
 const cm={schema:'proxy-pinned-build-cmake-v1',name:'CMake',version:'4.4.5',platform:'win-x64',scope:'build-host-only; static byte verification, not native execution',policy_sha256:inputs['packaging/build-tools/cmake-4.4.5-windows-x64.json'].raw.sha256,archive:pick(cp.archive,['filename','root','bytes','sha256','entries','regular_files','expanded_bytes']),executable:pick(cp.executable,['path','bytes','sha256']),notices:cp.notices.map(n=>pick(n,['path','bytes','sha256'])),tree_sha256:zero,regular_files:8817,directories:163,runtime_collection_allowed:false,production_execution_allowed:false,source_delivery_approved:false,native_payload_in_source_review:false,native_windows_11_acceptance:'unavailable',r19_complete:false,operation:'verified'};
 const value={schema:'proxy-r19-mp3-ci-native-observation-v1',status:'validated-controller-native-passed',source_commit:null,draft_base_commit:baseCommit,source_binding_scope:'ignored functional draft plus exact input cohort; not clean0f evidence',project_inputs:inputs,source_review_files:kit,original_source_tree:p.original_source_tree,derived_lame_tree:p.lame_working_source_tree,source_inputs:originals,project_license:p.build_recipe_license,final_four_copies:{schema:'proxy-r19-mp3-final-bsd-copies-v3',license:p.build_recipe_license,approved_baselines:approved,supplemental_approved_baselines:p.build_recipe_license.supplemental_approval.approved_baselines,import_alias_approved_baselines:p.build_recipe_license.import_alias_approval.approved_baselines,copies:Object.fromEntries(four.map(n=>[n,inputs[n]])),scope:'Byte bindings only; no future-functional, helper, upstream or complete-source approval',...flags},candidate_files:candidate,generated_configuration:Object.fromEntries(['.config','config.fate','config.mak','config.sh'].map(n=>[n,{bytes:1,sha256:zero}])),tool_observation:{image_os:'win25-vs2026',image_version:'20261030.294.1',compiler:'19.51.36260.0',visual_studio_version:'18.11.12315.225',toolset:'14.51.36231',sdk:'10.0.26100.0',cmake:'4.4.5',compiler_executable:{bytes:4,sha256:zero},observer_python:{bytes:4,sha256:zero},seal_comparison:'exact-before-after-private-tree-comparison',unbound_prerequisites:p.host.unbound_prerequisites},cmake_supplier:cm,native_imports:Object.fromEntries([...libs,'ffmpeg.exe','mp3-codec-origin.exe'].map(n=>[n,{imports:['KERNEL32.dll'],delay_imports:[]}])),observer_loaded_origins:Object.fromEntries(libs.map(n=>[n,{origin:'quarantined-candidate-observer-process',...candidate[n]}])),cli_child_origins:['encode-440','decode-440','encode-880','decode-880'].map(operation=>({operation,loaded_native:[...[...libs,'ffmpeg.exe'].map(file=>({origin:'application',file,...candidate[file]})),{origin:'windows-system-observed',file:'kernel32.dll',bytes:4,sha256:zero}],scope:'two stable snapshots of this live CLI operation only'})),cli_scope:'two stable live snapshots during each authored encode/decode only; not all possible CLI paths',authored_two_tones:'actual CLI encode/decode and forbidden-other-tone check passed',malformed_input:'rejected; previous complete output preserved',ordinary_voiced_mobile_export:'not-run',runtime_integration:'not-implemented',fft_provenance:'unresolved',...flags};return JSON.parse(JSON.stringify(value));
}
const failFixture=()=>({schema:'proxy-r19-mp3-ci-failure-v1',status:'failed',producer_schema:'proxy-r19-mp3-draft-failure-v1',phase:'build-ffmpeg',controller_source_commit:h,draft_base_commit:baseCommit,details:{exit_code:2,diagnostic_codes:['C1083'],diagnostic_categories:['compiler-error'],log_truncated:false},...flags});
function configureFixture(){const v=failFixture();v.schema='proxy-r19-mp3-ci-configure-failure-v2';v.phase='configure-ffmpeg';v.details.configure_observation={scope:'private-log-observations-not-cause',logs:['configure-log','cumulative-build-output'].map(role=>({role,state:'missing',truncated:false,terminal:'missing',fatal_templates:[],probe_codes:[]}))};return v;}
const source=()=>({head:h,base:{status:'not-requested',sha:null},sourceHash,sourceStatus:'available',sourceIssue:null});
function rig(mode='success'){
 const native=fixture(),state={schema:'proxy-r19-mp3-ci-start-v1',source:source(),project_inputs:native.project_inputs},seen=[];
 const options={mode,cwd:root,platform:'win32',environment:{GITHUB_SHA:h,GITHUB_RUN_ID:'41234567890',GITHUB_RUN_ATTEMPT:'1'},snapshot:source,git:(_cwd,args)=>args[0]==='status'?'':args[0]==='rev-parse'?h:readFileSync(join(root,args[2].slice(41))),python:(_env,_cwd,command,args,input)=>{seen.push(command);if(command==='snapshot')return canonical({schema:'proxy-r19-mp3-project-inputs-v1',project_inputs:native.project_inputs});if(command==='read-start')return canonical(state);if(command==='observe')return canonical(native);if(command==='failure')return canonical(failFixture());if(command==='save-start')return Buffer.from('START_WRITTEN');if(command==='publish'){options.values=JSON.parse(input);return Buffer.from('PAIR_WRITTEN');}if(command==='read-pair'){assert.deepEqual(JSON.parse(input),options.values);return Buffer.from('PAIR_VERIFIED');}throw Error('unexpected fixed command');}};
 return {options,seen,native,state};
}
const python=process.env.R19_MP3_PYTHON||resolve(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
function pythonSource(body,args=[],input){return execFileSync(python,['-I','-B','-c',`import importlib.util,json,pathlib,sys\nroot=pathlib.Path(sys.argv[1])\ns=importlib.util.spec_from_file_location('publisher',root/'scripts/mp3-codec-observation.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)\nm=p.load_controller(root)\n${body}`,root,...args],{input,maxBuffer:1024*1024,timeout:15000});}

test('closed native projection retains actual four-operation metadata, source copies and false gates',()=>{const value=fixture();assert.equal(validateNative(value),value);assert.equal(Object.keys(value.project_inputs).length,17);assert.equal(Object.keys(value.source_review_files).length,26);assert.equal(value.cli_child_origins.length,4);assert.equal(value.source_commit,null);});
test('unknown fields, private names, source/copy drift and enum/type coercions refuse before public hashing',()=>{for(const mutate of [v=>v.private='PRIVATE-path',v=>v.project_inputs['LICENSE'].raw.bytes=true,v=>v.source_review_files['project-orchestration/LICENSE'].sha256='a'.repeat(64),v=>v.final_four_copies.copies[four[0]].raw.bytes++,v=>v.cli_child_origins[0].loaded_native.push({origin:'windows-system-observed',file:'PRIVATE-model.dll',bytes:1,sha256:zero}),v=>v.cli_child_origins.pop(),v=>v.cli_child_origins[0].loaded_native[0].file='C:/PRIVATE/file.dll',v=>v.cmake_supplier.private='PRIVATE',v=>v.generated_configuration['config.log']={bytes:1,sha256:zero},v=>v.native_imports['ffmpeg.exe'].private='PRIVATE',v=>v.production_execution_allowed=0,v=>v.project_license.identifier='MIT',v=>v.project_license.supplemental_approval.approved_baselines['scripts/future.py']={bytes:1,sha256:zero},v=>v.project_license.supplemental_approval.approval_proposal.sha256=zero,v=>v.project_license.original_notice_prefix.bytes++,v=>delete v.final_four_copies.supplemental_approved_baselines,v=>v.final_four_copies.approved_baselines['scripts/build-mp3-codec-replay.ps1'].sha256='1b0cc7746a84d6152ddc0bb48c6857213d05c7cad68f05b2a537e0346a0ceb64',v=>v.candidate_files['notices/PRIVATE-name']={bytes:1,sha256:zero},v=>delete v.candidate_files['notices/lame/COPYING'],v=>v.candidate_files['notices/lame/README'].bytes++,v=>v.cmake_supplier.executable.path='PRIVATE/name',v=>v.cmake_supplier.notices[0].sha256=zero]){const value=fixture();mutate(value);assert.throws(()=>validateNative(value));}});
test('accessors, foreign prototypes, duplicate authority rows, NaN and sparse arrays do not become projections',()=>{let calls=0;const value=fixture();Object.defineProperty(value,'status',{get(){calls++;return 'PRIVATE';},enumerable:true});assert.throws(()=>validateNative(value));assert.equal(calls,0);const inherited=Object.create({secret:'PRIVATE'});Object.assign(inherited,fixture());assert.throws(()=>validateNative(inherited));const duplicate=fixture();duplicate.cli_child_origins[0].loaded_native.push(duplicate.cli_child_origins[0].loaded_native[0]);assert.throws(()=>validateNative(duplicate));const nan=fixture();nan.candidate_files['ffmpeg.exe'].bytes=NaN;assert.throws(()=>validateNative(nan));const sparse=fixture();delete sparse.cli_child_origins[0];assert.throws(()=>validateNative(sparse));});
test('failure schema has finite code families and no private/unknown detail echo',()=>{assert.equal(validateFailure(failFixture()).details.exit_code,2);for(const mutate of [v=>v.details.private='PRIVATE',v=>v.details.diagnostic_codes=['C99999'],v=>v.details.diagnostic_categories=['PRIVATE-model'],v=>v.details.exit_code=true,v=>v.phase='PRIVATE argv',v=>v.phase=['build-ffmpeg'],v=>v.details.log_truncated=1,v=>v.r19_complete=true]){const v=failFixture();mutate(v);assert.throws(()=>validateFailure(v));}});
test('capture and success binding keep historical null/0f while current source/head and exact public bytes bind',()=>{const capture=rig('capture');assert.deepEqual(runObservation(capture.options),{captured:true});const r=rig();assert.deepEqual(runObservation(r.options),{validated_pair:true,publication:'success'});const b=r.options.values['MP3-CI-BINDING.json'],v=r.options.values['MP3-DRAFT-RECEIPT.json'];assert.equal(b.source_commit,h);assert.equal(b.source_hash,sourceHash);assert.equal(v.source_commit,null);assert.equal(v.draft_base_commit,baseCommit);assert.deepEqual(b.native_receipt,{file:'MP3-DRAFT-RECEIPT.json',...rec(canonical(v))});assert.equal(b.private_original_receipt_hash_published,false);assert.deepEqual(r.seen.slice(-2),['publish','read-pair']);});
test('dirty/head/sourceHash/raw-LF mismatch refuses and emits no validated pair',()=>{for(const change of [r=>r.options.git=()=> 'dirty',r=>r.options.snapshot=()=>({...source(),sourceHash:'3'.repeat(64)}),r=>r.state.project_inputs['LICENSE'].canonical_lf={bytes:1,sha256:zero},r=>r.options.environment.GITHUB_SHA='a'.repeat(40),r=>r.options.snapshot=()=>({...source(),sourceStatus:'unavailable'}),r=>r.options.snapshot=()=>({...source(),private:'PRIVATE'}),r=>r.options.environment.GITHUB_RUN_ATTEMPT='0']){const r=rig();change(r);assert.throws(()=>runObservation(r.options));assert.ok(!r.seen.includes('publish'));}});
test('postpublication source change or byte-readback failure never grants workflow upload',()=>{const changed=rig();let reads=0;changed.options.snapshot=()=>{reads++;return reads>=3?{...source(),sourceHash:'3'.repeat(64)}:source();};assert.throws(()=>runObservation(changed.options));const readback=rig();const call=readback.options.python;readback.options.python=(...args)=>args[2]==='read-pair'?Buffer.from('PRIVATE-corrupt'):call(...args);assert.throws(()=>runObservation(readback.options));});
test('a completed source change during the final actual pair readback refuses upload authority',()=>{const r=rig();let completed=false;const call=r.options.python;r.options.python=(...args)=>{const result=call(...args);if(args[2]==='read-pair')completed=true;return result;};r.options.snapshot=()=>completed?{...source(),sourceHash:'3'.repeat(64)}:source();assert.throws(()=>runObservation(r.options));assert.equal(completed,true);assert.deepEqual(r.seen.slice(-2),['publish','read-pair']);});
test('source-bound negative metadata remains a failure observation, not a native pass',()=>{const r=rig('failure');assert.deepEqual(runObservation(r.options),{validated_pair:true,publication:'failure'});assert.equal(r.options.values['MP3-CI-BINDING.json'].status,'source-bound-failed-observation');assert.ok(!r.options.values['MP3-DRAFT-RECEIPT.json']);});
test('actual Python fixed sink refuses linked ancestors/stale leaves and verifies both published files',()=>{for(const mode of ['valid','linked','stale','extra','tamper']){const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-publisher-')));try{const r=rig();runObservation(r.options);const values=r.options.values;if(mode==='linked'){mkdirSync(join(dir,'outside'));symlinkSync(join(dir,'outside'),join(dir,'output'),'dir');}if(mode==='stale'){mkdirSync(join(dir,'output/checks/r19-mp3-published'),{recursive:true});writeFileSync(join(dir,'output/checks/r19-mp3-published/MP3-CI-BINDING.json'),'old');}if(mode==='extra'){mkdirSync(join(dir,'output/checks/r19-mp3-published'),{recursive:true});writeFileSync(join(dir,'output/checks/r19-mp3-published/PRIVATE-extra'),'owned');}const program=`base=pathlib.Path(sys.argv[2]);v=json.loads(sys.stdin.buffer.read())\ntry:\n p.publish_pair(m,base,v)\n if sys.argv[3]=='tamper':
  target=base/'output/checks/r19-mp3-published/MP3-CI-BINDING.json';raw=target.read_bytes();target.write_bytes(b'X'+raw[1:])\n p.read_pair(m,base,v)\n print('VALID')\nexcept (ValueError,OSError):print('REFUSED')`;const result=pythonSource(program,[dir,mode],canonical(values)).toString().trim();assert.equal(result,mode==='valid'?'VALID':'REFUSED');if(mode==='linked')assert.deepEqual(readdirSync(join(dir,'outside')),[]);if(mode==='stale')assert.ok(!existsSync(join(dir,'output/checks/r19-mp3-published/MP3-DRAFT-RECEIPT.json')));}finally{rmSync(dir,{recursive:true,force:true});}}});

test('actual Python projector compares the complete producer/context, discards known private inventories, and refuses unknown fields',()=>{
 const input=fixture();
 const body=String.raw`import copy
v=json.loads(sys.stdin.buffer.read());pin=copy.deepcopy(m.policy());r={'bytes':4,'sha256':'0'*64};marker='PRIVATE-TOOL-MARKER';private_hash=p.SHA(marker.encode())
original={'authored-source.c':r};derived={'authored-lame.c':r};pin['original_source_tree']=m.base.tree_identity(original);pin['lame_working_source_tree']=m.base.tree_identity(derived)
required=['msvc-bin','msvc-include','msvc-lib-x64','sdk-bin-x64','sdk-include','sdk-ucrt-x64','sdk-um-x64','cmake','msbuild','vc-auxiliary','isolated-msys-bin'];trees={n:{'header.h':r} for n in required};trees['msvc-bin']={'cl.exe':r};trees['msvc-include']={marker+'.h':{'bytes':4,'sha256':private_hash}}
tool={k:v['tool_observation'][k] for k in ['image_os','image_version','compiler','visual_studio_version','toolset','sdk','cmake']};tool.update(trees=trees,individual={n:r for n in ['windows-tar','vswhere','cmd','python']})
cc=dict(sources=pin['sources'],original_recipes=pin['original_recipes'],notices=pin['notices'],project_inputs={n:row['raw'] for n,row in v['project_inputs'].items()},mp3_project_license=m.MP3_PROJECT_LICENSE,mp3_project_copies=m.mp3_copy_inventory(m.project_bytes(),pin),source_review_files=v['source_review_files'],original_sources=original,lame_working_inputs=derived,lame_installed={'bin/libmp3lame.dll':r},build_tools=tool,cmake_supplier=v['cmake_supplier'],ffmpeg_generated=v['generated_configuration'],candidate_files=v['candidate_files'])
context=dict(correspondence=cc,project_inputs=v['project_inputs'],native_imports=v['native_imports'])
raw=dict(schema='proxy-r19-mp3-functional-draft-native-v1',status='quarantined-build-host-probe-passed',source_commit=None,draft_base_commit=p.BASE,source_binding_scope=v['source_binding_scope'],identity='quarantined-mp3-'+p.SHA(m.canonical(cc)),source_correspondence=copy.deepcopy(cc),native_imports=v['native_imports'],loaded_origins=v['observer_loaded_origins'],origin_scope='supplementary observer plus four real CLI creation-handle censuses',cli_child_origins=v['cli_child_origins'],cli_scope=v['cli_scope'],authored_two_tones=v['authored_two_tones'],malformed_input=v['malformed_input'],ordinary_voiced_mobile_export='not-run',runtime_integration='not-implemented',fft_provenance='unresolved',**p.FLAGS)
public=p.projected_native(raw,context,pin,m);text=p.serialized(public).decode();assert marker not in text and private_hash not in text and raw['identity'] not in text and 'original_sources' not in public and 'build_tools' not in public
cases=[]
for kind in ['unknown-top','unknown-private-key','changed-native-hash','missing-child','config-log','identity','wrong-supplier']:
 bad=copy.deepcopy(raw)
 if kind=='unknown-top':bad['private']='PRIVATE'
 elif kind=='unknown-private-key':bad['source_correspondence']['build_tools']['private']='PRIVATE'
 elif kind=='changed-native-hash':bad['native_imports']['ffmpeg.exe']['private']='PRIVATE'
 elif kind=='missing-child':bad['cli_child_origins'].pop()
 elif kind=='config-log':bad['source_correspondence']['ffmpeg_generated']['config.log']=r
 elif kind=='identity':bad['identity']='quarantined-mp3-'+'a'*64
 else:bad['source_correspondence']['sources'][0]['sha256']='a'*64
 try:p.projected_native(bad,context,pin,m)
 except (ValueError,TypeError):cases.append(kind)
 else:raise AssertionError('refusal missing')
print(json.dumps({'positive_closed_projection':True,'private_fields_and_hashes_absent':True,'negative_cases':cases,'native_execution':False}))`;
 const result=JSON.parse(pythonSource(body,[],canonical(input)));assert.equal(result.positive_closed_projection,true);assert.equal(result.private_fields_and_hashes_absent,true);assert.equal(result.negative_cases.length,7);assert.equal(result.native_execution,false);
});
test('actual Python failure projector retains only finite observations and refuses malformed/unknown input',()=>{
 const body=String.raw`raw=dict(schema='proxy-r19-mp3-draft-failure-v1',status='failed',phase='build-ffmpeg',source_commit='1'*40,exit_code=2,profile_manifest=p.record(m.base.recipe_bytes(m.PIN)),diagnostic_codes=['C1083'],diagnostic_categories=['compiler-error'],log_truncated=False,raw_log_published=False,**p.FLAGS)
result=p.projected_failure(raw,m,'1'*40);p.public_failure_shape(m,result,'1'*40);assert result['details']['diagnostic_codes']==['C1083']
import copy
for change in ['unknown','code','gate','manifest','phase']:
 bad=copy.deepcopy(raw)
 if change=='unknown':bad['private']='PRIVATE'
 elif change=='code':bad['diagnostic_codes']=['C99999']
 elif change=='gate':bad['production_execution_allowed']=0
 elif change=='manifest':bad['profile_manifest']['sha256']='a'*64
 else:bad['phase']='PRIVATE'
 try:p.projected_failure(bad,m,'1'*40)
 except (ValueError,TypeError):pass
 else:raise AssertionError('missing refusal')
print('FINITE_ONLY')`;
 assert.equal(pythonSource(body).toString().trim(),'FINITE_ONLY');
});

test('configure v2 is closed in both verifiers and still binds a failed two-file publication',()=>{
 const good=configureFixture();assert.equal(validateFailure(good),good);
 const mutations=[v=>v.phase='build-ffmpeg',v=>v.controller_source_commit=null,v=>v.producer_schema='proxy-r19-mp3-cli-cleanup-refusal-v1',v=>v.schema='proxy-r19-mp3-ci-failure-v1',v=>v.details.configure_observation.scope='cause',v=>v.details.configure_observation.logs.reverse(),v=>v.details.configure_observation.logs.pop(),v=>v.details.configure_observation.logs[0].private='PRIVATE',v=>v.details.configure_observation.logs[0].truncated=1,v=>v.details.configure_observation.logs[0].probe_codes=['C99999'],v=>v.details.configure_observation.logs[0].state='PRIVATE',v=>v.details.configure_observation.logs[0].terminal='libmp3lame-check-failed',v=>v.details.configure_observation.logs[1].terminal='unknown',v=>{Object.assign(v.details.configure_observation.logs[0],{state:'read',terminal:'compiler-test-failed',fatal_templates:[]});},v=>{Object.assign(v.details.configure_observation.logs[0],{state:'read',terminal:'unknown',fatal_templates:['compiler-test-failed','libmp3lame-check-failed']});},v=>{Object.assign(v.details.configure_observation.logs[1],{state:'read',terminal:'not-attributed',probe_codes:['C1083','C1083']});}];
 const bad=mutations.map(change=>{const v=structuredClone(good);change(v);assert.throws(()=>validateFailure(v));return v;});
 const program=String.raw`values=json.loads(sys.stdin.buffer.read())
p.public_failure_shape(m,values[0],'1'*40)
for value in values[1:]:
 try:p.public_failure_shape(m,value,'1'*40)
 except (ValueError,TypeError):pass
 else:raise AssertionError('missing closed refusal')
print('CLOSED')`;
 assert.equal(pythonSource(program,[],JSON.stringify([good,...bad])).toString().trim(),'CLOSED');
 const r=rig('failure'),call=r.options.python;r.options.python=(...args)=>args[2]==='failure'?canonical(good):call(...args);
 assert.deepEqual(runObservation(r.options),{validated_pair:true,publication:'failure'});
 assert.deepEqual(r.options.values['MP3-CI-BINDING.json'].native_receipt,{file:'MP3-FAILURE.json',...rec(canonical(good))});
 assert.deepEqual(r.seen.slice(-2),['publish','read-pair']);
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-pair-')));
 try{assert.equal(pythonSource("v=json.loads(sys.stdin.buffer.read());base=pathlib.Path(sys.argv[2]);p.publish_pair(m,base,v);print(p.read_pair(m,base,v))",[dir],canonical(r.options.values)).toString().trim(),'PAIR_VERIFIED');}
 finally{rmSync(dir,{recursive:true,force:true});}
});

test('actual Python current failure checks precede private-log access and retain old nonconfigure v1 behavior',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-')));
 try{
 const program=String.raw`import copy
out=pathlib.Path(sys.argv[2]);failure=out/'FAILED-STAGE.json'
raw=dict(schema='proxy-r19-mp3-draft-failure-v1',status='failed',phase='configure-ffmpeg',source_commit='1'*40,exit_code=1,profile_manifest=p.record(m.base.recipe_bytes(m.PIN)),diagnostic_codes=[],diagnostic_categories=['unclassified-command-failure'],log_truncated=False,raw_log_published=False,**p.FLAGS)
original=pathlib.Path.open
def guarded(path,*a,**kw):
 if path.name in ('config.log','PRIVATE-BUILD.log'):raise AssertionError('premature private read')
 return original(path,*a,**kw)
pathlib.Path.open=guarded
for change in ['head','null-head','manifest','shape','two-failures']:
 bad=copy.deepcopy(raw)
 if change=='head':bad['source_commit']='2'*40
 elif change=='null-head':bad['source_commit']=None
 elif change=='manifest':bad['profile_manifest']['sha256']='0'*64
 elif change=='shape':bad['private']='SECRET'
 failure.write_bytes(p.serialized(bad))
 if change=='two-failures':(out/'FAILED-CLI-OWNERSHIP.json').write_bytes(p.serialized(bad))
 try:p.collect_failure(m,out,'1'*40)
 except ValueError:pass
 else:raise AssertionError('missing identity refusal')
 if change=='two-failures':(out/'FAILED-CLI-OWNERSHIP.json').unlink()
raw['phase']='build-ffmpeg';failure.write_bytes(p.serialized(raw));old=p.collect_failure(m,out,'1'*40)
assert old==p.projected_failure(raw,m,'1'*40) and old['schema']=='proxy-r19-mp3-ci-failure-v1'
raw['phase']='configure-ffmpeg';failure.write_bytes(p.serialized(raw));pathlib.Path.open=original
value=p.collect_failure(m,out,'1'*40);p.public_failure_shape(m,value,'1'*40)
assert value['schema']==p.CONFIGURE_SCHEMA and all(r['terminal']=='missing' for r in value['details']['configure_observation']['logs'])
print('IDENTITY_FIRST')`;
 assert.equal(pythonSource(program,[dir]).toString().trim(),'IDENTITY_FIRST');
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('real private tails expose only complete pinned fatal templates and noncausal known code observations',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-')));
 try{
 const program=String.raw`out=pathlib.Path(sys.argv[2]);log=out/'ffmpeg-build/ffbuild/config.log';log.parent.mkdir(parents=True);private=out/'PRIVATE-BUILD.log'
def forbidden_classifier(*args,**kwargs):raise AssertionError('unnecessary category classifier called')
m.base.classify_failure=forbidden_classifier
secret=b'SECRET-PRIVATE-ENV-CANARY';private.write_bytes(secret+b'\nC compiler test failed.\n')
cases=[(b'', 'not-observed', []),(b'authored capability test\nerror C1083: '+secret+b'\n','unknown',[]),(b'C compiler test failed.\n','compiler-test-failed',['compiler-test-failed']),(b'ERROR: libmp3lame >= 3.98.3 not found\r\n','libmp3lame-check-failed',['libmp3lame-check-failed']),(b'ERROR: opus not found using pkg-config\n\n'+p.CONFIGURE_STATIC_NOTE+b'\n','opus-pkg-config-check-failed',['opus-pkg-config-check-failed']),(b'ERROR: libmp3lame >= 3.98.3 not found\ncontinued unknown\n','unknown',['libmp3lame-check-failed']),(b'C compiler test failed.\n'+secret,'unknown',['compiler-test-failed']),(b'C compiler test failed.\nERROR: libmp3lame >= 3.98.3 not found\n','conflicting',['compiler-test-failed','libmp3lame-check-failed']),(b'prefix C compiler test failed.\nERROR: libmp3lame >= 3.98.3 not found '+secret+b'\n','unknown',[])]
values=[]
for data,terminal,templates in cases:
 log.write_bytes(data);value=p.configure_context(m,out);a,b=value['logs']
 assert a['terminal']==terminal and a['fatal_templates']==templates
 assert b['terminal']=='not-attributed' and b['fatal_templates']==['compiler-test-failed']
 assert secret not in p.serialized(value) and p.SHA(secret).encode() not in p.serialized(value)
 values.append(value)
assert values[1]['logs'][0]['probe_codes']==['C1083']
log.write_bytes(b'error c1083: private\nerror D8021:\nerror LNK2019:\nerror MSB4018:\nerror C99999:\nwarning C1189:\nerrorx C1001:\nerror C10830:\n'+b'\xe4\xb8\xaderror C1001:\n')
value=p.configure_context(m,out);assert value['logs'][0]['probe_codes']==['C1083','D8021','LNK2019','MSB4018'];values.append(value)
print(json.dumps(values))`;
 const contexts=JSON.parse(pythonSource(program,[dir]));
 for(const context of contexts){const value=configureFixture();value.details.configure_observation=context;validateFailure(value);assert.ok(!canonical(value).includes(Buffer.from('SECRET')));}
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('maximum real configure tails avoid unrelated category regexes and finish in a bounded owned Python child',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-cpu-')));
 try{
 const program=String.raw`out=pathlib.Path(sys.argv[2]);log=out/'ffmpeg-build/ffbuild/config.log';log.parent.mkdir(parents=True)
def forbidden_classifier(*args,**kwargs):raise AssertionError('unnecessary category classifier called')
m.base.classify_failure=forbidden_classifier
cap=p.CONFIGURE_LOG_LIMIT;unit=b'/sh: private: ';suffix=b'unmatched\n';data=(unit*((cap-len(suffix))//len(unit)))[:cap-len(suffix)]
data=data+b'x'*(cap-len(suffix)-len(data))+suffix
assert len(data)==cap
log.write_bytes(data);(out/'PRIVATE-BUILD.log').write_bytes(data)
value=p.configure_context(m,out);a,b=value['logs']
assert a==dict(role='configure-log',state='read',truncated=False,terminal='unknown',fatal_templates=[],probe_codes=[])
assert b==dict(role='cumulative-build-output',state='read',truncated=False,terminal='not-attributed',fatal_templates=[],probe_codes=[])
assert not p._CONFIGURE_READERS
print('CODE_ONLY_BOUNDED')`;
 // pythonSource owns this one child and enforces its existing 15s deadline.
 // The fail-on-call check independently rejects the unnecessary classifier.
 assert.equal(pythonSource(program,[dir]).toString().trim(),'CODE_ONLY_BOUNDED');
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('each real log read stays within one MiB and tail fragments never become new literal or code boundaries',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-')));
 try{
 const program=String.raw`out=pathlib.Path(sys.argv[2]);log=out/'ffmpeg-build/ffbuild/config.log';log.parent.mkdir(parents=True);private=out/'PRIVATE-BUILD.log'
cap=p.CONFIGURE_LOG_LIMIT;original=pathlib.Path.open;reads=[]
class Reader:
 def __init__(self,actual):self.actual=actual
 def fileno(self):return self.actual.fileno()
 def seek(self,*a):return self.actual.seek(*a)
 def read(self,n):reads.append(n);assert 0<n<=cap;return self.actual.read(n)
 def close(self):return self.actual.close()
def wrapped(path,*a,**kw):
 value=original(path,*a,**kw)
 return Reader(value) if a==('rb',) and path in (log,private) else value
pathlib.Path.open=wrapped
for newline in (b'\n',b'\r\n'):
 fragment=b'C compiler test failed.'+newline
 suffix=b'ordinary successful test'+newline
 data=b'X'*97+fragment+b'P'*(cap-len(fragment)-len(suffix))+suffix
 log.write_bytes(data);private.write_bytes(data)
 value=p.configure_context(m,out);a,b=value['logs'];assert a['truncated'] and b['truncated']
 assert a['terminal']=='unknown' and a['fatal_templates']==[] and b['fatal_templates']==[]
 # At the exact cap there is no partial-first-line discard.
 prefix=b'C compiler test failed.\n';log.write_bytes(prefix+b' '*(cap-len(prefix)))
 a=p.configure_context(m,out)['logs'][0];assert not a['truncated'] and a['fatal_templates']==['compiler-test-failed']
 # No newline in the retained cap: none of that fragment is classified.
 log.write_bytes(b'X'*(cap+19));a=p.configure_context(m,out)['logs'][0];assert a['truncated'] and a['terminal']=='not-observed'
assert len(reads)==12 and sum(reads)<=6*2*cap
assert not p._CONFIGURE_READERS
print('BOUNDED')`;
 assert.equal(pythonSource(program,[dir]).toString().trim(),'BOUNDED');
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('root-first private log guards reject actual linked parents before descendant stat, lstat or open',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-')));
 try{
 const program=String.raw`import os
out=pathlib.Path(sys.argv[2]);outside=out/'outside';outside.mkdir();(outside/'ffbuild').mkdir();(outside/'ffbuild/config.log').write_bytes(b'SECRET\n')
linked=out/'ffmpeg-build';linked.symlink_to(outside,target_is_directory=True)
originals={n:getattr(pathlib.Path,n) for n in ('stat','lstat','open')};calls=[]
def guard(name):
 def action(path,*a,**kw):
  if path!=linked and linked in path.parents:calls.append(name);raise AssertionError('descendant inspected')
  return originals[name](path,*a,**kw)
 return action
for name in originals:setattr(pathlib.Path,name,guard(name))
try:p.configure_context(m,out)
except ValueError:pass
else:raise AssertionError('link accepted')
assert calls==[] and len(p._CONFIGURE_READERS)==1 and p._CONFIGURE_READERS[0]['stream'] is None
p._CONFIGURE_READERS.clear()  # Independent authored hardlink refusal, not a retry of that reader.
for name,original in originals.items():setattr(pathlib.Path,name,original)
linked.unlink();linked.mkdir();(linked/'ffbuild').mkdir();leaf=linked/'ffbuild/config.log';os.link(outside/'ffbuild/config.log',leaf)
try:p.configure_context(m,out)
except ValueError:pass
else:raise AssertionError('hardlink accepted')
assert (outside/'ffbuild/config.log').read_bytes()==b'SECRET\n'
print('NO_DESCENDANT_ACCESS')`;
 assert.equal(pythonSource(program,[dir]).toString().trim(),'NO_DESCENDANT_ACCESS');
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('real readers retain original read and close faults, never retry close or produce a public pair',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-')));
 try{
 const program=String.raw`out=pathlib.Path(sys.argv[2]);log=out/'ffmpeg-build/ffbuild/config.log';log.parent.mkdir(parents=True);log.write_bytes(b'C compiler test failed.\n')
values=json.loads(sys.stdin.buffer.read());p.publication_values(m,values)
original=pathlib.Path.open
for mode in ('read','close-before','close-after','changed'):
 p._CONFIGURE_READERS.clear();error=OSError('SECRET-CLOSE-FAULT');objects=[]
 class Reader:
  def __init__(self,actual):self.actual=actual;self.closes=0
  def fileno(self):return self.actual.fileno()
  def seek(self,*a):return self.actual.seek(*a)
  def read(self,n):
   if mode=='read':raise error
   value=self.actual.read(n)
   if mode=='changed':
    with original(log,'ab') as writer:writer.write(b'changed\n')
   return value
  def close(self):
   self.closes+=1
   if mode=='close-before':raise error
   self.actual.close()
   if mode=='close-after':raise error
 def wrapped(path,*a,**kw):
  value=original(path,*a,**kw)
  if path==log and a==('rb',):value=Reader(value);objects.append(value)
  return value
 pathlib.Path.open=wrapped
 try:p.configure_context(m,out)
 except ValueError as rejected:assert 'SECRET' not in str(rejected)
 else:raise AssertionError('unsafe read accepted')
 held=p._CONFIGURE_READERS[0];reader=objects[0]
 assert held['stream'] is reader and reader.closes==1 and held['errors']
 if mode!='changed':assert held['errors'][0] is error
 assert held['close_confirmed']==(mode in ('read','changed'))
 try:p.configure_context(m,out)
 except ValueError:pass
 else:raise AssertionError('unsafe observation retried')
 assert len(objects)==1 and reader.closes==1
 try:p.publish_pair(m,out,values)
 except ValueError:pass
 else:raise AssertionError('retained uncertainty published')
 assert not (out/'output/checks/r19-mp3-published').exists()
 # Test owns the exact real file object; close it only after retention assertions.
 if not reader.actual.closed:reader.actual.close()
 pathlib.Path.open=original
print('RETAINED_PRIVATE_ONLY')`;
 const r=rig('failure');runObservation(r.options);
 assert.equal(pythonSource(program,[dir],canonical(r.options.values)).toString().trim(),'RETAINED_PRIVATE_ONLY');
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('actual failure CLI returns only the fixed refusal when a private log ancestor is unsafe',()=>{
 const dir=realpathSync(mkdtempSync(join(tmpdir(),'mp3-configure-cli-')));
 try{
 const setup=String.raw`out=pathlib.Path(sys.argv[2]);outside=out/'SECRET-OUTSIDE';outside.mkdir();(out/'ffmpeg-build').symlink_to(outside,target_is_directory=True)
raw=dict(schema='proxy-r19-mp3-draft-failure-v1',status='failed',phase='configure-ffmpeg',source_commit='1'*40,exit_code=1,profile_manifest=p.record(m.base.recipe_bytes(m.PIN)),diagnostic_codes=[],diagnostic_categories=['unclassified-command-failure'],log_truncated=False,raw_log_published=False,**p.FLAGS)
(out/'FAILED-STAGE.json').write_bytes(p.serialized(raw))`;
 pythonSource(setup,[dir]);let refused=false;
 try{execFileSync(python,['-I','-B',join(root,'scripts/mp3-codec-observation.py'),'failure',root,dir,h],{timeout:15000,maxBuffer:1024*1024,stdio:['pipe','pipe','pipe']});}
 catch(error){refused=true;assert.equal(error.status,1);assert.equal(error.stderr.length,0);assert.deepEqual(JSON.parse(error.stdout),{schema:'proxy-r19-mp3-observer-failure-v1',status:'failed',reason:'unavailable'});}
 assert.equal(refused,true);assert.ok(!existsSync(join(dir,'output/checks/r19-mp3-published')));assert.deepEqual(readdirSync(join(dir,'SECRET-OUTSIDE')),[]);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('import-alias BSD approval and final-copy v3 reject every unknown or missing scope',()=>{
 const mutations=[v=>delete v.project_license.import_alias_approval,v=>v.project_license.schema='proxy-r19-mp3-recipe-additional-license-v2',v=>v.project_license.import_alias_approval.future=true,v=>v.project_license.import_alias_approval.approval_proposal.sha256=zero,v=>v.project_license.import_alias_approval.prior_notice_prefix.bytes++,v=>v.project_license.import_alias_approval.approved_baselines['scripts/future.py']={bytes:1,sha256:zero},v=>v.final_four_copies.schema='proxy-r19-mp3-final-bsd-copies-v2',v=>delete v.final_four_copies.import_alias_approved_baselines,v=>v.final_four_copies.import_alias_approved_baselines['scripts/replay-mp3-codec.py'].sha256=zero,v=>v.final_four_copies.import_alias_approved_baselines['scripts/future.py']={bytes:1,sha256:zero},v=>v.candidate_files['mp3lame.lib']={bytes:1,sha256:zero}];
 for(const mutate of mutations){const value=fixture();mutate(value);assert.throws(()=>validateNative(value));}
});
