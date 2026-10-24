import {execFileSync} from 'node:child_process';
import {createHash, randomUUID} from 'node:crypto';
import {lstatSync, mkdirSync, readFileSync, readlinkSync, renameSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const browserNames = ['browser-e2e','setup-e2e','language-account-e2e','ui-state-e2e','ui-state-react-e2e','setup-build-e2e','local-access-e2e','companion-e2e','mobile-reader-layout-e2e','mobile-capture-e2e','mobile-recovery-e2e','mobile-vdo-source-e2e','mobile-source-e2e','mobile-library-e2e','mobile-update-e2e','mobile-layout-e2e','mobile-games-e2e','ocr-packs-e2e'];
const suiteNames = ['desktop','setup','capture','offline','ocr','all'];
export const commandIds = new Set(['npm:check','npm:test','npm:test:python','npm:typecheck','npm:build','npm:mobile:build','docs:check','audit:public','release:candidate', ...browserNames.map(name => `browser:${name}`), ...['companion-process-identity-e2e','setup-e2e','update-companion-e2e'].map(name => `windows:${name}`), ...suiteNames.map(name => `suite:${name}`)]);
const checkNames = new Set(['full','python','desktop','mobile','windows','selector','docs']);
const sha = value => typeof value === 'string' && /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(value) && !/^0+$/.test(value) ? value : null;
const git = (cwd, args, encoding = 'utf8') => execFileSync('git', args, {cwd, encoding, maxBuffer: 64 * 1024 * 1024, stdio: ['ignore','pipe','pipe']});

// Git diff may hide changed bytes behind either index flag. Do not clear the
// user's flags or publish paths; these checkouts cannot supply source proof.
export function hasHiddenIndexEntries(cwd = process.cwd()) {
  return git(cwd, ['ls-files','-v','-z']).split('\0').some(entry => /^[a-zS] /.test(entry));
}

// Hash source identities and bytes, never persist file names, diffs, or contents.
// Ignored runtime data and generated artifacts are deliberately outside the input.
export function captureSourceSnapshot({cwd = process.cwd(), base} = {}) {
  const snapshot = {head: null, base: {status: base === undefined ? 'not-requested' : 'unavailable', sha: null}, sourceHash: null, sourceStatus: 'unavailable', sourceIssue: null};
  try { snapshot.head = sha(git(cwd, ['rev-parse','--verify','HEAD']).trim()); } catch {}
  if (base !== undefined) {
    try {
      if (typeof base !== 'string' || !base) throw new Error('Missing base');
      snapshot.base.sha = sha(git(cwd, ['rev-parse','--verify','--end-of-options',`${base}^{commit}`]).trim());
      if (snapshot.base.sha) snapshot.base.status = 'resolved';
    } catch {}
  }
  try {
    if (hasHiddenIndexEntries(cwd)) {
      snapshot.sourceIssue = 'hidden-index-entries';
      return snapshot;
    }
    const hash = createHash('sha256');
    const add = bytes => { hash.update(String(bytes.length)); hash.update(':'); hash.update(bytes); };
    add(git(cwd, ['ls-files','--stage','-z'], null));
    add(git(cwd, ['diff','--no-ext-diff','--no-textconv','--binary','HEAD','--'], null));
    const untracked = git(cwd, ['ls-files','--others','--exclude-standard','-z']).split('\0').filter(Boolean).sort();
    for (const file of untracked) {
      add(Buffer.from(file));
      const path = join(cwd, file), stat = lstatSync(path);
      add(Buffer.from(String(stat.mode)));
      if (stat.isSymbolicLink()) add(Buffer.from(readlinkSync(path)));
      else if (stat.isFile()) add(readFileSync(path));
      else throw new Error('Unsupported source entry');
    }
    snapshot.sourceHash = hash.digest('hex');
    if (snapshot.head) snapshot.sourceStatus = 'available';
  } catch {}
  return snapshot;
}

function ciIdentity(environment, testedSha) {
  if (environment.GITHUB_ACTIONS !== 'true') return null;
  const event = ['pull_request','push','workflow_dispatch'].includes(environment.GITHUB_EVENT_NAME) ? environment.GITHUB_EVENT_NAME : 'other';
  let payload = {};
  try { payload = JSON.parse(readFileSync(environment.GITHUB_EVENT_PATH, 'utf8')); } catch {}
  return {provider: 'github', event, headSha: sha(payload.pull_request?.head?.sha) ?? (event === 'push' ? sha(payload.after) : null), baseSha: sha(payload.pull_request?.base?.sha) ?? (event === 'push' ? sha(payload.before) : null), testedSha, workflowSha: sha(environment.GITHUB_SHA), runId: /^\d+$/.test(environment.GITHUB_RUN_ID ?? '') ? environment.GITHUB_RUN_ID : null, runAttempt: /^\d+$/.test(environment.GITHUB_RUN_ATTEMPT ?? '') ? environment.GITHUB_RUN_ATTEMPT : null};
}

function atomicWrite(path, record) {
  const temporary = `${path}.${randomUUID()}.tmp`;
  writeFileSync(temporary, JSON.stringify(record, null, 2) + '\n', {flag: 'wx'});
  renameSync(temporary, path);
}

const sourceMatches = (a, b) => a?.sourceStatus === 'available' && b?.sourceStatus === 'available' && a.base.status !== 'unavailable' && b.base.status !== 'unavailable' && JSON.stringify(a) === JSON.stringify(b);

export function readCurrentEvidence({cwd = process.cwd(), base} = {}) {
  try {
    const pointerPath = join(cwd, 'output/checks/latest.json');
    const pointer = JSON.parse(readFileSync(pointerPath, 'utf8'));
    if (pointer.schemaVersion !== 1 || !/^[0-9a-f-]{36}$/.test(pointer.id ?? '')) return null;
    const record = JSON.parse(readFileSync(join(cwd, 'output/checks/runs', `${pointer.id}.json`), 'utf8'));
    if (record.schemaVersion !== 1 || record.id !== pointer.id || record.status !== 'passed' || !record.finishedAt || !record.commands?.length || !record.commands.every(command => commandIds.has(command.id) && command.status === 'passed') || !sourceMatches(record.sourceBefore, record.sourceAfter)) return null;
    if (!sourceMatches(record.sourceAfter, captureSourceSnapshot({cwd, base}))) return null;
    // A new run may have started while the snapshot was being read.
    return JSON.parse(readFileSync(pointerPath, 'utf8')).id === pointer.id ? record : null;
  } catch { return null; }
}

// Persist the running state before looking at Git or launching any child. A hard
// kill therefore leaves an unfinished record instead of yesterday's success.
export function startCheckRun({cwd = process.cwd(), base, environment = process.env, scope = 'selected'} = {}) {
  if (!['selected','browser-suite','candidate'].includes(scope)) throw new Error('Unknown evidence scope');
  const directory = join(cwd, 'output/checks');
  mkdirSync(join(directory, 'runs'), {recursive: true});
  const record = {schemaVersion: 1, scope, id: randomUUID(), durationMs: null, startedAt: new Date().toISOString(), finishedAt: null, status: 'running', runtime: {node: /^v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(process.version) ? process.version : null, platform: ['aix','darwin','freebsd','linux','openbsd','sunos','win32','android'].includes(process.platform) ? process.platform : 'other', arch: ['arm','arm64','ia32','x64','ppc64','s390x','riscv64','loong64'].includes(process.arch) ? process.arch : 'other'}, ci: null, checks: [], commands: [], sourceBefore: null, sourceAfter: null, issues: []};
  const path = join(directory, 'runs', `${record.id}.json`), latest = join(directory, 'latest.json');
  const persist = () => atomicWrite(path, record);
  persist();
  // Only activation publishes this pointer. Progress and completion write only
  // the unique run record, so an older completion cannot replace a newer run.
  atomicWrite(latest, {schemaVersion: 1, id: record.id});
  record.sourceBefore = captureSourceSnapshot({cwd, base});
  record.ci = ciIdentity(environment, record.sourceBefore.head);
  persist();
  const entry = id => {
    const command = record.commands.find(item => item.id === id);
    if (!command) throw new Error('Unplanned check command');
    return command;
  };
  return {
    get record() { return structuredClone(record); },
    setPlan(checks, commands) {
      if (checks.some(check => !checkNames.has(check)) || commands.some(command => !commandIds.has(command.id)) || new Set(commands.map(command => command.id)).size !== commands.length) throw new Error('Unknown check plan');
      record.checks = [...checks];
      record.commands = commands.map(({id}) => ({id, status: 'not-run', startedAt: null, finishedAt: null, durationMs: null, exitCode: null, reason: null}));
      persist();
    },
    startCommand(id) {
      const command = entry(id);
      command.status = 'running'; command.startedAt = new Date().toISOString();
      persist();
    },
    finishCommand(id, error) {
      const command = entry(id);
      command.finishedAt = new Date().toISOString();
      command.durationMs = Math.max(0, Date.parse(command.finishedAt) - Date.parse(command.startedAt));
      command.status = error ? 'failed' : 'passed';
      command.exitCode = error ? (Number.isInteger(error.status) && error.status >= 0 && error.status <= 255 ? error.status : null) : 0;
      // Child error messages, arguments, stdout/stderr and environment are private.
      command.reason = error ? (['ENOENT','EACCES','EPERM'].includes(error.code) ? 'spawn-failed' : 'command-failed') : null;
      persist();
    },
    markCommand(id, status, reason) {
      if (!['unavailable','delegated'].includes(status) || !['requires-windows','split-browser-job','ci-head-audit','release-tag'].includes(reason)) throw new Error('Unknown check disposition');
      const command = entry(id); command.status = status; command.reason = reason;
      persist();
    },
    finish({failed = false} = {}) {
      record.sourceAfter = captureSourceSnapshot({cwd, base});
      if ([record.sourceBefore, record.sourceAfter].some(source => source.sourceIssue === 'hidden-index-entries')) record.issues.push('hidden-index-entries');
      if (record.sourceBefore.base.status === 'unavailable' || record.sourceAfter.base.status === 'unavailable') record.issues.push('base-unavailable');
      if (record.sourceBefore.sourceStatus !== 'available' || record.sourceAfter.sourceStatus !== 'available') record.issues.push('source-unavailable');
      if (!record.issues.length && !sourceMatches(record.sourceBefore, record.sourceAfter)) record.issues.push('source-changed');
      const invalid = record.issues.length > 0;
      const commandFailed = failed || record.commands.some(command => command.status === 'failed');
      const incomplete = record.commands.length === 0 || record.commands.some(command => command.status !== 'passed');
      if (commandFailed) record.issues.push('command-failed');
      if (incomplete) record.issues.push('commands-incomplete');
      record.status = invalid ? 'invalid' : commandFailed ? 'failed' : incomplete ? 'incomplete' : 'passed';
      record.finishedAt = new Date().toISOString();
      record.durationMs = Math.max(0, Date.parse(record.finishedAt) - Date.parse(record.startedAt));
      persist();
      // Exit 0 covers completed local commands; status remains incomplete when
      // native checks are unavailable or hosted checks are delegated. Consumers
      // must inspect the record before treating this as complete validation.
      return {record: structuredClone(record), exitCode: invalid ? 2 : commandFailed ? 1 : 0};
    },
  };
}

export function runFixedCheckWithEvidence(kind, suite, {cwd = process.cwd(), base, environment = process.env, runCommand = (command, args) => execFileSync(command, args, {cwd, stdio: 'inherit'})} = {}) {
  const evidence = startCheckRun({cwd, base, environment, scope: kind === 'candidate' ? 'candidate' : 'browser-suite'});
  let failed = false;
  try {
    if (kind !== 'candidate' && (kind !== 'browser-suite' || !suiteNames.includes(suite))) throw new Error('Unknown fixed check');
    const id = kind === 'candidate' ? 'release:candidate' : `suite:${suite}`;
    evidence.setPlan([], [{id}]);
    if (evidence.record.sourceBefore.base.status !== 'unavailable' && evidence.record.sourceBefore.sourceStatus === 'available') {
      evidence.startCommand(id);
      try {
        runCommand(process.execPath, kind === 'candidate' ? ['scripts/validate-candidate.mjs'] : ['scripts/check-browser-suite.mjs', suite]);
        evidence.finishCommand(id);
      } catch (error) { evidence.finishCommand(id, error); throw error; }
    }
  } catch (error) { console.error(error); failed = true; }
  return evidence.finish({failed});
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const index = process.argv.indexOf('--browser-suite');
  const candidate = process.argv.includes('--candidate');
  process.exitCode = runFixedCheckWithEvidence(candidate ? 'candidate' : 'browser-suite', index < 0 ? undefined : process.argv[index + 1]).exitCode;
}
