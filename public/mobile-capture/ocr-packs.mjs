import {get,put,remove} from './storage.mjs';
let manifestPromise;
export function manifest(){return manifestPromise??=fetch(new URL('./ocr-models.json',import.meta.url)).then(r=>{if(!r.ok)throw Error('OCR model list unavailable.');return r.json();}).catch(error=>{manifestPromise=null;throw error;});}
const key=(code,model)=>`ocr-model:${code}:${model.sha256}`;
export async function verifyModel(bytes,model){
 if(bytes.byteLength!==model.bytes)throw Error('OCR model size does not match the manifest.');
 const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
 if(sha!==model.sha256)throw Error('OCR model checksum does not match. Retry the download.');
 return bytes;
}
export async function modelStatus(code){
 const model=(await manifest()).models[code];if(!model)throw Error('Unsupported OCR language.');
 const saved=await get(key(code,model));
 return {...model,installed:model.builtin||!!saved,storedBytes:saved?.byteLength??0};
}
export async function loadModel(code,{download=false,onProgress=()=>{}}={}){
 const model=(await manifest()).models[code];if(!model)throw Error('Unsupported OCR language.');
 const saved=await get(key(code,model));
 if(saved)return {code,data:new Uint8Array(await verifyModel(saved,model))};
 if(!download&&!model.builtin)throw Error('Download the selected OCR language pack first.');
 const response=await fetch(new URL(model.url,import.meta.url),{credentials:'omit',referrerPolicy:'no-referrer'});
 if(!response.ok)throw Error(`OCR download failed (${response.status}). Retry when connected.`);
 const reader=response.body.getReader(),chunks=[];let size=0;
 for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>model.bytes){await reader.cancel();throw Error('OCR download exceeds its declared size.');}chunks.push(value);onProgress(size/model.bytes);}
 const data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
 await verifyModel(data,model);
 if(!model.builtin)await put(key(code,model),data.buffer);
 return {code,data};
}
export async function removeModel(code){
 const model=(await manifest()).models[code];if(!model||model.builtin)throw Error('Bundled OCR languages are part of the application.');
 await remove(key(code,model));
}
