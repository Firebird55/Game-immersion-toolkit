import assert from 'node:assert/strict';
import test from 'node:test';
import {EventEmitter} from 'node:events';
import {runInNewContext} from 'node:vm';
import {createAuthoredRecoveryObservation, recoveryGenerationHeader, recoveryRoute,
 observeRecoveryPredicate, observeRecoveryForm} from '../scripts/android-authored-recovery-observation.mjs';
import {createAuthoredRuntimeDiagnostics} from '../scripts/android-runtime-diagnostics.mjs';

const origin='http://127.0.0.1:8123',path='/api/lexirise/accounts/recover';
const privateValue='authored-private-credential-owner-or-window-must-not-be-retained';

test('only exact same-origin loopback account routes and canonical safe generations are observed',()=>{
 assert.equal(recoveryRoute(origin+path,origin),path);
 for(const value of [origin+path+'?key='+privateValue,origin+path+'#'+privateValue,
  origin+path+'/extra','https://foreign.invalid'+path,'http://127.0.0.1:8124'+path,
  'http://private@127.0.0.1:8123'+path,'not a URL'])assert.equal(recoveryRoute(value,origin),null);
 for(const value of ['0','3',String(Number.MAX_SAFE_INTEGER)])assert.equal(recoveryGenerationHeader(value),Number(value));
 for(const value of [undefined,null,0,true,'','03','-1','1.0','1e2',' 3','9007199254740992',privateValue])
  assert.equal(recoveryGenerationHeader(value),null);
});

test('status and kind bind to a known request without retaining arbitrary provider fields',()=>{
 const o=createAuthoredRecoveryObservation();o.generation(7);
 const request=o.request(path,'POST','6');o.response(request,409,'account_generation_changed');
 o.response({},200,privateValue);
 assert.equal(o.request('/api/unknown/'+privateValue,'POST','7'),null);
 assert.equal(o.request(path,privateValue,'7'),null);
 const row=o.snapshot().http[0];
 assert.deepEqual(row,{path,method:'POST',expected_generation:6,last_snapshot_generation:7,
  status:409,kind:'account_generation_changed',response_snapshot_generation:7});
 const unknown=o.request(path,'POST',privateValue);o.generation(Infinity);o.response(unknown,999,privateValue);
 assert.equal(o.snapshot().http[1].status,null);assert.equal(o.snapshot().http[1].kind,null);
 assert.equal(JSON.stringify(o.snapshot()).includes(privateValue),false);
});

test('bounded account polling cannot evict the recovery POST or mutate exported observations',()=>{
 const o=createAuthoredRecoveryObservation(),post=o.request(path,'POST','3');o.response(post,200,null);
 let firstRead;
 for(let i=0;i<100;i++){
  const read=o.request('/api/lexirise/accounts','GET',String(i));if(i===0)firstRead=read;
  o.response(read,200,null);
 }
 assert.equal(o.snapshot().http.filter(row=>row.path===path).length,1);
 assert.equal(o.snapshot().http.length,33);o.response(firstRead,500,'account_recovery_required');
 assert.equal(o.snapshot().http.some(row=>row.status===500),false);
 const copy=o.snapshot();copy.http[0].path=privateValue;
 assert.equal(JSON.stringify(o.snapshot()).includes(privateValue),false);
});

test('predicate samples keep only 32 changes and nullable booleans, never identities',()=>{
 const o=createAuthoredRecoveryObservation();
 for(let i=0;i<50;i++){
  o.generation(i);const value={owner_matches:i%2===0,account_recovery_present:true,
   platform_recovery_present:true,library_import:false,account_id:privateValue};
  o.predicate(value);o.predicate(value);
 }
 assert.equal(o.snapshot().predicates.length,32);assert.equal(o.snapshot().predicates[0].last_snapshot_generation,18);
 o.predicate({owner_matches:privateValue});assert.equal(o.snapshot().predicates.at(-1).owner_matches,null);
 assert.equal(JSON.stringify(o.snapshot()).includes(privateValue),false);
});

test('form telemetry is closed and readonly and carries the exact scoped GET generation',async()=>{
 const o=createAuthoredRecoveryObservation();o.generation(9);o.request('/api/lexirise/accounts','GET','8');
 o.generation(undefined);o.request('/api/lexirise/accounts','GET',undefined);
 await observeRecoveryForm({evaluate:async()=>({input_connected:false,input_present:true,input_nonempty:false,
  input_valid:false,submit_disabled:false,value:privateValue})},o,'before-submit',{});
 assert.deepEqual(o.snapshot().forms,[{phase:'before-submit',input_connected:false,input_present:true,
  input_nonempty:false,input_valid:false,submit_disabled:false,last_scoped_accounts_generation:8,last_snapshot_generation:9}]);
 assert.throws(()=>o.form(privateValue,{}),/Unknown authored/);
 await observeRecoveryForm({evaluate:async()=>{throw Error(privateValue);}},o,'after-fill',null);
 assert.equal(o.snapshot().forms.at(-1).input_present,null);
 assert.equal(JSON.stringify(o.snapshot()).includes(privateValue),false);
});

test('observation preserves every original recovery condition and the same two readonly requests',async()=>{
 for(const failure of [null,'owner','account-recovery','platform-recovery','capability']){
  const reads=[],o=createAuthoredRecoveryObservation();o.generation(4);
  const page={evaluate:(fn,identity)=>runInNewContext('('+fn.toString()+')(identity)',{identity,
   fetch:async route=>{reads.push(route);return{json:async()=>route.endsWith('/accounts')?
    {active:failure==='owner'?'different':identity,recovery:failure==='account-recovery'?{}:null,key:privateValue}:
    {account_recovery:failure==='platform-recovery'?{}:null,library_import:failure!=='capability',cookie:privateValue}};}})};
  assert.equal(await observeRecoveryPredicate(page,'authored-owner',o),failure===null);
  assert.deepEqual(reads,['/api/lexirise/accounts','/api/platform']);
  assert.equal(o.snapshot().predicates[0].owner_matches,failure!=='owner');
  assert.equal(o.snapshot().predicates[0].library_import,failure!=='capability');
  assert.equal(JSON.stringify(o.snapshot()).includes(privateValue),false);
 }
});

test('actual diagnostic event wiring captures recovery delivery without reading a request body or cookie',async()=>{
 class Page extends EventEmitter{url(){return origin;}async addInitScript(){}async evaluate(){}}
 const page=new Page(),{recovery}=await createAuthoredRuntimeDiagnostics(page,{});
 const request={url:()=>origin+path,method:()=>'POST',headers:()=>({'x-toolkit-account-generation':'3',cookie:privateValue}),
  postData(){throw Error('A credential body must never be inspected');}};
 page.emit('request',request);
 page.emit('response',{url:()=>origin+'/api/snapshot',status:()=>200,request:()=>({}),json:async()=>({context:{account_generation:4},key:privateValue})});
 await new Promise(resolve=>setImmediate(resolve));
 page.emit('response',{url:request.url,status:()=>409,request:()=>request,json:async()=>({state:'account_generation_changed',key:privateValue,active:privateValue})});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(recovery.snapshot().http[0].status,409);
 assert.equal(recovery.snapshot().http[0].response_snapshot_generation,4);
 assert.equal(JSON.stringify(recovery.snapshot()).includes(privateValue),false);
});
