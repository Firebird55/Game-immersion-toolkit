// An actual module worker instantiates the adjacent authored WASM module.
import { readFile } from 'node:fs/promises';
import { workerData, parentPort } from 'node:worker_threads';
const { instance } = await WebAssembly.instantiate(await readFile(new URL('./sum.wasm', import.meta.url)));
parentPort.postMessage({ sum: instance.exports.add(workerData.a, workerData.b), wasm: true });
