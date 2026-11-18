// Runs in an app-owned Blob worker. Only the signed app supplies software.
const modules = {
  'catalogue-bytes.mjs': [],
  'catalogue-runtime.mjs': ['catalogue-bytes.mjs'],
  'scene-catalog.mjs': [],
  'comic-links.mjs': [],
  'cinematic-links.mjs': [],
  'zzz-dialogue.mjs': [],
  'zzz-presentation-config.mjs': ['zzz-dialogue.mjs', 'cinematic-links.mjs'],
  'zzz-cinema-timeline.mjs': ['cinematic-links.mjs'],
  'zzz-publisher-dialogue.mjs': ['scene-catalog.mjs', 'comic-links.mjs', 'zzz-dialogue.mjs',
    'zzz-presentation-config.mjs', 'zzz-cinema-timeline.mjs'],
  'mhy-format.mjs': [],
  'oodle-adapter.mjs': [],
  'oodle-factory.mjs': [],
  'xxhash.mjs': [],
};
const pins = {
  'oodle-factory.mjs': 'fda7d49be8ee8f45cf7de2c7411b36627b6c5f358397f86900744f79964aca27',
  'xxhash.mjs': 'e3be9143c10d60a015448de1ceef383b8f2ea1fd2773a5a5c69973ed52d8325a',
  'mhy-format.mjs': '928260ca49f476316e2a45b9004ea68ddffd1963923e0e854e51f4dce7db4c4f',
};
const hex = /^[a-f0-9]{64}$/;
const utf8 = new TextDecoder('utf-8', {fatal: true});

function verify(condition) {
  if (!condition) throw Error('Invalid ZZZ catalogue software');
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function loadCatalogueSoftware(files, manifestBytes, identity) {
  verify(hex.test(identity) && manifestBytes instanceof Uint8Array && manifestBytes.length <= 16384 &&
    await sha256(manifestBytes) === identity);
  const manifest = JSON.parse(utf8.decode(manifestBytes));
  verify(manifest.schema === 'toolkit-android-zzz-catalogue-assets-v1' && Object.keys(files).length === Object.keys(modules).length &&
    Object.keys(manifest.modules).length === Object.keys(modules).length);
  const urls = new Map();
  try {
    for (const [name, dependencies] of Object.entries(modules)) {
      const bytes = files[name], receipt = manifest.modules[name];
      verify(bytes instanceof Uint8Array && bytes.length > 0 && bytes.length <= 128 * 1024 &&
        bytes.length === receipt.bytes && hex.test(receipt.sha256) &&
        (!Object.hasOwn(pins, name) || receipt.sha256 === pins[name]) && await sha256(bytes) === receipt.sha256);
      const found = [];
      const source = utf8.decode(bytes).replace(/^import (.+?) from ['"]\.\/([a-z0-9.-]+)['"];$/gm,
        (_match, imports, dependency) => {
          verify(urls.has(dependency));
          found.push(dependency);
          return 'import ' + imports + ' from ' + JSON.stringify(urls.get(dependency)) + ';';
        });
      verify(found.length === dependencies.length && dependencies.every(dependency => found.includes(dependency)));
      urls.set(name, URL.createObjectURL(new Blob([source], {type: 'text/javascript'})));
    }
    const load = name => import(urls.get(name));
    const {CatalogueBytes} = await load('catalogue-bytes.mjs');
    globalThis.Buffer = CatalogueBytes;
    const {runPublisherOperation} = await load('zzz-publisher-dialogue.mjs');
    const {executeStage, aes128EncryptBlock} = await load('catalogue-runtime.mjs');
    const {createMhyReader} = await load('mhy-format.mjs');
    const {createDecoder} = await load('oodle-adapter.mjs');
    const {default: oodle} = await load('oodle-factory.mjs');
    const {default: xxhash} = await load('xxhash.mjs');
    const decompressOodle = await createDecoder(oodle);
    const {h64: xxHash64} = await xxhash();
    verify(xxHash64('') === 0xef46db3751d8e999n &&
      decompressOodle(Uint8Array.of(0x8c, 6, 7, 255, 255, 65), 65536).every(byte => byte === 65));
    const reader = {xxHash64, unpackMhyFile: createMhyReader({decompressOodle, aes128EncryptBlock})};
    return {reader, operation: runPublisherOperation, executeStage};
  } finally {
    for (const url of urls.values()) URL.revokeObjectURL(url);
  }
}

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope) {
  let pending = null;
  let stopped = false;
  let running = false;
  let next = 0;
  const check = () => { if (stopped) throw Error('ZZZ stage cancelled'); };

  function request(type, name, bytes) {
    check();
    if (pending) throw Error('Unexpected concurrent ZZZ stage I/O');
    const id = ++next;
    return new Promise((resolve, reject) => {
      pending = {id, resolve, reject};
      if (bytes) {
        const copy = new Uint8Array(bytes);
        self.postMessage({type, id, name, bytes: copy}, [copy.buffer]);
      } else self.postMessage({type, id, name});
    });
  }

  self.onmessage = async ({data}) => {
    if (data?.type === 'reply' && pending && data.id === pending.id) {
      const waiter = pending;
      pending = null;
      if (data.error) waiter.reject(Error('ZZZ stage I/O failed'));
      else waiter.resolve(data.bytes);
      return;
    }
    if (data?.type === 'cancel') {
      stopped = true;
      if (pending) pending.reject(Error('ZZZ stage cancelled'));
      return;
    }
    if (running || data?.type !== 'start') return;
    running = true;
    try {
      const {files, manifest, identity, mode, input} = data;
      const runtime = await loadCatalogueSoftware(files, manifest, identity);
      self.postMessage({type: 'started', identity});
      await runtime.executeStage({mode, input, reader: runtime.reader, operation: runtime.operation, check,
        host: {read: name => request('read', name), write: (name, bytes) => request('write', name, bytes)}});
      self.postMessage({type: 'complete'});
    } catch {
      self.postMessage({type: 'failed'});
    }
  };
}
