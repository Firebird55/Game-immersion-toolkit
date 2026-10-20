import {execFileSync} from 'node:child_process';
import {appendFileSync, mkdirSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

// Unknown inputs deliberately select the comprehensive gate.
export function selectChecks(files, full = false) {
  const selected = new Set(full ? ['full'] : []);
  for (const file of files) {
    if (/^(docs\/.*|[^/]+)\.(md|html)$/.test(file) || /^\.github\/(ISSUE_TEMPLATE\/|dependabot\.yml)/.test(file)) selected.add('docs');
    else if (/^backend\/|^tests\/.*\.py$/.test(file)) selected.add('python');
    else if (/^(app|components|hooks|lib|styles)\//.test(file)) selected.add('desktop');
    else if (/^(mobile|public\/mobile-capture|services)\//.test(file) || /^scripts\/(mobile-|companion-e2e|build-mobile|build-browser|prepare-mobile|serve-mobile|webrtc)/.test(file) || /^tests\/mobile-/.test(file)) selected.add('mobile');
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
    for(const script of ['browser-e2e','setup-e2e','language-account-e2e','update-companion-e2e'])
      run(process.execPath,[`scripts/${script}.mjs`]);
    run('npm',['run','mobile:check']);
  } else {
    if(checks.includes('python')) run('npm',['run','test:python']);
    if(checks.includes('desktop')) {
      run('npm',['run','typecheck']);
      run('npm',['run','test']);
      run('npm',['run','build']);
      run(process.execPath,['scripts/language-account-e2e.mjs']);
    }
    if(checks.includes('mobile')) {
      run('npm',['test']);
      run('npm',['run','mobile:build']);
      for(const script of ['companion-e2e','mobile-games-e2e'])
        run(process.execPath,[`scripts/${script}.mjs`]);
    }
  }
  run(process.execPath,['scripts/check-docs.mjs']);
  run('npm',['run','audit:public']);
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const baseIndex=process.argv.indexOf('--base');
  const base=baseIndex>=0?process.argv[baseIndex+1]:process.env.CHECK_BASE;
  const checks=selectChecks(changedFiles(base),process.argv.includes('--full'));
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
