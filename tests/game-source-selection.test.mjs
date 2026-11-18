import test from 'node:test';
import assert from 'node:assert/strict';
import {createGameSourceSelection} from '../lib/game-source-selection.mjs';
const deferred=()=>{let resolve;const promise=new Promise(value=>{resolve=value;});return {promise,resolve};};

test('no automatic activation; newest explicit choice wins after old HTTP settles', async()=>{
 const gate=deferred(),calls=[],commits=[];
 const controller=createGameSourceSelection({current:()=>true,
  activate:async game=>{calls.push(game);if(game==='a')await gate.promise;},committed:()=>commits.push(calls.at(-1))});
 assert.deepEqual(calls,[]);
 controller.select('a');controller.select('b');const done=controller.select('c');
 assert.deepEqual(calls,['a']);gate.resolve();await done;
 assert.deepEqual(calls,['a','c']);assert.deepEqual(commits,['c']);
});
test('A to B to A owner change rejects stale work and queued choices', async()=>{
 const gate=deferred(),calls=[],commits=[];let generation=1;
 const controller=createGameSourceSelection({current:()=>generation===1,
  activate:async game=>{calls.push(game);await gate.promise;},committed:()=>commits.push(true)});
 const done=controller.select('a');controller.select('b');generation=2;generation=3;gate.resolve();await done;
 assert.deepEqual(calls,['a']);assert.deepEqual(commits,[]);
});
test('dispose/cancel do not pretend an in-flight mutation was rolled back', async()=>{
 const gate=deferred();let calls=0,commits=0;
 const controller=createGameSourceSelection({current:()=>true,activate:async()=>{calls++;await gate.promise;},committed:()=>commits++});
 const done=controller.select('a');controller.select('b');controller.cancel();controller.dispose();
 gate.resolve();await done;await controller.select('c');assert.equal(calls,1);assert.equal(commits,0);
});
test('a current error is visible and a subsequent explicit choice still runs', async()=>{
 const calls=[];let errors=0,commits=0;
 const controller=createGameSourceSelection({current:()=>true,activate:async game=>{calls.push(game);if(game==='a')throw Error('authored');},
  failed:()=>errors++,committed:()=>commits++});
 await controller.select('a');await controller.select('b');
 assert.deepEqual(calls,['a','b']);assert.equal(errors,1);assert.equal(commits,1);
});
