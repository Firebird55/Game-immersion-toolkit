import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const contract = Object.freeze({
  frontendOrigin: 'http://127.0.0.1:3000',
  apiBase: 'http://127.0.0.1:8766',
  websocketUrl: 'ws://127.0.0.1:8766/api/ws',
  browser: 'ordinary browser, existing selected profile',
});

function filesBelow(root, directory = root) {
  if (!existsSync(directory)) return [];
  if (lstatSync(directory).isSymbolicLink()) throw Error('Frontend evidence cannot follow symbolic links.');
  return readdirSync(directory, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name)).flatMap(entry => {
    const path = join(directory, entry.name);
    if (lstatSync(path).isSymbolicLink()) throw Error('Frontend evidence cannot follow symbolic links.');
    return entry.isDirectory() ? filesBelow(root, path) : entry.isFile() ? [relative(root, path).replaceAll('\\', '/')] : [];
  });
}

/** Inspect emitted bytes, without inventing an HTML shell or changing hosting. */
export function inspectStaticFrontend(root) {
  root = resolve(root);
  const client = join(root, 'dist/client'), server = join(root, 'dist/server');
  const clientFiles = filesBelow(client);
  const routeSources = filesBelow(join(root, 'app')).filter(name => /(^|\/)page\.[jt]sx?$/.test(name));
  const htmlFiles = clientFiles.filter(name => /\.html$/.test(name));
  const artifacts = [];
  for (const name of ['vite.config.ts', 'app/page.tsx', 'app/layout.tsx', 'dist/server/wrangler.json',
    'dist/server/index.js', 'dist/server/ssr/index.js', 'dist/client/vinext-client-entry-manifest.json']) {
    const path = join(root, name);
    if (existsSync(path)) {
      if (lstatSync(path).isSymbolicLink()) throw Error('Frontend evidence cannot follow symbolic links.');
      artifacts.push({name, sha256: sha256(readFileSync(path))});
    }
  }
  let sourceCommit = null;
  try { sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']}).trim(); } catch {}
  const buildPresent = clientFiles.length > 0 && existsSync(join(server, 'wrangler.json'));
  let wrangler = {};
  if (buildPresent) wrangler = JSON.parse(readFileSync(join(server, 'wrangler.json'), 'utf8'));
  const rootHtml = htmlFiles.includes('index.html');
  const serverEntry = typeof wrangler.main === 'string' && existsSync(join(server, wrangler.main));
  const ssrEntry = existsSync(join(server, 'ssr/index.js'));
  const reasons = [];
  if (!buildPresent) reasons.push('The canonical frontend build is unavailable; no output equivalence can be established.');
  if (buildPresent && !rootHtml) reasons.push('The emitted client tree has no index.html for the desktop / route. A file server cannot supply the current desktop document.');
  if (serverEntry) reasons.push('The emitted Wrangler configuration requires its server main entry.');
  if (ssrEntry) reasons.push('The emitted build contains a separate SSR entry; client assets alone do not establish hydration or navigation equivalence.');
  if (rootHtml) reasons.push('A root document alone does not prove route, hydration, worker, storage, extension or update equivalence.');
  const status = !buildPresent ? 'unavailable' : !rootHtml && serverEntry ? 'disproved-current-output' : 'incomplete';
  return {
    schema: 'proxy-r19-static-experiment-v1', sourceCommit, status,
    decision: 'retain-current-host', staticActivationAllowed: false, contract,
    facts: {routeSources, rootHtml, htmlFiles, serverEntry, ssrEntry, clientFileCount: clientFiles.length,
      clientTreeSha256: sha256(JSON.stringify(clientFiles.map(name => [name, sha256(readFileSync(join(client, name)))])))},
    artifacts, reasons,
    evidence: {
      emittedOutputInspection: buildPresent ? 'executed' : 'unavailable',
      staticBrowserEquivalence: 'not-run', ordinaryProfileContinuity: 'unchanged-unverified',
      localStorage: 'unchanged-unverified', indexedDB: 'unchanged-unverified', opfs: 'unchanged-unverified',
      extensionCompatibility: 'not-run', nativeWindows: 'unavailable',
      sourceFallback: 'Vinext/Wrangler remains the source host; it still requires development tools.',
    },
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const arguments_ = process.argv.slice(2);
  const option = name => { const index = arguments_.indexOf(name); if (index < 0) return null; if (!arguments_[index + 1] || arguments_[index + 1].startsWith('--')) throw Error(name + ' requires a value'); return arguments_[index + 1]; };
  const root = resolve(option('--root') ?? '.');
  const report = inspectStaticFrontend(root);
  const output = resolve(option('--output') ?? join(root, 'output/checks/r19-static-frontend.json'));
  mkdirSync(dirname(output), {recursive: true});
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({status: report.status, decision: report.decision, staticActivationAllowed: false, reasons: report.reasons}, null, 2));
  if (arguments_.includes('--require-static-equivalence')) process.exitCode = 2;
}
