import assert from 'node:assert/strict';
import test from 'node:test';
import {assertNativeDataDecoder} from '../scripts/android-native-decoder-proof.mjs';

test('native acceptance rejects substituted software and absent exact CAPI contracts', () => {
 const manifest = {libraries:{'arm64-v8a':{sha256:'a'.repeat(64)}}};
 const value = {schema:'toolkit-x64-capi-v1',version:'5.0.7',
  source_sha256:'796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede',
  abi:'arm64-v8a',library_sha256:'a'.repeat(64),manifest_sha256:'b'.repeat(64),
  pointer_bits:64,api_major:5,api_minor:0,apk_entry_verified:true,licenses_verified:true,
  python_owned_provider:true,authored_operand_probe:true,large_integer_exact:true,
  register_contract_exact:true,groups_access_exact:true,system_fallback:false,original_client_execution:false,
  instructions:3,rip_displacement:32,imul_immediate:7,authored_contract_cases:15,
  authored_contract_sha256:'574bf513b176dd742e0dd73681716a85822bd926476dfd389e94c6028f66a7d1'};
 assert.doesNotThrow(() => assertNativeDataDecoder(value,manifest,'b'.repeat(64)));
 for (const key of Object.keys(value)) {
  const changed={...value};delete changed[key];
  assert.throws(() => assertNativeDataDecoder(changed,manifest,'b'.repeat(64)), key);
 }
 assert.throws(() => assertNativeDataDecoder({...value,library_sha256:'c'.repeat(64)},manifest,'b'.repeat(64)));
 assert.throws(() => assertNativeDataDecoder(value,manifest,'c'.repeat(64)));
});
