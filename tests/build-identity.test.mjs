import assert from 'node:assert/strict';
import test from 'node:test';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {sourceCommit} from '../scripts/build-identity.mjs';

test('build identity follows checked-out source when CI event points elsewhere', () => {
  const cwd=mkdtempSync(join(tmpdir(),'toolkit-build-identity-'));
  const env={...process.env,GIT_AUTHOR_NAME:'Fixture',GIT_COMMITTER_NAME:'Fixture',
    GIT_AUTHOR_EMAIL:'fixture@users.noreply.github.com',GIT_COMMITTER_EMAIL:'fixture@users.noreply.github.com'};
  const git=(...args)=>execFileSync('git',args,{cwd,env,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
  const previous=process.env.GITHUB_SHA;
  try {
    git('init');writeFileSync(join(cwd,'fixture'),'first');git('add','fixture');git('-c','commit.gpgsign=false','commit','-m','fixture');
    const first=git('rev-parse','HEAD');
    writeFileSync(join(cwd,'fixture'),'second');git('-c','commit.gpgsign=false','commit','-am','second fixture');
    process.env.GITHUB_SHA=git('rev-parse','HEAD');git('checkout','--detach',first);
    assert.equal(sourceCommit(cwd),first);assert.notEqual(sourceCommit(cwd),process.env.GITHUB_SHA);
  } finally {
    if(previous===undefined)delete process.env.GITHUB_SHA;else process.env.GITHUB_SHA=previous;
    rmSync(cwd,{recursive:true,force:true});
  }
});
