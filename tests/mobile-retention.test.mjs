import test from 'node:test';
import assert from 'node:assert/strict';
import {createLibraryStore} from '../public/mobile-capture/retained-library.mjs';
function fixture(){
 const values=new Map(),folders=new Map();let fail=false;
 const directory={async getDirectoryHandle(name,{create=false}={}){if(!folders.has(name)){if(!create)throw Error('missing');folders.set(name,new Map());}const entries=folders.get(name);return {async getFileHandle(name,{create=false}={}){if(!entries.has(name)){if(!create)throw Error('missing');entries.set(name,new Uint8Array());}return {async createSyncAccessHandle(){return {write(bytes,{at}){if(fail)throw Error('quota');const old=entries.get(name),next=new Uint8Array(Math.max(old.length,at+bytes.length));next.set(old);next.set(bytes,at);entries.set(name,next);return bytes.length;},flush(){},close(){}};},async getFile(){return new File([entries.get(name)],name);}};}};},async removeEntry(name){folders.delete(name);},async *[Symbol.asyncIterator](){for(const entry of folders)yield entry;}};
 const storage={get:async key=>structuredClone(values.get(key)),put:async(key,value)=>{values.set(key,structuredClone(value));}};
 const store=createLibraryStore({storage,directory:async()=>({getDirectoryHandle:async()=>directory}),exclusive:fn=>fn()});
 return {store,folders,setFail:value=>{fail=value;}};
}
const metadata=id=>({id,game:id,sourceLocale:'ja',audioLocale:'ja',translationLocale:'en',revision:'r1',title:id});
test('retains several libraries, restores last and only removes its own copy',async()=>{
 const {store,folders}=fixture();await store.save([new File(['first'],'first.zip')],metadata('one'));await store.save([new File(['second'],'second.zip')],metadata('two'));
 assert.equal(await(await store.files()).files[0].text(),'second');await store.select('one');assert.equal((await store.files()).item.id,'one');
 await store.remove('two');assert.equal((await store.list()).items.length,1);assert.equal(folders.size,1);
});
test('quota and cancellation cannot replace a working copy; orphan cleanup preserves registry',async()=>{
 const {store,folders,setFail}=fixture();await store.save([new File(['good'],'first.zip')],metadata('one'));
 setFail(true);await assert.rejects(store.save([new File(['bad'],'update.zip')],metadata('one')),/quota/);setFail(false);
 let guards=0;await assert.rejects(store.save([new File(['bad'],'update.zip')],metadata('one'),()=>{if(++guards===3)throw Error('cancelled');}),/cancelled/);
 assert.equal(await(await store.files()).files[0].text(),'good');assert.equal(folders.size,1);
 folders.set(crypto.randomUUID(),new Map());folders.set('unrelated',new Map());await store.cleanup();assert.equal(folders.size,2);
 const saved=await store.list();folders.delete(saved.items[0].folder);await assert.rejects(store.files(),/Update from file/);assert.deepEqual(await store.list(),saved);
});
