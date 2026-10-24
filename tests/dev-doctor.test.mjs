import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, relative} from 'node:path';
import {runDoctor, parsePythonLock, parseDoctorArgs, prerequisitePlan, probePython, probeBrowsers} from '../scripts/dev-doctor.mjs';

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'toolkit-doctor-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  const put = (path, text) => {const target = join(root, path); mkdirSync(join(target, '..'), {recursive: true}); writeFileSync(target, text);};
  const manifest = {version: '1.0.0', engines: {node: '>=22.13.0'}, dependencies: {synthetic: '1.2.3'}};
  put('package.json', JSON.stringify(manifest));
  put('package-lock.json', JSON.stringify({version: '1.0.0', packages: {'': manifest, 'node_modules/synthetic': {version: '1.2.3'}}}));
  put('node_modules/synthetic/package.json', JSON.stringify({version: '1.2.3'}));
  put('requirements.lock.txt', 'pytest==9.1.1\nwindows-capture==2.0.1; sys_platform == \'win32\'\n');
  put('scripts/mobile-ocr-integrity.json', JSON.stringify({files: {'ocr/core/synthetic.wasm.js': 'unused'}}));
  return {root, put};
}
const scenarios = {browser: [], windows: []};
const options = {env: {}, platform: 'win32', nodeVersion: '24.1.0', checks: ['python'], scenarios,
  exists: () => true, pythonProbe: () => ({available: true, version: '3.12.10', platform: 'win32', packages: {pytest: '9.1.1', 'windows_capture': '2.0.1'}})};
const item = (report, id) => report.items.find(value => value.id === id);
const snapshot = root => readdirSync(root, {recursive: true, withFileTypes: true}).filter(entry => entry.isFile()).map(entry => {
  const path = join(entry.parentPath || entry.path, entry.name);
  return [relative(root, path), readFileSync(path).toString('base64')];
}).sort(([a], [b]) => a.localeCompare(b));

test('docs-only plan does not require or probe Python, npm installs, browsers or generated assets', async t => {
  const {root} = fixture(t);
  const report = await runDoctor({root, files: ['README.md'], env: {}, nodeVersion: '22.13.0',
    pythonProbe: () => {throw Error('must not probe Python');}, browserProbe: () => {throw Error('must not probe browsers');}});
  assert.equal(report.status, 'pass');
  assert.deepEqual(report.plan.checks, ['docs']);
  for (const id of ['python', 'npm-packages', 'generated-assets', 'windows-host']) assert.equal(item(report, id), undefined);
  assert.equal(item(report, 'node-ci-version').required, false);
});
test('read-only metadata and injected probes leave a temporary checkout unchanged', async t => {
  const {root, put} = fixture(t);
  put('backend/__init__.py', 'raise RuntimeError("Application must never be imported")\n');
  const before = snapshot(root);
  const report = await runDoctor({...options, root});
  assert.equal(report.status, 'pass');
  assert.deepEqual(snapshot(root), before);
  assert.ok(!JSON.stringify(report).includes(root));
});
test('missing interpreter and incomplete venv are unavailable without leaking command or errors', async t => {
  const {root, put} = fixture(t);
  put('.venv/pyvenv.cfg', 'synthetic');
  const report = await runDoctor({...options, root, exists: undefined, env: {PYTHON: '/private/credential-name/python'}, pythonProbe: () => {throw Error('/private/secret/path');}});
  assert.equal(item(report, 'python').status, 'unavailable');
  assert.equal(item(report, 'python').details.source, 'override');
  assert.ok(!JSON.stringify(report).includes('/private/'));
  const venv = await runDoctor({...options, root, exists: undefined, pythonProbe: ({source}) => {assert.equal(source, 'project-venv'); return {available: false};}});
  assert.equal(item(venv, 'python').details.source, 'project-venv');
});
test('required missing packages, browser executables and assets cannot report pass', async t => {
  const {root} = fixture(t);
  const report = await runDoctor({...options, root, exists: () => false,
    scenarios: {browser: ['local-access-e2e'], windows: []}, browserProbe: () => ({chromium: true, firefox: false, webkit: false}),
    pythonProbe: () => ({available: true, version: '3.12.8', platform: 'win32', packages: {}})});
  assert.equal(report.status, 'unavailable');
  assert.deepEqual(item(report, 'python-packages').details.missing, ['pytest', 'windows-capture']);
  assert.equal(item(report, 'browser-firefox').status, 'unavailable');
  assert.equal(item(report, 'generated-assets').status, 'unavailable');
  assert.ok(item(report, 'generated-assets').details.missing.includes('ocr/core/synthetic.wasm'));
});
test('package mismatch and wrong Python are configuration failures', async t => {
  const {root, put} = fixture(t);
  put('node_modules/synthetic/package.json', '{"version":"0.0.1"}');
  const report = await runDoctor({...options, root, pythonProbe: () => ({available: true, version: '3.11.10', platform: 'win32', packages: {pytest: '0.0.1'}})});
  assert.equal(report.status, 'fail');
  assert.equal(item(report, 'python').status, 'fail');
  assert.equal(item(report, 'npm-packages').status, 'fail');
  assert.deepEqual(item(report, 'python-packages').details.mismatched, ['pytest']);
});
test('missing npm install is actionable while unsupported Node is a failed prerequisite', async t => {
  const {root} = fixture(t);
  rmSync(join(root, 'node_modules'), {recursive: true});
  const report = await runDoctor({...options, root, nodeVersion: '20.10.0'});
  assert.equal(item(report, 'node').status, 'fail');
  assert.equal(item(report, 'npm-packages').status, 'unavailable');
  assert.match(item(report, 'npm-packages').remediation, /npm ci/);
});
test('optional native unavailability is separate from a selected required native scenario', async t => {
  const {root} = fixture(t);
  const optional = await runDoctor({...options, root, platform: 'darwin', checks: ['mobile']});
  assert.equal(optional.status, 'pass');
  assert.equal(item(optional, 'windows-host').required, false);
  const required = await runDoctor({...options, root, platform: 'darwin'});
  assert.equal(required.status, 'unavailable');
  assert.equal(item(required, 'windows-host').required, true);
});
test('Windows scenarios probe PowerShell without starting a fixture', async t => {
  const {root} = fixture(t);
  const report = await runDoctor({...options, root, checks: ['windows'], scenarios: {browser: [], windows: ['setup-e2e']}, commandProbe: (command, args) => {
    assert.equal(command, 'powershell.exe'); assert.ok(args.includes('-NoProfile')); return false;
  }});
  assert.equal(item(report, 'powershell').status, 'unavailable');
  assert.equal(item(report, 'python'), undefined);
});
test('metadata probe disables bytecode, reads stdlib distribution metadata and hides stderr', () => {
  const output = probePython({command: 'synthetic-python', root: 'synthetic-root', env: {}, spawn: (command, args, settings) => {
    assert.equal(command, 'synthetic-python'); assert.equal(args[0], '-B');
    assert.equal(settings.env.PYTHONDONTWRITEBYTECODE, '1');
    assert.match(args[2], /sys.dont_write_bytecode = True/); assert.match(args[2], /from importlib.metadata import distributions/);
    assert.doesNotMatch(args[2], /backend|subprocess|pip install/);
    return {status: 0, stdout: '{"version":"3.12.0","platform":"win32","packages":{}}'};
  }});
  assert.equal(output.available, true);
  assert.deepEqual(probePython({command: 'missing', spawn: () => ({error: Error('/private/secret'), stderr: '/private/secret'})}), {available: false});
});
test('lock parser evaluates platform markers, normalizes later and fails closed on new syntax', () => {
  const text = '# comment\npytest==9.1.1\nwindows-capture==2.0.1; sys_platform == "win32"\nother==1.0; sys_platform != "win32"\n';
  assert.deepEqual(parsePythonLock(text, 'win32').map(value => value.name), ['pytest', 'windows-capture']);
  assert.deepEqual(parsePythonLock(text, 'darwin').map(value => value.name), ['pytest', 'other']);
  assert.throws(() => parsePythonLock('package>=1.0', 'win32'), /Unsupported/);
  assert.throws(() => parsePythonLock('package==1.0; python_version > "3.9"', 'win32'), /Unsupported/);
});
test('doctor args and selected scenarios preserve the selector scope', () => {
  assert.deepEqual(parseDoctorArgs(['--base', 'origin/main', '--json', '--full']), {json: true, full: true, base: 'origin/main'});
  assert.throws(() => parseDoctorArgs(['--base'])); assert.throws(() => parseDoctorArgs(['--install']));
  assert.deepEqual(prerequisitePlan(['docs'], scenarios), {nodePackages: false, python: false, assets: false, engines: [], windows: false});
  assert.deepEqual(prerequisitePlan(['desktop'], {browser: ['ui-state-react-e2e'], windows: []}).engines, ['chromium', 'firefox']);
});


test('an unavailable Git base fails even when every selected prerequisite is ready', async t => {
  const {root} = fixture(t);
  const report = await runDoctor({...options, root, files:['__unknown_base__'], checks:['full']});
  assert.equal(report.status, 'fail');
  assert.equal(item(report, 'git-base').required, true);
  assert.equal(item(report, 'git-base').status, 'fail');
  assert.ok(report.items.filter(value => value.id !== 'git-base').every(value => value.status === 'pass'));
});
test('PowerShell override only applies to the update fixture, never setup or identity', async t => {
  const {root} = fixture(t);
  const override = '/private/synthetic-powershell';
  for (const name of ['setup-e2e','companion-process-identity-e2e']) {
    const commands=[];
    const report = await runDoctor({...options, root, env:{PWSH:override}, checks:['windows'], scenarios:{browser:[],windows:[name]}, commandProbe: command => {commands.push(command); return command === override;}});
    assert.deepEqual(commands,['powershell.exe']);
    assert.equal(report.status,'unavailable');
    assert.equal(item(report,'powershell').status,'unavailable');
  }
  const commands=[];
  const combined = await runDoctor({...options, root, env:{PWSH:override}, checks:['windows'], scenarios:{browser:[],windows:['setup-e2e','update-companion-e2e']}, commandProbe: command => {commands.push(command); return command === override;}});
  assert.deepEqual(commands,['powershell.exe',override]);
  assert.equal(combined.status,'unavailable');
  assert.equal(item(combined,'powershell-update').status,'pass');
  assert.ok(!JSON.stringify(combined).includes(override));
  const updateCommands=[];
  const update = await runDoctor({...options, root, env:{PWSH:override}, checks:['windows'], scenarios:{browser:[],windows:['update-companion-e2e']}, commandProbe: command => {updateCommands.push(command); return true;}});
  assert.deepEqual(updateCommands,[override]);
  assert.equal(update.status,'pass');
});


test('selector scope requires the npm packages and assets used by its npm test command', async t => {
  const {root} = fixture(t);
  rmSync(join(root, 'node_modules'), {recursive: true});
  const report = await runDoctor({root, files: ['tests/check-selection.test.mjs'], env: {}, nodeVersion: '24.1.0',
    pythonProbe: () => {throw Error('No Python in selector scope');}, browserProbe: () => {throw Error('No browser scenarios in selector scope');}});
  assert.deepEqual(report.plan.checks, ['selector']);
  assert.equal(report.status, 'unavailable');
  assert.equal(item(report, 'npm-packages').status, 'unavailable');
  assert.equal(item(report, 'generated-assets').status, 'unavailable');
  assert.equal(item(report, 'python'), undefined);
});

function browserModules({version = '1.64.0', coreVersion = '1.64.0', registry = true} = {}) {
  return name => {
    if (name === 'playwright/package.json') return {version};
    if (name === 'playwright-core/package.json') return {version: coreVersion};
    if (name === 'playwright') return Object.fromEntries(['chromium','firefox','webkit'].map(engine => [engine, {executablePath: () => `synthetic/${engine}`} ]));
    if (name === 'playwright-core/lib/coreBundle') return registry ? {registry: {registry: {findExecutable: name => {
      assert.equal(name, 'chromium-headless-shell');
      return {executablePath: () => 'synthetic/chromium-headless-shell'};
    }}}} : {};
    throw Error('Unexpected metadata import');
  };
}

test('Chromium prerequisites follow the pinned headless launch executable without launching', () => {
  const engines = ['chromium','firefox','webkit'];
  const regularOnly = probeBrowsers({engines, loadModule: browserModules(), exists: path => !path.endsWith('headless-shell')});
  assert.deepEqual(regularOnly, {chromium: false, firefox: true, webkit: true});
  const shellOnly = probeBrowsers({engines, loadModule: browserModules(), exists: path => path.endsWith('headless-shell')});
  assert.deepEqual(shellOnly, {chromium: true, firefox: false, webkit: false});
  assert.deepEqual(probeBrowsers({engines: ['chromium'], loadModule: browserModules(), exists: () => false}), {chromium: false});
});

test('Chromium metadata fails closed for an unreviewed version or missing registry export', () => {
  for (const options of [{version: '1.65.0'}, {coreVersion: '1.65.0'}, {registry: false}]) {
    assert.deepEqual(probeBrowsers({engines: ['chromium'], loadModule: browserModules(options), exists: () => true}), {chromium: false});
  }
  assert.deepEqual(probeBrowsers({engines: ['chromium'], loadModule: () => {throw Error('Unavailable metadata');}, exists: () => true}), {chromium: false});
});

test('hidden or uninspectable Git index entries cannot report ready prerequisites', async t => {
  const {root} = fixture(t);
  for (const sentinel of ['__hidden_index_entries__', '__unknown_index__']) {
    const report = await runDoctor({...options, root, files: [sentinel], checks: ['full']});
    assert.equal(report.status, 'fail');
    assert.equal(item(report, 'git-source').status, 'fail');
    assert.equal(item(report, 'git-source').required, true);
  }
});
