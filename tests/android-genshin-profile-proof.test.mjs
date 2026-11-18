import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {assertNativeGenshinProfile} from '../scripts/android-genshin-profile-proof.mjs';

function fixture() {
  const decoder = {schema:'toolkit-x64-capi-v1',version:'5.0.7',abi:'x86_64',pointer_bits:64,api_major:5,api_minor:0,
    source_sha256:'796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede',library_sha256:'a'.repeat(64),manifest_sha256:'b'.repeat(64),
    apk_entry_verified:true,licenses_verified:true,python_owned_provider:true,authored_operand_probe:true,
    large_integer_exact:true,register_contract_exact:true,groups_access_exact:true,system_fallback:false,original_client_execution:false,
    instructions:3,rip_displacement:32,imul_immediate:7,authored_contract_cases:15,
    authored_contract_sha256:'574bf513b176dd742e0dd73681716a85822bd926476dfd389e94c6028f66a7d1'};
  const keys=['schema','version','abi','pointer_bits','api_major','api_minor','source_sha256','library_sha256','manifest_sha256',
    'authored_contract_sha256','apk_entry_verified','licenses_verified','system_fallback','original_client_execution',
    'authored_contract_cases','large_integer_exact','register_contract_exact','groups_access_exact'];
  const runtime={schema:'genshin-android-channel-profile-runtime-v1',decoder:Object.fromEntries(keys.map(key=>[key,decoder[key]])),
    portable_blb_sha256:'c'.repeat(64),implementation_sha256:'d'.repeat(64)};
  const canonical = value => JSON.stringify(value,function(_key,child){return child && !Array.isArray(child) && typeof child==='object'
    ? Object.fromEntries(Object.keys(child).sort().map(key=>[key,child[key]])):child;});
  const expected={body_sha256:'e'.repeat(64),payload_sha256:'f'.repeat(64),parameters_sha256:'0'.repeat(64),method_sha256s:['1'.repeat(64),'2'.repeat(64),'3'.repeat(64)]};
  const component={schema:'toolkit-android-genshin-profile-component-v1',sha256:'4'.repeat(64),expected,
    original_game_bytes:false,profile_only:true,factory_activated:false,software_notice:{expression:'MIT',
      sha256:'e6a2268c715fce13cdf0979786c51d152b3e67d32a99a67dbbeb592c64d37e29'}};
  const audit={genshin_profile_component:component,native_data_decoder:{libraries:{x86_64:{sha256:decoder.library_sha256}}}};
  const provenance={genshin_profile_component:structuredClone(component),native_decoder_manifest_sha256:decoder.manifest_sha256};
  const value={schema:'toolkit-authored-genshin-profile-proof-v1',passed:true,installed_host_decoder:true,
    complete_named_object_map:true,strict_payload_eof:true,prior_state_retained_on_failure:true,profile_only:true,
    full_catalog_validated:false,selected_shards_validated:false,response_signature_verified:false,complete_dispatch_bootstrap:false,
    later_override_excluded:false,community_numeric_data_used:false,original_game_bytes:false,factory_activated:false,
    network_requests:0,codec_candidates:2,accepted_candidates:1,malformed_rejections:2,fixture_sha256:component.sha256,
    body_sha256:expected.body_sha256,payload_sha256:expected.payload_sha256,parameters_sha256:expected.parameters_sha256,
    method_sha256s:expected.method_sha256s,runtime_provenance:runtime,runtime_identity:createHash('sha256').update(canonical(runtime)).digest('hex')};
  return {value,audit,provenance,decoder};
}
test('binds the complete profile to the existing 15 actual CAPI contracts and delivered fixture',()=>{
  const x=fixture();assertNativeGenshinProfile(x.value,x.audit,x.provenance,x.decoder);
});
for(const [name,mutate] of Object.entries({
  missing:x=>{x.value=undefined;}, missingHost:x=>{x.value.installed_host_decoder=false;},
  wrongFixture:x=>{x.provenance.genshin_profile_component.sha256='9'.repeat(64);},
  foreignDecoder:x=>{x.value.runtime_provenance.decoder.library_sha256='9'.repeat(64);},
  staleContract:x=>{x.decoder.authored_contract_sha256='9'.repeat(64);},
  wrongIdentity:x=>{x.value.runtime_identity='9'.repeat(64);},
  body:x=>{x.value.body_sha256='9'.repeat(64);}, methods:x=>{x.value.method_sha256s=[];},
  candidates:x=>{x.value.codec_candidates=1;}, ambiguous:x=>{x.value.accepted_candidates=2;},
  eof:x=>{x.value.strict_payload_eof=false;}, map:x=>{x.value.complete_named_object_map=false;},
  malformed:x=>{x.value.malformed_rejections=0;}, sentinel:x=>{x.value.prior_state_retained_on_failure=false;},
  sourceReady:x=>{x.value.full_catalog_validated=true;}, activation:x=>{x.value.factory_activated=true;},
  signature:x=>{x.value.response_signature_verified=true;}, gameBytes:x=>{x.value.original_game_bytes=true;},
  fallback:x=>{x.value.runtime_provenance.decoder.system_fallback=true;}, network:x=>{x.value.network_requests=1;},
  unboundRuntimeField:x=>{x.value.runtime_provenance.decoder.unknown=true;}, notice:x=>{x.audit.genshin_profile_component.software_notice.sha256='9'.repeat(64);},
}))test('rejects '+name,()=>{
  const x=fixture();mutate(x);assert.throws(()=>assertNativeGenshinProfile(x.value,x.audit,x.provenance,x.decoder));
});
