import test from 'node:test';import assert from 'node:assert/strict';import {gzipSync} from 'node:zlib';
import {scanArtifact,scanContent,privatePath} from '../scripts/publication-scan.mjs';
import {readFileSync} from 'node:fs';
import {mkdtempSync,mkdirSync,copyFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
function tgz(name,text){const h=Buffer.alloc(512);h.write(name);h.write('0000644',100);h.write('0000000',108);h.write('0000000',116);h.write(Buffer.byteLength(text).toString(8).padStart(11,'0'),124);h[156]=48;const b=Buffer.from(text);return gzipSync(Buffer.concat([h,b,Buffer.alloc((512-b.length%512)%512),Buffer.alloc(1024)]));}
test('archive scan inspects compressed payloads and rejects private paths',()=>{
 assert.throws(()=>scanArtifact(tgz('package/source.js','ghp_'+ 'a'.repeat(40)),'package.tgz'),/credential/);
 assert.throws(()=>scanArtifact(tgz('package/data/cache.db','local'),'package.tgz'),/Private/);
 assert.throws(()=>scanArtifact(tgz('../outside','text'),'package.tgz'),/unsafe/);
 assert.equal(scanArtifact(tgz('package/LICENSE','Project license'),'package.tgz').length,1);
});
test('profile paths and credentials are rejected without echoing their values',()=>{
 assert.throws(()=>scanContent(Buffer.from('C:/'+['Users','example','private'].join('/')),'fixture'),/profile path: fixture/);
 assert(privatePath('.toolkit-mobile-work/fixture/cache/marker.json'));assert(privatePath('.toolkit-work/fixture.json'));assert(privatePath('data/new-game/index.db'));assert(!privatePath('backend/data-model.py'));
});

test('encoded upstream WASM is trusted only by exact bytes and its bundled location',()=>{
 const bytes=readFileSync('node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js'),name='package/dist/client/mobile-capture/ocr/core/tesseract-core-lstm.wasm.js';
 assert.doesNotThrow(()=>scanContent(bytes,name));
 assert.throws(()=>scanContent(bytes,'arbitrary.js'),/credential/);
 assert.throws(()=>scanContent(Buffer.concat([bytes,Buffer.from('\n// changed')]),name),/credential/);
 assert.throws(()=>scanContent(Buffer.concat([bytes,Buffer.from('ghp_'+'a'.repeat(40))]),name),/credential/);
});
test('game archives and voice files are rejected outside the normal cache directories',()=>{
 for(const file of ['assets/game.PAK','assets/re_chunk.pak.patch_001','public/voice.wem','assets/voice.pck','assets/game.exe','assets/app.asar','assets/cnpc.w3speech','Data/lookup.json',
  'public/game.locres','public/patch.hpw','public/game.wmv','assets/level.assets','assets/story.unity3d','assets/voice.bundle','assets/cinematic.usm','tools/reader.pdb',
  'assets/captions.srt','assets/captions.srt_zh-CN','assets/unreal.usmap','assets/table.uasset','assets/table.uexp','assets/table.ubulk',
  'public/zzz.catalog.zip','public/zzz.voices-123456789abcdef0.zip']){
  assert(privatePath(file),file);
  assert.throws(()=>scanArtifact(tgz('package/'+file,'synthetic game asset'),'package.tgz'),/Private/);
 }
 assert(!privatePath('assets/fireredvad/fireredvad_vad.onnx'));
});

// Exercise the real publication CLI: the existing compressed-payload tests do
// not cover its tracked-ZIP ban or the exact public-source exception.
test('tracked source delivery accepts only the reviewed snapshot and rejects altered or unrelated ZIPs',()=>{
 const root=mkdtempSync(join(tmpdir(),'xiph-source-publication-'));
 try{
  const name='third_party/codecs/xiph-flac-1.5.0/codec-sources.zip';
  const bytes=readFileSync(name),target=join(root,name);
  mkdirSync(join(root,'scripts'),{recursive:true});mkdirSync(join(root,'hooks'));
  mkdirSync(join(root,'third_party/codecs/xiph-flac-1.5.0'),{recursive:true});
  for(const file of ['secret-check.mjs','publication-scan.mjs','mobile-ocr-integrity.json'])copyFileSync('scripts/'+file,join(root,'scripts',file));
  const git=(...args)=>execFileSync('git',['-c','user.name=fixture','-c','user.email=noreply@github.com','-c','commit.gpgsign=false','-c','core.hooksPath='+join(root,'hooks'),...args],{cwd:root,stdio:'pipe',env:{...process.env,GIT_AUTHOR_EMAIL:'noreply@github.com',GIT_COMMITTER_EMAIL:'noreply@github.com'}});
  git('init');writeFileSync(target,bytes);git('add',name);git('commit','-m','Public source fixture');
  const audit=()=>execFileSync(process.execPath,['scripts/secret-check.mjs','--public'],{cwd:root,stdio:'pipe'});
  assert.match(audit().toString(),/Publication scan passed/);
  const reject=()=>assert.throws(audit,error=>error.stderr.toString().includes('Private/generated tracked file:'));
  const changed=Buffer.from(bytes);changed[changed.length-1]^=1;writeFileSync(target,changed);reject();
  writeFileSync(target,Buffer.concat([bytes,Buffer.from('unreviewed trailer')]));reject();
  writeFileSync(target,bytes.subarray(0,bytes.length-1));reject();
  writeFileSync(target,bytes);writeFileSync(join(root,'unknown.zip'),bytes);git('add','unknown.zip');reject();
 }finally{rmSync(root,{recursive:true,force:true});}
});
