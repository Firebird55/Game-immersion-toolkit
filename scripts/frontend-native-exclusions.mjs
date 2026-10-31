// Native image-optimizer packages are build-host inputs, never browser assets.
// Exclusion needs observed module/output evidence for every shipped build path.
import {createHash} from 'node:crypto';
import {existsSync, readFileSync, readdirSync, lstatSync, mkdirSync, writeFileSync} from 'node:fs';
import {resolve, relative, sep, dirname, join} from 'node:path';

export const POLICY = 'packaging/frontend-notices/native-build-inputs.json';
export const GUARD = 'scripts/frontend-native-exclusions.mjs';
export const EVIDENCE = 'notices/FRONTEND-BUILD-INPUTS.json';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const stable = value => JSON.stringify(value, (_key, item) => item && !Array.isArray(item) && typeof item === 'object'
  ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b, 'en'))) : item);
const safe = name => typeof name === 'string' && name && !name.startsWith('/') && !name.includes('\\') &&
  !name.includes(':') && name.split('/').every(part => part && part !== '.' && part !== '..');
const native = bytes => bytes.subarray(0, 2).equals(Buffer.from('MZ')) || bytes.subarray(0, 4).equals(Buffer.from([0x7f, 0x45, 0x4c, 0x46])) ||
  ['cffaedfe', 'cefaedfe', 'feedfacf', 'feedface', 'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca'].includes(bytes.subarray(0, 4).toString('hex'));

export function nativeBuildPolicy(root) {
  root = resolve(root);
  const path = join(root, POLICY);
  if (!existsSync(path)) return null;
  const policyBytes = readFileSync(path), policy = JSON.parse(policyBytes);
  const lockBytes = readFileSync(join(root, 'package-lock.json')), lock = JSON.parse(lockBytes);
  if (policy.schema !== 'toolkit-native-build-inputs-v1' || !Array.isArray(policy.packages) || !policy.packages.length) throw Error('Invalid native build-input policy');
  const names = new Set();
  for (const item of policy.packages) {
    if (!safe(item.package) || !item.package.startsWith('node_modules/@img/sharp-libvips-') || names.has(item.package)) throw Error('Invalid native build-input package');
    names.add(item.package);
    const locked = lock.packages?.[item.package];
    if (!locked || locked.version !== item.version || locked.integrity !== item.integrity) throw Error('Native build-input policy differs from exact lock');
  }
  return {...policy, policy_sha256: hash(policyBytes), lock_sha256: hash(lockBytes), guard_sha256: hash(readFileSync(join(root, GUARD)))};
}

function packageForModule(id, root, policy) {
  const normalized = id.replaceAll('\\', '/').split('?')[0];
  const base = resolve(root).replaceAll('\\', '/');
  return policy.packages.find(item => normalized === base + '/' + item.package || normalized.startsWith(base + '/' + item.package + '/') ||
    normalized.includes('/' + item.package + '/') || normalized === item.package || normalized.startsWith(item.package + '/'));
}

function identity(policy, kind) {
  return {schema: 'toolkit-browser-native-exclusion-v1', kind, policy_sha256: policy.policy_sha256,
    lock_sha256: policy.lock_sha256, guard_sha256: policy.guard_sha256, packages: policy.packages};
}

function postBuildAsset(name, bytes, kind) {
  if (/\.css$/.test(name)) {
    try { const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes); return text.includes('\0')?null:'stylesheet'; } catch { return null; }
  }
  if (/\.(?:woff2?|ttf)$/.test(name) && ['774f4646','774f4632','00010000','4f54544f'].includes(bytes.subarray(0,4).toString('hex'))) return 'font';
  if (kind!=='canonical') return null;
  const text=bytes.toString('utf8').trim();
  if (/\/_ssgManifest\.js$/.test(name) && text==='self.__SSG_MANIFEST=new Set;self.__SSG_MANIFEST_CB&&self.__SSG_MANIFEST_CB()') return 'empty-ssg-manifest';
  if (/\/_buildManifest\.js$/.test(name)) {
    const prefix='self.__BUILD_MANIFEST = ',suffix=';self.__BUILD_MANIFEST_CB && self.__BUILD_MANIFEST_CB()';
    if (!text.startsWith(prefix)||!text.endsWith(suffix)) return null;
    try {
      const value=JSON.parse(text.slice(prefix.length,-suffix.length));
      if (value && typeof value==='object' && !Array.isArray(value) && Array.isArray(value.sortedPages) && value.__rewrites) return 'json-build-manifest';
    } catch { /* Unknown executable output remains rejected. */ }
  }
  return null;
}

// Vinext writes compatibility manifests and moves SSR-generated styles/fonts
// after Rollup's client bundle hook. Only data-only formats and the exact
// manifest wrappers may supplement the observed executable chunk inventory.
export function sealBrowserNativeEvidence(proof, payloads) {
  if (!proof?.outputs) throw Error('Missing observed browser bundle');
  const postbuild_outputs={};
  for (const [name, value] of payloads) {
    const bytes=Buffer.from(value),sha256=hash(bytes);
    if (Object.values(proof.outputs).some(item=>item.sha256===sha256&&item.bytes===bytes.length)) continue;
    const format=postBuildAsset(name,bytes,proof.kind);
    if (!format || native(bytes)) throw Error('Unobserved executable browser output: '+name);
    postbuild_outputs[name]={sha256,bytes:bytes.length,format};
  }
  return {...proof,postbuild_outputs};
}

export function browserNativeGuard({root = process.cwd(), kind = '', receipt = '', onEvidence = null} = {}) {
  root = resolve(root);
  const policy = nativeBuildPolicy(root);
  if (!policy || !['canonical', 'desktop', 'mobile'].includes(kind)) throw Error('Missing browser native build-input policy');
  const modules = new Set();
  const observe = id => {
    if (packageForModule(id, root, policy)) throw Error('Native build-only dependency entered the browser module graph');
    const path = id.replaceAll('\\', '/').split('?')[0], base = root.replaceAll('\\', '/') + '/';
    if (path.startsWith(base)) modules.add(path.slice(base.length));
  };
  return {
    name: 'toolkit-browser-native-input-guard', enforce: 'pre', apply: 'build',
    applyToEnvironment: environment => environment.name === 'client',
    buildStart() { modules.clear(); },
    load(id) {
      observe(id);
      return null;
    },
    moduleParsed(info) { observe(info.id); },
    generateBundle: {order: 'post', handler(_options, bundle) {
      const outputs = {};
      for (const [name, item] of Object.entries(bundle)) {
        if (!safe(name)) throw Error('Unsafe browser build evidence output');
        if (item.type === 'chunk') for (const id of Object.keys(item.modules)) {
          if (packageForModule(id, root, policy)) throw Error('Native build-only dependency entered an emitted browser chunk');
        }
        const bytes = Buffer.from(item.type === 'chunk' ? item.code : item.source);
        if (native(bytes) || /\.(?:node|dll|exe|dylib|so)(?:\.|$)/i.test(name)) throw Error('Native binary entered browser assets');
        outputs[name] = {sha256: hash(bytes), bytes: bytes.length};
      }
      const evidence = {...identity(policy, kind), modules: [...modules].sort(), outputs};
      if (receipt) { mkdirSync(dirname(receipt), {recursive: true}); writeFileSync(receipt, JSON.stringify(evidence) + '\n'); }
      onEvidence?.(evidence);
    }},
  };
}

export function verifyBrowserNativeEvidence({root = process.cwd(), payloads, proofs}) {
  root = resolve(root);
  const policy = nativeBuildPolicy(root);
  if (!policy || !proofs || Object.keys(proofs).sort().join(',') !== 'canonical,desktop,mobile') throw Error('All browser build paths need native exclusion evidence');
  for (const kind of ['canonical', 'desktop', 'mobile']) {
    const proof = proofs[kind];
    for (const [key, expected] of Object.entries(identity(policy, kind))) if (stable(proof?.[key]) !== stable(expected)) throw Error('Browser native exclusion identity changed');
    if (!Array.isArray(proof.modules) || !proof.modules.length || !proof.outputs || !Object.keys(proof.outputs).length) throw Error('Empty browser build evidence');
    if (proof.modules.some(name => !safe(name) || packageForModule(name, root, policy))) throw Error('Excluded native input appears in browser evidence');
    for (const [name, output] of Object.entries(proof.outputs)) if (!safe(name) || !/^[a-f0-9]{64}$/.test(output.sha256) || !Number.isSafeInteger(output.bytes) || output.bytes < 0) throw Error('Invalid browser output evidence');
  }
  const coverage = {canonical: 0, desktop: 0, mobile: 0};
  for (const [name, value] of payloads) {
    if (!safe(name)) throw Error('Unsafe browser payload');
    const bytes = Buffer.from(value);
    if (native(bytes) || /\.(?:node|dll|exe|dylib|so)(?:\.|$)/i.test(name)) throw Error('Native binary entered browser payload');
    const kind = name.startsWith('_next/static/') ? 'canonical' : name.startsWith('assets/') ? 'desktop' :
      /^mobile-capture\/companion\.(?:js|css)$/.test(name) ? 'mobile' : null;
    if (!kind) continue;
    const expected = {sha256: hash(bytes), bytes: bytes.length};
    const bundled=Object.values(proofs[kind].outputs).some(item => item.sha256 === expected.sha256 && item.bytes === expected.bytes);
    const post=proofs[kind].postbuild_outputs?.[name];
    if (!bundled && !(post && typeof post.format==='string' && post.format && post.sha256===expected.sha256 && post.bytes===expected.bytes && post.format===postBuildAsset(name,bytes,kind))) throw Error('Shipped browser output has no matching native exclusion evidence: ' + name);
    coverage[kind]++;
  }
  if (Object.values(coverage).some(count => count === 0)) throw Error('Browser native exclusion coverage is incomplete');
  return {schema: 'toolkit-frontend-native-exclusions-v1', packages: policy.packages, coverage, proofs};
}

export function readBrowserNativeExclusions(root, frontendRoot) {
  const document = JSON.parse(readFileSync(join(frontendRoot, EVIDENCE), 'utf8'));
  if (document.schema !== 'toolkit-frontend-native-exclusions-v1') throw Error('Unknown frontend exclusion evidence');
  const payloads = new Map();
  function walk(directory) {
    for (const entry of readdirSync(directory, {withFileTypes: true})) {
      const path = join(directory, entry.name);
      if (lstatSync(path).isSymbolicLink()) throw Error('Frontend exclusion evidence cannot traverse links');
      if (entry.isDirectory()) walk(path);
      else if (entry.isFile()) payloads.set(relative(frontendRoot, path).split(sep).join('/'), readFileSync(path));
    }
  }
  walk(frontendRoot);
  return verifyBrowserNativeEvidence({root, payloads, proofs: document.proofs});
}
