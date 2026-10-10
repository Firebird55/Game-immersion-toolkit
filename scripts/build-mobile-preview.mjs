import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

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
const core = asset('core.mjs', source('core.mjs'));
asset('capture.js', source('capture.js').replace("'./core.mjs'", `'./${core}'`));
asset('style.css', source('style.css'));
const escape = value => value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
let html = source('index.html').replace('<html lang="en">', `<html lang="en" data-build-commit="${commit}" data-build-branch="${escape(branch)}" data-build-time="${builtAt}">`);
if (!html.includes(`data-build-commit="${commit}"`)) throw new Error('Preview HTML must expose its build version.');
for (const [name, hashedName] of assets) html = html.replaceAll(`./${name}`, `./${hashedName}`);
writeFileSync(new URL('index.html', destination), html);
writeFileSync(new URL('build.json', destination), JSON.stringify({ format: 'proxy-mobile-preview-v1', commit, branch, builtAt }) + '\n');
writeFileSync(new URL('.nojekyll', destination), '');
// Only these generated files are eligible for publication. Stale hashed files
// from prior local builds stay outside the final publication directory.
const publish = new URL('output/mobile-preview-publish/', root);
mkdirSync(publish, { recursive: true });
const files = ['index.html', 'build.json', '.nojekyll', ...assets.values()];
// The publisher must use a fresh directory rather than accumulate older assets.
// No recursive deletion: version each package by its content and build time.
const packageDir = new URL(`${commit}-${Date.now()}/`, publish);
mkdirSync(packageDir);
for (const name of files) writeFileSync(new URL(name, packageDir), readFileSync(new URL(name, destination)));
const path = fileURLToPath(packageDir);
if (process.env.GITHUB_OUTPUT) {
  const { appendFileSync } = await import('node:fs');
  appendFileSync(process.env.GITHUB_OUTPUT, `directory=${path}\n`);
}
console.log(`Mobile preview: ${path}`);
console.log(`Build ${commit.slice(0, 8)} · ${branch} · ${files.length} public files`);
