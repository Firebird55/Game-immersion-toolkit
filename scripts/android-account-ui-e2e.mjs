// Real shared React UI + maintained Android HTTP/session services on desktop.
// Credential protection and remote accounts are explicit authored mocks.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium, firefox} from 'playwright';

const frontend=resolve(process.argv[2] ?? 'output/android-account-ui-frontend');
const output=resolve(process.argv[3] ?? 'output/checks/android-account-ui');
mkdirSync(output,{recursive:true});
const proofs=[];
async function until(operation,label) {
 const end=Date.now()+30000;
 while(Date.now()<end) {if(await operation())return;await delay(100);}
 throw Error('The authored UI did not establish '+label);
}
for(const [name,engine] of Object.entries({chromium,firefox})) {
 const root=mkdtempSync(join(output,name+'-'));
 const service=spawn(process.env.PYTHON ?? 'python',['-u','-m','scripts.android-account-ui-fixture',root,frontend],{stdio:['pipe','pipe','inherit']});
 const lines=createInterface({input:service.stdout})[Symbol.asyncIterator]();
 const next=async()=>{const value=await lines.next();if(value.done)throw Error('Authored host exited');return JSON.parse(value.value);};
 let browser,page;
 try {
  const {origin,library,cookie}=await next();
  browser=await engine.launch({headless:true});
  page=await browser.newPage({viewport:{width:412,height:915}});
  // The native Activity injects this private bootstrap cookie before navigation.
  await page.context().addCookies([{name:'toolkit_session',value:cookie,url:origin,httpOnly:true,sameSite:'Strict'}]);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin);
  await page.getByRole('button',{name:'Lexirise account',exact:true}).click();
  const register=async(key,label)=>{
   await page.getByRole('button',{name:'Add account securely',exact:true}).click();
   await page.getByLabel('Lexirise API key',{exact:true}).fill(key);
   await page.getByLabel('Account label (optional)',{exact:true}).fill(label);
   await page.getByRole('button',{name:'Verify and save',exact:true}).click();
   await page.waitForFunction(label=>document.querySelector('select[aria-label="Active Lexirise account"]')?.selectedOptions[0]?.textContent===label,label);
   return page.getByRole('combobox',{name:'Active Lexirise account',exact:true}).inputValue();
  };
  const first=await register('lx_first_authored_account_fixture_only','First authored owner');
  await page.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
  await page.getByLabel('Private toolkit library',{exact:true}).setInputFiles(library);
  await until(()=>page.evaluate(async()=>!!(await(await fetch('/api/snapshot')).json()).status.textmaps.ready),'completed library import');
  service.stdin.write(JSON.stringify({action:'capture'})+'\n');
  const captured=await next();
  assert.equal(captured.captured,1,JSON.stringify(captured));
  await page.getByRole('button',{name:'Play current voice line',exact:true}).waitFor();
  const initial=await page.evaluate(async()=>await(await fetch('/api/snapshot')).json());
  assert.equal(initial.lines.length,1);
  const firstGeneration=initial.context.account_generation;
  const firstLine=initial.lines[0].id;
  // The actual UI favorite request must carry the account scope.
  await page.getByRole('button',{name:'Favorite current line',exact:true}).click();
  await until(()=>page.evaluate(async()=>!!(await(await fetch('/api/snapshot')).json()).lines[0]?.favorite),'saved favorite');
  await page.getByRole('button',{name:'Account settings',exact:true}).click();
  const second=await register('lx_second_authored_account_fixture_only','Second authored owner');
  assert.notEqual(first,second);
  const other=await page.evaluate(async()=>await(await fetch('/api/snapshot')).json());
  assert.equal(other.lines.length,0);
  assert.equal(other.status.textmaps.ready,false);
  assert.ok(other.context.account_generation>firstGeneration);
  assert.equal(await page.getByRole('button',{name:'Play current voice line',exact:true}).count(),0);
  // A delayed first-owner callback cannot mutate the new owner's settings.
  const stale=await page.evaluate(async generation=>{
   const response=await fetch('/api/settings',{method:'PATCH',headers:{'Content-Type':'application/json','X-Toolkit-Account-Generation':String(generation)},body:JSON.stringify({stable_frames:9})});
   return response.status;
  },firstGeneration);
  assert.equal(stale,409);
  await page.getByRole('combobox',{name:'Active Lexirise account',exact:true}).selectOption(first);
  await until(()=>page.evaluate(async identity=>(await(await fetch('/api/lexirise/accounts')).json()).active===identity,first),'restored first account');
  await page.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
  await page.locator('.transcript-line').filter({hasText:'Follow the river beyond the bridge.'}).first().waitFor();
  const restored=await page.evaluate(async()=>await(await fetch('/api/snapshot')).json());
  assert.equal(restored.lines.length,1);
  assert.equal(restored.lines[0].favorite,true);
  assert.notEqual(restored.lines[0].id,firstLine);
  assert.ok(restored.context.account_generation>other.context.account_generation);
  assert.equal(restored.status.settings.stable_frames,2);
  assert.deepEqual(errors,[]);
  proofs.push({engine:name,viewport:'412x915',protected_storage:'authored-desktop-mock',remote_transport:'immutable-authored-mock',native_android_execution:false,account_switch:'A-B-A',separate_libraries:true,history_favorite_retained:true,stale_generation_rejected:true});
 } catch(error) {
  if(page) {
   writeFileSync(join(root,'authored-page.txt'),await page.locator('body').innerText());
   writeFileSync(join(root,'authored-host-state.json'),JSON.stringify(await page.evaluate(async()=>({platform:await(await fetch('/api/platform')).json(),snapshot:await(await fetch('/api/snapshot')).json()})),null,2));
   await page.screenshot({path:join(root,'authored-page.png')});
  }
  throw error;
 } finally {
  await browser?.close();
  service.stdin.write(JSON.stringify({action:'close'})+'\n');service.stdin.end();
  if(service.exitCode===null)await new Promise(resolve=>service.once('exit',resolve));
 }
}
writeFileSync(join(output,'proof.json'),JSON.stringify(proofs,null,2)+'\n');
console.log(JSON.stringify({cases:proofs.length,result:'passed',native_android_execution:false}));
