import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, writeFileSync} from 'node:fs';
import {dirname, extname, isAbsolute, join, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import {sourceCommit} from './build-identity.mjs';
import {dependencyNotices, dependencyNoticeAudit} from './dependency-notices.mjs';
import {ocrAssets} from './mobile-assets.mjs';
import {previewSources} from './mobile-publication.mjs';

const repository = realpathSync(fileURLToPath(new URL('..', import.meta.url)));
export const DESKTOP_SCHEMA = 'proxy-desktop-frontend-v1';
export const MANIFEST_NAME = 'desktop-manifest.json';
const contract = Object.freeze({frontend_origin: 'http://127.0.0.1:3000', api_base: 'http://127.0.0.1:8766', websocket_url: 'ws://127.0.0.1:8766/api/ws'});
const sourceTrees = ['app', 'components', 'desktop', 'hooks', 'lib', 'mobile', 'styles', 'vendor/lexirise-components'];
const sourceFiles = ['package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', '.openai/hosting.json',
  'LICENSE', 'THIRD_PARTY_NOTICES.md', 'scripts/build-desktop-frontend.mjs', 'scripts/build-identity.mjs', 'scripts/prepare-mobile-assets.mjs',
  'scripts/build-browser-reader.mjs', 'scripts/dependency-notices.mjs', 'scripts/mobile-assets.mjs',
  'scripts/mobile-publication.mjs', 'scripts/mobile-ocr-integrity.json', 'scripts/ocr-worker-compat.js'];
const mimeTypes = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.webmanifest': 'application/manifest+json',
  '.wasm': 'application/wasm', '.gz': 'application/gzip', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8',
  '.ttf': 'font/ttf', '.woff': 'font/woff', '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'};
const forbiddenParts = new Set(['.git', 'node_modules', 'data', 'work', 'server', 'diagnostics']);
const sha256 = value => createHash('sha256').update(value).digest('hex');
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const stable = value => JSON.stringify(canonical(value));

export function safeDesktopName(name) {
  if (typeof name !== 'string' || !name || name.includes('\\') || name.startsWith('/') || name.split('/').some(part => !part ||
    part === '.' || part === '..' || /[^\x20-\x7e]/.test(part) || part.includes(':') || /[. ]$/.test(part) ||
    /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i.test(part))) throw Error('Unsafe desktop payload name.');
  return name;
}

function rejectLinks(path) {
  for (let current = resolve(path); ; current = dirname(current)) {
    try { if (lstatSync(current).isSymbolicLink()) throw Error('Desktop build paths cannot follow symbolic links or junctions.'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (dirname(current) === current) break;
  }
}

function walkFiles(root, onDirectory = () => {}) {
  rejectLinks(root);
  if (!existsSync(root)) throw Error('A required desktop input directory is missing.');
  const result = [];
  const visit = directory => {
    for (const entry of readdirSync(directory, {withFileTypes: true}).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
      const path = join(directory, entry.name);
      if (lstatSync(path).isSymbolicLink()) throw Error('Desktop payload/input links are prohibited.');
      if (entry.isDirectory()) { onDirectory(relative(root, path).split(sep).join('/')); visit(path); }
      else if (entry.isFile()) result.push(relative(root, path).split(sep).join('/'));
      else throw Error('Desktop payload/input must contain regular files only.');
    }
  };
  visit(root);
  return result;
}

function readInput(name) {
  safeDesktopName(name);
  const path = join(repository, name);
  rejectLinks(path);
  if (!lstatSync(path).isFile()) throw Error('A required desktop input file is missing.');
  return readFileSync(path);
}

function sourceCwd(action) {
  const prior = process.cwd();
  try { process.chdir(repository); return action(); } finally { process.chdir(prior); }
}

function selectedPublic() {
  const files = new Map([['proxy-transcript.png', readInput('public/proxy-transcript.png')]]);
  for (const name of ['index.html', 'games.html', ...previewSources]) files.set('mobile-capture/' + name, readInput('public/mobile-capture/' + name));
  for (const [name, bytes] of sourceCwd(ocrAssets)) files.set('mobile-capture/' + name, bytes);
  return files;
}

function inputState(publicFiles) {
  const inputs = {};
  for (const tree of sourceTrees) for (const name of walkFiles(join(repository, tree))) inputs[tree + '/' + name] = sha256(readInput(tree + '/' + name));
  for (const name of sourceFiles) inputs[name] = sha256(readInput(name));
  for (const [name, bytes] of publicFiles) inputs['public/' + name] = sha256(bytes);
  const tools = {};
  const lock = JSON.parse(readInput('package-lock.json'));
  // Bind every actual nested/vendor notice, declaration and pinned supplement
  // consumed by the collector. A root-only scan misses vendored libraries and
  // would let changed attribution reuse an old desktop build fingerprint.
  const noticeAudit = dependencyNoticeAudit({root: repository});
  if (noticeAudit.omissions.length) throw Error('Production dependency notices are incomplete.');
  for (const path of noticeAudit.inputs) {
    rejectLinks(path);
    const name = relative(repository, path).split(sep).join('/');
    if (name.startsWith('../') || isAbsolute(name)) throw Error('A dependency notice escapes the source installation.');
    inputs[name] = sha256(readFileSync(path));
  }
  for (const name of ['vite', '@vitejs/plugin-react', '@tailwindcss/postcss', 'tailwindcss', 'react', 'react-dom']) {
    const packagePath = join(repository, 'node_modules', name, 'package.json');
    rejectLinks(packagePath);
    const installed = JSON.parse(readFileSync(packagePath, 'utf8'));
    if (installed.version !== lock.packages['node_modules/' + name]?.version) throw Error('Installed desktop build dependencies do not match the lock.');
    tools[name] = installed.version;
    inputs['node_modules/' + name + '/package.json'] = sha256(readFileSync(join(repository, 'node_modules', name, 'package.json')));
  }
  return {commit: sourceCommit(repository), inputs, tools: {node: process.version, ...tools}};
}

export function desktopBuildId(files) {
  // This canonical form is shared with the stdlib Python host.
  const ordered = Object.fromEntries(Object.keys(files).sort().map(name => [name,
    {bytes: files[name].bytes, mime: files[name].mime, sha256: files[name].sha256}]));
  return sha256(JSON.stringify(ordered));
}

function permittedPayload(name) {
  safeDesktopName(name);
  if (name.split('/').some(part => forbiddenParts.has(part.toLowerCase()))) return false;
  if (!mimeTypes[extname(name).toLowerCase()]) return false;
  return name === 'index.html' || name === 'proxy-transcript.png' || name.startsWith('assets/') ||
    name.startsWith('mobile-capture/') || name.startsWith('notices/') || name.startsWith('_next/static/');
}

export function inventoryDesktopPayload(root) {
  const files = {}, names = new Set(), directories = [];
  for (const name of walkFiles(root, name => directories.push(name))) {
    if (name === MANIFEST_NAME) continue;
    if (!permittedPayload(name)) throw Error('Unreviewed file in the desktop payload: ' + name);
    const folded = name.toLowerCase();
    if (names.has(folded)) throw Error('Case-aliased desktop payload names are prohibited.');
    names.add(folded);
    const bytes = readFileSync(join(root, name));
    files[name] = {bytes: bytes.length, mime: mimeTypes[extname(name).toLowerCase()], sha256: sha256(bytes)};
  }
  if (directories.some(directory => directory.split('/').some(part => forbiddenParts.has(part.toLowerCase())) ||
    !Object.keys(files).some(name => name.startsWith(directory + '/')))) throw Error('Desktop payload has an unreviewed or empty directory.');
  return Object.fromEntries(Object.keys(files).sort().map(name => [name, files[name]]));
}

export function verifyDesktopOutput(root) {
  rejectLinks(root);
  rejectLinks(join(root, MANIFEST_NAME));
  const manifest = JSON.parse(readFileSync(join(root, MANIFEST_NAME), 'utf8'));
  if (manifest.schema !== DESKTOP_SCHEMA || manifest.entry !== 'index.html' || stable(manifest.routes) !== '["/"]' ||
    !/^[a-f0-9]{40}$/.test(manifest.source_commit ?? '') || !/^[a-f0-9]{64}$/.test(manifest.source_fingerprint ?? '') ||
    !/^[a-f0-9]{64}$/.test(manifest.lock_sha256 ?? '') || Object.entries(contract).some(([key, value]) => manifest[key] !== value)) throw Error('Desktop manifest identity is invalid.');
  const actual = inventoryDesktopPayload(root);
  if (!actual['index.html'] || stable(actual) !== stable(manifest.files) || desktopBuildId(actual) !== manifest.build_id) throw Error('Desktop payload does not match its exact manifest inventory.');
  return manifest;
}

function writePayload(root, name, bytes) {
  if (!permittedPayload(name)) throw Error('Unreviewed desktop output name.');
  const target = join(root, name);
  rejectLinks(target);
  mkdirSync(dirname(target), {recursive: true});
  writeFileSync(target, bytes, {flag: 'wx'});
}

function validateFonts() {
  const provenance = JSON.parse(readInput('desktop/fonts/PROVENANCE.json'));
  if (provenance.schema !== 'proxy-desktop-fonts-v1' || provenance.source_commit !== 'bd8f81ddb5c74d5c8897b36ad88b440266245103' ||
    stable(Object.keys(provenance.files ?? {}).sort()) !== '["geist-mono-variable.ttf","geist-variable.ttf"]') throw Error('Desktop font provenance is missing.');
  for (const [name, record] of Object.entries(provenance.files)) {
    const bytes = readInput('desktop/fonts/' + safeDesktopName(name));
    if (bytes.length !== record.bytes || sha256(bytes) !== record.sha256 || createHash('sha1').update(Buffer.concat([Buffer.from('blob ' + bytes.length + '\0'), bytes])).digest('hex') !== record.git_blob) throw Error('Pinned desktop font bytes changed.');
  }
  const notice = readInput('desktop/fonts/' + provenance.notice.path);
  if (sha256(notice) !== provenance.notice.sha256 || !notice.equals(readInput('styles/GEIST-OFL.txt'))) throw Error('The original pinned desktop font notice changed.');
  return provenance;
}

function runSourceBuild(script, args = []) {
  try {
    execFileSync(process.execPath, [join(repository, script), ...args], {cwd: repository, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
      env: {...process.env, WRANGLER_SEND_METRICS: 'false', WRANGLER_WRITE_LOGS: 'false', MINIFLARE_REGISTRY_PATH: join(repository, '.wrangler/registry')}});
  } catch (error) {
    throw Error('Desktop build prerequisite failed: ' + String(error.stderr ?? error.message).replaceAll(repository, '<source>').slice(-3000));
  }
}

function compatibilityFiles() {
  const root = join(repository, 'dist/client/_next/static'), result = new Map();
  for (const name of walkFiles(root)) {
    if (name.endsWith('.map')) continue;
    if (!/\.(?:js|css|woff2?|ttf)$/.test(name)) throw Error('Unexpected canonical client compatibility resource.');
    const bytes = readFileSync(join(root, name));
    if (/\.(?:js|css)$/.test(name) && (bytes.includes(Buffer.from(repository)) || bytes.includes(Buffer.from(repository.split(sep).join('/'))) || /sourceMappingURL\s*=/.test(bytes.toString('utf8')))) throw Error('Canonical client compatibility assets expose a build path or sourcemap.');
    result.set('_next/static/' + name, bytes);
  }
  if (!result.size) throw Error('The canonical client compatibility snapshot is empty.');
  return result;
}

function ensureCompatibility(state, force) {
  const receiptPath = join(repository, 'output/build-cache/desktop-vinext-compatibility.json');
  const key = sha256(stable(state));
  if (!force && existsSync(receiptPath)) {
    try {
      const receipt = JSON.parse(readFileSync(receiptPath, 'utf8'));
      const files = compatibilityFiles();
      if (receipt.input_key === key && stable(receipt.files) === stable(Object.fromEntries([...files].map(([name, bytes]) => [name, sha256(bytes)])))) return files;
    } catch { /* A stale/missing canonical output is rebuilt, never accepted. */ }
  }
  runSourceBuild('node_modules/vinext/dist/cli.js', ['build']);
  const after = inputState(selectedPublic());
  if (stable(after) !== stable(state)) throw Error('Desktop source changed during the canonical compatibility build.');
  const files = compatibilityFiles();
  mkdirSync(dirname(receiptPath), {recursive: true});
  writeFileSync(receiptPath, stable({input_key: key, files: Object.fromEntries([...files].map(([name, bytes]) => [name, sha256(bytes)]))}) + '\n');
  return files;
}

function dependencyInputsUnchanged(inputs) {
  return inputs && Object.entries(inputs).every(([name, digest]) => {
    try { return sha256(readInput(name)) === digest; } catch { return false; }
  });
}

async function renameBuildDirectory(from, to) {
  // Antivirus and filesystem sync clients briefly hold new Windows assets.
  // Keep the atomic rename and rollback semantics; never copy a partial tree.
  for (let attempt = 0; ; attempt++) {
    try { renameSync(from, to); return; }
    catch (error) {
      if (process.platform !== 'win32' || !['EPERM', 'EACCES', 'EBUSY'].includes(error.code) || attempt >= 9) throw error;
      await new Promise(resolve => setTimeout(resolve, Math.min(1000, 100 * (attempt + 1))));
    }
  }
}

function removeBuildFolderMetadata(directory) {
  // Only a dedicated ignored build directory may call this. Installed payload
  // validation remains read-only and continues to reject unexpected files.
  for (const name of walkFiles(directory)) {
    if (name.split('/').at(-1).toLowerCase() === 'desktop.ini') rmSync(join(directory, name));
  }
}

/** Build on the developer host; the emitted payload needs no JS server/runtime. */
export async function buildDesktopFrontend({outputDirectory = join(repository, 'output/desktop-frontend'), force = false} = {}) {
  outputDirectory = resolve(outputDirectory);
  const outputParent = join(repository, 'output');
  const local = relative(outputParent, outputDirectory);
  if (!local || local.startsWith('..' + sep) || local === '..' || isAbsolute(local)) throw Error('Desktop builds must use a dedicated ignored output directory.');
  rejectLinks(outputDirectory);
  runSourceBuild('scripts/prepare-mobile-assets.mjs');
  const fonts = validateFonts(), publicFiles = selectedPublic(), state = inputState(publicFiles);
  const compatibility = ensureCompatibility(state, force);
  const inputKey = sha256(stable(state));
  const receiptPath = join(outputParent, 'build-cache/desktop-frontend-' + sha256(Buffer.from(local)).slice(0, 16) + '.json');
  let prior = null;
  if (existsSync(outputDirectory)) {
    removeBuildFolderMetadata(outputDirectory);
    prior = verifyDesktopOutput(outputDirectory);
  }
  if (!force && prior && existsSync(receiptPath)) {
    const receipt = JSON.parse(readFileSync(receiptPath, 'utf8'));
    if (receipt.input_key === inputKey && receipt.build_id === prior.build_id && dependencyInputsUnchanged(receipt.module_inputs) &&
      prior.source_commit === state.commit && prior.lock_sha256 === sha256(readInput('package-lock.json')) &&
      prior.source_fingerprint === sha256(stable({state, module_inputs: receipt.module_inputs}))) return {root: outputDirectory, manifest: prior, reused: true};
  }
  const staging = outputDirectory + '.staging-' + randomUUID();
  mkdirSync(staging, {recursive: true});
  const moduleInputs = {}, packages = new Map();
  const shared = JSON.parse(readInput('vendor/lexirise-components/package.json'));
  packages.set(shared.name + '@' + shared.version, {name: shared.name, version: shared.version, license: shared.license ?? 'see retained notices'});
  const observeModules = {
    name: 'desktop-input-evidence', enforce: 'pre',
    load(id) {
      const file = id.split('?')[0];
      if (!isAbsolute(file) || !existsSync(file) || !lstatSync(file).isFile()) return null;
      const name = relative(repository, realpathSync(file)).split(sep).join('/');
      if (name.startsWith('../') || isAbsolute(name)) throw Error('Desktop build dependency escaped the source/locked installation.');
      moduleInputs[name] = sha256(readFileSync(file));
      if (name.startsWith('node_modules/')) {
        for (let folder = dirname(file); folder !== repository && dirname(folder) !== folder; folder = dirname(folder)) {
          const candidate = join(folder, 'package.json');
          if (!existsSync(candidate)) continue;
          rejectLinks(candidate);
          const data = JSON.parse(readFileSync(candidate, 'utf8'));
          if (!data.name || !data.version) continue;
          const notices = readdirSync(folder).filter(name => /^(?:licen[cs]e|notice|copying)(?:[.-].*)?$/i.test(name));
          if (!notices.length) throw Error('An emitted frontend dependency has no retained license notice.');
          packages.set(data.name + '@' + data.version, {name: data.name, version: data.version, license: data.license ?? 'see retained notices'});
          break;
        }
      }
      return null;
    },
  };
  try {
    await build({root: join(repository, 'desktop'), configFile: false, publicDir: false,
      plugins: [observeModules, react()], resolve: {alias: {'@': repository}},
      css: {postcss: {plugins: [tailwindcss({base: repository})]}},
      define: {'process.env.NODE_ENV': '"production"'}, logLevel: 'warn',
      build: {target: 'es2022', outDir: staging, emptyOutDir: false, assetsInlineLimit: 0, sourcemap: false,
        rollupOptions: {onwarn(warning, warn) { if (warning.code !== 'MODULE_LEVEL_DIRECTIVE') warn(warning); }}}});
    for (const [name, bytes] of [...publicFiles, ...compatibility]) writePayload(staging, name, bytes);
    for (const [name, source] of [['PROJECT-LICENSE.txt', 'LICENSE'], ['THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'],
      ['GEIST-OFL.txt', 'desktop/fonts/LICENSE.txt'], ['FONT-PROVENANCE.json', 'desktop/fonts/PROVENANCE.json'],
      ['SHADCN-LICENSE.md', 'styles/SHADCN-LICENSE.md']]) writePayload(staging, 'notices/' + name, readInput(source));
    writePayload(staging, 'notices/THIRD_PARTY_LICENSES.txt', Buffer.from(sourceCwd(dependencyNotices)));
    if (stable(inputState(selectedPublic())) !== stable(state) || !dependencyInputsUnchanged(moduleInputs)) throw Error('Desktop build inputs changed during compilation.');
    // Windows shell / sync clients can decorate newly created build folders.
    // Remove only that exact metadata filename from our owned staging tree;
    // the inventory and installed-payload verifier still reject every extra file.
    removeBuildFolderMetadata(staging);
    const files = inventoryDesktopPayload(staging);
    const sourceFingerprint = sha256(stable({state, module_inputs: moduleInputs}));
    const fontAssets = Object.fromEntries(Object.entries(fonts.files).map(([name, record]) => [name,
      Object.keys(files).find(path => path.startsWith('assets/') && files[path].sha256 === record.sha256)]));
    if (Object.values(fontAssets).some(name => !name)) throw Error('Pinned font resources are missing from the emitted desktop assets.');
    const manifest = {schema: DESKTOP_SCHEMA, entry: 'index.html', routes: ['/'], runtime: 'static-local-no-node',
      ...contract, version: JSON.parse(readInput('package.json')).version, source_commit: state.commit,
      source_fingerprint: sourceFingerprint, lock_sha256: sha256(readInput('package-lock.json')), build_id: desktopBuildId(files),
      files, notices: Object.keys(files).filter(name => name.startsWith('notices/')),
      fonts: {...fonts, assets: fontAssets, notice_asset: 'notices/GEIST-OFL.txt'},
      dependencies: [...packages.values()].sort((a, b) => (a.name + '@' + a.version) < (b.name + '@' + b.version) ? -1 : (a.name + '@' + a.version) > (b.name + '@' + b.version) ? 1 : 0),
      build_tools: state.tools, legacy_compatibility: {origin: contract.frontend_origin, source_commit: state.commit,
        source_fingerprint: inputKey, files: [...compatibility.keys()].sort(), source: 'verified-canonical-client-output'},
      desktop_service_worker: false, browser_profile: 'existing-selected-profile', acceptance: 'browser-and-native-probes-required'};
    writeFileSync(join(staging, MANIFEST_NAME), JSON.stringify(manifest, null, 2) + '\n', {flag: 'wx'});
    verifyDesktopOutput(staging);
    let retainedDirectory = null;
    if (prior) {
      retainedDirectory = join(outputParent, 'desktop-frontend-retained', prior.build_id + '-' + randomUUID().slice(0, 8));
      rejectLinks(retainedDirectory);
      mkdirSync(dirname(retainedDirectory), {recursive: true});
      await renameBuildDirectory(outputDirectory, retainedDirectory);
    }
    try { await renameBuildDirectory(staging, outputDirectory); } catch (error) { if (retainedDirectory) await renameBuildDirectory(retainedDirectory, outputDirectory); throw error; }
    mkdirSync(dirname(receiptPath), {recursive: true});
    writeFileSync(receiptPath, stable({input_key: inputKey, build_id: manifest.build_id, module_inputs: moduleInputs}) + '\n');
    return {root: outputDirectory, manifest, reused: false, retainedDirectory};
  } finally {
    if (existsSync(staging)) rmSync(staging, {recursive: true, force: true});
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2), index = args.indexOf('--output-root');
  if (index >= 0 && (!args[index + 1] || args[index + 1].startsWith('--'))) throw Error('--output-root requires a directory.');
  const result = await buildDesktopFrontend({outputDirectory: index >= 0 ? args[index + 1] : undefined, force: args.includes('--force')});
  console.log(JSON.stringify({schema: DESKTOP_SCHEMA, build_id: result.manifest.build_id, files: Object.keys(result.manifest.files).length,
    reused: result.reused, runtime: result.manifest.runtime, acceptance: result.manifest.acceptance}));
}
