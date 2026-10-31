// Build-host tooling only. Nothing here is available to the shipped runtime.
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync,
  realpathSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { tmpdir, release } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const INPUTS = JSON.parse(readFileSync(join(ROOT, 'packaging/zzz-reader/inputs.json'), 'utf8'));
const OWNED = ['probe.mjs', 'probe-worker.mjs', 'sum.wat', 'sum.wasm.hex', 'NOTICE.md'];
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const ordinal = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const canonical = value => JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a], [b]) => ordinal(a, b))));
const textBytes = path => Buffer.from(readFileSync(path, 'utf8').replace(/\r\n/g, '\n'));

export function closedTree(root) {
  const files = {}, directories = [];
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name), name = relative(root, path).split(sep).join('/');
      if (entry.isSymbolicLink() || !entry.isDirectory() && !entry.isFile()) throw Error('Helper tree contains a nonregular file.');
      if (entry.isDirectory()) { directories.push(name); visit(path); }
      else { const bytes = readFileSync(path); files[name] = { bytes: bytes.length, sha256: sha256(bytes) }; }
    }
  }
  visit(root);
  const needed = new Set(Object.keys(files).flatMap(name => {
    const parts = name.split('/'); return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'));
  }));
  if (directories.some(name => !needed.has(name))) throw Error('Helper tree contains an unlisted empty directory.');
  const folded = Object.keys(files).map(name => name.toLowerCase());
  if (new Set(folded).size !== folded.length) throw Error('Helper tree contains a case alias.');
  return Object.fromEntries(Object.entries(files).sort(([a], [b]) => ordinal(a, b)));
}
function noLinks(path) {
  for (let current = path; ; current = dirname(current)) {
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) throw Error('Build paths cannot follow links.');
    if (current === dirname(current)) return;
  }
}
function member(archive, name) {
  const entries = execFileSync('tar', ['-tf', archive], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 }).split(/\r?\n/);
  if (entries.filter(entry => entry === name).length !== 1) throw Error('An exact build member is missing or ambiguous.');
  return execFileSync('tar', ['-xOf', archive, name], { maxBuffer: 150 * 1024 * 1024 });
}
function nodeInput(archive, platform) {
  const pin = INPUTS.node[platform];
  if (!pin || !archive || sha256(readFileSync(archive)) !== pin.archive_sha256) throw Error('The Node archive does not match the exact official pin.');
  const prefix = `node-v${INPUTS.node.version}-${platform}/`;
  const binary = member(archive, prefix + pin.executable), license = member(archive, prefix + 'LICENSE');
  if (sha256(binary) !== pin.executable_sha256 || license.length < 10000) throw Error('The selected Node binary or complete license is incompatible.');
  if (platform === 'win-x64') {
    const pe = binary.readUInt32LE(0x3c);
    if (binary.toString('ascii', 0, 2) !== 'MZ' || pe + 6 > binary.length
        || binary.toString('ascii', pe, pe + 4) !== 'PE\0\0' || binary.readUInt16LE(pe + 4) !== 0x8664) throw Error('The supplied Node executable is not Windows x64 PE.');
  }
  return { binary, license, pin };
}
export function helperEnvironment(environ = process.env) {
  const result = { PATH: '' };
  // No HOME/account locations, npm configuration, loader flags or compile cache.
  for (const [name, value] of Object.entries(environ)) if (['systemroot', 'windir', 'temp', 'tmp', 'tmpdir'].includes(name.toLowerCase())) result[name] = value;
  return result;
}
function sourceCommit() {
  const value = execFileSync('git', ['-C', ROOT, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  if (!/^[a-f0-9]{40}$/.test(value)) throw Error('The source commit is unavailable.');
  return value;
}
const sourceDirty = () => Boolean(execFileSync('git', ['-C', ROOT, 'status', '--porcelain'], { encoding: 'utf8' }).trim());
function stageOutput(outputRoot) {
  const target = resolve(outputRoot);
  noLinks(target);
  if (existsSync(target)) throw Error('Choose an absent, private helper output directory.');
  mkdirSync(dirname(target), { recursive: true });
  return { target, stage: mkdtempSync(join(dirname(target), '.r19-node-build-')) };
}
export function buildProbe({ archive, platform, outputRoot }) {
  const { binary, license, pin } = nodeInput(archive, platform);
  const { target, stage } = stageOutput(outputRoot);
  try {
    mkdirSync(join(stage, 'runtime'));
    const executable = 'runtime/' + (platform === 'win-x64' ? 'node.exe' : 'node');
    writeFileSync(join(stage, executable), binary); chmodSync(join(stage, executable), 0o755);
    writeFileSync(join(stage, 'runtime/LICENSE'), license);
    const sourceInputs = {};
    for (const name of OWNED) {
      // These authored text inputs have a specified LF emission on every host.
      const bytes = textBytes(join(ROOT, 'packaging/zzz-reader', name));
      sourceInputs['packaging/zzz-reader/' + name] = sha256(bytes);
      if (name.endsWith('.mjs') || name === 'NOTICE.md') writeFileSync(join(stage, name), bytes);
    }
    const wasm = textBytes(join(ROOT, 'packaging/zzz-reader/sum.wasm.hex')).toString().trim();
    if (!/^[a-f0-9]+$/.test(wasm) || wasm.length % 2) throw Error('Invalid authored WASM bytes.');
    writeFileSync(join(stage, 'sum.wasm'), Buffer.from(wasm, 'hex'));
    const licenseBytes = textBytes(join(ROOT, 'LICENSE'));
    sourceInputs.LICENSE = sha256(licenseBytes); writeFileSync(join(stage, 'LICENSE'), licenseBytes);
    const files = closedTree(stage);
    const manifest = { schema: 'proxy-prebuilt-node-reader-v1', kind: 'authored-probe',
      purpose: 'authored-probe-only', platform, source_commit: sourceCommit(), source_dirty: sourceDirty(), entry: 'probe.mjs', executable,
      runtime: { version: INPUTS.node.version, archive_sha256: pin.archive_sha256,
        executable_sha256: pin.executable_sha256, license_sha256: sha256(license) },
      source_inputs: sourceInputs, files, build_id: sha256(canonical(files)), game_execution_allowed: false };
    writeFileSync(join(stage, 'helper-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    renameSync(stage, target);
    return { root: target, manifest };
  } finally { if (existsSync(stage)) rmSync(stage, { recursive: true, force: true }); }
}
export function probeHelper({ root, manifest }, reportPath = join(ROOT, 'output/checks/r19-node-helper.json')) {
  rmSync(reportPath, { force: true });
  if (manifest.platform !== `${process.platform === 'win32' ? 'win' : process.platform}-${process.arch}`) throw Error('Native execution requires a build host matching the selected runtime.');
  const stamp = () => Object.fromEntries(Object.entries(closedTree(root)).map(([name, value]) => {
    const info = statSync(join(root, name)); return [name, { ...value, mode: info.mode, mtime: info.mtimeMs, ctime: info.ctimeMs }];
  }));
  const before = stamp(), temporary = realpathSync(mkdtempSync(join(tmpdir(), 'r19-node-probe-')));
  let report;
  try {
    const work = join(temporary, 'private-work'), unrelated = join(temporary, 'unrelated');
    mkdirSync(work); mkdirSync(unrelated);
    const input = join(work, 'request.json'), output = join(work, 'result.json');
    const text = '合成测试：中文保留，不含用户资料。';
    writeFileSync(input, JSON.stringify({ schema: 'proxy-node-probe-input-v1', text, a: 19, b: 23 }), { mode: 0o600 });
    const executable = join(root, manifest.executable);
    const version = spawnSync(executable, ['--version'], { encoding: 'utf8', cwd: unrelated, env: helperEnvironment(), timeout: 15000 });
    if (version.status !== 0 || version.stdout.trim() !== 'v' + INPUTS.node.version) throw Error('App-local Node runtime version probe failed.');
    const child = spawnSync(executable, [join(root, manifest.entry), '--probe', '--work', work, '--input', input, '--output', output],
      { cwd: unrelated, env: helperEnvironment(), encoding: 'utf8', timeout: 30000, maxBuffer: 16384, windowsHide: true });
    if (child.status !== 0 || child.error || child.stderr || child.stdout !== JSON.stringify({ schema: 'proxy-node-probe-stdout-v1', success: true }) + '\n') throw Error('Authored app-local Node execution failed.');
    const value = JSON.parse(readFileSync(output, 'utf8'));
    const files = readdirSync(work).sort();
    if (value.schema !== 'proxy-node-probe-result-v1' || value.text !== text || value.sum !== 42
        || value.worker !== true || value.wasm !== true || value.app_local_runtime !== true
        || files.join(',') !== 'request.json,result.json' || readdirSync(unrelated).length
        || JSON.stringify(stamp()) !== JSON.stringify(before)) throw Error('Synthetic protocol or write-isolation proof failed.');
    report = { schema: 'proxy-node-helper-observation-v1', status: 'passed', platform: manifest.platform,
      os_release: release(), source_commit: manifest.source_commit, source_dirty: manifest.source_dirty, build_id: manifest.build_id,
      runtime_version: INPUTS.node.version, runtime_archive_sha256: manifest.runtime.archive_sha256,
      runtime_executable_sha256: manifest.runtime.executable_sha256, runtime_license_sha256: manifest.runtime.license_sha256,
      worker: true, wasm: true, chinese_json_preserved: true, app_local_runtime: true,
      developer_path_removed: true, loader_environment_removed: true, application_writes: false,
      game_reader_accepted: false, supplier_accepted: false, windows_11_25h2_accepted: false, full_r19_complete: false };
  } finally { rmSync(temporary, { recursive: true }); }
  // A successful receipt is impossible until owned children and cleanup finish.
  report.owned_cleanup = 'passed'; mkdirSync(dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  return report;
}

function verifyPackage(path, name) {
  const pin = INPUTS.npm[name], bytes = readFileSync(path);
  if ('sha512-' + createHash('sha512').update(bytes).digest('base64') !== pin.integrity
      || sha256(bytes) !== pin.archive_sha256) throw Error('An npm build input differs from the exact lock integrity.');
  return pin;
}
export function immutableExtractor(name, original) {
  const replace = (source, before, after) => {
    if (source.split(before).length !== 2) throw Error('The owned extractor input changed; review its immutable adaptation.');
    return source.replace(before, after);
  };
  let source = original;
  if (name === 'extract_voice_links.mjs') {
    source = replace(source, "import { pathToFileURL } from 'node:url';\nimport ts from 'typescript';\n", '');
    const start = "const source = await readFile(join(toolDir, 'galgame-perform.ts'), 'utf8');";
    const end = "  await import(pathToFileURL(join(toolDir, 'galgame-perform.mjs')).href);";
    const begin = source.indexOf(start), finish = source.indexOf(end);
    if (begin < 0 || finish < begin || source.indexOf(start, begin + 1) !== -1 || source.indexOf(end, finish + 1) !== -1) throw Error('The voice extractor bootstrap changed.');
    source = source.slice(0, begin) + "import { galGameLinksFromBlocks, unpackMhyFile, xxHash64 } from './reader.mjs';" + source.slice(finish + end.length);
  } else if (name === 'extract_cinematic_links.mjs') {
    source = replace(source, "import{pathToFileURL}from'node:url';", '');
    source = replace(source, "import ts from'typescript';", '');
    source = replace(source, "const source=await readFile(join(tools,'galgame-perform.ts'),'utf8');", "const source=await readFile(new URL('./reader.mjs',import.meta.url),'utf8');");
    const bootstrap = "const readerPath=join(tools,'cinematic-reader.mjs');\nawait writeFile(readerPath,ts.transpileModule(source+'\\nexport {unpackMhyFile};',{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText);\nconst{unpackMhyFile}=await import(pathToFileURL(readerPath).href);";
    source = replace(source, bootstrap, "import{unpackMhyFile}from'./reader.mjs';");
  } else throw Error('Unknown extractor adaptation.');
  if (/typescript|transpileModule|galgame-perform\.(?:ts|mjs)|cinematic-reader\.mjs|pathToFileURL/.test(source)) throw Error('The extractor still contains runtime compilation.');
  return source;
}
export async function prepareBlockedReader({ readerSource, readerLicense, archivesRoot, outputRoot }) {
  const reader = readFileSync(readerSource), license = readFileSync(readerLicense), pin = INPUTS.upstream_reader;
  if (sha256(reader) !== pin.sha256 || sha256(license) !== pin.license_sha256) throw Error('The quarantined reader source or license differs from its pin.');
  const { target, stage } = stageOutput(outputRoot);
  const compilerRoot = realpathSync(mkdtempSync(join(tmpdir(), 'r19-build-only-ts-')));
  try {
    const sources = { 'upstream/galgame-perform.ts': sha256(reader), 'upstream/LICENSE': sha256(license) };
    let compiler;
    for (const name of ['typescript', 'ooz-wasm', 'xxhash-wasm']) {
      const archive = join(archivesRoot, `${name}-${INPUTS.npm[name].version}.tgz`), packagePin = verifyPackage(archive, name);
      sources[`npm/${name}.tgz`] = sha256(readFileSync(archive));
      for (const file of packagePin.files) {
        const bytes = member(archive, 'package/' + file);
        if (packagePin.runtime_sha256 && sha256(bytes) !== packagePin.runtime_sha256[file]) throw Error('A runtime npm module differs from the reviewed inventory.');
        const destination = name === 'typescript' ? join(compilerRoot, file) : join(stage, 'node_modules', name, file);
        mkdirSync(dirname(destination), { recursive: true }); writeFileSync(destination, bytes);
        if (name === 'typescript' && file === 'lib/typescript.js') compiler = destination;
      }
    }
    const { default: ts } = await import(pathToFileURL(compiler).href);
    const result = ts.transpileModule(reader.toString('utf8') + '\nexport { unpackMhyFile };', {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext }, reportDiagnostics: true });
    if (result.diagnostics?.some(value => value.category === ts.DiagnosticCategory.Error)) throw Error('The pinned reader did not transpile.');
    writeFileSync(join(stage, 'reader.mjs'), result.outputText);
    mkdirSync(join(stage, 'notices')); writeFileSync(join(stage, 'notices/upstream-reader-LICENSE'), license);
    writeFileSync(join(stage, 'notices/toolkit-LICENSE'), textBytes(join(ROOT, 'LICENSE')));
    for (const name of ['extract_voice_links.mjs', 'extract_cinematic_links.mjs', 'scene-catalog.mjs', 'cinematic-links.mjs', 'comic-links.mjs', 'zzz-dialogue.mjs']) {
      const bytes = textBytes(join(ROOT, 'scripts', name)); sources['scripts/' + name] = sha256(bytes);
      const emitted = name.startsWith('extract_') ? immutableExtractor(name, bytes.toString('utf8')) : bytes;
      writeFileSync(join(stage, name), emitted);
    }
    // Syntax inspection does not import modules, execute the reader or open a game.
    for (const name of ['reader.mjs', 'extract_voice_links.mjs', 'extract_cinematic_links.mjs']) {
      execFileSync(process.execPath, ['--check', join(stage, name)], { env: helperEnvironment(), stdio: 'pipe' });
    }
    const files = closedTree(stage);
    const manifest = { schema: 'proxy-zzz-quarantine-v1', status: 'blocked', game_execution_allowed: false,
      source_commit: sourceCommit(), source_dirty: sourceDirty(), upstream_commit: pin.commit, source_inputs: sources, files,
      build_id: sha256(canonical(files)), runtime_entrypoints: [],
      missing: ['combined GPL/custom-attribution rights review', 'game constants/catalog redistribution review',
        'complete corresponding ooz C++/WASM sources and reproducible toolchain',
        'Windows worker/native dependency validation', 'installed-game acceptance'] };
    writeFileSync(join(stage, 'blocked-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    renameSync(stage, target); return manifest;
  } finally { rmSync(compilerRoot, { recursive: true }); if (existsSync(stage)) rmSync(stage, { recursive: true }); }
}
async function main() {
  const args = process.argv.slice(2), values = {};
  for (let index = 0; index < args.length; index++) {
    const key = args[index];
    if (['--probe', '--prepare-blocked-reader'].includes(key)) { if (values[key]) throw Error('Duplicate option.'); values[key] = true; }
    else if (['--node-archive', '--platform', '--output-root', '--reader-source', '--reader-license', '--archives-root'].includes(key)
        && args[index + 1] && !args[index + 1].startsWith('--') && !values[key]) values[key] = args[++index];
    else throw Error('Unknown or incomplete build option.');
  }
  if (!values['--output-root']) throw Error('Pass an explicit absent output directory.');
  if (values['--probe']) rmSync(join(ROOT, 'output/checks/r19-node-helper.json'), { force: true });
  if (values['--prepare-blocked-reader']) {
    if (values['--probe'] || values['--node-archive'] || values['--platform']) throw Error('Quarantined game inputs cannot enter the authored executable profile.');
    await prepareBlockedReader({ readerSource: values['--reader-source'], readerLicense: values['--reader-license'], archivesRoot: values['--archives-root'], outputRoot: values['--output-root'] });
    process.stdout.write('Pinned reader transpiled into blocked private quarantine; no game execution is authorized.\n');
  } else {
    if (values['--reader-source'] || values['--reader-license'] || values['--archives-root']) throw Error('Game inputs cannot enter the authored executable profile.');
    const artifact = buildProbe({ archive: values['--node-archive'], platform: values['--platform'], outputRoot: values['--output-root'] });
    if (values['--probe']) probeHelper(artifact);
    process.stdout.write(JSON.stringify({ build_id: artifact.manifest.build_id, authored_probe_only: true, game_execution_allowed: false }) + '\n');
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(() => {
  process.stderr.write('Prebuilt Node helper preparation failed; no game helper was authorized.\n'); process.exitCode = 1;
});
