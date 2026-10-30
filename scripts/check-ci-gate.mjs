import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {appendFileSync, mkdirSync, renameSync, rmSync, writeFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const sha = value => typeof value === 'string' && /^[0-9a-f]{40}$/.test(value);
const checkNames = new Set(['full', 'docs', 'python', 'desktop', 'mobile', 'windows', 'selector']);
const results = new Set(['success', 'failure', 'cancelled', 'skipped']);

// Validate every output before it is used to omit a dependency or a CI job.
export function validateScope(scope) {
  assert.ok(scope && typeof scope === 'object', 'Missing check scope');
  for (const name of ['full', 'dependencies', 'python', 'browsers'])
    assert.ok(scope[name] === 'true' || scope[name] === 'false', `Invalid ${name} scope output`);
  const checks = JSON.parse(scope.checks);
  assert.ok(Array.isArray(checks) && checks.every(name => checkNames.has(name)), 'Invalid selected checks');
  assert.equal(new Set(checks).size, checks.length, 'Duplicate selected checks');
  assert.equal(scope.full, String(checks.includes('full')), 'Inconsistent full scope');
  assert.ok(!checks.includes('full') || checks.length === 1, 'Full scope must stand alone');
  assert.equal(scope.dependencies, String(checks.some(name => name !== 'docs')), 'Inconsistent dependency scope');
  assert.equal(scope.python, String(checks.some(name => name === 'full' || name === 'python')), 'Inconsistent Python scope');
  if (checks.some(name => ['full', 'desktop', 'mobile'].includes(name)))
    assert.equal(scope.browsers, 'true', 'Application scope must include browsers');
  if (scope.browsers === 'true') assert.equal(scope.dependencies, 'true', 'Browser scope needs dependencies');
  return {...scope, checks, scope_valid: 'true'};
}

export function verifyCheckout({kind, event, expectedSha, headSha, baseSha, commit, parents}) {
  assert.ok(['source-audit', 'integration', 'browser', 'package', 'required-checks'].includes(kind), 'Unknown checkout purpose');
  assert.ok(['push', 'pull_request', 'workflow_dispatch', 'release'].includes(event), 'Unsupported CI event');
  assert.ok(sha(expectedSha) && sha(commit), 'Missing or invalid workflow/checkout SHA');
  assert.ok(Array.isArray(parents) && parents.every(sha), 'Invalid checkout parent SHAs');
  if (event === 'pull_request') {
    assert.ok(sha(headSha) && sha(baseSha), 'Missing or invalid PR head/base SHA');
    if (kind === 'source-audit') assert.equal(commit, headSha, 'Audit must inspect submitted PR HEAD');
    else {
      assert.equal(commit, expectedSha, 'Application checks must inspect the workflow merge SHA');
      assert.deepEqual(parents, [baseSha, headSha], 'PR merge parents must match the event base and head');
    }
  } else assert.equal(commit, expectedSha, 'Checkout must match the workflow SHA');
  return {
    schemaVersion: 1, kind, event, status: 'verified', testedSha: commit, workflowSha: expectedSha,
    ...(event === 'pull_request' ? {headSha, baseSha} : {}),
    source: event === 'pull_request' ? kind === 'source-audit' ? 'submitted-head' : 'event-merge' : 'workflow-commit',
    // Matching event parents does not prove that the base has stayed current.
    baseFreshness: event === 'pull_request' ? 'event-only' : 'not-applicable',
  };
}

export function requiredChecks({scopeValid, full, audit, check, browsers}) {
  const errors = [];
  if (scopeValid !== 'true') errors.push('Check scope was not validated');
  if (full !== 'true' && full !== 'false') errors.push('Missing or invalid full scope output');
  if (audit !== 'success') errors.push('Source audit did not succeed');
  if (check !== 'success') errors.push('Selected checks did not succeed');
  if (full === 'true' && browsers !== 'success') errors.push('Comprehensive browser matrix did not succeed');
  if (full === 'false' && browsers !== 'skipped') errors.push('Selected browser checks must complete inline with the matrix skipped');
  return {
    schemaVersion: 1, kind: 'required-checks', status: errors.length ? 'failure' : 'success',
    scopeValid: scopeValid === 'true', full: full === 'true' ? true : full === 'false' ? false : null,
    jobs: Object.fromEntries(Object.entries({audit, check, browsers}).map(([key, value]) => [key, results.has(value) ? value : 'invalid'])),
    errors,
  };
}

function record(name, value) {
  mkdirSync('output/checks/ci', {recursive: true});
  const path = `output/checks/ci/${name}.json`, temporary = `${path}.${randomUUID()}.tmp`;
  try {
    writeFileSync(temporary, JSON.stringify(value, null, 2) + '\n', {flag: 'wx'});
    renameSync(temporary, path);
  } finally { rmSync(temporary, {force: true}); }
  if (process.env.GITHUB_STEP_SUMMARY) {
    const lines = [`### CI ${name}`, '', `Status: ${value.status}`, ''];
    if (value.testedSha) {
      lines.push(`Tested SHA: \`${value.testedSha}\``, `Workflow SHA: \`${value.workflowSha}\``, `Source: ${value.source}`);
      if (value.headSha) lines.push(`Submitted HEAD: \`${value.headSha}\``, `Event base: \`${value.baseSha}\``, 'Base freshness: event snapshot only.');
    }
    if (value.jobs) for (const [job, result] of Object.entries(value.jobs)) lines.push(`${job}: ${result}`);
    if (value.errors) lines.push(...value.errors);
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join('\n') + '\n');
  }
}

function checkoutIdentity(kind) {
  const [commit, ...parents] = execFileSync('git', ['rev-list', '--parents', '-n', '1', 'HEAD'], {
    encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  }).trim().split(/\s+/);
  return verifyCheckout({
    kind, event: process.env.GITHUB_EVENT_NAME, expectedSha: process.env.GITHUB_SHA,
    headSha: process.env.CI_PR_HEAD_SHA, baseSha: process.env.CI_PR_BASE_SHA, commit, parents,
  });
}

function main() {
  const mode = process.argv[2];
  if (mode === 'scope') {
    const scope = validateScope({
      full: process.env.CI_SCOPE_FULL, dependencies: process.env.CI_SCOPE_DEPENDENCIES,
      python: process.env.CI_SCOPE_PYTHON, browsers: process.env.CI_SCOPE_BROWSERS,
      checks: process.env.CI_SCOPE_CHECKS,
    });
    if (process.env.GITHUB_OUTPUT) for (const [key, value] of Object.entries(scope))
      appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${key === 'checks' ? JSON.stringify(value) : value}\n`);
    console.log('CI scope outputs validated.');
  } else if (mode === 'checkout') {
    const identity = checkoutIdentity(process.argv[3]);
    record(identity.kind, identity);
    console.log(`Verified ${identity.source}: ${identity.testedSha}`);
  } else if (mode === 'required') {
    const gate = requiredChecks({
      scopeValid: process.env.CI_SCOPE_VALID, full: process.env.CI_SCOPE_FULL,
      audit: process.env.CI_AUDIT_RESULT, check: process.env.CI_CHECK_RESULT,
      browsers: process.env.CI_BROWSER_RESULT,
    });
    // Revalidate the actual checkout instead of trusting an earlier JSON file.
    // Preserve its verified source fields when the aggregate replaces the
    // checkout-step record, including when a selected job failed.
    let identity;
    try { identity = checkoutIdentity('required-checks'); }
    catch {
      gate.status = 'failure';
      gate.errors.unshift('Gate checkout identity could not be verified');
    }
    record('required-checks', {...identity, ...gate, identityStatus: identity ? 'verified' : 'unavailable'});
    if (gate.status !== 'success') throw new Error(gate.errors.join('; '));
    console.log('All required checks succeeded.');
  } else throw new Error('Expected scope, checkout, or required mode');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
