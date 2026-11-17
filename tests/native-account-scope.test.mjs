import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeAccountHeaders, nativeAccountQuery} from '../lib/native-account-scope.mjs';

test('native mutations and preview URLs retain their captured account generation',()=>{
 let selected=0;
 const first=nativeAccountHeaders(selected, {'Content-Type':'application/zip'});
 const firstPreview=nativeAccountQuery(selected);
 selected=2; // A→B→A still has a new generation.
 assert.equal(first['X-Toolkit-Account-Generation'],'0');
 assert.equal(firstPreview,'&account_generation=0');
 assert.equal(nativeAccountHeaders(selected)['X-Toolkit-Account-Generation'],'2');
 assert.equal(first['Content-Type'],'application/zip');
 assert.deepEqual(nativeAccountHeaders(undefined,{'Content-Type':'application/json'}),{'Content-Type':'application/json'});
 assert.equal(nativeAccountQuery(undefined),'');
});

test('an Android document without a valid snapshot cannot create an unscoped mutation',()=>{
 for(const generation of [null,-1,0.5,'0',Infinity,Number.MAX_SAFE_INTEGER+1]) {
  assert.throws(()=>nativeAccountHeaders(generation),/selected account/);
  assert.throws(()=>nativeAccountQuery(generation),/selected account/);
 }
});
