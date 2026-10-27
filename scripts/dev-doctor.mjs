import {spawnSync} from 'node:child_process';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {changedFiles, selectChecks, scenarioPlan} from './check-changed.mjs';
import {resolvePython} from './python-runtime.mjs';

const allEngines = ['chromium', 'firefox', 'webkit'];
const threeEngineScenarios = new Set(['local-access-e2e', 'companion-e2e', 'mobile-reader-layout-e2e', 'mobile-capture-e2e', 'mobile-recovery-e2e', 'mobile-vdo-source-e2e', 'mobile-source-e2e', 'mobile-library-e2e', 'mobile-games-e2e', 'mobile-update-e2e']);
const pythonScenarios = new Set(['ui-state-e2e', 'ui-state-react-e2e', 'local-access-e2e']);
const normalize = name => name.toLowerCase().replace(/[-_.]+/g, '-');
const safeVersion = value => /^\d+(?:\.\d+)*(?:[a-zA-Z0-9.+-]*)$/.test(String(value)) ? String(value) : 'unknown';
const json = (read, path) => JSON.parse(read(path, 'utf8'));
const atLeast = (actual, minimum) => {
  const a = actual.split('.').map(Number), b = minimum.split('.').map(Number);
  for (let i = 0; i < b.length; i++) if (a[i] !== b[i]) return a[i] > b[i];
  return true;
};

export function prerequisitePlan(checks, scenarios) {
  const application = checks.some(check => ['full', 'desktop', 'mobile', 'python', 'selector'].includes(check));
  const engines = new Set();
  for (const scenario of scenarios.browser) {
    for (const engine of threeEngineScenarios.has(scenario) ? allEngines : scenario === 'mobile-layout-e2e' ? ['chromium'] : ['chromium', 'firefox']) engines.add(engine);
  }
  return {nodePackages: application || engines.size > 0,
    python: checks.some(check => ['full', 'python'].includes(check)) || scenarios.browser.some(scenario => pythonScenarios.has(scenario)) || scenarios.windows.includes('update-companion-e2e'),
    assets: application || engines.size > 0, engines: [...engines].sort(), windows: scenarios.windows.length > 0};
}

// The lock currently contains exact pins and sys_platform markers. Refuse new
// syntax until its semantics are supported; never silently drop a requirement.
export function parsePythonLock(text, platform) {
  return text.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith('#')).flatMap(line => {
    const match = /^([A-Za-z0-9_.-]+)==([A-Za-z0-9.+!-]+)(?:\s*;\s*sys_platform\s*(==|!=)\s*(['"])([A-Za-z0-9_-]+)\4)?$/.exec(line);
    if (!match) throw Error('Unsupported requirement syntax');
    const [, name, version, operator, , target] = match;
    if (operator && ((platform === target) !== (operator === '=='))) return [];
    return [{name, version}];
  });
}

export function probePython({command, root, env, spawn = spawnSync}) {
  // No application, native runtime or package imports: distribution metadata is
  // enough to compare the pinned dependency versions without starting services.
  const code = `import sys\nsys.dont_write_bytecode = True\nimport json\nfrom importlib.metadata import distributions\nprint(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), 'platform': sys.platform, 'packages': {d.metadata['Name']: d.version for d in distributions() if d.metadata['Name']}}))`;
  const result = spawn(command, ['-B', '-c', code], {cwd: root, env: {...env, PYTHONDONTWRITEBYTECODE: '1'}, encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024, windowsHide: true});
  if (result.error || result.status !== 0) return {available: false};
  try { return {available: true, ...JSON.parse(result.stdout)}; } catch { return {available: false}; }
}

export function probeBrowsers({root = process.cwd(), engines, exists = existsSync, loadModule}) {
  try {
    const load = loadModule || createRequire(join(root, 'package.json'));
    const playwright = load('playwright');
    let headlessExecutable;
    if (engines.includes('chromium')) {
      // Reviewed Playwright 1.64.0/1.64.1 launch chromium-headless-shell by default;
      // chromium.executablePath() instead identifies headed Chromium. Its
      // exported registry supplies the exact platform/revision-specific path.
      // Recheck this internal metadata contract when upgrading Playwright.
      const version = load('playwright/package.json').version;
      if (['1.64.0', '1.64.1'].includes(version) && load('playwright-core/package.json').version === version) {
        const registry = load('playwright-core/lib/coreBundle')?.registry?.registry;
        headlessExecutable = registry?.findExecutable?.('chromium-headless-shell')?.executablePath?.();
      }
    }
    return Object.fromEntries(engines.map(name => {
      const executable = name === 'chromium' ? headlessExecutable : playwright[name]?.executablePath();
      return [name, typeof executable === 'string' && !!executable && exists(executable)];
    }));
  } catch { return Object.fromEntries(engines.map(name => [name, false])); }
}

// Injection keeps failure branches testable without installing runtimes or
// launching applications. This function performs reads and metadata probes only.
export async function runDoctor({root = process.cwd(), env = process.env, platform = process.platform, nodeVersion = process.versions.node,
  files = [], checks = selectChecks(files), scenarios = scenarioPlan(files, checks),
  exists = existsSync, read = readFileSync, pythonProbe = probePython, browserProbe = probeBrowsers,
  commandProbe = (command, args) => {const result = spawnSync(command, args, {cwd: root, env, stdio: 'ignore', timeout: 10000, windowsHide: true}); return !result.error && result.status === 0;}} = {}) {
  const requirements = prerequisitePlan(checks, scenarios);
  const items = [];
  const add = (id, status, required, message, remediation, details) => items.push({id, status, required, message, ...(remediation ? {remediation} : {}), ...(details ? {details} : {})});
  if (files.includes('__unknown_base__')) add('git-base', 'fail', true, 'The requested Git base is unavailable; the selected scope cannot be verified.', 'Fetch or choose an existing base commit, then rerun the doctor with --base.');
  if (files.some(file => ['__hidden_index_entries__', '__unknown_index__'].includes(file))) add('git-source', 'fail', true, 'Git source visibility could not be verified; tracked changes may be hidden by index flags.', 'Inspect the Git index for assume-unchanged or skip-worktree flags and resolve source visibility before checking.');
  else if (files.some(file => ['__git_source_transforms__', '__unknown_source_attributes__'].includes(file))) add('git-source', 'fail', true, 'Git source transformation attributes prevent verified source selection, or their inspection failed.', 'Inspect effective filter, ident and working-tree-encoding attributes and use a checkout whose source bytes can be verified. The doctor does not execute or change source transformations.');
  let manifest, lock;
  try { manifest = json(read, join(root, 'package.json')); lock = json(read, join(root, 'package-lock.json')); }
  catch { add('npm-lock', 'fail', true, 'Project package metadata is missing or unreadable.', 'Restore package.json and package-lock.json from the checkout.'); }
  const minimum = /^>=(\d+\.\d+\.\d+)$/.exec(manifest?.engines?.node || '')?.[1];
  const nodeValid = minimum && safeVersion(nodeVersion) !== 'unknown' && atLeast(nodeVersion, minimum);
  add('node', nodeValid ? 'pass' : 'fail', true, nodeValid ? `Node ${safeVersion(nodeVersion)} satisfies the package engine.` : 'Node does not satisfy the package engine.', nodeValid ? undefined : 'Install Node 24 and reopen the development shell.', {version: safeVersion(nodeVersion), minimum: minimum || 'unknown', recommendedMajor: 24});
  if (nodeValid && Number(nodeVersion.split('.')[0]) !== 24) add('node-ci-version', 'unavailable', false, 'This Node version differs from the recommended CI major (24).', 'Use Node 24 to reproduce CI; the package engine is still supported.');
  if (manifest && lock) {
    const declared = {...manifest.dependencies, ...manifest.devDependencies};
    const pinned = {...lock.packages?.['']?.dependencies, ...lock.packages?.['']?.devDependencies};
    const lockValid = lock.version === manifest.version && JSON.stringify(Object.entries(declared).sort()) === JSON.stringify(Object.entries(pinned).sort());
    add('npm-lock', lockValid ? 'pass' : 'fail', true, lockValid ? 'Package declarations match the lock metadata.' : 'Package declarations differ from the lock metadata.', lockValid ? undefined : 'Regenerate and review package-lock.json with the supported npm version.');
    if (requirements.nodePackages) {
      const missing = [], mismatched = [];
      for (const name of Object.keys(declared).sort()) {
        const wanted = lock.packages?.[`node_modules/${name}`]?.version;
        try {
          const installed = json(read, join(root, 'node_modules', name, 'package.json')).version;
          if (!wanted || installed !== wanted) mismatched.push(name);
        } catch { missing.push(name); }
      }
      add('npm-packages', missing.length ? 'unavailable' : mismatched.length ? 'fail' : 'pass', true,
        missing.length || mismatched.length ? 'Installed npm package metadata does not match the selected checks.' : 'Direct npm packages match the lock metadata.',
        missing.length || mismatched.length ? 'Run npm ci, then npm run dev:prepare.' : undefined, {missing, mismatched});
    }
  }
  if (requirements.python) {
    const selected = resolvePython({root, env, platform, exists});
    let probe;
    try { probe = await pythonProbe({...selected, root, env}); } catch { probe = {available: false}; }
    if (!probe.available || !probe.version || !probe.platform || !probe.packages) {
      add('python', 'unavailable', true, 'The selected Python interpreter could not provide metadata.', 'Install Python 3.12 and create .venv, or set PYTHON to a working development interpreter.', {source: selected.source});
    } else {
      const version = safeVersion(probe.version), supported = /^3\.12\./.test(version);
      add('python', supported ? 'pass' : 'fail', true, supported ? 'Python 3.12 is selected.' : 'The selected Python version differs from the locked Python 3.12 environment.', supported ? undefined : 'Create the project .venv with Python 3.12 or set PYTHON explicitly.', {source: selected.source, version});
      try {
        const pinned = parsePythonLock(read(join(root, 'requirements.lock.txt'), 'utf8'), probe.platform);
        const installed = new Map(Object.entries(probe.packages).map(([name, version]) => [normalize(name), version]));
        const missing = [], mismatched = [];
        for (const {name, version: wanted} of pinned) {
          const current = installed.get(normalize(name));
          if (current === undefined) missing.push(name); else if (current !== wanted) mismatched.push(name);
        }
        add('python-packages', missing.length ? 'unavailable' : mismatched.length ? 'fail' : 'pass', true,
          missing.length || mismatched.length ? 'Python distribution metadata does not match the applicable lock pins.' : 'Python distribution metadata matches the applicable lock pins.',
          missing.length || mismatched.length ? 'With the selected interpreter, run python -m pip install -r requirements.lock.txt (Windows; Python 3.12).' : undefined, {missing, mismatched});
      } catch { add('python-lock', 'fail', true, 'The Python lock is missing or uses unsupported pin/marker syntax.', 'Restore the lock file or extend the doctor parser with tests for the new syntax.'); }
    }
  }
  if (requirements.engines.length) {
    let browsers;
    try { browsers = await browserProbe({root, engines: requirements.engines, exists}); } catch { browsers = {}; }
    for (const name of requirements.engines) add(`browser-${name}`, browsers[name] ? 'pass' : 'unavailable', true,
      browsers[name] ? `The ${name} executable is installed.` : `The ${name} executable is missing.`, browsers[name] ? undefined : `Run npx playwright install ${requirements.engines.join(' ')}. Browser launch is verified by the selected tests.`);
  }
  if (requirements.assets) {
    const expected = ['companion.js', 'companion.css', 'ocr/checksums.json', 'ocr/verified-worker.js', 'ocr/tesseract.esm.min.js', 'ocr/worker.min.js', 'ocr/opencc.mjs', 'ocr/lang/eng.traineddata.gz', 'ocr/lang/chi_sim.traineddata.gz', 'ocr/lang/chi_tra.traineddata.gz', 'pairing/qrcode.mjs', 'pairing/jsqr.mjs', 'pairing/fflate.mjs'];
    try { for (const name of Object.keys(json(read, join(root, 'scripts/mobile-ocr-integrity.json')).files)) {expected.push(name); if (name.endsWith('.wasm.js')) expected.push(name.slice(0, -3));} } catch { add('asset-manifest', 'fail', true, 'The pinned mobile asset manifest is missing or unreadable.', 'Restore scripts/mobile-ocr-integrity.json.'); }
    const missing = expected.filter(name => !exists(join(root, 'public/mobile-capture', name)));
    add('generated-assets', missing.length ? 'unavailable' : 'pass', true, missing.length ? 'Generated browser/mobile assets are missing.' : 'Required generated browser/mobile assets exist.', missing.length ? 'Run npm run dev:prepare after npm ci.' : undefined, {missing});
  }
  if (requirements.windows || requirements.python) {
    // Existing Python suites import Windows-only capture/audio packages. Their
    // metadata can be inspected anywhere, but that is not proof they can run.
    if (platform !== 'win32') add('windows-host', 'unavailable', true, 'The selected backend/native scenarios require a Windows host.', 'Run these selected checks on Windows or use the GitHub-hosted Windows gate.');
    else if (requirements.windows) {
      // The selector invokes setup/identity with powershell.exe directly. Only
      // the update fixture accepts PWSH, so its override cannot satisfy those.
      const commands = new Map();
      if (scenarios.windows.some(name => name !== 'update-companion-e2e')) commands.set('powershell.exe', 'powershell');
      if (scenarios.windows.includes('update-companion-e2e')) {
        const command = env.PWSH || 'powershell.exe';
        if (!commands.has(command)) commands.set(command, command === 'powershell.exe' ? 'powershell' : 'powershell-update');
      }
      for (const [command, id] of commands) {
        let available = false;
        try { available = commandProbe(command, ['-NoProfile', '-Command', '$PSVersionTable.PSVersion.Major']); } catch {}
        const override = id === 'powershell-update';
        add(id, available ? 'pass' : 'unavailable', true,
          available ? 'The required PowerShell executable is available.' : 'A required PowerShell executable is unavailable.',
          available ? undefined : override ? 'Set PWSH to a working executable for the update fixture.' : 'Install Windows PowerShell and make powershell.exe available on PATH.',
          {source: override ? 'override' : 'path'});
      }
    }
  } else if (requirements.nodePackages && platform !== 'win32') add('windows-host', 'unavailable', false, 'Native Windows capture is not available here and is not required by this plan.', 'Use hosted Windows validation when a native scenario is selected.');
  const status = items.some(item => item.required && item.status === 'fail') ? 'fail' : items.some(item => item.required && item.status === 'unavailable') ? 'unavailable' : 'pass';
  return {schemaVersion: 1, status, plan: {checks, browser: scenarios.browser, windows: scenarios.windows}, items};
}

export function parseDoctorArgs(args) {
  const options = {json: false, full: false};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--json') options.json = true;
    else if (args[i] === '--full') options.full = true;
    else if (args[i] === '--base' && args[i + 1] && !args[i + 1].startsWith('--')) options.base = args[++i];
    else throw Error('Usage: node scripts/dev-doctor.mjs [--base <git-ref>] [--full] [--json]');
  }
  return options;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const options = parseDoctorArgs(process.argv.slice(2));
    const files = changedFiles(options.base || process.env.CHECK_BASE);
    const checks = selectChecks(files, options.full);
    const report = await runDoctor({files, checks});
    if (options.json) console.log(JSON.stringify(report, null, 2));
    else {
      console.log(`Development prerequisites: ${report.status}; selected checks: ${checks.join(', ') || 'publication only'}`);
      for (const item of report.items) console.log(`${item.status.toUpperCase()} ${item.id}${item.required ? '' : ' (optional)'}: ${item.message}${item.remediation ? ` ${item.remediation}` : ''}`);
    }
    process.exitCode = report.status === 'pass' ? 0 : report.status === 'unavailable' ? 2 : 1;
  } catch { console.error('Could not read the development plan. Use [--base <git-ref>] [--full] [--json] from the repository root.'); process.exitCode = 1; }
}
