// Read authored subtitle -> Mandarin event links from installed cinematic
// timelines. This runs once per changed local catalog, outside the OCR process.
import {readFile,writeFile,rename,open}from'node:fs/promises';
import{join,resolve}from'node:path';import{pathToFileURL}from'node:url';import{createHash}from'node:crypto';import ts from'typescript';
import{sceneCatalog,cinematicBundleRanges}from'./scene-catalog.mjs';
import{cinematicVoicePairs}from'./cinematic-links.mjs';
const[gameArgument,toolsArgument]=process.argv.slice(2);
if(!gameArgument||!toolsArgument)throw Error('Pass installed game data and the private tool directory');
const game=resolve(gameArgument),tools=resolve(toolsArgument);
if(tools.toLowerCase().startsWith(game.toLowerCase()))throw Error('Generated files must stay outside the game');
const source=await readFile(join(tools,'galgame-perform.ts'),'utf8');
const signatures=[];
for(const[layer,name]of[['Persistent','res_version_persist'],['StreamingAssets','res_version']]){
 try{signatures.push(await readFile(join(game,layer,name),'utf8'));}catch{signatures.push('');}
}
const signature=createHash('sha256').update(JSON.stringify([1,source,signatures,
 await readFile(new URL('./cinematic-links.mjs',import.meta.url),'utf8'),
 await readFile(new URL('./scene-catalog.mjs',import.meta.url),'utf8')])).digest('hex');
const output=join(tools,'scene-links-cinematic.json'),statePath=join(tools,'cinematic-link-state.json');
try{
 const state=JSON.parse(await readFile(statePath,'utf8')),links=await readFile(output);
 if(state.signature===signature&&state.sha256===createHash('sha256').update(links).digest('hex')){
  console.log('Installed cinematic timeline links are current.');process.exit(0);
 }
}catch{/* An absent/incomplete cache must be rebuilt. */}
const readerPath=join(tools,'cinematic-reader.mjs');
await writeFile(readerPath,ts.transpileModule(source+'\nexport {unpackMhyFile};',{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText);
const{unpackMhyFile}=await import(pathToFileURL(readerPath).href);
async function local(name){for(const layer of['Persistent','StreamingAssets']){try{return await readFile(join(game,layer,name));}catch{}}}
let catalog;
for(const[layer,name]of[['Persistent','res_version_persist'],['StreamingAssets','res_version']]){
 let version;try{version=JSON.parse(await readFile(join(game,layer,name),'utf8'));}catch{continue;}
 for(const row of version.files??[]){
  if(row.tags?.length||!/^Blocks\/\d+\.blk$/.test(row.remoteName))continue;
  const compressed=await local(row.remoteName);if(compressed?.[0]!==31||compressed[1]!==139)continue;
  try{const current=sceneCatalog(compressed);if(!catalog||current.assets>catalog.assets)catalog=current;}catch{/* another catalog kind */}
 }
 if(catalog)break; // A complete current patch catalog supersedes the base.
}
if(!catalog)throw Error('Installed cinematic resource catalog was not found');
const groups=new Map();
for(const range of cinematicBundleRanges(catalog)){const list=groups.get(range.block)??[];list.push(range);groups.set(range.block,list);}
const links=new Map(),marker=Buffer.from('WwiseAudioClip'),subtitle=Buffer.from('CS_');let scanned=0;
for(const[block,ranges]of groups){
 let file;for(const layer of['Persistent','StreamingAssets']){try{file=await open(join(game,layer,block),'r');break;}catch{}}
 if(!file)continue; // Optional resources need not be installed on every PC.
 try{const total=(await file.stat()).size;
  for(const{offset,size}of ranges){
   if(offset+size>total)throw Error('Cinematic bundle exceeds installed block');
   const bytes=Buffer.alloc(size),read=await file.read(bytes,0,size,offset);
   if(read.bytesRead!==size)throw Error('Cinematic block changed during indexing');
   try{
    const result=unpackMhyFile(bytes,0);
    if(result.end!==size)continue;
    for(const cab of result.files){
     if(!cab.includes(marker)||!cab.includes(subtitle))continue;
     for(const pair of cinematicVoicePairs(Buffer.from(cab)))links.set(pair.text_id+'\0'+pair.event.toLowerCase(),pair);
    }
   }catch{/* Unsupported resource/object formats never supply a voice mapping. */}
   if(++scanned%100000===0)console.log(`Checked ${scanned.toLocaleString()} small local bundles; capture continues.`);
  }
 }finally{await file.close();}
}
if(!links.size)throw Error('No supported authored cinematic voice links were found; previous index kept');
const encoded=JSON.stringify([...links.values()]);await writeFile(output+'.pending',encoded);await rename(output+'.pending',output);
await writeFile(statePath+'.pending',JSON.stringify({signature,sha256:createHash('sha256').update(encoded).digest('hex')}));await rename(statePath+'.pending',statePath);
console.log(`Found ${links.size.toLocaleString()} authored Mandarin cinematic event links.`);
