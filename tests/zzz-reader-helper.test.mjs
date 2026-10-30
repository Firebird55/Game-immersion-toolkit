import test from 'node:test';
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { buildProbe, closedTree, helperEnvironment, immutableExtractor, probeHelper } from '../scripts/build-zzz-reader-helper.mjs';

const sourceRoot = resolve(import.meta.dirname, '..');
function temporary(t) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'r19-node-test-')));
  t.after(() => rmSync(root, { recursive: true })); return root;
}
test('authored module worker runs actual WASM and retains Chinese JSON using app-local Node', t => {
  const temporaryRoot = temporary(t), root = join(temporaryRoot, 'helper'), work = join(temporaryRoot, 'work');
  mkdirSync(join(root, 'runtime'), { recursive: true }); mkdirSync(work);
  const executable = join(root, 'runtime', process.platform === 'win32' ? 'node.exe' : 'node');
  copyFileSync(process.execPath, executable);
  for (const name of ['probe.mjs', 'probe-worker.mjs']) copyFileSync(join(sourceRoot, 'packaging/zzz-reader', name), join(root, name));
  writeFileSync(join(root, 'sum.wasm'), Buffer.from(readFileSync(join(sourceRoot, 'packaging/zzz-reader/sum.wasm.hex'), 'utf8').trim(), 'hex'));
  const input = join(work, 'input.json'), output = join(work, 'result.json'), text = '合成中文';
  writeFileSync(input, JSON.stringify({ schema: 'proxy-node-probe-input-v1', text, a: 19, b: 23 }));
  const result = spawnSync(executable, [join(root, 'probe.mjs'), '--probe', '--work', work, '--input', input, '--output', output],
    { env: helperEnvironment({ ...process.env, NODE_OPTIONS: '--import=invalid', NODE_PATH: 'invalid', NODE_COMPILE_CACHE: 'invalid' }), encoding: 'utf8', timeout: 15000 });
  assert.equal(result.status, 0, 'The authored helper must exit successfully without loader flags.');
  assert.deepEqual(JSON.parse(readFileSync(output, 'utf8')), { schema: 'proxy-node-probe-result-v1', text, sum: 42, worker: true, wasm: true, app_local_runtime: true });
  const outside = spawnSync(executable, [join(root, 'probe.mjs'), '--probe', '--work', work, '--input', input, '--output', join(root, 'forbidden.json')],
    { env: helperEnvironment(), encoding: 'utf8', timeout: 15000 });
  assert.equal(outside.status, 1);
  assert.equal(outside.stderr, 'Authored Node helper probe failed.\n');
  rmSync(join(root, 'sum.wasm'));
  const missing = spawnSync(executable, [join(root, 'probe.mjs'), '--probe', '--work', work, '--input', input, '--output', join(work, 'missing.json')],
    { env: helperEnvironment(), encoding: 'utf8', timeout: 15000 });
  assert.equal(missing.status, 1);
  assert.equal(missing.stderr, 'Authored Node helper probe failed.\n');
});
test('closed tree rejects empty directories and environment omits loader/account paths', t => {
  const root = temporary(t); writeFileSync(join(root, 'owned.mjs'), '// authored');
  assert.deepEqual(Object.keys(closedTree(root)), ['owned.mjs']);
  mkdirSync(join(root, 'unlisted-empty'));
  assert.throws(() => closedTree(root), /empty directory/);
  assert.deepEqual(helperEnvironment({ PATH: 'developer', HOME: 'private', NODE_OPTIONS: '--eval=bad', NODE_COMPILE_CACHE: 'bad', SystemRoot: 'Windows' }), { PATH: '', SystemRoot: 'Windows' });
});
test('unverified archives fail before tar, output creation or runtime execution', t => {
  const root = temporary(t), archive = join(root, 'bad.zip'), output = join(root, 'output');
  writeFileSync(archive, 'not an archive');
  assert.throws(() => buildProbe({ archive, platform: 'win-x64', outputRoot: output }), /exact official pin/);
  assert.deepEqual(Object.keys(closedTree(root)), ['bad.zip']);
});
test('a failed native probe removes earlier passing metadata', t => {
  const root = temporary(t), report = join(root, 'previous.json');
  writeFileSync(report, '{"status":"passed"}');
  assert.throws(() => probeHelper({ root, manifest: { platform: 'unsupported-native-platform' } }, report), /matching/);
  assert.deepEqual(Object.keys(closedTree(root)), []);
});
test('both real extractor inputs adapt at build time and refuse changed bootstrap shapes', () => {
  for (const name of ['extract_voice_links.mjs', 'extract_cinematic_links.mjs']) {
    const source = readFileSync(join(sourceRoot, 'scripts', name), 'utf8').replace(/\r\n/g, '\n');
    const built = immutableExtractor(name, source);
    assert.match(built, /from\s*['"]\.\/reader\.mjs['"]/);
    assert.doesNotMatch(built, /typescript|transpileModule|galgame-perform\.(ts|mjs)|cinematic-reader\.mjs/);
    assert.throws(() => immutableExtractor(name, source.replace(/galgame-perform\.ts/g, 'changed.ts')), /changed/);
  }
});
