import {CatalogueBytes, MAX_FILE_BYTES} from './catalogue-bytes.mjs';

const MODES = {
  'scene-plan': ['design', 'catalogs'],
  'presentation-config-plan': ['catalogs', 'roots'],
  'presentation-owners': ['catalogs', 'blocks'],
  'comic-plan': ['catalogs', 'roots'],
  catalogue: ['design', 'blocks', 'comics', 'cinemaTimelines', 'voiceDirectory'],
};
const FILE = /^[A-Za-z0-9_.-]{1,80}$/;
const LOCALE = /^(?:en|zh-Hans|zh-Hant|ja|ko|de|es-ES|fr|id|pt-BR|ru|th|vi)$/;
const MAX_FILES = 512;
const MAX_WRITES = 256 * 1024 * 1024;

function requireValid(condition, message) {
  if (!condition) throw Error(message);
}

export function stageRoles(mode, input) {
  requireValid(Object.hasOwn(MODES, mode) && input && typeof input === 'object', 'Invalid ZZZ catalogue operation');
  const files = new Set();
  for (const role of MODES[mode]) {
    const names = input[role] ?? [];
    requireValid(Array.isArray(names) && names.length <= MAX_FILES, 'Invalid ZZZ input role');
    for (const name of names) {
      requireValid(typeof name === 'string' && FILE.test(name) && name !== '.' && name !== '..', 'Invalid ZZZ stage filename');
      files.add(name);
    }
  }
  requireValid(files.size <= MAX_FILES, 'ZZZ stage contains too many files');
  const output = new Set([mode + '-output.json']);
  if (mode === 'catalogue') {
    requireValid(typeof input.includeAudio === 'boolean', 'Choose an explicit ZZZ data mode');
    requireValid(input.includeAudio || !input.voiceDirectory?.length, 'ZZZ text mode cannot open voice data');
    requireValid(Array.isArray(input.locales) && input.locales.length > 0 && input.locales.length <= 13, 'Invalid ZZZ text languages');
    for (const locale of input.locales) {
      requireValid(typeof locale === 'string' && LOCALE.test(locale), 'Invalid ZZZ text language');
      output.add('texts-' + locale + '.json');
    }
    output.add('links.json');
    output.add('voice-directory.json');
    if (input.includeAudio) output.add('audio-resource.flex');
  }
  return {files, output};
}

export async function aes128EncryptBlock(key, data, subtle = crypto.subtle) {
  requireValid(key instanceof Uint8Array && key.length === 16 &&
    data instanceof Uint8Array && data.length === 16, 'Invalid ZZZ MHY AES block');
  // With a zero IV, the first CBC block is AES-ECB(K, input). MHY only uses
  // that block. WebCrypto's second block is PKCS#7 padding and is discarded.
  const imported = await subtle.importKey('raw', key, 'AES-CBC', false, ['encrypt']);
  const output = await subtle.encrypt({name: 'AES-CBC', iv: new Uint8Array(16)}, imported, data);
  requireValid(output.byteLength === 32, 'Unexpected ZZZ MHY AES result');
  return new Uint8Array(output, 0, 16);
}

async function gunzip(bytes, {maxOutputLength}, check) {
  requireValid(Number.isSafeInteger(maxOutputLength) && maxOutputLength > 0 && maxOutputLength <= MAX_FILE_BYTES,
    'Invalid ZZZ gzip bounds');
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  let size = 0, finished = false;
  const chunks = [];
  try {
    for (;;) {
      check();
      const {value, done} = await stream.read();
      if (done) { finished = true; break; }
      size += value.length;
      requireValid(size <= maxOutputLength, 'ZZZ gzip output exceeds limit');
      chunks.push(value);
    }
  } finally {
    if (!finished) await stream.cancel();
    stream.releaseLock();
  }
  const output = CatalogueBytes.alloc(size);
  let at = 0;
  for (const chunk of chunks) { output.set(chunk, at); at += chunk.length; }
  return output;
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

// Both file capabilities belong to one caller-owned staging operation. The
// caller validates and publishes pending outputs only after this completes.
export async function executeStage({mode, input, reader, operation, host, check}) {
  const {files, output} = stageRoles(mode, input);
  const written = new Set();
  let size = 0;
  check();
  await operation(mode, input, {
    xxHash64: reader.xxHash64,
    async unpackMhyFile(bytes, start) {
      check();
      const result = await reader.unpackMhyFile(bytes, start, check);
      check();
      return result;
    },
  }, {
    async read(name) {
      requireValid(files.has(name), 'ZZZ stage read leaves its selected data role');
      check();
      const bytes = await host.read(name);
      check();
      return CatalogueBytes.from(bytes);
    },
    async write(name, bytes, {exclusive}) {
      requireValid(output.has(name) && !written.has(name) && exclusive === !name.endsWith('-output.json') &&
        bytes instanceof Uint8Array && bytes.length > 0 && bytes.length <= MAX_FILE_BYTES,
      'ZZZ stage write leaves its selected data role');
      size += bytes.length;
      requireValid(size <= MAX_WRITES, 'ZZZ stage outputs exceed the bound');
      check();
      await host.write(name, bytes);
      check();
      written.add(name);
    },
    gunzip: (bytes, options) => gunzip(bytes, options, check),
    sha256,
  });
  requireValid(written.size === output.size, 'Incomplete ZZZ catalogue output');
  check();
}
