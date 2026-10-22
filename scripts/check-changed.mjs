import {execFileSync} from 'node:child_process';
import {appendFileSync, mkdirSync, writeFileSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {browserSuites} from './check-browser-suite.mjs';

// Unknown inputs deliberately select the comprehensive gate.
export function selectChecks(files, full = false) {
  const selected = new Set(full ? ['full'] : []);
  for (const file of files) {
    if (['scripts/check-changed.mjs','scripts/check-browser-suite.mjs','tests/check-selection.test.mjs'].includes(file)) { selected.add('selector'); continue; }
    if (['backend/api.py','backend/state_version.py','app/companion.tsx','app/language-setup.tsx','app/state-sync.ts','scripts/ui-state-e2e.mjs','scripts/ui-state-browser-server.py','tests/state-sync.test.mjs'].includes(file)) { selected.add('python'); selected.add('desktop'); continue; }
    if (['scripts/update-companion.ps1','scripts/companion-runtime.ps1'].includes(file)) { selected.add('python'); selected.add('windows'); continue; }
    if (/^scripts\/(start-companion|companion-process-identity-e2e).*\.ps1$/.test(file)) { selected.add('windows'); continue; }
    if(file==='lib/interface-language.tsx'){selected.add('desktop');selected.add('mobile');continue;}
    if(file==='public/mobile-capture/games-data.json'){selected.add('mobile');selected.add('python');selected.add('docs');continue;}
    if(['scripts/generate-language-docs.mjs','scripts/check-docs.mjs'].includes(file)){selected.add('docs');continue;}
    if (/^(docs\/.*|[^/]+)\.(md|html)$/.test(file) || /^\.github\/(ISSUE_TEMPLATE\/|dependabot\.yml)/.test(file)) selected.add('docs');
    else if (/^backend\/|^tests\/.*\.py$/.test(file)) selected.add('python');
    else if (/^(app|components|hooks|lib|styles)\//.test(file)) selected.add('desktop');
    else if (/^(mobile|public\/mobile-capture|services)\//.test(file) || /^scripts\/(ocr-|mobile-|companion-e2e|build-mobile|build-browser|prepare-mobile|serve-mobile|webrtc)/.test(file) || /^tests\/mobile-/.test(file)) selected.add('mobile');
    else selected.add('full');
  }
  return selected.has('full') ? ['full'] : [...selected].sort();
}
function git(...args) { return execFileSync('git', args, {encoding:'utf8'}).trim(); }
export function changedFiles(base) {
  const files = new Set();
  if (base) {
    try { for (const file of git('diff','--name-only',base,'HEAD').split('\n')) if(file) files.add(file); }
    catch { files.add('__unknown_base__'); }
  }
  for (const args of [['diff','--name-only','HEAD'],['ls-files','--others','--exclude-standard']])
    for (const file of git(...args).split('\n')) if(file) files.add(file);
  return [...files];
}
const run = (command,args) => execFileSync(command,args,{stdio:'inherit',shell:process.platform==='win32'&&command==='npm'});
// These are executable scenarios, not just categories. Source dependencies below
// augment the normal consumer gates; unknown files still require the full gate.
export function scenarioPlan(files, checks = selectChecks(files)) {
  if (checks.includes('full')) return {browser: Object.values(browserSuites).flat(), windows: ['companion-process-identity-e2e', 'setup-e2e', 'update-companion-e2e']};
  const browser = new Set(), windows = new Set();
  if (checks.includes('desktop')) browser.add('language-account-e2e');
  if (checks.includes('mobile')) for (const name of ['companion-e2e','mobile-reader-layout-e2e','mobile-games-e2e','ocr-packs-e2e']) browser.add(name);
  if (files.some(file => ['backend/api.py','backend/state_version.py'].includes(file))) for (const name of ['setup-e2e','local-access-e2e']) browser.add(name);
  if (files.some(file => ['backend/api.py','backend/state_version.py','scripts/update-companion.ps1','scripts/companion-runtime.ps1'].includes(file))) windows.add('update-companion-e2e');
  if (files.some(file => ['backend/api.py','backend/state_version.py','app/companion.tsx','app/language-setup.tsx','app/state-sync.ts','scripts/ui-state-e2e.mjs','scripts/ui-state-browser-server.py','tests/state-sync.test.mjs'].includes(file))) browser.add('ui-state-e2e');
  if (checks.includes('windows')) windows.add('companion-process-identity-e2e');
  return {browser: [...browser].sort(), windows: [...windows].sort()};
}
export function executeChecks(checks, {scenarios = scenarioPlan([], checks), runCommand = run,
  platform = process.platform, splitBrowsers = process.env.CHECK_SPLIT_BROWSER_TESTS === 'true'} = {}) {
  if(checks.includes('full')) runCommand('npm',['run','check']);
  else {
    if(checks.includes('python')) runCommand('npm',['run','test:python']);
    if(checks.includes('desktop')) runCommand('npm',['run','typecheck']);
    if(checks.some(x => ['desktop','mobile','selector'].includes(x))) runCommand('npm',['test']);
    if(checks.includes('desktop')) runCommand('npm',['run','build']);
    if(checks.includes('mobile')) runCommand('npm',['run','mobile:build']);
  }
  if (!splitBrowsers) for (const script of scenarios.browser) runCommand(process.execPath,[`scripts/${script}.mjs`]);
  const unavailable = [];
  for (const script of scenarios.windows) {
    if (platform === 'win32') {
      if (script === 'update-companion-e2e') runCommand(process.execPath,[`scripts/${script}.mjs`]);
      else runCommand('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',`scripts/${script}.ps1`,'-VerifyBaseline']);
    }
    else { unavailable.push(script); console.log('Requires hosted Windows validation: ' + script); }
  }
  runCommand(process.execPath,['scripts/check-docs.mjs']);
  runCommand('npm',['run','audit:public']);
  return {unavailable};
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const baseIndex=process.argv.indexOf('--base');
  const base=baseIndex>=0?process.argv[baseIndex+1]:process.env.CHECK_BASE;
  // An atomic release push has a separate tag run for this exact commit.
  // The main run keeps documentation/audit gates but delegates comprehensive work.
  const releaseTag='v'+JSON.parse(readFileSync('package.json','utf8')).version;
  const delegated=process.env.GITHUB_EVENT_NAME==='push'&&process.env.GITHUB_REF==='refs/heads/main'
    &&git('tag','--points-at','HEAD').split('\n').includes(releaseTag);
  const files=changedFiles(base);
  const checks=delegated?[]:process.argv.includes('--full')?['full']:selectChecks(files);
  const scenarios=delegated?{browser:[],windows:[]}:scenarioPlan(files,checks);
  console.log('Required scenarios: '+JSON.stringify(scenarios));
  if(delegated)console.log('Comprehensive checks run on '+releaseTag+' for this same commit.');
  console.log('Selected checks: '+(checks.join(', ')||'publication only'));
  if(process.env.GITHUB_OUTPUT) for(const [key,value] of Object.entries({
    checks:JSON.stringify(checks),dependencies:checks.some(x=>x!=='docs'),
    python:checks.some(x=>x==='full'||x==='python'),browsers:scenarios.browser.length>0,
    full:checks.includes('full')
  })) appendFileSync(process.env.GITHUB_OUTPUT,`${key}=${value}\n`);
  if(!process.argv.includes('--plan')) {
    const start=Date.now();const result=executeChecks(checks,{scenarios});
    mkdirSync('output/checks',{recursive:true});
    writeFileSync('output/checks/latest.json',JSON.stringify({checks,scenarios,...result,commit:git('rev-parse','HEAD'),seconds:(Date.now()-start)/1000},null,2));
  }
}
