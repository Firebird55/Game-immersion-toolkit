import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {assertNativeDataDecoder} from './android-native-decoder-proof.mjs';

const decoderFields = ['schema','version','abi','pointer_bits','api_major','api_minor',
  'source_sha256','library_sha256','manifest_sha256','authored_contract_sha256',
  'apk_entry_verified','licenses_verified','system_fallback','original_client_execution',
  'authored_contract_cases','large_integer_exact','register_contract_exact','groups_access_exact'];
const canonical = value => JSON.stringify(value, function(_key, child) {
  return child && !Array.isArray(child) && typeof child === 'object'
    ? Object.fromEntries(Object.keys(child).sort().map(key => [key,child[key]])) : child;
});

/** The real started host's decoder must perform the complete authored profile. */
export function assertNativeGenshinProfile(value, audit, provenance, decoder) {
  const component = audit?.genshin_profile_component;
  assertNativeDataDecoder(decoder, audit?.native_data_decoder, provenance?.native_decoder_manifest_sha256);
  assert.equal(component?.schema, 'toolkit-android-genshin-profile-component-v1');
  assert.deepEqual(component, provenance.genshin_profile_component);
  assert.equal(component.original_game_bytes, false);assert.equal(component.profile_only, true);
  assert.equal(component.factory_activated, false);assert.equal(component.software_notice.expression, 'MIT');
  assert.equal(component.software_notice.sha256, 'e6a2268c715fce13cdf0979786c51d152b3e67d32a99a67dbbeb592c64d37e29');
  assert.equal(value?.schema, 'toolkit-authored-genshin-profile-proof-v1');
  for (const name of ['passed','installed_host_decoder','complete_named_object_map','strict_payload_eof',
    'prior_state_retained_on_failure','profile_only']) assert.equal(value[name], true, name);
  for (const name of ['full_catalog_validated','selected_shards_validated','response_signature_verified',
    'complete_dispatch_bootstrap','later_override_excluded','community_numeric_data_used','original_game_bytes',
    'factory_activated']) assert.equal(value[name], false, name);
  assert.equal(value.network_requests, 0);assert.equal(value.codec_candidates, 2);
  assert.equal(value.accepted_candidates, 1);assert.equal(value.malformed_rejections, 2);
  assert.equal(value.fixture_sha256, component.sha256);assert.match(component.sha256, /^[a-f0-9]{64}$/);
  const expected = component.expected;
  for (const name of ['body_sha256','payload_sha256','parameters_sha256']) {
    assert.match(expected[name], /^[a-f0-9]{64}$/);assert.equal(value[name], expected[name]);
  }
  assert.deepEqual(value.method_sha256s, expected.method_sha256s);
  assert.equal(value.method_sha256s.length, 3);
  const runtime = value.runtime_provenance;
  assert.equal(runtime?.schema, 'genshin-android-channel-profile-runtime-v1');
  assert.deepEqual(Object.keys(runtime).sort(), ['schema','decoder','portable_blb_sha256','implementation_sha256'].sort());
  assert.deepEqual(Object.keys(runtime.decoder).sort(), [...decoderFields].sort());
  for (const name of decoderFields) assert.equal(runtime.decoder[name], decoder[name], name);
  for (const name of ['portable_blb_sha256','implementation_sha256']) assert.match(runtime[name], /^[a-f0-9]{64}$/);
  assert.equal(value.runtime_identity, createHash('sha256').update(canonical(runtime)).digest('hex'));
}
