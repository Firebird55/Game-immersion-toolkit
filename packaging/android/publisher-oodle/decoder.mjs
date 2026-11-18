// SPDX-License-Identifier: GPL-3.0-or-later
// Separate invocation layer for the pinned, source-built ooz component.
export const MAX_PACKED = 16 * 1024 * 1024;
export const MAX_OUTPUT = 16 * 1024 * 1024;
const MAX_BLOCKS = 256;
const PADDING = 64;

function requireValid(valid) {
  if (!valid) throw new Error('Invalid Oodle decoder input or output');
}

export async function createDecoder(factory) {
  const module = await factory();
  const { _malloc: allocate, _free: free, _Kraken_Decompress: expand } = module;
  requireValid([allocate, free, expand].every(value => typeof value === 'function'));
  return (stored, size) => {
    requireValid(stored instanceof Uint8Array && stored.length >= 2 && stored.length <= MAX_PACKED &&
      Number.isSafeInteger(size) && size > 0 && size <= MAX_OUTPUT);
    const input = allocate(stored.length + PADDING);
    let output = 0;
    try {
      output = allocate(size + PADDING);
      const heap = module.HEAPU8;
      requireValid(heap instanceof Uint8Array && input > 0 && output > 0 &&
        input + stored.length + PADDING <= heap.length && output + size + PADDING <= heap.length);
      heap.set(stored, input);
      heap.fill(0, input + stored.length, input + stored.length + PADDING);
      requireValid(expand(input, stored.length, output, size) === size);
      return module.HEAPU8.slice(output, output + size);
    } finally {
      if (output) free(output);
      if (input) free(input);
    }
  };
}

export function decodeFrames(framed, size, decode) {
  requireValid(framed instanceof Uint8Array && Number.isSafeInteger(size) && size > 0 &&
    size <= MAX_OUTPUT && framed.length <= MAX_PACKED + MAX_BLOCKS * 8);
  const header = new DataView(framed.buffer, framed.byteOffset, framed.byteLength);
  const blocks = [];
  let source = 0;
  let packed = 0;
  let expanded = 0;
  while (source < framed.length) {
    requireValid(source + 8 <= framed.length && blocks.length < MAX_BLOCKS);
    const length = header.getUint32(source, true);
    const output = header.getUint32(source + 4, true);
    source += 8;
    packed += length;
    expanded += output;
    requireValid(length >= 2 && output > 0 && packed <= MAX_PACKED &&
      expanded <= size && source + length <= framed.length);
    blocks.push([framed.subarray(source, source + length), output]);
    source += length;
  }
  requireValid(expanded === size);
  const decoded = new Uint8Array(size);
  let offset = 0;
  for (const [block, length] of blocks) {
    const result = decode(block, length);
    requireValid(result instanceof Uint8Array && result.length === length);
    decoded.set(result, offset);
    offset += length;
  }
  return decoded;
}

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope) {
  let decoder;
  self.onmessage = async ({data}) => {
    try {
      if (!decoder) {
        requireValid(typeof data === 'string' && data.startsWith('blob:'));
        const {default: factory} = await import(data);
        const expand = await createDecoder(factory);
        // Authored compressed Kraken fill quantum. A healthy import alone does
        // not prove the selected WebView can execute SIMD decompression.
        requireValid(expand(Uint8Array.of(0x8c, 6, 7, 255, 255, 65), 4096).every(byte => byte === 65));
        decoder = expand;
        self.postMessage('ready');
        return;
      }
      const output = decodeFrames(new Uint8Array(data.input), data.size, decoder);
      self.postMessage(output, [output.buffer]);
    } catch {
      self.postMessage('failed');
    }
  };
}
