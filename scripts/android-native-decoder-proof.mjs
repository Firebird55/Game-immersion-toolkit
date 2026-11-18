// Actual target report: no proprietary code, paths or instruction bodies.
import assert from 'node:assert/strict';

export function assertNativeDataDecoder(value, manifest, manifestSha256) {
 assert.equal(value?.schema, 'toolkit-x64-capi-v1');
 assert.equal(value.version, '5.0.7');
 assert.equal(value.source_sha256, '796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede');
 assert.ok(['arm64-v8a', 'x86_64'].includes(value.abi));
 assert.equal(value.library_sha256, manifest.libraries[value.abi].sha256);
 assert.equal(value.manifest_sha256, manifestSha256);
 assert.equal(value.pointer_bits, 64);assert.equal(value.api_major, 5);assert.equal(value.api_minor, 0);
 for (const name of ['apk_entry_verified', 'licenses_verified', 'python_owned_provider', 'authored_operand_probe',
   'large_integer_exact', 'register_contract_exact', 'groups_access_exact']) assert.equal(value[name], true);
 assert.equal(value.system_fallback, false);assert.equal(value.original_client_execution, false);
 assert.equal(value.instructions, 3);assert.equal(value.rip_displacement, 32);assert.equal(value.imul_immediate, 7);
 assert.equal(value.authored_contract_cases, 15);
 assert.equal(value.authored_contract_sha256, '574bf513b176dd742e0dd73681716a85822bd926476dfd389e94c6028f66a7d1');
}
