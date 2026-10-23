import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {ocrAssets} from './mobile-assets.mjs';

import {buildBrowserReader} from './build-browser-reader.mjs';
await buildBrowserReader();
const root = new URL('../', import.meta.url);
const git = (...args) => execFileSync('git', args, { cwd: fileURLToPath(root), encoding: 'utf8' }).trim();
const commit = process.env.GITHUB_SHA || git('rev-parse', 'HEAD');
const branch = process.env.GITHUB_REF_NAME || git('branch', '--show-current');
if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error('Preview requires a full Git commit SHA.');
const builtAt = new Date().toISOString();
const destination = new URL('output/mobile-preview/', root);
mkdirSync(destination, { recursive: true });
const assets = new Map();
function asset(name, content) {
  const credentials = [/lx_[A-Za-z0-9]{40,}/, /gh[pousr]_[A-Za-z0-9]{30,}/, /github_pat_[A-Za-z0-9_]{30,}/, /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/, /AKIA[0-9A-Z]{16}/];
  if (credentials.some(pattern => pattern.test(content))) throw new Error(`Potential credential in preview asset: ${name}`);
  const ext = name.slice(name.lastIndexOf('.'));
  const stem = name.slice(0, -ext.length);
  const hashedName = `${stem}.${createHash('sha256').update(content).digest('hex').slice(0, 16)}${ext}`;
  writeFileSync(new URL(hashedName, destination), content);
  assets.set(name, hashedName);
  return hashedName;
}
const source = name => readFileSync(new URL(`public/mobile-capture/${name}`, root), 'utf8');
for(const name of ['interface-copy.mjs','interface-language.mjs','ocr-models.json','caption-confirmation.mjs','games-data.json','games.css','games.mjs','core.mjs','recovery-config.json','relay.mjs','qr-pairing.mjs','qr-render.mjs','qr-ui.mjs','library.mjs','storage.mjs','ocr-packs.mjs','library-worker.mjs','ocr-pipeline.mjs','frame-source.mjs','vdo-source.mjs','receiver-source.mjs','transcript-channel.mjs','pc-provider.mjs','vault.mjs','pc-connection.mjs','capture.js','mobile-ui.mjs','companion.js','companion.css','style.css','icon.svg','icon.png','manifest.webmanifest']){
 let content=name.endsWith('.png')?readFileSync(new URL('public/mobile-capture/'+name,root)):source(name);
 if(name==='games-data.json')content=JSON.stringify({...JSON.parse(content),releaseVersion:JSON.parse(readFileSync(new URL('package.json',root),'utf8')).version})+'\n';
 if(typeof content==='string')for(const [original,hashed] of assets)content=content.replaceAll('./'+original,'./'+hashed);asset(name,content);
}
const ocr=ocrAssets();
const escape = value => value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
let html = source('index.html').replace('<html lang="en">', `<html lang="en" data-build-commit="${commit}" data-build-branch="${escape(branch)}" data-build-time="${builtAt}">`);
html=html.replace(' http://127.0.0.1:8766 ws://127.0.0.1:8766','');
if (!html.includes(`data-build-commit="${commit}"`)) throw new Error('Preview HTML must expose its build version.');
for (const [name, hashedName] of assets) html = html.replaceAll(`./${name}`, `./${hashedName}`);
writeFileSync(new URL('index.html', destination), html);
let gamesHtml=source('games.html').replace('<html lang="en">',`<html lang="en" data-build-commit="${commit}">`);
for(const [name,hashedName]of assets)gamesHtml=gamesHtml.replaceAll('./'+name,'./'+hashedName);
writeFileSync(new URL('games.html',destination),gamesHtml);
writeFileSync(new URL('build.json', destination), JSON.stringify({ format: 'proxy-mobile-preview-v1', commit, branch, builtAt }) + '\n');
writeFileSync(new URL('.nojekyll', destination), '');
// Only these generated files are eligible for publication. Stale hashed files
// from prior local builds stay outside the final publication directory.
const publish = new URL('output/mobile-preview-publish/', root);
mkdirSync(publish, { recursive: true });
const files = ['index.html', 'games.html', 'build.json', '.nojekyll', 'sw.js', ...assets.values(), ...ocr.keys()];
const cacheName='proxy-mobile-'+createHash('sha256').update([html,gamesHtml,...assets.values(),...[...ocr].map(([name,data])=>name+':'+createHash('sha256').update(data).digest('hex'))].join('\n')).digest('hex').slice(0,16);
writeFileSync(new URL('sw.js',destination),`const NAME=${JSON.stringify(cacheName)},FILES=${JSON.stringify(files.filter(n=>n!=='sw.js'))};
const ROOT=new URL('./',self.location),ALLOW=new Set(FILES.map(n=>new URL(n,ROOT).href)),NAMES=new Set(${JSON.stringify([...assets.keys(),...ocr.keys()])});
self.addEventListener('install',event=>event.waitUntil(caches.open(NAME).then(cache=>cache.addAll(FILES.filter(n=>!n.startsWith('pairing/')&&!/^(pc-connection|pc-provider|qr-|relay[.]|recovery-config[.]|core[.])/.test(n)&&(!n.startsWith('ocr/')||n==='ocr/tesseract.esm.min.js'||n==='ocr/opencc.mjs'))))));
self.addEventListener('activate',event=>event.waitUntil((async()=>{const clients=await self.clients.matchAll({includeUncontrolled:true});if(clients.length<=1){const names=(await caches.keys()).filter(n=>n.startsWith('proxy-mobile-'));const keep=new Set([NAME,...names.filter(n=>n!==NAME).slice(-1)]);await Promise.all(names.filter(n=>!keep.has(n)).map(n=>caches.delete(n)));}await self.clients.claim();})()));
self.addEventListener('message',event=>{if(event.data==='activate-update')self.skipWaiting();});
self.addEventListener('fetch',event=>{if(event.request.method!=='GET'||event.request.headers.has('Authorization'))return;const url=new URL(event.request.url);if(event.request.mode==='navigate'&&url.origin===ROOT.origin&&url.pathname.startsWith(ROOT.pathname)){const page=url.pathname===new URL('games.html',ROOT).pathname?'games.html':'index.html';event.respondWith(fetch(event.request).catch(()=>caches.open(NAME).then(cache=>cache.match(new URL(page,ROOT).href))));return;}const prior=url.origin===ROOT.origin&&url.pathname.startsWith(ROOT.pathname)&&!url.search&&NAMES.has(url.pathname.slice(ROOT.pathname.length).replace(/\\.[a-f0-9]{16}(?=\\.[^.]+$)/,''));if(!ALLOW.has(url.href)&&!prior)return;event.respondWith(caches.open(NAME).then(async cache=>{const saved=await cache.match(event.request)??await caches.match(event.request);if(saved)return saved;const response=await fetch(event.request);if(response.ok)await cache.put(event.request,response.clone());return response;}));});
`);
// The publisher must use a fresh directory rather than accumulate older assets.
// No recursive deletion: version each package by its content and build time.
const packageDir = new URL(`${commit}-${Date.now()}/`, publish);
mkdirSync(packageDir);
for (const name of files){mkdirSync(new URL(name.includes('/')?name.slice(0,name.lastIndexOf('/')+1):'./',packageDir),{recursive:true});writeFileSync(new URL(name, packageDir),ocr.get(name)??readFileSync(new URL(name, destination)));}
const path = fileURLToPath(packageDir);
if (process.env.GITHUB_OUTPUT) {
  const { appendFileSync } = await import('node:fs');
  appendFileSync(process.env.GITHUB_OUTPUT, `directory=${path}\n`);
}
console.log(`Mobile preview: ${path}`);
console.log(`Build ${commit.slice(0, 8)} · ${branch} · ${files.length} public files`);
