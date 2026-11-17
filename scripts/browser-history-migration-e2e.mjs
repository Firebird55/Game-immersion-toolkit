// Actual retired-origin IndexedDB export -> shared React UI + Android HTTP core.
// Native protection and remote accounts are the explicit authored desktop mocks.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {createInterface} from 'node:readline';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium,firefox} from 'playwright';

const frontend=resolve(process.argv[2]??'output/android-browser-migration-frontend');
const output=resolve(process.argv[3]??'output/checks/browser-history-migration-ui');mkdirSync(output,{recursive:true});
const exporter=readFileSync(new URL('./export-browser-history.js',import.meta.url),'utf8');
const proofs=[];
async function until(fn,label){const end=Date.now()+30000;while(Date.now()<end){if(await fn())return;await delay(100);}throw Error('Missing migration assertion: '+label);}
for(const [name,engine]of Object.entries({chromium,firefox})){
 const root=mkdtempSync(join(output,name+'-'));
 const service=spawn(process.env.PYTHON??'python',['-u','-m','scripts.android-account-ui-fixture',root,frontend],{stdio:['pipe','pipe','inherit']});
 const lines=createInterface({input:service.stdout})[Symbol.asyncIterator]();
 let browser;
 try{
  const first=await lines.next();assert.equal(first.done,false);const {origin,cookie}=JSON.parse(first.value);
  browser=await engine.launch({headless:true});
  const oldContext=await browser.newContext({acceptDownloads:true}),old=await oldContext.newPage();
  await old.route('https://old-toolkit.invalid/**',route=>route.fulfill({status:404,contentType:'text/html',body:'<html><body>Authored retired-origin fixture</body></html>'}));
  await old.goto('https://old-toolkit.invalid/retired');
  await old.evaluate(async()=>{
   const db=await new Promise((resolve,reject)=>{const request=indexedDB.open('proxy-mobile-library',2);
    request.onupgradeneeded=()=>request.result.createObjectStore('state');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
   await new Promise((resolve,reject)=>{const tx=db.transaction('state','readwrite'),store=tx.objectStore('state');
    store.put(Array.from({length:301},(_,n)=>({id:'authored-mobile-'+n,textId:'zzz:authored:legacy:'+n,game:'zzz',
     createdAt:1794783739000+n,favorite:n===0,english:'Preserved legacy history '+n+'.',chinese:'保存された旧文章 '+n+'。',
     sourceText:'保存された旧文章 '+n+'。',sourceLocale:'ja',sourceLanguage:'ja',translationLocale:'en',
     translationText:'Preserved legacy history '+n+'.',audioLocale:'ja',textTruncated:n===300,sourceVoice:'1'.repeat(64)})),'history');
    store.put([{source:'pc-1234567890abcdef',id:1,game:'zzz',createdAt:1794783739999,favorite:false,
     english:'Preserved desktop history.',chinese:'保留的电脑历史。',audio:true}],'pc-history');
    store.put({key:'authored-private-vault-sentinel'},'lexirise-remembered');
    store.put({url:'authored-private-stream-sentinel'},'private-viewer-link');
    tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});db.close();
   window.migrationReadKeys=[];const get=IDBObjectStore.prototype.get;
   IDBObjectStore.prototype.get=function(key){window.migrationReadKeys.push(key);return get.call(this,key);};
  });
  old.on('dialog',dialog=>dialog.accept());
  const downloaded=old.waitForEvent('download');await old.addScriptTag({content:exporter});
  const download=await downloaded,backup=join(root,'history.json');await download.saveAs(backup);
  assert.deepEqual(await old.evaluate(()=>window.migrationReadKeys),['history','pc-history']);
  const raw=readFileSync(backup,'utf8');assert.doesNotMatch(raw,/private-vault|private-stream|lexirise-remembered|private-viewer-link/);
  assert.equal(JSON.parse(raw).rows.length,302);
  const oldRetained=await old.evaluate(async()=>{const db=await new Promise(resolve=>{const r=indexedDB.open('proxy-mobile-library');r.onsuccess=()=>resolve(r.result);});
   const result=await new Promise(resolve=>{const r=db.transaction('state').objectStore('state').get('lexirise-remembered');r.onsuccess=()=>resolve(r.result);});db.close();return result;});
  assert.equal(oldRetained.key,'authored-private-vault-sentinel');

  const context=await browser.newContext({viewport:{width:412,height:915}});
  await context.addCookies([{name:'toolkit_session',value:cookie,url:origin,httpOnly:true,sameSite:'Strict'}]);
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(origin);
  await page.getByRole('button',{name:'Lexirise account',exact:true}).click();
  await page.getByRole('button',{name:'Add account securely',exact:true}).click();
  await page.getByLabel('Lexirise API key',{exact:true}).fill('lx_first_authored_account_fixture_only');
  await page.getByLabel('Account label (optional)',{exact:true}).fill('Migration authored owner');
  await page.getByRole('button',{name:'Verify and save',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('select[aria-label="Active Lexirise account"]')?.selectedOptions[0]?.textContent==='Migration authored owner');
  await page.getByRole('button',{name:'Close Lexirise settings',exact:true}).click();
  await page.getByText('Import old browser history',{exact:true}).click();
  await page.getByText('Export from the old browser',{exact:true}).click();
  const bookmark=await page.getByLabel('Old browser history export bookmark',{exact:true}).inputValue();
  assert.ok(bookmark.startsWith('javascript:'));
  await old.evaluate(bookmark=>{
    window.migrationReadKeys=[];
    const button=document.createElement('button');button.textContent='Run authored history bookmark';
    button.onclick=()=>{window.location.href=bookmark;};document.body.append(button);
  },bookmark);
  const bookmarkDownload=old.waitForEvent('download');
  await old.getByRole('button',{name:'Run authored history bookmark',exact:true}).click();
  const bookmarkPath=join(root,'bookmark-history.json');await(await bookmarkDownload).saveAs(bookmarkPath);
  assert.equal(readFileSync(bookmarkPath,'utf8'),raw);
  assert.deepEqual(await old.evaluate(()=>window.migrationReadKeys),['history','pc-history']);
  await oldContext.close();
  await page.getByLabel('Browser history backup',{exact:true}).setInputFiles(backup);
  await page.getByText('302 lines · 1 favorites · 1 excerpts.',{exact:false}).waitFor();
  assert.equal(await page.evaluate(async()=>(await(await fetch('/api/snapshot')).json()).lines.length),0);
  await page.getByRole('button',{name:'Import history and favorites',exact:true}).click();
  await page.getByText('History imported: 302 new lines, 0 already imported. Original browser data is unchanged.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Imported history',exact:true}).click();
  const archive=page.getByRole('region',{name:'Imported browser history',exact:true});
  await archive.getByText('保留的电脑历史。',{exact:true}).waitFor();
  await archive.getByText('Imported browser excerpt',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Previous 10',exact:true}).click();
  await archive.getByText('保存された旧文章 291。',{exact:true}).waitFor();
  await page.getByLabel('Imported favorites only',{exact:true}).check();
  await archive.getByText('保存された旧文章 0。',{exact:true}).waitFor();
  assert.equal(await archive.locator('.transcript-line').count(),1);
  assert.equal(await archive.getByRole('button',{name:/Remove from favorites/}).count(),1);
  assert.equal(await archive.getByText('0%',{exact:true}).count(),0);
  await page.getByLabel('Browser history backup',{exact:true}).setInputFiles(backup);
  await page.getByRole('button',{name:'Import history and favorites',exact:true}).click();
  await page.getByText('History imported: 0 new lines, 302 already imported. Original browser data is unchanged.',{exact:true}).waitFor();
  const snapshot=await page.evaluate(async()=>await(await fetch('/api/snapshot')).json());
  assert.equal(snapshot.status.session.total_line_count,302);
  assert.ok(snapshot.lines.every(line=>!line.has_audio&&line.voice_status==='unavailable'));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:join(root,'migration-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
  proofs.push({browser:name,old_origin_readonly:true,actual_ui_bookmark_executes_exact_export:true,credential_stream_excluded:true,source_rows:302,
   preview_no_write:true,repeat_idempotent:true,history_paged_beyond_recent_limit:true,oldest_favorite_visible:true,
   excerpt_preserved:true,original_audio_not_invented:true,native_android_execution:false});
 }finally{service.stdin.write('{"action":"close"}\n');service.stdin.end();if(browser)await browser.close();}
}
writeFileSync(join(output,'proof.json'),JSON.stringify(proofs,null,2)+'\n');console.log(JSON.stringify({cases:proofs.length,result:'passed'}));
