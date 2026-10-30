import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,mkdirSync,copyFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';

// The existing compressed-payload tests do not exercise the real tracked-ZIP
// ban, exact source exception or a bad historical version hidden by a revert.
// Builtins only, so the bounded Windows source job needs no npm dependencies.
test('publication accepts only the reviewed source snapshot, including every reachable historical version',()=>{
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
  writeFileSync(target,bytes);
  for(const unknown of ['unknown.zip','unknown.ZIP','unknown.tgz']){
   writeFileSync(join(root,unknown),bytes);git('add',unknown);reject();
   git('rm','--cached',unknown);rmSync(join(root,unknown));
  }
  writeFileSync(target,changed);git('add',name);git('commit','-m','Altered snapshot fixture');
  writeFileSync(target,bytes);git('add',name);git('commit','-m','Restored current snapshot fixture');
  assert.throws(audit,error=>error.stderr.toString().includes('Unreviewed source archive in reachable history:'));
 }finally{rmSync(root,{recursive:true,force:true});}
});
