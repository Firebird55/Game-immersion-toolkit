// Shared compiled React + maintained mock backend; no Android runtime claim.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium,firefox} from 'playwright';
import {createAuthoredRuntimeDiagnostics} from './android-runtime-diagnostics.mjs';
import {observeRecoveryForm, observeRecoveryPredicate} from './android-authored-recovery-observation.mjs';

const frontend=resolve(process.argv[2] ?? 'output/android-account-ui-frontend');
const output=resolve(process.argv[3] ?? 'output/checks/android-recovery-observation');mkdirSync(output,{recursive:true});
const manifest=JSON.parse(readFileSync(join(frontend,'desktop-manifest.json'),'utf8'));
assert.match(manifest.source_commit,/^[0-9a-f]{40}$/);assert.equal(manifest.runtime,'static-local-no-node');
const proof=[];
const key='lx_first_authored_account_fixture_only';
async function until(fn,label){const end=Date.now()+30000;while(Date.now()<end){const v=await fn();if(v)return v;await delay(50);}throw Error(label);}
for(const [engineName,engine] of Object.entries({chromium,firefox}))for(const mode of ['control','injected-owned-scope-reset']){
 const root=mkdtempSync(join(output,engineName+'-'+mode+'-'));
 const service=spawn(process.env.PYTHON,['-u','-m','scripts.android-account-ui-fixture',root,frontend],{stdio:['pipe','pipe','pipe']});
 const events=createInterface({input:service.stdout})[Symbol.asyncIterator]();
 const next=async()=>{const v=await events.next();if(v.done)throw Error('Authored backend exited');return JSON.parse(v.value);};
 let browser,page,holdSnapshots=false,releaseSnapshots=()=>{},expectedOwner;
 const latch=new Promise(resolve=>{releaseSnapshots=resolve;});
 try{
  const {origin,cookie}=await next();browser=await engine.launch({headless:true});
  page=await browser.newPage({viewport:{width:412,height:915}});
  await page.context().addCookies([{name:'toolkit_session',value:cookie,url:origin,httpOnly:true,sameSite:'Strict'}]);
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin!==origin)return route.abort('blockedbyclient');
   if(url.pathname==='/api/snapshot'&&holdSnapshots)await latch;
   return route.continue();
  });
  const {recovery}=await createAuthoredRuntimeDiagnostics(page,{output:root});
  const state=()=>page.evaluate(async()=>({snapshot:await(await fetch('/api/snapshot')).json(),
   accounts:await(await fetch('/api/lexirise/accounts')).json(),platform:await(await fetch('/api/platform')).json()}));
  await page.goto(origin);await page.getByRole('button',{name:'Connect Lexirise',exact:true}).click();
  await page.getByRole('button',{name:'Add account securely',exact:true}).click();
  await page.getByLabel('Lexirise API key',{exact:true}).fill(key);
  await page.getByRole('button',{name:'Verify and save',exact:true}).click();
  expectedOwner=await until(async()=>{const v=await state();return v.accounts.active!=='legacy'?v.accounts.active:null;},'Initial authored registration');
  await until(()=>page.getByRole('combobox',{name:'Active Lexirise account',exact:true}).inputValue().then(v=>v===expectedOwner),'Initial owner reflected in component');
  await page.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
  service.stdin.write(JSON.stringify({action:'corrupt'})+'\n');assert.equal((await next()).locked,true);
  await until(async()=>{const v=await state();return v.snapshot.lexirise.account==='recovery'&&v.platform.capture_source==='unavailable';},'Authored store locked');
  await until(()=>page.getByRole('button',{name:'Connect Lexirise',exact:true}).isVisible(),'Recovery owner rendered');
  await page.getByRole('button',{name:'Connect Lexirise',exact:true}).click();
  const submit=page.getByRole('button',{name:'Verify and restore local data',exact:true});
  await until(()=>submit.isEnabled(),'Actual recovery component loaded');
  const before=await state();
  assert.equal(before.accounts.recovery.state,'credentials_unreadable');
  const input=page.getByLabel('Lexirise API key',{exact:true});
  const oldInput=await input.elementHandle();
  await observeRecoveryForm(page,recovery,'before-fill',oldInput);
  await input.fill(key);assert.equal(await input.inputValue(),key);
  await observeRecoveryForm(page,recovery,'after-fill',oldInput);
  let remounted=false,emptyAfterReset=false;
  if(mode==='injected-owned-scope-reset'){
   holdSnapshots=true;
   // Explicit hypothesis injection: use the maintained reset handler, never
   // spoof an HTTP generation or alter actual account/backend state.
   await page.evaluate(()=>window.dispatchEvent(new Event('lexirise-credentials-changed')));
   await until(()=>oldInput.evaluate(input=>!input.isConnected),'Old component retired');
   holdSnapshots=false;releaseSnapshots();
   await until(()=>submit.isEnabled(),'Fresh recovery component loaded');
   remounted=await oldInput.evaluate(input=>!input.isConnected);
   emptyAfterReset=(await input.inputValue())==='';
   assert.equal(remounted,true);assert.equal(emptyAfterReset,true);
  }
  await observeRecoveryForm(page,recovery,'before-submit',oldInput);
  await submit.click();
  if(mode==='control'){
   await until(()=>observeRecoveryPredicate(page,expectedOwner,recovery),'Explicit recovery predicate');
   await until(()=>recovery.snapshot().http.some(row=>row.path.endsWith('/recover')&&row.status===200),'Recovery response receipt');
   const posts=recovery.snapshot().http.filter(row=>row.path.endsWith('/recover'));
   assert.equal(posts.length,1);assert.equal(posts[0].status,200);
   assert.equal(posts[0].expected_generation,before.snapshot.context.account_generation);
  }else{
   assert.equal(await input.evaluate(value=>value.validity.valueMissing),true);
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   assert.equal(recovery.snapshot().http.filter(row=>row.path.endsWith('/recover')).length,0);
  }
  const after=await state();service.stdin.write(JSON.stringify({action:'verify_recovery'})+'\n');
  assert.equal((await next()).old_store_preserved,true);
  const observations=recovery.snapshot();
  const submitMetrics=observations.forms.at(-1);
  assert.equal(submitMetrics.input_connected,!remounted);assert.equal(submitMetrics.input_nonempty,!remounted);
  assert.equal(submitMetrics.input_valid,!remounted);assert.equal(submitMetrics.submit_disabled,false);
  await oldInput.dispose();
  proof.push({engine:engineName,mode,frontend_source:manifest.source_commit,frontend_build:manifest.build_id,
   actual_shared_react:true,maintained_android_host:true,remote_transport:'immutable-authored-mock',
   native_android_execution:false,real_account_writes:false,
   before_generation:before.snapshot.context.account_generation,after_generation:after.snapshot.context.account_generation,
   remounted,input_empty_after_reset:emptyAfterReset,observations,
   original_store_preserved:true,synthetic_reset_is_observed_ci_cause:false,
   final_owner_matches:after.accounts.active===expectedOwner,recovery_still_required:!!after.accounts.recovery});
 }finally{
  releaseSnapshots();await browser?.close();service.stdin.write(JSON.stringify({action:'close'})+'\n');service.stdin.end();
  if(service.exitCode===null)await new Promise(resolve=>service.once('exit',resolve));
 }
}
writeFileSync(join(output,'proof.json'),JSON.stringify(proof,null,2)+'\n');
console.log(JSON.stringify({cases:proof.length,source:manifest.source_commit,result:'passed',native_android_execution:false}));
