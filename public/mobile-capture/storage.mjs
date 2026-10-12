const database=new Promise((resolve,reject)=>{
 const request=indexedDB.open('proxy-mobile-library',1);
 request.onupgradeneeded=()=>request.result.createObjectStore('state');
 request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
});
database.catch(()=>{});
export async function get(key){const db=await database;return new Promise((resolve,reject)=>{const r=db.transaction('state').objectStore('state').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function put(key,value){const db=await database;return new Promise((resolve,reject)=>{const tx=db.transaction('state','readwrite');tx.objectStore('state').put(value,key);tx.oncomplete=()=>resolve();tx.onabort=tx.onerror=()=>reject(tx.error);});}
export async function remove(key){const db=await database;return new Promise((resolve,reject)=>{const tx=db.transaction('state','readwrite');tx.objectStore('state').delete(key);tx.oncomplete=()=>resolve();tx.onabort=tx.onerror=()=>reject(tx.error);});}
export async function storageStatus(request=false){
 let persistent=false,estimate={};
 async function bounded(call,fallback){let timer;try{return await Promise.race([call(),new Promise(resolve=>{timer=setTimeout(()=>resolve(fallback),2000);})])??fallback;}finally{clearTimeout(timer);}}
 try{persistent=await bounded(()=>navigator.storage?.persisted?.(),false);estimate=await bounded(()=>navigator.storage?.estimate?.(),{});if(request&&!persistent)persistent=await bounded(()=>navigator.storage?.persist?.(),false);}catch{}
 return {persistent,usage:estimate.usage??null,quota:estimate.quota??null};
}
export function cacheBudget(manifest,state){
 const bytes=manifest?.catalog?.reduce((n,p)=>n+p.size,0)??0;
 const needed=bytes*3+32*1024**2; // IndexedDB object overhead and application headroom.
 const remaining=Number.isFinite(state.quota)&&Number.isFinite(state.usage)?Math.max(0,state.quota-state.usage):null;
 return {needed,remaining,sufficient:remaining==null?null:remaining>=needed};
}
