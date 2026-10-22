import test from 'node:test';
import assert from 'node:assert/strict';
import {selectChecks,scenarioPlan,executeChecks} from '../scripts/check-changed.mjs';
import {browserSuites,runBrowserSuite} from '../scripts/check-browser-suite.mjs';
test('documentation avoids application builds',()=>assert.deepEqual(selectChecks(['README.md','docs/beyond-support.md']),['docs']));
test('backend and frontend changes combine their gates',()=>assert.deepEqual(selectChecks(['backend/capture.py','app/companion.tsx']),['desktop','python']));
test('unknown and dependency changes require the full gate',()=>{
  for(const file of ['package-lock.json','.github/workflows/ci-release.yml','new-system/file.ts'])assert.deepEqual(selectChecks([file]),['full']);
});
test('explicit release gate is full even without changes',()=>assert.deepEqual(selectChecks([],true),['full']));
test('isolated browser suites retain every comprehensive check exactly once',()=>{
 const scripts=Object.values(browserSuites).flat();
 assert.equal(new Set(scripts).size,scripts.length);
 assert.deepEqual([...scripts].sort(),['browser-e2e','setup-e2e','language-account-e2e','ui-state-e2e','setup-build-e2e','local-access-e2e','companion-e2e','mobile-reader-layout-e2e','mobile-capture-e2e','mobile-recovery-e2e','mobile-library-e2e','mobile-update-e2e','mobile-layout-e2e','mobile-games-e2e','ocr-packs-e2e'].sort());
 assert.throws(()=>runBrowserSuite('typo'),/Unknown browser suite/);
});

test('shared interface and support catalog select their consumer checks',()=>{
 assert.deepEqual(selectChecks(['lib/interface-language.tsx']),['desktop','mobile']);
 assert.deepEqual(selectChecks(['public/mobile-capture/games-data.json']),['docs','mobile','python']);
 assert.deepEqual(selectChecks(['scripts/generate-language-docs.mjs']),['docs']);
});


test('API changes run actual backend/browser contract scenarios',()=>{
 const files=['backend/api.py'], checks=selectChecks(files), scenarios=scenarioPlan(files,checks);
 assert.ok(checks.includes('python'));
 for(const name of ['language-account-e2e','local-access-e2e','setup-e2e']) assert.ok(scenarios.browser.includes(name));
 const commands=[];
 executeChecks(checks,{scenarios,runCommand:(command,args)=>commands.push([command,...args]),platform:'darwin',splitBrowsers:false});
 for(const name of scenarios.browser) assert.ok(commands.some(command=>command.includes(`scripts/${name}.mjs`)));
});
test('mobile reader source includes reader layout and Shadow DOM regression execution',()=>{
 const files=['mobile/companion.jsx'],checks=selectChecks(files),scenarios=scenarioPlan(files,checks),commands=[];
 executeChecks(checks,{scenarios,runCommand:(_command,args)=>commands.push(args),platform:'darwin',splitBrowsers:false});
 assert.ok(commands.some(args=>args.includes('scripts/mobile-reader-layout-e2e.mjs')));
});
test('process lifecycle sources require owned Windows fixtures on the executing platform',()=>{
 for(const file of ['scripts/start-companion.ps1','scripts/update-companion.ps1','scripts/companion-runtime.ps1']) {
  const checks=selectChecks([file]),scenarios=scenarioPlan([file],checks),commands=[];
  const unavailable=executeChecks(checks,{scenarios,runCommand:(...args)=>commands.push(args),platform:'darwin'});
  assert.ok(unavailable.unavailable.includes('companion-process-identity-e2e'));
  assert.ok(!commands.some(([command])=>command==='powershell.exe'));
  executeChecks(checks,{scenarios,runCommand:(...args)=>commands.push(args),platform:'win32'});
  assert.ok(commands.some(([command,args])=>command==='powershell.exe'&&args.includes('scripts/companion-process-identity-e2e.ps1')));
 }
});
test('split browser CI still executes Windows fixtures and records full unknown fallback',()=>{
 const checks=selectChecks(['unrecognized/file']),scenarios=scenarioPlan([],checks),commands=[];
 executeChecks(checks,{scenarios,runCommand:(command,args)=>commands.push([command,...args]),platform:'win32',splitBrowsers:true});
 assert.deepEqual(checks,['full']);
 assert.equal(commands.filter(command=>command[0]==='powershell.exe').length,2);
 assert.equal(commands.filter(command=>command.includes('scripts/update-companion-e2e.mjs')).length,1);
 assert.ok(!commands.some(command=>command.includes('scripts/ui-state-e2e.mjs')));
});

test('state sources select the real backend-to-browser scenario and its Python dependency',()=>{
 for(const file of ['backend/api.py','backend/state_version.py','app/companion.tsx','app/language-setup.tsx','app/state-sync.ts','scripts/ui-state-e2e.mjs']){
  const checks=selectChecks([file]);assert.ok(checks.includes('python'),file);
  assert.ok(scenarioPlan([file],checks).browser.includes('ui-state-e2e'),file);
 }
});

test('updater and runtime helper changes execute native update handoff with Python available',()=>{
 for(const file of ['scripts/update-companion.ps1','scripts/companion-runtime.ps1']){
  const checks=selectChecks([file]),scenarios=scenarioPlan([file],checks),commands=[];
  assert.ok(checks.includes('python'),file+' needs the Python update fixture');
  assert.ok(scenarios.windows.includes('update-companion-e2e'),file+' must exercise prepared updates');
  executeChecks(checks,{scenarios,runCommand:(command,args)=>commands.push([command,...args]),platform:'win32',splitBrowsers:true});
  assert.equal(commands.filter(args=>args.includes('scripts/update-companion-e2e.mjs')).length,1);
 }
});
test('native update scenarios are recorded unavailable off Windows and never silently pass',()=>{
 const scenarios=scenarioPlan(['backend/api.py']),commands=[];
 assert.ok(scenarios.windows.includes('update-companion-e2e'));
 const result=executeChecks(selectChecks(['backend/api.py']),{scenarios,runCommand:(command,args)=>commands.push([command,...args]),platform:'darwin',splitBrowsers:true});
 assert.ok(result.unavailable.includes('update-companion-e2e'));
 assert.ok(!commands.some(args=>args.includes('scripts/update-companion-e2e.mjs')));
});
