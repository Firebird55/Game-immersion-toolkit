import test from 'node:test';
import assert from 'node:assert/strict';
import {hostPlatform, parseNativeCapabilities, canCaptureDeviceFrames} from '../lib/native-host-policy.mjs';

const report = () => ({platform:'android',library_import:true,protected_accounts:false,capture_source:'authored-observations',message:'Prepared library prototype'});

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
