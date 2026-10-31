import test from 'node:test';
import {releaseMetadata} from '../scripts/prepare-release-version.mjs';
import assert from 'node:assert/strict';
import {execFileSync, spawnSync} from 'node:child_process';
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {requiredChecks, validateScope, verifyCheckout} from '../scripts/check-ci-gate.mjs';

const scope = (checks = ['docs'], overrides = {}) => ({
  checks: JSON.stringify(checks), full: String(checks.includes('full')),
  dependencies: String(checks.some(name => name !== 'docs')),
  python: String(checks.some(name => name === 'python' || name === 'full')),
  browsers: String(checks.some(name => ['desktop', 'mobile', 'full'].includes(name))),
  ...overrides,
});
const passing = {scopeValid: 'true', full: 'false', audit: 'success', check: 'success', browsers: 'skipped'};
const headSha = 'a'.repeat(40), baseSha = 'b'.repeat(40), mergeSha = 'c'.repeat(40);
const identity = {
  kind: 'integration', event: 'pull_request', expectedSha: mergeSha,
  headSha, baseSha, commit: mergeSha, parents: [baseSha, headSha],
};

test('scope accepts documentation, selected, full and delegated release plans', () => {
  for (const checks of [[], ['docs'], ['desktop', 'python'], ['mobile'], ['selector'], ['windows'], ['full']]) {
    const actual = validateScope(scope(checks));
    assert.equal(actual.scope_valid, 'true');
    assert.deepEqual(actual.checks, checks);
  }
  // Some Python-only inputs select an additional browser scenario.
  assert.equal(validateScope(scope(['python'], {browsers: 'true'})).browsers, 'true');
});

test('scope rejects missing, malformed and inconsistent flags before any skip', () => {
  for (const name of ['full', 'dependencies', 'python', 'browsers'])
    for (const value of [undefined, null, true, false, '', 'TRUE', '0', 'false\nfull=true'])
      assert.throws(() => validateScope({...scope(), [name]: value}), name);
  for (const checks of ['', 'null', '{}', 'true', '["unknown"]', '["docs","docs"]'])
    assert.throws(() => validateScope({...scope(), checks}), checks);
  for (const invalid of [
    scope(['full', 'docs']), scope(['full'], {full: 'false'}), scope(['docs'], {full: 'true'}),
    scope(['docs'], {dependencies: 'true'}), scope(['python'], {python: 'false'}),
    scope(['full'], {browsers: 'false'}), scope(['mobile'], {browsers: 'false'}),
    scope(['desktop'], {browsers: 'false'}), scope(['docs'], {browsers: 'true'}),
  ]) assert.throws(() => validateScope(invalid));
});

test('required gate accepts only the two legitimate success combinations', () => {
  const values = ['success', 'failure', 'cancelled', 'skipped', undefined, '', 'invalid'];
  for (const full of ['true', 'false', undefined, '', 'invalid'])
    for (const scopeValid of ['true', 'false', undefined])
      for (const audit of values) for (const check of values) for (const browsers of values) {
        const result = requiredChecks({full, scopeValid, audit, check, browsers});
        const expected = scopeValid === 'true' && audit === 'success' && check === 'success'
          && (full === 'true' && browsers === 'success' || full === 'false' && browsers === 'skipped');
        assert.equal(result.status === 'success', expected, JSON.stringify({full, scopeValid, audit, check, browsers}));
      }
});

test('PR application checks require exact workflow SHA and ordered event parents', () => {
  for (const kind of ['integration', 'browser', 'required-checks']) {
    const verified = verifyCheckout({...identity, kind});
    assert.equal(verified.testedSha, mergeSha);
    assert.equal(verified.source, 'event-merge');
    assert.equal(verified.baseFreshness, 'event-only');
    for (const patch of [
      {commit: headSha}, {expectedSha: headSha}, {parents: [headSha, baseSha]},
      {parents: [baseSha, 'd'.repeat(40)]}, {parents: [headSha]}, {parents: []},
      {parents: [baseSha, headSha, mergeSha]}, {headSha: ''}, {baseSha: undefined},
    ]) assert.throws(() => verifyCheckout({...identity, kind, ...patch}));
  }
});

test('public source audit uses submitted HEAD while other events use workflow SHA', () => {
  assert.equal(verifyCheckout({...identity, kind: 'source-audit', commit: headSha}).source, 'submitted-head');
  assert.throws(() => verifyCheckout({...identity, kind: 'source-audit'}), /submitted PR HEAD/);
  for (const event of ['push', 'workflow_dispatch', 'release']) for (const kind of ['source-audit', 'integration', 'browser', 'package']) {
    assert.equal(verifyCheckout({...identity, event, kind}).source, 'workflow-commit');
    assert.throws(() => verifyCheckout({...identity, event, kind, commit: headSha}), /workflow SHA/);
  }
  for (const patch of [{event: 'pull_request_target'}, {kind: 'unknown'}, {commit: 'private-path'}, {expectedSha: ''}, {parents: ['invalid']}])
    assert.throws(() => verifyCheckout({...identity, ...patch}));
});

test('gate CLI fails nonzero and persists only safe failure evidence', () => {
  const cwd = mkdtempSync(join(tmpdir(), 'ci-gate-'));
  try {
    const result = spawnSync(process.execPath, [fileURLToPath(new URL('../scripts/check-ci-gate.mjs', import.meta.url)), 'required'], {
      cwd, encoding: 'utf8', env: {
        ...process.env, GITHUB_STEP_SUMMARY: '', CI_SCOPE_VALID: passing.scopeValid, CI_SCOPE_FULL: passing.full,
        CI_AUDIT_RESULT: passing.audit, CI_CHECK_RESULT: passing.check, CI_BROWSER_RESULT: 'private-value-must-not-be-recorded',
      },
    });
    assert.notEqual(result.status, 0);
    const raw = readFileSync(join(cwd, 'output/checks/ci/required-checks.json'), 'utf8');
    const evidence = JSON.parse(raw);
    assert.equal(evidence.status, 'failure');
    assert.equal(evidence.jobs.browsers, 'invalid');
    assert.ok(!raw.includes('private-value-must-not-be-recorded'));
    assert.ok(!raw.includes(cwd));
  } finally { rmSync(cwd, {recursive: true, force: true}); }
});

const normalizeWorkflow = source => source.replace(/\r\n/g, '\n');
const workflow = normalizeWorkflow(readFileSync(new URL('../.github/workflows/ci-release.yml', import.meta.url), 'utf8'));
const nativeWorkflow = normalizeWorkflow(readFileSync(new URL('../.github/workflows/desktop-native.yml', import.meta.url), 'utf8'));
function job(name, source = workflow) {
  const text = normalizeWorkflow(source);
  const start = text.indexOf(`\n  ${name}:\n`);
  assert.notEqual(start, -1, `Missing ${name} job`);
  const content = text.slice(start + 1);
  const end = content.slice(1).search(/\n  [a-z][a-z-]*:\n/);
  return end < 0 ? content : content.slice(0, end + 1);
}

test('publication waits for native construction and rechecks all downloaded artifacts', () => {
  assert.match(job('publish'), /needs: \[package, native-desktop\]/);
  assert.match(job('publish'), /pattern: tested-desktop-\*/);
  assert.match(job('publish'), /python scripts\/assemble-desktop-release\.py --source-release release --native-root native-release/);
  assert.match(job('publish'), /gh release upload "\$RELEASE_TAG" published-release\/\*/);
  assert.match(nativeWorkflow, /if: steps\.package\.outputs\.release_eligible == 'true'/);
  assert.match(nativeWorkflow, /DESKTOP-PROVENANCE-\$\{\{ matrix\.target \}\}\.json/);
  for (const resource of ['node-resources', 'native-notices', 'managed-reader-resources']) {
    assert.ok(nativeWorkflow.includes(`'output/${resource}'`));
  }
  assert.match(nativeWorkflow, /\$options \+= @\('--resources-root', \$root\)/);
  assert.match(nativeWorkflow, /--nte-helper-root', 'output\/reader-helper\/nte'/);
  assert.match(nativeWorkflow, /prepare-desktop-python\.py.*--github-path \$env:GITHUB_PATH/);
  assert.match(nativeWorkflow, /--python-archive', '\$\{\{ steps\.python_supplier\.outputs\.python_archive \}\}'/);
});

test('workflow extraction accepts actual LF and Windows CRLF checkout text', () => {
  const crlf = workflow.replaceAll('\n', '\r\n');
  assert.ok(crlf.includes('\r\n  source-audit:\r\n'));
  for (const name of ['source-audit', 'check', 'browser-checks', 'required-checks', 'package', 'publish'])
    assert.equal(job(name, crlf), job(name, workflow), `${name} must retain the same job boundaries with CRLF`);
  assert.equal(normalizeWorkflow(crlf), workflow);
});

test('workflow separates source audit and integration checkout and always runs stable gate', () => {
  assert.match(job('source-audit'), /ref: \$\{\{ github\.event\.pull_request\.head\.sha \|\| github\.sha \}\}/);
  assert.match(job('source-audit'), /run: npm run audit:public/);
  for (const name of ['check', 'browser-checks', 'required-checks', 'package']) {
    assert.match(job(name), /ref: \$\{\{ github\.sha \}\}/);
    assert.match(job(name), /run: node scripts\/check-ci-gate\.mjs checkout /);
    assert.doesNotMatch(job(name), /ref: .*pull_request\.head/);
  }
  assert.match(job('check'), /scope_valid: \$\{\{ steps\.scope\.outputs\.scope_valid \}\}/);
  assert.ok(job('check').indexOf('check-ci-gate.mjs scope') < job('check').indexOf('run: npm ci'));
  assert.match(job('check'), /CHECK_SKIP_PUBLIC_AUDIT: .*github\.event_name == 'pull_request'/);
  assert.match(job('required-checks'), /if: \$\{\{ always\(\) \}\}/);
  assert.match(job('required-checks'), /needs: \[source-audit, check, browser-checks\]/);
  for (const name of ['CI_SCOPE_VALID', 'CI_SCOPE_FULL', 'CI_AUDIT_RESULT', 'CI_CHECK_RESULT', 'CI_BROWSER_RESULT'])
    assert.match(job('required-checks'), new RegExp(`${name}: \\$\\{\\{ needs\\.`));
  assert.equal((workflow.match(/\n      matrix:/g) || []).length, 1);
  assert.match(job('browser-checks'), /scope_valid == 'true' && needs\.check\.outputs\.full == 'true'/);
});

test('tag and manual packages validate the extracted artifact before publishing the same assets', () => {
  const packaged = job('package'), published = job('publish');
  assert.match(packaged, /if: startsWith\(github\.ref, 'refs\/tags\/v'\) \|\| github\.event_name == 'workflow_dispatch'/);
  assert.match(packaged, /needs: \[source-audit, check, browser-checks, required-checks\]/);
  const validation = packaged.slice(packaged.indexOf('run: node scripts/validate-artifacts.mjs'), packaged.indexOf('name: tested-release-assets'));
  assert.match(validation, /run: npx playwright install chromium firefox webkit/);
  assert.match(validation, /run: node scripts\/check-evidence\.mjs --candidate/);
  assert.doesNotMatch(validation, /if: github\.event_name == 'workflow_dispatch'/);
  assert.match(published, /github\.event_name == 'release'/);
  assert.match(published, /github\.event_name == 'workflow_dispatch' && inputs\.publish/);
  assert.match(published, /github\.repository == 'Firebird55\/Game-immersion-toolkit' && startsWith\(github\.ref, 'refs\/tags\/v'\)/);
  assert.match(workflow, /release:\n    types: \[published\]/);
  assert.match(published, /gh release upload .*--clobber/);
  assert.match(published, /needs: \[package, native-desktop\]/);
  assert.match(published, /name: tested-release-assets/);
  assert.doesNotMatch(published, /package-release|validate-candidate/);
  assert.match(workflow, /permissions:\n  contents: read/);
  assert.equal((workflow.match(/contents: write/g) || []).length, 1);
  assert.doesNotMatch(workflow, /pull_request_target|secrets\./);
});

test('evidence uploads stay limited to JSON and survive failed checks', () => {
  for (const name of ['source-audit', 'check', 'browser-checks', 'required-checks', 'package']) {
    const content = job(name);
    assert.match(content, /if: \$\{\{ always\(\) && hashFiles\('output\/checks\//);
    assert.doesNotMatch(content, /path: output\/?\s*$|path: output\/checks\/?\s*$/m);
    for (const line of content.split('\n').filter(line => /^\s+(?:path: )?output\//.test(line)))
      assert.match(line, /output\/checks\/(?:ci\/[a-z-]+\.json|runs\/\*\.json|latest\.json|game-screenshots\/rapid\.json)$/);
  }
});


test('gate CLI preserves verified merge identity and cannot reuse stale checkout evidence', () => {
  const cwd = mkdtempSync(join(tmpdir(), 'ci-gate-identity-'));
  const git = (...args) => execFileSync('git', args, {cwd, encoding:'utf8', stdio:['ignore','pipe','pipe']}).trim();
  const script = fileURLToPath(new URL('../scripts/check-ci-gate.mjs', import.meta.url));
  const recordPath = join(cwd,'output/checks/ci/required-checks.json');
  try {
    git('init','-q','-b','main');
    git('config','user.name','Synthetic CI Fixture');
    git('config','user.email','synthetic@users.noreply.github.com');
    git('config','commit.gpgsign','false');
    writeFileSync(join(cwd,'base.txt'),'base');git('add','.');git('commit','-qm','Synthetic base');
    git('branch','feature');
    writeFileSync(join(cwd,'main.txt'),'main');git('add','.');git('commit','-qm','Synthetic main');
    const base = git('rev-parse','HEAD');
    git('checkout','-q','feature');
    writeFileSync(join(cwd,'feature.txt'),'feature');git('add','.');git('commit','-qm','Synthetic feature');
    const head = git('rev-parse','HEAD');
    git('checkout','-q','main');git('merge','--no-ff','-qm','Synthetic event merge','feature');
    const merge = git('rev-parse','HEAD');
    const environment = {...process.env, GITHUB_STEP_SUMMARY:'', GITHUB_EVENT_NAME:'pull_request',
      GITHUB_SHA:merge, CI_PR_BASE_SHA:base, CI_PR_HEAD_SHA:head,
      CI_SCOPE_VALID:'true', CI_SCOPE_FULL:'true', CI_AUDIT_RESULT:'success', CI_CHECK_RESULT:'success', CI_BROWSER_RESULT:'success'};
    const run = (mode, overrides={}) => spawnSync(process.execPath,[script,...mode],{cwd,encoding:'utf8',env:{...environment,...overrides}});
    const read = () => JSON.parse(readFileSync(recordPath,'utf8'));
    const assertIdentity = result => {
      assert.equal(result.testedSha,merge);assert.equal(result.workflowSha,merge);
      assert.equal(result.headSha,head);assert.equal(result.baseSha,base);
      assert.equal(result.source,'event-merge');assert.equal(result.baseFreshness,'event-only');
      assert.equal(result.identityStatus,'verified');
    };
    assert.equal(run(['checkout','required-checks']).status,0);
    assert.equal(read().status,'verified');
    assert.equal(run(['required']).status,0);
    assert.equal(read().status,'success');assertIdentity(read());
    assert.notEqual(run(['required'],{CI_BROWSER_RESULT:'failure'}).status,0);
    assert.equal(read().status,'failure');assertIdentity(read());
    // A previous valid checkout file must not let altered event parents pass.
    assert.equal(run(['checkout','required-checks']).status,0);
    assert.notEqual(run(['required'],{CI_PR_BASE_SHA:'f'.repeat(40)}).status,0);
    assert.equal(read().status,'failure');assert.equal(read().identityStatus,'unavailable');
    assert.equal(read().testedSha,undefined);assert.equal(read().headSha,undefined);
    // Even an existing successful aggregate cannot bless a different checkout.
    assert.equal(run(['required']).status,0);
    git('checkout','-q','feature');
    assert.notEqual(run(['required']).status,0);
    assert.equal(read().status,'failure');assert.equal(read().identityStatus,'unavailable');
    assert.equal(read().testedSha,undefined);
  } finally {rmSync(cwd,{recursive:true,force:true});}
});


test('a manually created tag supplies matching distribution metadata without changing dependencies', () => {
  const pkg = {name:'game-immersion-toolkit',version:'0.19.2',dependencies:{example:'1.0.0'}};
  const lock = {version:pkg.version,packages:{'':pkg,'node_modules/example':{version:'1.0.0'}}};
  const prepared = releaseMetadata('v0.19.3',pkg,lock);
  assert.equal(prepared.pkg.version,'0.19.3');
  assert.equal(prepared.lock.version,'0.19.3');
  assert.equal(prepared.lock.packages[''].version,'0.19.3');
  assert.deepEqual(prepared.pkg.dependencies,pkg.dependencies);
  assert.deepEqual(prepared.lock.packages['node_modules/example'],lock.packages['node_modules/example']);
  assert.equal(pkg.version,'0.19.2');
  assert.throws(() => releaseMetadata('main',pkg,lock));
});
