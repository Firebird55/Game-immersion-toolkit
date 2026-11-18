// Stage an Android catalogue software closure from already retained inputs.
// This command imports no publisher data and does not contact the network.
import {createHash} from 'node:crypto';
import {lstat, mkdir, readFile, realpath, writeFile} from 'node:fs/promises';
import {dirname, join, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {COMPILED_READER_SHA256, portableMhySource} from './zzz-android-mhy-source.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const assetDir = 'packaging/android/zzz-catalogue/';
const names = ['catalogue-bytes.mjs', 'catalogue-runtime.mjs', 'catalogue-host.js', 'catalogue-worker.mjs'];
const owned = ['scene-catalog.mjs', 'comic-links.mjs', 'cinematic-links.mjs', 'zzz-dialogue.mjs',
  'zzz-presentation-config.mjs', 'zzz-cinema-timeline.mjs', 'zzz-publisher-dialogue.mjs'];
const manifestSchema = 'toolkit-android-zzz-catalogue-assets-v1';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const stable = async path => Buffer.from((await readFile(path, 'utf8')).replaceAll('\r\n', '\n'));
const describe = bytes => ({bytes: bytes.length, sha256: sha256(bytes)});

async function input(directory, name, expected, limit) {
  const path = resolve(directory, name);
  const physical = await realpath(path);
  const rel = relative(directory, physical);
  const info = await lstat(path);
  if (rel === '..' || rel.startsWith('..' + sep) || physical !== path ||
      !info.isFile() || info.size <= 0 || info.size > limit) throw Error('Invalid retained ZZZ software member');
  const raw = await readFile(path);
  if (raw.length !== info.size || sha256(raw) !== expected) throw Error('Retained ZZZ software differs from the pin');
  return raw;
}

export async function stageCatalogueSoftware(directory, output) {
  directory = await realpath(directory);
  output = resolve(output);
  const desktop = JSON.parse(await readFile(join(root, 'packaging/zzz-reader/production-inputs.json')));
  const ooz = JSON.parse(await readFile(join(root, 'packaging/zzz-reader/ooz-build.json')));
  const archive = name => desktop.archives.find(item => item.name === name);
  const staged = Object.fromEntries(await Promise.all(names.map(async name => [name, await stable(join(root, assetDir, name))])));
  for (const name of owned) staged[name] = await stable(join(root, 'scripts', name));
  const optional = await stable(join(root, 'packaging/android/publisher-oodle/decoder.mjs'));
  if (sha256(optional) !== '8bd69063c71f52d549b625fc2872928676510c9cfb725a21e72722ee8920e013')
    throw Error('The reviewed shared Oodle adapter changed');
  // The catalogue has its own worker message handler. Reuse only the pure
  // functions from the already reviewed standalone decoder.
  const source = optional.toString('utf8');
  const boundary = source.indexOf('\nif (typeof WorkerGlobalScope');
  if (boundary < 0) throw Error('Incomplete shared Oodle adapter');
  staged['oodle-adapter.mjs'] = Buffer.from(source.slice(0, boundary));
  staged['oodle-factory.mjs'] = await input(directory, 'sources/ooz-build/build/ooz.js', ooz.output.sha256, 128 * 1024);
  staged['xxhash.mjs'] = await input(directory, 'dependencies/xxhash/esm/xxhash-wasm.js',
    archive('xxhash-wasm').files.find(item => item.member === 'package/esm/xxhash-wasm.js').sha256, 128 * 1024);
  const compiled = await input(directory, 'upstream/galgame-perform.mjs', COMPILED_READER_SHA256, 128 * 1024);
  staged['mhy-format.mjs'] = Buffer.from(portableMhySource(compiled));

  const sources = {};
  for (const role of ['reader-source', 'xxhash-source']) {
    const pin = archive(role);
    sources[pin.archive] = await input(directory, 'sources/' + pin.archive, pin.sha256, 16 * 1024 * 1024);
    sources[role + '-license.txt'] = await input(directory, 'notices/' + role + '-01.txt',
      pin.notices[0].sha256, 256 * 1024);
  }
  for (const role of ['source', 'emscripten_source']) {
    const pin = ooz[role];
    sources[pin.archive] = await input(directory, 'sources/ooz-build/sources/' + pin.archive,
      pin.sha256, 64 * 1024 * 1024);
  }
  for (const notice of ooz.notices) {
    sources[notice.path.replace('notices/', '')] = await input(directory,
      'sources/ooz-build/' + notice.path, notice.sha256, 256 * 1024);
  }
  for (const path of ['scripts/build-ooz-runtime.py', 'packaging/zzz-reader/ooz-build.json',
    'packaging/zzz-reader/production-inputs.json', 'scripts/stage-android-zzz-catalogue.mjs',
    'scripts/zzz-android-mhy-source.mjs', 'LICENSE']) sources[path.split('/').at(-1)] = await stable(join(root, path));
  sources['galgame-perform.mjs'] = compiled;
  sources['original-oodle-adapter.mjs'] = optional;

  const modules = {};
  for (const [name, bytes] of Object.entries(staged)) if (!['catalogue-worker.mjs', 'catalogue-host.js'].includes(name)) {
    if (bytes.length > 128 * 1024) throw Error('Android catalogue software member exceeds bound');
    modules[name] = describe(bytes);
  }
  const record = {schema:manifestSchema, modules,
    worker:describe(staged['catalogue-worker.mjs']), host:describe(staged['catalogue-host.js']),
    sources:Object.fromEntries(Object.entries(sources).map(([name, bytes]) => [name, describe(bytes)]))};
  const raw = Buffer.from(JSON.stringify(record));
  const parent = await realpath(dirname(output));
  if (dirname(output) !== parent) throw Error('Choose an ordinary Android catalogue destination');
  await mkdir(output);
  await mkdir(join(output, 'sources'));
  for (const [name, bytes] of Object.entries(sources)) await writeFile(join(output, 'sources', name), bytes, {flag:'wx'});
  for (const [name, bytes] of Object.entries(staged)) await writeFile(join(output, name), bytes, {flag:'wx'});
  await writeFile(join(output, 'manifest.json'), raw, {flag:'wx'});
  return {identity:sha256(raw), modules:Object.keys(modules).length};
}

if (import.meta.main) {
  const [directory, output] = process.argv.slice(2);
  if (!directory || !output || process.argv.length !== 4)
    throw Error('Pass the retained verified ZZZ software folder and a fresh staging directory');
  console.log(JSON.stringify(await stageCatalogueSoftware(directory, output)));
}
