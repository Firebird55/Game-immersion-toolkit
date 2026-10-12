import {test} from 'node:test';
import assert from 'node:assert/strict';
import {encryptKey,decryptKey,createVault,BACKGROUND_LOCK_MS} from '../public/mobile-capture/vault.mjs';
const phrase='twelve characters plus';
test('vault roundtrip, fresh randomness, wrong passphrase and authenticated damage',async()=>{
 const a=await encryptKey('test-only-key',phrase,phrase),b=await encryptKey('test-only-key',phrase,phrase);
 assert.equal(await decryptKey(a,phrase),'test-only-key');assert.notDeepEqual(a.salt,b.salt);assert.notDeepEqual(a.iv,b.iv);
 await assert.rejects(decryptKey(a,'wrong'));new Uint8Array(a.ciphertext)[0]^=1;await assert.rejects(decryptKey(a,phrase));
 await assert.rejects(encryptKey('key','short','short'));await assert.rejects(encryptKey('key',phrase,'different'));
 await assert.rejects(decryptKey({...b,iterations:1},phrase));
});
test('locking aborts requests, restore starts locked, replacement and forget',async()=>{
 const records=new Map(),storage={get:async k=>records.get(k),put:async(k,v)=>records.set(k,v),remove:async k=>records.delete(k)};
 let time=0,cleared=0;const vault=createVault(storage,{now:()=>time,onLock:()=>cleared++});
 await vault.connect('first',phrase,phrase);const signal=vault.signal;vault.visibility(true);time=BACKGROUND_LOCK_MS;vault.visibility(false);
 assert.equal(vault.unlocked,false);assert.equal(signal.aborted,true);assert.throws(()=>vault.credential());assert.ok(cleared);
 await vault.unlock(phrase);await vault.changePassphrase(phrase+'new',phrase+'new');vault.lock();await assert.rejects(vault.unlock(phrase));await vault.unlock(phrase+'new');
 assert.equal(createVault(storage).unlocked,false);await vault.connect('replacement',phrase,phrase);assert.equal(vault.credential(),'replacement');await vault.forget();assert.equal(await vault.exists(),false);
});
test('unavailable storage never leaves a key unlocked',async()=>{
 const vault=createVault({get:async()=>{throw Error('Unavailable');},put:async()=>{throw Error('Unavailable');}});
 await assert.rejects(vault.connect('test',phrase,phrase));assert.equal(vault.unlocked,false);
});
