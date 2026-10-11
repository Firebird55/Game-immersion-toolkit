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
 try{persistent=await navigator.storage?.persisted?.()??false;if(request&&!persistent)persistent=await navigator.storage?.persist?.()??false;estimate=await navigator.storage?.estimate?.()??{};}catch{}
 return {persistent,usage:estimate.usage??null,quota:estimate.quota??null};
}
