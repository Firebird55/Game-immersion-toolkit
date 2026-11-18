import test from 'node:test';
import assert from 'node:assert/strict';
import {hostPlatform, parseNativeCapabilities, canCaptureDeviceFrames} from '../lib/native-host-policy.mjs';

const report = () => ({platform:'android',library_import:true,protected_accounts:false,capture_source:'authored-observations',message:'Prepared library prototype'});

test('history import is absent for older hosts and cannot bypass credential recovery',()=>{
  assert.equal(parseNativeCapabilities(report()).history_migration,false);
  assert.equal(parseNativeCapabilities({...report(),history_migration:true}).history_migration,true);
  assert.throws(()=>parseNativeCapabilities({...report(),history_migration:'true'}),/complete device capability/);
  assert.throws(()=>parseNativeCapabilities({...report(),history_migration:true,protected_accounts:true,
    account_protocol:'scoped-accounts-v1',library_import:false,capture_source:'unavailable',
    account_recovery:{state:'credentials_unreadable',data_preserved:true,action:'reenter_verified_account',message:'Authored recovery'}}),/complete device capability/);
});

test('native controls require the exact owned Android marker and never replace an ordinary desktop reader',()=>{
  assert.equal(hostPlatform(undefined),'desktop');
  for (const marker of ['android-app','Android','ios',''])
    assert.equal(hostPlatform({querySelector:()=>({getAttribute:()=>marker})}),'desktop');
  assert.equal(hostPlatform({querySelector:name=>name==='meta[name="toolkit-host-platform"]'?{getAttribute:()=> 'android'}:null}),'android');
});

test('authored observations do not advertise actual device capture or protected accounts',()=>{
  const value=parseNativeCapabilities(report());
  assert.equal(value.library_import,true);
  assert.equal(value.protected_accounts,false);
  assert.equal(canCaptureDeviceFrames(value),false);
  for (const source of ['remote-stream','media-projection'])
    assert.equal(canCaptureDeviceFrames(parseNativeCapabilities({...report(),capture_source:source})),true);
});

test('incomplete, stringified or unknown capabilities fail before exposing native actions',()=>{
  for (const patch of [{platform:'desktop'},{library_import:'true'},{protected_accounts:'false'},
    {capture_source:'web-page'},{message:null},{message:'x'.repeat(1001)}])
    assert.throws(()=>parseNativeCapabilities({...report(),...patch}),/complete device capability/);
  assert.throws(()=>parseNativeCapabilities(null),/complete device capability/);
  assert.equal(canCaptureDeviceFrames(null),false);
});

test('the receiver uses an explicitly supported protocol and a bounded native frame limit',()=>{
  const value=parseNativeCapabilities({...report(),capture_source:'remote-stream',
    receiver_protocol:'leased-frames-v1',max_frame_bytes:10*1024**2});
  assert.equal(value.receiver_protocol,'leased-frames-v1');
  assert.equal(value.max_frame_bytes,10*1024**2);
  assert.equal(parseNativeCapabilities({...report(),receiver_protocol:'unknown-version'}).receiver_protocol,undefined);
  for(const maximum of [0,-1,16777217,Infinity,'10485760'])
    assert.throws(()=>parseNativeCapabilities({...report(),max_frame_bytes:maximum}),/complete device capability/);
});

test('protected accounts require the reviewed generation-bound protocol',()=>{
 for(const account_protocol of [undefined,null,'accounts-v1','scoped-accounts-v2'])
  assert.throws(()=>parseNativeCapabilities({...report(),protected_accounts:true,account_protocol}),/complete device capability/);
 const value=parseNativeCapabilities({...report(),protected_accounts:true,account_protocol:'scoped-accounts-v1'});
 assert.equal(value.protected_accounts,true);
 assert.equal(value.account_protocol,'scoped-accounts-v1');
});

test('credential recovery retains only a complete locked and preserved-data state',()=>{
 const recovery={state:'credentials_unreadable',data_preserved:true,action:'reenter_verified_account',message:'Re-enter the verified account to restore local data.'};
 const locked={...report(),protected_accounts:true,account_protocol:'scoped-accounts-v1',library_import:false,capture_source:'unavailable',account_recovery:recovery};
 assert.deepEqual(parseNativeCapabilities(locked).account_recovery,recovery);
 for(const patch of [{library_import:true},{capture_source:'remote-stream'},{protected_accounts:false},
  {account_recovery:{...recovery,data_preserved:false}},{account_recovery:{...recovery,action:'reset'}}])
  assert.throws(()=>parseNativeCapabilities({...locked,...patch}),/complete device capability/);
});

test('available publisher games belong to the native host and are unique supported IDs',()=>{
  assert.deepEqual(parseNativeCapabilities({...report(),publisher_games:['zzz']}).publisher_games,['zzz']);
  assert.equal(parseNativeCapabilities(report()).publisher_games,undefined);
  for(const value of [['invalid'],['zzz','zzz'],'zzz'])
    assert.throws(()=>parseNativeCapabilities({...report(),publisher_games:value}),/complete device capability/);
});
