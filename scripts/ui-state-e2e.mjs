import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {chromium,firefox} from 'playwright';

// Real FastAPI serialization/WS + the exact state owner used by both React views.
// Existing language-account-e2e additionally exercises the built React bindings.
const source=ts.transpileModule(readFileSync('app/state-sync.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const python=spawn(process.env.PYTHON||'python',['scripts/ui-state-browser-server.py'],{stdio:['ignore','pipe','pipe']});
let errors='',browser;python.stderr.on('data',b=>errors+=b);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
try{
 const port=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error(errors||'State fixture startup timeout')),20000);python.stdout.on('data',b=>{output+=b;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]).port);}});python.once('exit',code=>{clearTimeout(timer);reject(Error('State fixture exited '+code+': '+errors));});python.once('error',reject);});
 const api='http://127.0.0.1:'+port;
 const control=async(path,body)=>{const response=await fetch(api+path,{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise'},body:body?JSON.stringify(body):undefined});assert(response.ok,path+': '+await response.text());};
 const state=async()=>await(await fetch(api+'/__test/state')).json();
 const until=async predicate=>{for(let n=0;n<100;n++){if(await predicate())return;await sleep(30);}throw Error('Synthetic state wait timed out: '+errors);};
 await until(async()=>{try{return (await fetch(api+'/__test/state')).ok;}catch{return false;}});
 for(const[name,engine]of Object.entries({chromium,firefox})){
  browser=await engine.launch();const context=await browser.newContext();if(name==='chromium')await context.grantPermissions(['local-network-access']);const page=await context.newPage();const pageErrors=[];page.on('pageerror',error=>pageErrors.push(error.message));page.on('console',message=>{if(message.type()==='error')console.error(name+': '+message.text());});
  await page.route('http://127.0.0.1:3000/__state',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><p id="line"></p><p id="target"></p>'}));
  await page.route('http://127.0.0.1:3000/state-sync.js',route=>route.fulfill({contentType:'text/javascript',body:source}));
  await page.goto('http://127.0.0.1:3000/__state');
  await page.evaluate(async api=>{
   const {StatePoll}=await import('/state-sync.js');window.commits=[];window.events=[];
   window.owner=new StatePoll(async signal=>{const response=await fetch(api+'/api/snapshot',{signal});if(!response.ok)throw Error('Snapshot unavailable');return response.json();},value=>{window.commits.push(value);document.querySelector('#line').textContent=String(value.lines.find(l=>l.id===1)?.favorite);});
   window.languages=new StatePoll(async signal=>{const response=await fetch(api+'/api/setup/games/zzz/languages',{signal});if(!response.ok)throw Error('Languages unavailable');return response.json();},value=>document.querySelector('#target').textContent=value.context.account_generation+':'+value.targets.zh);
   window.connect=()=>{
    const socket=window.socket=new WebSocket(api.replace('http:','ws:')+'/api/ws');
    socket.onopen=()=>{window.owner.reset(true);window.languages.reset(true);void window.owner.request();void window.languages.request();};
    socket.onmessage=message=>{
     if(window.socket!==socket)return;
     const event=JSON.parse(message.data);if(!window.owner.accept(event.context))return;window.events.push(event);
     if(event.type==='line')document.querySelector('#line').textContent=String(event.line.favorite);
     if(event.type==='account_changed'){window.owner.reset();window.languages.reset();void window.owner.request();void window.languages.request();}
    };
    socket.onclose=()=>{if(window.socket!==socket)return;window.socket=null;window.owner.reset(true);window.languages.reset(true);setTimeout(window.connect,10);};
   };window.connect();
  },api);
  await page.waitForFunction(()=>window.commits.length>0&&document.querySelector('#target').textContent).catch(async error=>{console.error({browser:name,pageErrors,diagnostics:await page.evaluate(()=>({commits:window.commits,events:window.events,target:document.querySelector('#target').textContent})),snapshot:await(await fetch(api+'/api/snapshot')).text(),languages:await(await fetch(api+'/api/setup/games/zzz/languages')).text()});throw error;});
  // A completed old HTTP payload is held at the ASGI boundary while a newer
  // real favorite event updates the same transcript ID in the browser.
  await control('/__test/hold/snapshot');await page.evaluate(()=>{void window.owner.request();});await until(async()=>(await state()).waiting.includes('snapshot'));
  const before=await page.evaluate(()=>window.commits.length);
  const favorite=!(await page.locator('#line').textContent()==='true');
  assert((await fetch(api+'/api/lines/1/favorite',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({favorite})})).ok);
  await page.waitForFunction(expected=>document.querySelector('#line').textContent===String(expected),favorite);
  await control('/__test/release/snapshot');await sleep(100);
  assert.equal(await page.evaluate(()=>window.commits.length),before,'Old HTTP payload must not commit after the newer real WS event');
  assert.equal(await page.locator('#line').textContent(),String(favorite));
  // A held language response is cancelled by real A→B→A account publications.
  await control('/__test/hold/languages');await page.evaluate(()=>{void window.languages.request();});await until(async()=>(await state()).waiting.includes('languages'));
  const accounts=(await state()).accounts;
  for(const id of [accounts[1],accounts[0]])await control('/api/lexirise/accounts/select',{id});
  const generation=(await state()).context.account_generation;
  await page.waitForFunction(g=>document.querySelector('#target').textContent===g+':en',generation);
  await control('/__test/release/languages');await sleep(100);assert.equal(await page.locator('#target').textContent(),generation+':en');
  const previous=(await state()).context.runtime_id;await control('/__test/replace-runtime');
  await page.waitForFunction(old=>window.owner.context?.runtime_id!==old&&window.commits.at(-1)?.context.runtime_id===window.owner.context?.runtime_id,previous);
  // Closing an owner cancels a response already serialized by the backend.
  await control('/__test/hold/snapshot');await page.evaluate(()=>{void window.owner.request();});await until(async()=>(await state()).waiting.includes('snapshot'));
  const count=await page.evaluate(()=>{const count=window.commits.length;window.owner.close();window.languages.close();window.socket.onclose=null;window.socket.close();return count;});
  await control('/__test/release/snapshot');await sleep(100);assert.equal(await page.evaluate(()=>window.commits.length),count);
  assert((await state()).remote_calls.every(([method])=>method==='GET'));
  assert.deepEqual(pageErrors,[]);await browser.close();browser=null;
  console.log(name+': real backend snapshot/WS ordering, same-ID update, A→B→A language cancellation, new runtime and unmount passed');
 }
}finally{await browser?.close();python.kill();await Promise.race([once(python,'exit').catch(()=>{}),sleep(5000)]);if(python.exitCode===null&&python.signalCode===null){python.kill('SIGKILL');await once(python,'exit').catch(()=>{});}if(errors.trim())console.error(errors);}
