// Authored synthetic protocol probe. It never opens a game or account store.
import { readFile, writeFile, rename, realpath, lstat } from 'node:fs/promises';
import { dirname, resolve, relative, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';

async function noLinks(path) {
  for (let item = path; ; item = dirname(item)) {
    if ((await lstat(item)).isSymbolicLink()) throw Error();
    if (item === dirname(item)) return;
  }
}
function inside(path, root) {
  const part = relative(root, path);
  return part && !part.startsWith('..') && !isAbsolute(part);
}
async function run() {
  const args = process.argv.slice(2);
  if (args.length !== 7 || args[0] !== '--probe' || args[1] !== '--work'
      || args[3] !== '--input' || args[5] !== '--output') throw Error();
  const [work, input, output] = [args[2], args[4], args[6]];
  if (![work, input, output].every(path => isAbsolute(path) && resolve(path) === path) || input === output
      || !inside(input, work) || !inside(output, work)
      || dirname(input) !== work || dirname(output) !== work
      || !/^[A-Za-z0-9_-]+\.json$/.test(relative(work, input))
      || !/^[A-Za-z0-9_-]+\.json$/.test(relative(work, output))) throw Error();
  const root = dirname(fileURLToPath(import.meta.url));
  if (inside(work, root) || inside(root, work) || work === root) throw Error();
  await noLinks(work); await noLinks(input);
  try { await lstat(output); throw Error(); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const runtime = join(root, 'runtime', process.platform === 'win32' ? 'node.exe' : 'node');
  if (await realpath(process.execPath) !== await realpath(runtime)) throw Error();
  const inputInfo = await lstat(input);
  if (!inputInfo.isFile() || inputInfo.size > 4096) throw Error();
  const value = JSON.parse(await readFile(input, 'utf8'));
  if (Object.keys(value).sort().join(',') !== 'a,b,schema,text' || value.schema !== 'proxy-node-probe-input-v1'
      || typeof value.text !== 'string' || value.text.length > 1024
      || ![value.a, value.b].every(number => Number.isInteger(number) && Math.abs(number) <= 1000000)) throw Error();
  const result = await new Promise((accept, reject) => {
    const worker = new Worker(new URL('./probe-worker.mjs', import.meta.url), { workerData: { a: value.a, b: value.b }, execArgv: [] });
    const timer = setTimeout(() => { void worker.terminate(); reject(Error()); }, 10000);
    let message;
    worker.once('message', value => { message = value; });
    worker.once('error', () => { clearTimeout(timer); reject(Error()); });
    worker.once('exit', code => { clearTimeout(timer); code === 0 && message ? accept(message) : reject(Error()); });
  });
  if (result.sum !== value.a + value.b || result.wasm !== true) throw Error();
  const encoded = JSON.stringify({ schema: 'proxy-node-probe-result-v1', text: value.text,
    sum: result.sum, worker: true, wasm: true, app_local_runtime: true });
  // Exclusive creation also prevents a pending-file symlink from being followed.
  await writeFile(output + '.pending', encoded, { flag: 'wx', mode: 0o600 });
  await rename(output + '.pending', output);
  process.stdout.write(JSON.stringify({ schema: 'proxy-node-probe-stdout-v1', success: true }) + '\n');
}
run().catch(() => { process.stderr.write('Authored Node helper probe failed.\n'); process.exitCode = 1; });
