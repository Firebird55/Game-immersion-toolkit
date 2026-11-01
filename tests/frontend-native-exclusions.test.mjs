import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync} from 'node:fs';
import {join, dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {browserNativeGuard, sealBrowserNativeEvidence, verifyBrowserNativeEvidence, readBrowserNativeExclusions, POLICY, GUARD, EVIDENCE} from '../scripts/frontend-native-exclusions.mjs';
import {dependencyNoticeAudit, requireCompleteNotices} from '../scripts/dependency-notices.mjs';

function fixture(t) {
  const root=mkdtempSync(join(tmpdir(),'browser-native-evidence-'));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  const put=(name,value)=>{const file=join(root,name);mkdirSync(dirname(file),{recursive:true});writeFileSync(file,typeof value==='object'?JSON.stringify(value):value);};
  const item={package:'node_modules/@img/sharp-libvips-linux-x64',version:'1.3.4',integrity:'sha512-authored'};
  put('package-lock.json',{packages:{[item.package]:{version:item.version,integrity:item.integrity}}});
  put(item.package+'/package.json',{name:'@img/sharp-libvips-linux-x64',version:item.version,license:'LGPL-3.0-or-later'});
  put(POLICY,{schema:'toolkit-native-build-inputs-v1',packages:[item]});put(GUARD,'// authored guard source identity');
  const proofs={},payloads=new Map();
  for (const [kind,name] of [['desktop','assets/main.js'],['canonical','_next/static/main.js'],['mobile','mobile-capture/companion.js']]) {
    const plugin=browserNativeGuard({root,kind,onEvidence:value=>{proofs[kind]=value;}});
    plugin.buildStart();plugin.load(join(root,'src/index.js').replaceAll('\\','/'));
    const code='// authored '+kind+' browser fixture';
    plugin.generateBundle.handler({}, {'main.js':{type:'chunk',code,modules:{[join(root,'src/index.js')]:{}}}});
    payloads.set(name,Buffer.from(code));
  }
  return {root,put,item,proofs,payloads};
}

test('exact native policy cannot excuse missing notices without all shipped build evidence',t=>{
  const {root,put,proofs,payloads}=fixture(t);
  const pending=dependencyNoticeAudit({root});
  assert.equal(pending.omissions[0].pending_native_build_evidence,true);
  assert.throws(()=>requireCompleteNotices(pending),/incomplete/);
  requireCompleteNotices(pending,{deferNativeBuildEvidence:true});
  const evidence=verifyBrowserNativeEvidence({root,proofs,payloads});
  for(const [name,bytes] of payloads)put('frontend/'+name,bytes.toString());
  put('frontend/'+EVIDENCE,evidence);
  const audit=dependencyNoticeAudit({root,frontendRoot:join(root,'frontend')});
  assert.equal(audit.omissions.length,0);assert.equal(audit.excluded.length,1);
  assert.deepEqual(audit.excluded[0].coverage,{canonical:1,desktop:1,mobile:1});
  put('frontend/assets/main.js','altered output');
  assert.throws(()=>readBrowserNativeExclusions(root,join(root,'frontend')),/no matching/);
});

test('native module inclusion is rejected at load and emitted chunk inspection',t=>{
  const {root,item}=fixture(t),plugin=browserNativeGuard({root,kind:'desktop'});
  const id=join(root,item.package,'lib/index.js');
  assert.throws(()=>plugin.load(id),/module graph/);
  assert.throws(()=>plugin.moduleParsed({id}),/module graph/);
  assert.throws(()=>plugin.generateBundle.handler({}, {'main.js':{type:'chunk',code:'',modules:{[id]:{}}}}),/emitted browser chunk/);
});

test('renamed native bytes cannot enter generated or copied static assets',t=>{
  const {root,proofs,payloads}=fixture(t),plugin=browserNativeGuard({root,kind:'desktop'});
  const native=Buffer.from([0x7f,0x45,0x4c,0x46,0,0]);
  assert.throws(()=>plugin.generateBundle.handler({}, {'image.png':{type:'asset',source:native}}),/Native binary/);
  payloads.set('mobile-capture/image.png',native);
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs,payloads}),/Native binary/);
});

test('missing path, changed policy, and excluded graph entries invalidate proof',t=>{
  const {root,put,proofs,payloads,item}=fixture(t);
  const incomplete={...proofs};delete incomplete.canonical;
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs:incomplete,payloads}),/All browser build paths/);
  const previous=proofs.mobile.modules;
  proofs.mobile.modules=[item.package+'/lib/index.js'];
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs,payloads}),/Excluded native input/);
  proofs.mobile.modules=previous;
  // Reordering JSON keys in a serialized cache does not change identity.
  proofs.mobile.packages=[{integrity:item.integrity,version:item.version,package:item.package}];
  assert.ok(verifyBrowserNativeEvidence({root,proofs,payloads}));
  put(GUARD,'// changed guard source identity');
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs,payloads}),/identity changed/);
});

test('post-build CSS and JSON manifests do not excuse new executable chunks',t=>{
  const {root,proofs,payloads}=fixture(t);
  const manifest='_next/static/build/_buildManifest.js';
  const bytes=Buffer.from('self.__BUILD_MANIFEST = {"__rewrites":{},"sortedPages":[]};self.__BUILD_MANIFEST_CB && self.__BUILD_MANIFEST_CB()');
  const additions=new Map([[manifest,bytes],['_next/static/css/main.css',Buffer.from('body{color:red}')]]);
  proofs.canonical=sealBrowserNativeEvidence(proofs.canonical,additions);
  for(const [name,value]of additions)payloads.set(name,value);
  assert.ok(verifyBrowserNativeEvidence({root,proofs,payloads}));
  assert.throws(()=>sealBrowserNativeEvidence(proofs.canonical,new Map([['extra.js',Buffer.from('arbitraryCode()')]])),/Unobserved executable/);
  payloads.set(manifest,Buffer.from(bytes.toString()+';arbitraryCode()'));
  proofs.canonical.postbuild_outputs[manifest].sha256=undefined;
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs,payloads}),/no matching/);
});

test('a null post-build format cannot attest an unobserved executable chunk',t=>{
  const {root,proofs,payloads}=fixture(t),name='_next/static/extra.js',bytes=Buffer.from('arbitraryCode()');
  payloads.set(name,bytes);
  proofs.canonical.postbuild_outputs={[name]:{format:null,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')}};
  assert.throws(()=>verifyBrowserNativeEvidence({root,proofs,payloads}),/no matching/);
});
