import test from 'node:test';
import assert from 'node:assert/strict';
import {assertNativeWuwaBootstrap} from '../scripts/android-wuwa-bootstrap-proof.mjs';

function authored() {
  const cryptoRuntime = {abi:'arm64-v8a',library_sha256:'c'.repeat(64)};
  const fixture = {sha256:'a'.repeat(64),apk_sha256:'b'.repeat(64),module_sha256:'d'.repeat(64),apk_bytes:2309,original_game_bytes:false};
  const native_files = {'assets/chaquopy/bootstrap-native/arm64-v8a/mmap.cpython-312.so':{sha256:'e'.repeat(64),minimum_load_alignment:16384}};
  const cases = ['text','text-audio'].map(value => ({case:value,stage:'manifest-format',downloaded_bytes:2309,
    module_sha256:fixture.module_sha256,full_apk_verified:true,mmap_data_parser:true,offline_restart:true,retained_data:true,snapshot_activated:false}));
  cases.push(...['corrupt','cancel'].map(value => ({case:value,rejected:true,retained_data:true,charged_bytes:173})));
  return {value:{schema:'toolkit-android-authored-wuwa-bootstrap-v1',passed:true,actual_network:false,original_game_bytes:false,
    snapshot_ready:false,fixture_sha256:fixture.sha256,apk_sha256:fixture.apk_sha256,crypto_proof:structuredClone(cryptoRuntime),
    mmap_runtime:{android_extension:true,sha256:'e'.repeat(64),bytes:25312},cases},
    audit:{wuwa_authored_fixture:structuredClone(fixture),native_files},provenance:{wuwa_authored_fixture:structuredClone(fixture)},cryptoRuntime};
}
test('binds actual packaged crypto, mmap and four real authored stage outcomes', () => {
  const d=authored();assertNativeWuwaBootstrap(d.value,d.audit,d.provenance,d.cryptoRuntime);
});
for (const [name,mutate] of Object.entries({
  fixture:d=>{d.value.fixture_sha256='f'.repeat(64);},missingMode:d=>{d.value.cases.splice(1,1);},
  ready:d=>{d.value.snapshot_ready=true;},unverified:d=>{d.value.cases[0].full_apk_verified=false;},
  corruptAccepted:d=>{d.value.cases[2].rejected=false;},unaccounted:d=>{d.value.cases[3].charged_bytes=0;},
  noRestart:d=>{d.value.cases[1].offline_restart=false;},realNetwork:d=>{d.value.actual_network=true;},
  desktopMmap:d=>{d.value.mmap_runtime.android_extension=false;},foreignMmap:d=>{d.value.mmap_runtime.sha256='f'.repeat(64);},
  foreignCrypto:d=>{d.value.crypto_proof.library_sha256='f'.repeat(64);},foreignReceipt:d=>{d.provenance.wuwa_authored_fixture.apk_bytes=2000;},
})) test('rejects '+name, () => {
  const d=authored();mutate(d);assert.throws(()=>assertNativeWuwaBootstrap(d.value,d.audit,d.provenance,d.cryptoRuntime));
});
