import {execFileSync} from 'node:child_process';
import {appendFileSync, mkdirSync, writeFileSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {runBrowserSuite} from './check-browser-suite.mjs';

// Unknown inputs deliberately select the comprehensive gate.
export function selectChecks(files, full = false) {
  const selected = new Set(full ? ['full'] : []);
  for (const file of files) {
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
export function executeChecks(checks) {
  if(checks.includes('full')) {
    run('npm',['run','check']);
    if(process.env.CHECK_SPLIT_BROWSER_TESTS !== 'true') runBrowserSuite('all');
  } else {
    if(checks.includes('python')) run('npm',['run','test:python']);
    if(checks.includes('desktop'))run('npm',['run','typecheck']);
    if(checks.includes('desktop')||checks.includes('mobile'))run('npm',['test']);
    if(checks.includes('desktop')) {
      run('npm',['run','build']);
      run(process.execPath,['scripts/language-account-e2e.mjs']);
    }
    if(checks.includes('mobile')) {
      run('npm',['run','mobile:build']);
      for(const script of ['companion-e2e','mobile-games-e2e','ocr-packs-e2e'])
        run(process.execPath,[`scripts/${script}.mjs`]);
    }
  }
  run(process.execPath,['scripts/check-docs.mjs']);
  run('npm',['run','audit:public']);
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const baseIndex=process.argv.indexOf('--base');
  const base=baseIndex>=0?process.argv[baseIndex+1]:process.env.CHECK_BASE;
  // An atomic release push has a separate tag run for this exact commit.
  // The main run keeps documentation/audit gates but delegates comprehensive work.
  const releaseTag='v'+JSON.parse(readFileSync('package.json','utf8')).version;
  const delegated=process.env.GITHUB_EVENT_NAME==='push'&&process.env.GITHUB_REF==='refs/heads/main'
    &&git('tag','--points-at','HEAD').split('\n').includes(releaseTag);
  const checks=delegated?[]:process.argv.includes('--full')?['full']:selectChecks(changedFiles(base));
  if(delegated)console.log('Comprehensive checks run on '+releaseTag+' for this same commit.');
  console.log('Selected checks: '+(checks.join(', ')||'publication only'));
  if(process.env.GITHUB_OUTPUT) for(const [key,value] of Object.entries({
    checks:JSON.stringify(checks),dependencies:checks.some(x=>x!=='docs'),
    python:checks.some(x=>x==='full'||x==='python'),browsers:checks.some(x=>['full','desktop','mobile'].includes(x)),
    full:checks.includes('full')
  })) appendFileSync(process.env.GITHUB_OUTPUT,`${key}=${value}\n`);
  if(!process.argv.includes('--plan')) {
    const start=Date.now();executeChecks(checks);
    mkdirSync('output/checks',{recursive:true});
    writeFileSync('output/checks/latest.json',JSON.stringify({checks,seconds:(Date.now()-start)/1000},null,2));
  }
}
