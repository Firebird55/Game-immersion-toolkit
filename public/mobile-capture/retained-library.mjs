// Browser-owned copies, independent of temporary permissions from the Files picker.
import {get,put} from './storage.mjs';
const KEY='retained-libraries-v1',ROOT='retained-libraries-v1',CHUNK=4*1024*1024;
const safe=name=>/^[a-f0-9-]{36}$/.test(name);
const empty=()=>({version:1,last:null,items:[]});
export function createLibraryStore({storage={get,put},directory=()=>navigator.storage.getDirectory(),exclusive=fn=>navigator.locks.request(ROOT,fn)}={}){
 const registry=async()=>{const saved=await storage.get(KEY);return saved?.version===1&&Array.isArray(saved.items)?saved:empty();};
 const root=async()=> (await directory()).getDirectoryHandle(ROOT,{create:true});
 const removeFolder=async(folder)=>{if(safe(folder))await (await root()).removeEntry(folder,{recursive:true}).catch(()=>{});};
 return {
  list:registry,
  async cleanup(){return exclusive(async()=>{const saved=await registry(),used=new Set(saved.items.map(i=>i.folder));for await(const [name]of await root())if(safe(name)&&!used.has(name))await removeFolder(name);});},
  async files(id){const saved=await registry(),item=saved.items.find(i=>i.id===(id??saved.last));if(!item)return null;
   if(!safe(item.folder))throw Error('Invalid retained library. Select the original ZIP again.');
   try{const folder=await(await root()).getDirectoryHandle(item.folder);const files=[];for(let i=0;i<item.files.length;i++){const file=await(await folder.getFileHandle(String(i))).getFile();if(file.size!==item.files[i].size)throw Error();files.push(new File([file],item.files[i].name));}return {item,files};}
   catch{throw Error('The saved library is no longer on this device. Use Update from file to restore it. Your history and library selection are preserved.');}
  },
  async save(files,metadata,guard=()=>{},progress=()=>{}){return exclusive(async()=>{
   guard();const saved=await registry(),folderName=crypto.randomUUID(),folder=await(await root()).getDirectoryHandle(folderName,{create:true});let committed=false;
   try{let copied=0;const total=files.reduce((n,f)=>n+f.size,0);
    for(let i=0;i<files.length;i++){const handle=await(await folder.getFileHandle(String(i),{create:true})).createSyncAccessHandle();try{for(let offset=0;offset<files[i].size;offset+=CHUNK){guard();const bytes=new Uint8Array(await files[i].slice(offset,offset+CHUNK).arrayBuffer());guard();let written=0;while(written<bytes.length){const n=handle.write(bytes.subarray(written),{at:offset+written});if(!n)throw Error('Retained library write failed.');written+=n;}copied+=bytes.length;progress(`Keeping library on this device: ${Math.round(100*copied/total)}%`);}handle.flush();}finally{handle.close();}}
    guard();const item={...metadata,folder:folderName,files:files.map(f=>({name:f.name,size:f.size})),bytes:total,lastSelected:Date.now()};
    await storage.put(KEY,{version:1,last:item.id,items:[...saved.items.filter(i=>i.id!==item.id),item]});
    try{guard();}catch(error){await storage.put(KEY,saved);throw error;}
    committed=true;
    // Keep the previous open file usable until this worker has handed off the
    // replacement. The next startup removes unreferenced, completed copies too.
    return item;
   }finally{if(!committed)await removeFolder(folderName);}
  });},
  async select(id){return exclusive(async()=>{const saved=await registry();if(saved.items.some(i=>i.id===id))await storage.put(KEY,{...saved,last:id});});},
  async remove(id){return exclusive(async()=>{const saved=await registry(),item=saved.items.find(i=>i.id===id);await storage.put(KEY,{...saved,last:saved.last===id?null:saved.last,items:saved.items.filter(i=>i.id!==id)});if(item)await removeFolder(item.folder);});}
 };
}
