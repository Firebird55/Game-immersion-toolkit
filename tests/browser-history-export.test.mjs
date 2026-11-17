import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const code=readFileSync(new URL('../scripts/export-browser-history.js',import.meta.url),'utf8');
const context={module:{exports:{}},TextEncoder};
vm.runInNewContext(code,context);
const {backup,readHistory}=context.module.exports;
const row={id:'authored_row',game:'endfield',createdAt:1794783739000,favorite:true,
 chinese:'原文',english:'Original translation',textId:'endfield:authored:one',sourceLocale:'zh-Hans',
 audio:'1'.repeat(64),sourceVoice:'2'.repeat(64)};

test('history projection retains identity/language/favorites and cannot include vault/stream metadata',()=>{
 const result=JSON.parse(backup([{...row,rememberedKey:'private-authored-key',viewerLink:'https://private.test',
  browserSettings:{credential:'not-allowed'},nested:{value:'not-allowed'}}],[]));
 assert.equal(result.format,'toolkit-browser-history-v1');assert.equal(result.rows.length,1);
 assert.equal(result.rows[0].favorite,true);assert.equal(result.rows[0].source,'mobile-ocr');
 assert.equal(result.rows[0].audioSha256,'1'.repeat(64));assert.equal(result.rows[0].hadAudio,true);
 assert.equal(result.rows[0].sourceLocale,'zh-Hans');
 assert.doesNotMatch(JSON.stringify(result),/private|credential|viewerLink|browserSettings|nested/);
});

test('export reads only exact history keys in a readonly transaction and closes the database',async()=>{
 const reads=[];let closed=false;
 const database={objectStoreNames:{contains:key=>key==='state'},close:()=>{closed=true;},
  transaction:(name,mode)=>{
   assert.equal(name,'state');assert.equal(mode,'readonly');
   const transaction={objectStore:()=>({get:key=>{
    reads.push(key);const request={};queueMicrotask(()=>{request.result=key==='history'?[row]:[];request.onsuccess();});return request;
   }})};setTimeout(()=>transaction.oncomplete(),0);return transaction;
  }};
 const indexedDB={open:name=>{assert.equal(name,'proxy-mobile-library');const request={result:database};
  queueMicrotask(()=>request.onsuccess());return request;}};
 const raw=await readHistory(indexedDB);
 assert.deepEqual(reads,['history','pc-history']);assert.equal(closed,true);assert.equal(JSON.parse(raw).rows.length,1);
});

test('empty, malformed or excessive archives fail without producing an export',()=>{
 assert.throws(()=>backup([],[]),/No saved history/);
 assert.throws(()=>backup(null,[]),/incomplete/);
 assert.throws(()=>backup([null],[]),/Invalid saved/);
 assert.throws(()=>backup(Array(12001).fill(row),[]),/too large/);
});

test('a missing old-origin database aborts creation instead of making or replacing a store',async()=>{
 let aborted=false;
 const indexedDB={open:()=>{const request={transaction:{abort:()=>{aborted=true;}}};
  queueMicrotask(()=>request.onupgradeneeded());return request;}};
 await assert.rejects(readHistory(indexedDB),/No existing/);assert.equal(aborted,true);
});
