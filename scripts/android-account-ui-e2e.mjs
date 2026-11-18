// Real shared React UI + maintained Android HTTP/session services on desktop.
// Credential protection and remote accounts are explicit authored mocks.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium, firefox} from 'playwright';
import {exerciseAccountUi} from './android-authored-account-ui.mjs';
import {prepareAuthoredGameData} from './android-authored-game-data-ui.mjs';
import {importBrowserHistoryThroughUi} from './android-browser-migration-ui.mjs';

const frontend=resolve(process.argv[2] ?? 'output/android-account-ui-frontend');
const output=resolve(process.argv[3] ?? 'output/checks/android-account-ui');
mkdirSync(output,{recursive:true});
const proofs=[];
async function until(operation,label) {
 const end=Date.now()+30000;
 while(Date.now()<end) {const value=await operation();if(value)return value;await delay(100);}
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
  // Unconnected use prepares through the same UI without an account or ZIP.
  await prepareAuthoredGameData(page,until,{bothModes:true});
  service.stdin.write(JSON.stringify({action:'capture'})+'\n');
  assert.equal((await next()).captured,1);
  await page.getByRole('button',{name:'Play current voice line',exact:true}).waitFor();
  const initial=await page.evaluate(async()=>await(await fetch('/api/snapshot')).json());
  assert.equal(initial.lexirise.configured,false);
  await page.getByRole('button',{name:'Favorite current line',exact:true}).click();
  await until(()=>page.evaluate(async()=>!!(await(await fetch('/api/snapshot')).json()).lines[0]?.favorite),'unconnected favorite');
  await importBrowserHistoryThroughUi(page,until,initial.lines[0].id);
  await page.reload();
  await page.getByRole('button',{name:'Connect Lexirise',exact:true}).waitFor();
  assert.equal(await page.getByRole('combobox',{name:'Reading',exact:true}).count(),0);
  await exerciseAccountUi(page, {library, until,
   capture: async () => {
    service.stdin.write(JSON.stringify({action:'capture'})+'\n');
    assert.equal((await next()).captured,1);
   },
   corrupt: async () => {
    service.stdin.write(JSON.stringify({action:'corrupt'})+'\n');
    assert.equal((await next()).locked,true);
   },
   preserved: async () => {
    service.stdin.write(JSON.stringify({action:'verify_recovery'})+'\n');
    return (await next()).old_store_preserved;
   },
  });
  assert.deepEqual(errors,[]);
  proofs.push({engine:name,viewport:'412x915',protected_storage:'authored-desktop-mock',remote_transport:'immutable-authored-mock',native_android_execution:false,shared_ui_direct_game_preparation:true,account_switch:'A-B-A',separate_direct_sources:true,history_favorite_retained:true,stale_generation_rejected:true,recovery_preserves_original_store:true,recovery_refreshes_capabilities:true,scoped_settings_and_original_audio_export:true});
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
