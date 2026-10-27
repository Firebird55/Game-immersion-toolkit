import {test} from 'node:test';
import assert from 'node:assert/strict';
import {StatePoll} from '../app/state-sync.ts';
const context=(version=0,account=0,runtime='first-runtime')=>({runtime_id:runtime,state_version:version,account_generation:account});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 const pending=[],commits=[],errors=[];
 const owner=new StatePoll(signal=>new Promise((resolve,reject)=>pending.push({signal,resolve,reject})),value=>commits.push(value),error=>errors.push(error));
 return {owner,pending,commits,errors};
}
test('late HTTP cannot overwrite a newer WebSocket event or its same-ID line',async()=>{
 const {owner,pending,commits}=fixture();const done=owner.request();await tick();
 assert(owner.accept(context(2)));pending[0].resolve({context:context(1),line:{id:1,favorite:false}});await done;
 assert.deepEqual(commits,[]);assert.equal(owner.context.state_version,2);
 owner.close();
});
test('poll bursts coalesce into exactly one follow-up without overlapping reads',async()=>{
 const {owner,pending,commits}=fixture();const first=owner.request();
 for(let i=0;i<20;i++)void owner.request();await tick();assert.equal(pending.length,1);
 pending[0].resolve({context:context(0)});await first;await tick();assert.equal(pending.length,2);
 pending[1].resolve({context:context(1)});await tick();assert.equal(pending.length,2);assert.equal(commits.length,2);owner.close();
});
test('scope reset aborts and rejects reverse responses even when fetch ignores abort',async()=>{
 const {owner,pending,commits}=fixture();const old=owner.request();await tick();owner.reset();const current=owner.request();await tick();
 assert(pending[0].signal.aborted);pending[1].resolve({context:context(3),value:'current'});await current;
 pending[0].resolve({context:context(10),value:'old'});await old;assert.deepEqual(commits.map(v=>v.value),['current']);owner.close();
});
test('A to B to A retains the account generation boundary',async()=>{
 const {owner,pending,commits}=fixture();const old=owner.request();await tick();
 owner.accept(context(1,1));owner.reset();owner.accept(context(2,2));owner.reset();
 const current=owner.request();await tick();pending[1].resolve({context:context(2,2),account:'A'});await current;
 pending[0].resolve({context:context(0,0),account:'A'});await old;assert.equal(commits.length,1);assert.equal(commits[0].context.account_generation,2);owner.close();
});
test('language setup reset and unmount invalidate callbacks and errors',async()=>{
 const {owner,pending,commits,errors}=fixture();const old=owner.request();await tick();owner.reset();
 const current=owner.request();await tick();owner.close();pending[0].resolve({context:context(),targets:{nl:'en'}});pending[1].reject(Error('unmounted'));
 await Promise.all([old,current]);assert.deepEqual(commits,[]);assert.deepEqual(errors,[]);assert(pending.every(p=>p.signal.aborted));
 await owner.request();assert.equal(pending.length,2);
});
test('only an explicit connection reset can adopt another runtime',async()=>{
 const {owner,pending,commits}=fixture();owner.accept(context(99));assert(!owner.accept(context(0,0,'replacement')));
 const old=owner.request();await tick();owner.reset(true);assert(owner.accept(context(0,0,'replacement')));
 pending[0].resolve({context:context(100)});await old;assert.equal(commits.length,0);assert.equal(owner.context.runtime_id,'replacement');owner.close();
});
test('missing revisions and lower account generations are never state',()=>{
 const {owner}=fixture();assert(!owner.accept(undefined));assert(!owner.accept({runtime_id:'x'}));assert(owner.accept(context(8,4)));
 assert(!owner.accept(context(9,3)));assert(!owner.accept(context(7,5)));assert(owner.accept(context(8,4)));owner.close();
});

test('a late failed HTTP poll cannot mark a newer WebSocket state offline',async()=>{
 const {owner,pending,errors}=fixture();const old=owner.request();await tick();
 owner.accept(context(2));pending[0].reject(Error('old disconnected request'));await old;assert.deepEqual(errors,[]);
 const current=owner.request();await tick();const failure=Error('current failure');pending[1].reject(failure);await current;assert.deepEqual(errors,[failure]);owner.close();
});

test('reconciled snapshots keep independent newer events without a read retry',async()=>{
 const {StateEvents}=await import('../app/state-sync.ts');
 const events=new StateEvents(),commits=[];let resolve,reads=0;
 const owner=new StatePoll(()=>{reads++;return new Promise(done=>resolve=done);},value=>commits.push(value),()=>assert.fail('Unexpected failure'),value=>events.reconcile(value,(snapshot,event)=>({...snapshot,[event.key]:event.value})));
 const pending=owner.request();await tick();
 for(const [version,key,value] of [[2,'capture','new capture'],[1,'line','new line']]) {
  const event={context:context(version),key,value};assert(owner.accept(event.context,true));assert(events.record(key,event));
 }
 assert(!events.record('line',{context:context(0),key:'line',value:'stale'}));
 resolve({context:context(0),line:'old line',capture:'old capture',ledger:'independent snapshot'});await pending;
 assert.deepEqual(commits.map(({line,capture,ledger})=>({line,capture,ledger})),[{line:'new line',capture:'new capture',ledger:'independent snapshot'}]);
 assert.equal(reads,1);assert.equal(owner.context.state_version,2);
 events.reconcile({context:context(2)},value=>value);
 assert(!events.record('line',{context:context(2),key:'line',value:'already snapshotted'}));
 owner.close();
});

test('partial-event acceptance cannot regress account generations or runtimes',()=>{
 const {owner}=fixture();assert(owner.accept(context(8,4)));
 assert(owner.accept(context(7,4),true));assert.equal(owner.context.state_version,8);
 assert(!owner.accept(context(9,3),true));assert(!owner.accept(context(9,4,'retired-runtime'),true));owner.close();
});


test('an independent late partial event also supersedes an outstanding failure',async()=>{
 const {owner,pending,errors}=fixture();owner.accept(context(2));const old=owner.request();await tick();
 assert(owner.accept(context(1),true));pending[0].reject(Error('old poll'));await old;
 assert.deepEqual(errors,[]);assert.equal(owner.context.state_version,2);owner.close();
});
