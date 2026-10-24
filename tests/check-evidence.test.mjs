import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, renameSync} from 'node:fs';
import {tmpdir} from 'node:os';
import fs from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';
import {join} from 'node:path';
import {captureSourceSnapshot, commandIds, readCurrentEvidence, runFixedCheckWithEvidence, startCheckRun} from '../scripts/check-evidence.mjs';
import {changedFiles, commandPlan, runChangedChecks, selectChecks} from '../scripts/check-changed.mjs';

function fixture(t) {
  t.mock.method(console, 'log', () => {});
  const cwd = mkdtempSync(join(tmpdir(), 'check-evidence-'));
  t.after(() => rmSync(cwd, {recursive: true, force: true}));
  const git = (...args) => execFileSync('git', args, {cwd, encoding: 'utf8', stdio: ['ignore','pipe','pipe']}).trim();
  git('init');
  git('config','user.name','Check Fixture');
  git('config','user.email','check-fixture@users.noreply.github.com');
  git('config','commit.gpgsign','false');
  writeFileSync(join(cwd, '.gitignore'), '/output/\n');
  writeFileSync(join(cwd, 'README.md'), 'Initial source\n');
  git('add','.'); git('commit','-m','Fixture baseline');
  const base = git('rev-parse','HEAD');
  return {cwd, base, git, write: (name, body) => writeFileSync(join(cwd, name), body)};
}
const latest = cwd => {
  const pointer = JSON.parse(readFileSync(join(cwd, 'output/checks/latest.json'), 'utf8'));
  return JSON.parse(readFileSync(join(cwd, 'output/checks/runs', `${pointer.id}.json`), 'utf8'));
};
const silentErrors = t => t.mock.method(console, 'error', () => {});
const noOp = () => {};

test('successful evidence identifies the exact source and persists unique atomic records', t => {
  const {cwd, base, write} = fixture(t);
  write('README.md', 'Document update\n');
  const first = runChangedChecks({cwd, base, runCommand: noOp, environment: {}});
  assert.equal(first.exitCode, 0); assert.equal(first.record.status, 'passed');
  assert.equal(first.record.sourceBefore.head, base);
  assert.equal(first.record.sourceBefore.base.sha, base);
  assert.deepEqual(first.record.sourceBefore, first.record.sourceAfter);
  assert.deepEqual(first.record.commands.map(({id, status}) => [id, status]), [['docs:check','passed'],['audit:public','passed']]);
  assert.equal(readCurrentEvidence({cwd, base}).id, first.record.id);
  const second = runChangedChecks({cwd, base, runCommand: noOp, environment: {}});
  assert.notEqual(first.record.id, second.record.id);
  assert.deepEqual(readdirSync(join(cwd, 'output/checks/runs')).sort(), [`${first.record.id}.json`,`${second.record.id}.json`].sort());
  write('README.md', 'A later edit\n');
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

test('failing aggregate records the real command and leaves subsequent commands not run', t => {
  silentErrors(t);
  const {cwd, base} = fixture(t);
  const result = runChangedChecks({cwd, base, full: true, environment: {}, runCommand: () => { throw Object.assign(new Error('private error details'), {status: 7}); }});
  assert.equal(result.exitCode, 1); assert.equal(result.record.status, 'failed');
  assert.equal(result.record.commands[0].id, 'npm:check');
  assert.equal(result.record.commands[0].status, 'failed');
  assert.equal(result.record.commands[0].exitCode, 7);
  assert.ok(result.record.commands.slice(1).every(command => command.status === 'not-run'));
  assert.ok(!result.record.commands.some(command => ['npm:typecheck','npm:test','npm:build'].includes(command.id)));
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

test('real spawn failure is recorded without serializing process messages or arguments', t => {
  silentErrors(t);
  const {cwd, base, write} = fixture(t);
  const privateMarker = 'sensitive-fixture-do-not-publish';
  write('README.md', privateMarker);
  const result = runChangedChecks({cwd, base, environment: {PRIVATE_TOKEN: privateMarker}, runCommand: () => execFileSync(join(cwd, 'missing-program'), [privateMarker])});
  assert.equal(result.record.status, 'failed');
  assert.equal(result.record.commands[0].reason, 'spawn-failed');
  assert.equal(result.record.commands[0].exitCode, null);
  const serialized = JSON.stringify(result.record);
  for (const privateValue of [privateMarker, cwd, 'README.md', 'missing-program','PRIVATE_TOKEN']) assert.ok(!serialized.includes(privateValue), privateValue);
});

test('missing or invalid base selects conservatively but cannot produce branch proof', t => {
  silentErrors(t);
  const {cwd} = fixture(t);
  for (const base of ['missing-fixture-ref','', '--not-a-git-option', '0'.repeat(40)]) {
    assert.deepEqual(selectChecks(changedFiles(base, {cwd})), ['full']);
    let executions = 0;
    const result = runChangedChecks({cwd, base, runCommand: () => executions++, environment: {}});
    assert.equal(result.exitCode, 2); assert.equal(result.record.status, 'invalid');
    assert.equal(result.record.sourceBefore.base.status, 'unavailable');
    assert.ok(result.record.issues.includes('base-unavailable')); assert.equal(executions, 0);
    assert.ok(result.record.commands.every(command => command.status === 'not-run'));
  }
});

test('source mutation while checks execute invalidates otherwise successful results', t => {
  const {cwd, base, write} = fixture(t);
  write('README.md', 'Initial edit\n');
  const result = runChangedChecks({cwd, base, environment: {}, runCommand: () => write('README.md', 'Changed during validation\n')});
  assert.equal(result.exitCode, 2); assert.equal(result.record.status, 'invalid');
  assert.ok(result.record.issues.includes('source-changed'));
  assert.ok(result.record.commands.every(command => command.status === 'passed'));
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

for (const flag of ['assume-unchanged', 'skip-worktree']) {
  test(`${flag} blocks source proof and selects conservative checks without changing the index`, t => {
    silentErrors(t);
    const {cwd, base, git, write} = fixture(t);
    const passed = runChangedChecks({cwd, base, environment: {}, runCommand: noOp});
    assert.equal(readCurrentEvidence({cwd, base}).id, passed.record.id);
    git('update-index', `--${flag}`, 'README.md');
    const flaggedIndex = git('ls-files', '-v');
    // Even before any byte changes, an older result cannot certify this index.
    assert.equal(readCurrentEvidence({cwd, base}), null);
    write('README.md', 'Hidden source mutation\n');
    assert.ok(changedFiles(base, {cwd}).includes('__hidden_index_entries__'));
    assert.deepEqual(selectChecks(changedFiles(base, {cwd})), ['full']);
    let executions = 0;
    const result = runChangedChecks({cwd, base, environment: {}, runCommand: () => executions++});
    assert.equal(executions, 0);
    assert.equal(result.exitCode, 2);
    assert.equal(result.record.status, 'invalid');
    assert.equal(result.record.sourceBefore.sourceIssue, 'hidden-index-entries');
    assert.ok(result.record.issues.includes('hidden-index-entries'));
    assert.ok(result.record.commands.every(command => command.status === 'not-run'));
    assert.equal(git('ls-files', '-v'), flaggedIndex);
    assert.equal(readCurrentEvidence({cwd, base}), null);
    assert.ok(!JSON.stringify(result.record).includes('README.md'));
  });

  test(`${flag} enabled during execution invalidates successful commands`, t => {
    const {cwd, base, git, write} = fixture(t);
    const result = runChangedChecks({cwd, base, environment: {}, runCommand: () => {
      git('update-index', `--${flag}`, 'README.md');
      write('README.md', 'Source changed behind an index flag\n');
    }});
    assert.equal(result.record.sourceBefore.sourceStatus, 'available');
    assert.equal(result.record.sourceAfter.sourceIssue, 'hidden-index-entries');
    assert.equal(result.exitCode, 2);
    assert.equal(result.record.status, 'invalid');
    assert.ok(result.record.issues.includes('hidden-index-entries'));
    assert.ok(result.record.commands.every(command => command.status === 'passed'));
    assert.equal(readCurrentEvidence({cwd, base}), null);
  });
}

test('untracked source bytes and names affect identity, ignored outputs do not', t => {
  const {cwd, base, write} = fixture(t);
  const initial = captureSourceSnapshot({cwd, base});
  write('untracked-fixture.txt','first bytes');
  const added = captureSourceSnapshot({cwd, base});
  assert.notEqual(added.sourceHash, initial.sourceHash);
  write('untracked-fixture.txt','other bytes');
  const edited = captureSourceSnapshot({cwd, base});
  assert.notEqual(edited.sourceHash, added.sourceHash);
  renameSync(join(cwd,'untracked-fixture.txt'), join(cwd,'renamed-fixture.txt'));
  const renamed = captureSourceSnapshot({cwd, base});
  assert.notEqual(renamed.sourceHash, edited.sourceHash);
  mkdirSync(join(cwd, 'output'));
  write('output/private-log.txt', 'ignored local diagnostics');
  assert.deepEqual(captureSourceSnapshot({cwd, base}), renamed);
  assert.ok(!JSON.stringify(renamed).includes('fixture.txt'));
});

test('HEAD and staged changes are part of identity even when file contents are unchanged', t => {
  const {cwd, base, write, git} = fixture(t);
  write('README.md', 'Changed content\n');
  const dirty = captureSourceSnapshot({cwd, base});
  git('add','README.md');
  const staged = captureSourceSnapshot({cwd, base});
  assert.notEqual(dirty.sourceHash, staged.sourceHash);
  git('commit','-m','Fixture change');
  const committed = captureSourceSnapshot({cwd, base});
  assert.notEqual(committed.head, staged.head); assert.equal(committed.base.sha, base);
});

test('delegated browser checks and unavailable Windows checks never become passes', t => {
  const {cwd, base} = fixture(t);
  const result = runChangedChecks({cwd, base, full: true, platform: 'darwin', runCommand: noOp, environment: {CHECK_SPLIT_BROWSER_TESTS: 'true'}});
  assert.equal(result.exitCode, 0); assert.equal(result.record.status, 'incomplete');
  const browsers = result.record.commands.filter(command => command.id.startsWith('browser:'));
  assert.ok(browsers.length); assert.ok(browsers.every(command => command.status === 'delegated' && command.startedAt === null));
  const windows = result.record.commands.filter(command => command.id.startsWith('windows:'));
  assert.equal(windows.length, 3); assert.ok(windows.every(command => command.status === 'unavailable'));
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

test('release delegation remains incomplete even after the local publication commands pass', t => {
  const {cwd, base} = fixture(t);
  const result = runChangedChecks({cwd, base, releaseDelegated: true, environment: {}, runCommand: noOp});
  assert.equal(result.record.status, 'incomplete');
  assert.deepEqual(result.record.commands.map(({id,status}) => [id,status]), [['npm:check','delegated'],['docs:check','passed'],['audit:public','passed']]);
});

test('public audit delegation is restricted to GitHub PR integration', t => {
  for (const environment of [{CHECK_SKIP_PUBLIC_AUDIT:'true'}, {CHECK_SKIP_PUBLIC_AUDIT:'true',GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'push'}]) {
    assert.equal(commandPlan([], {environment}).find(command => command.id === 'audit:public').status, undefined);
  }
  const {cwd, base} = fixture(t);
  const result = runChangedChecks({cwd, base, runCommand: noOp, environment: {CHECK_SKIP_PUBLIC_AUDIT:'true',GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'pull_request'}});
  assert.equal(result.record.status, 'incomplete');
  assert.equal(result.record.commands.find(command => command.id === 'audit:public').reason, 'ci-head-audit');
});

test('CI metadata persists validated identities only, without event details or environment', t => {
  const {cwd, base, write} = fixture(t);
  mkdirSync(join(cwd, 'output'));
  write('output/event.json', JSON.stringify({pull_request:{head:{sha:base,label:'private-label'},base:{sha:'bad-private-base'}}}));
  const result = runChangedChecks({cwd, base, runCommand: noOp, environment: {GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'pull_request',GITHUB_EVENT_PATH:join(cwd,'output/event.json'),GITHUB_SHA:base,GITHUB_RUN_ID:'123',GITHUB_RUN_ATTEMPT:'private-attempt',PRIVATE_TOKEN:'private-token'}});
  assert.deepEqual(result.record.ci, {provider:'github',event:'pull_request',headSha:base,baseSha:null,testedSha:base,workflowSha:base,runId:'123',runAttempt:null});
  assert.ok(!JSON.stringify(result.record).includes('private-'));
});

test('begin and progress are persisted before launch; a hard kill leaves unfinished evidence', t => {
  const {cwd, base} = fixture(t);
  const moduleUrl = new URL('../scripts/check-evidence.mjs', import.meta.url).href;
  const source = `import {startCheckRun} from ${JSON.stringify(moduleUrl)}; const run = startCheckRun(${JSON.stringify({cwd,base,environment:{}})}); run.setPlan(['selector'], [{id:'npm:test'}]); run.startCommand('npm:test'); process.kill(process.pid, 'SIGKILL');`;
  assert.throws(() => execFileSync(process.execPath, ['--input-type=module','-e',source], {stdio:'pipe'}));
  const record = latest(cwd);
  assert.equal(record.status, 'running'); assert.equal(record.finishedAt, null);
  assert.equal(record.commands[0].status, 'running'); assert.equal(record.sourceAfter, null);
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

test('an older concurrent run cannot overwrite latest evidence from a newer run', t => {
  const {cwd, base} = fixture(t);
  const first = startCheckRun({cwd, base, environment:{}});
  first.setPlan(['docs'], [{id:'docs:check'}]); first.startCommand('docs:check');
  const second = startCheckRun({cwd, base, environment:{}});
  first.finishCommand('docs:check'); first.finish();
  assert.equal(latest(cwd).id, second.record.id); assert.equal(latest(cwd).status, 'running');
  assert.equal(readCurrentEvidence({cwd, base}), null);
});

test('fixed browser and candidate gates observe only their actual aggregate command', t => {
  const {cwd} = fixture(t);
  for (const [kind, suite, id, expected] of [['browser-suite','setup','suite:setup',['scripts/check-browser-suite.mjs','setup']],['candidate',undefined,'release:candidate',['scripts/validate-candidate.mjs']]]) {
    const calls = [];
    const result = runFixedCheckWithEvidence(kind, suite, {cwd, environment:{CHECK_BASE:'invalid-unused-base'},runCommand:(command,args) => calls.push([command,args])});
    assert.equal(result.record.status, 'passed'); assert.equal(result.record.sourceBefore.base.status, 'not-requested');
    assert.deepEqual(result.record.commands.map(command => command.id), [id]);
    assert.deepEqual(calls[0], [process.execPath, expected]);
  }
});

test('all generated command identities belong to the evidence allowlist', () => {
  const commands = commandPlan(['full'], {platform:'win32',environment:{}});
  assert.ok(commands.every(command => commandIds.has(command.id)));
  assert.equal(new Set(commands.map(command => command.id)).size, commands.length);
});


test('an empty run and a latest record without its matching run file are not proof', t => {
  const {cwd, base} = fixture(t);
  const empty = startCheckRun({cwd, base, environment: {}}).finish();
  assert.equal(empty.record.status, 'incomplete');
  const passed = runChangedChecks({cwd, base, runCommand: noOp, environment: {}});
  rmSync(join(cwd, 'output/checks/runs', `${passed.record.id}.json`));
  assert.equal(readCurrentEvidence({cwd, base}), null);
});


test('a stale latest read cannot let older completion replace a newer failed run', t => {
  const {cwd, base} = fixture(t);
  const first = startCheckRun({cwd, base, environment: {}});
  first.setPlan(['docs'], [{id: 'docs:check'}]); first.startCommand('docs:check');
  const pointerPath = join(cwd, 'output/checks/latest.json');
  const staleBytes = readFileSync(pointerPath, 'utf8');
  const second = startCheckRun({cwd, base, environment: {}});
  second.setPlan(['docs'], [{id: 'docs:check'}]); second.startCommand('docs:check');
  second.finishCommand('docs:check', {status: 1}); second.finish();
  const expectedPointer = readFileSync(pointerPath, 'utf8');
  const originalRead = fs.readFileSync;
  let replayed = false;
  try {
    // Replay a read begun before the newer run published its pointer. The old
    // compare-then-write implementation would now overwrite the newer failure.
    fs.readFileSync = (path, ...args) => {
      if (path === pointerPath && !replayed) { replayed = true; return staleBytes; }
      return originalRead(path, ...args);
    };
    syncBuiltinESMExports();
    first.finishCommand('docs:check'); first.finish();
  } finally {
    fs.readFileSync = originalRead;
    syncBuiltinESMExports();
  }
  assert.equal(readFileSync(pointerPath, 'utf8'), expectedPointer);
  assert.deepEqual(JSON.parse(expectedPointer), {schemaVersion: 1, id: second.record.id});
  assert.equal(latest(cwd).status, 'failed');
  assert.equal(readCurrentEvidence({cwd, base}), null);
});
