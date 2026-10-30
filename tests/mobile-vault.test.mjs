import {test} from 'node:test';
import assert from 'node:assert/strict';
import {encryptKey,decryptKey,createVault,BACKGROUND_LOCK_MS} from '../public/mobile-capture/vault.mjs';
const phrase='twelve characters plus';
test('vault roundtrip, fresh randomness, wrong passphrase and authenticated damage',async()=>{
 const a=await encryptKey('test-only-key',phrase,phrase),b=await encryptKey('test-only-key',phrase,phrase);
 assert.equal(await decryptKey(a,phrase),'test-only-key');assert.notDeepEqual(a.salt,b.salt);assert.notDeepEqual(a.iv,b.iv);
 await assert.rejects(decryptKey(a,'wrong'));new Uint8Array(a.ciphertext)[0]^=1;await assert.rejects(decryptKey(a,phrase));
 await assert.rejects(encryptKey('key','abc','abc'));await assert.rejects(encryptKey('key',phrase,'different'));
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
test('a lock during derivation cannot restore an unlocked session',async()=>{
 const record=await encryptKey('test-key',phrase,phrase),vault=createVault({get:async()=>record});
 const attempt=vault.unlock(phrase);vault.lock();await assert.rejects(attempt,/cancelled/);assert.equal(vault.unlocked,false);
});

test('four-character passwords and encrypted viewer linking survive reload without storing the code',async()=>{
 const records=new Map(),storage={get:async k=>records.get(k),put:async(k,v)=>records.set(k,v),remove:async k=>records.delete(k)};
 const vault=createVault(storage);await vault.connect('mock-key','1234','1234');
 await vault.linkViewer('testCode42');vault.lock();
 const restored=createVault(storage);await restored.unlockViewer('testCode42');assert.equal(restored.credential(),'mock-key');
 assert(!JSON.stringify([...records]).includes('testCode42'));
 restored.lock();await assert.rejects(restored.unlockViewer('wrong'));assert.equal(restored.unlocked,false);
 await restored.unlock('1234');await restored.changePassphrase('5678','5678');restored.lock();
 await assert.rejects(restored.unlockViewer('testCode42'));await restored.unlockViewer('5678');
 await restored.forget();assert.equal(records.size,0);
});

test('trusted device restores without password, opt-out preserves encrypted vault, forget clears both',async()=>{
 const records=new Map(),storage={get:async k=>records.get(k),put:async(k,v)=>records.set(k,v),remove:async k=>records.delete(k)};
 const vault=createVault(storage);await vault.connect('mock-trusted',phrase,phrase);const encrypted=records.get('lexirise-vault');
 await vault.remember(true);const next=createVault(storage);assert(await next.restoreRemembered());assert.equal(next.credential(),'mock-trusted');
 await next.remember(false);assert.equal(await createVault(storage).restoreRemembered(),false);assert.deepEqual(records.get('lexirise-vault'),encrypted);
 await next.connectRemembered('mock-replacement');assert.equal(await next.exists(),false);await next.forget();assert.equal(records.size,0);
});
test('late trusted restore and queued save cannot defeat forgetting',async()=>{
 let release;const records=new Map(),storage={get:async()=>new Promise(r=>{release=r;}),put:async(k,v)=>records.set(k,v),remove:async k=>records.delete(k)};
 const vault=createVault(storage);const restoring=vault.restoreRemembered();await new Promise(r=>setTimeout(r,0));vault.lock();release({version:1,key:'mock-key'});assert.equal(await restoring,false);
 const saving=vault.connectRemembered('mock-key');const forgetting=vault.forget();await assert.rejects(saving,/cancelled/);await forgetting;assert.equal(records.size,0);assert.equal(vault.unlocked,false);
});
