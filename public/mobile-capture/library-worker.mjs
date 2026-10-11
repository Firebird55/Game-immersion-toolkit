import {openZip,readCatalog,validateVoices,readVoice,DialogueMatcher} from './library.mjs';
let catalog=null, matcher=null, voices=new Map(), epoch=0;
self.onmessage=async({data})=>{
 const {id,action}=data;
 try{
  let result;
  if(action==='open'){
   const token=++epoch, opened=[];for(const file of data.files)opened.push(await openZip(file));
   const chosen=opened.filter(z=>z.manifest.kind==='catalog');if(chosen.length>1)throw new Error('Open one game catalog at a time.');
   const candidate=chosen.length?await readCatalog(chosen[0],count=>self.postMessage({progress:count})):catalog;
   if(!candidate)throw new Error('Select the catalog ZIP together with its voices.');
   if(data.expectedGame&&candidate.manifest.game!==data.expectedGame)throw new Error('Stop capture before opening a different game.');
   const incoming=new Map(chosen.length?[]:voices);
   for(const zip of opened.filter(z=>z.manifest.kind==='voices'))for(const sha of validateVoices(zip,candidate))incoming.set(sha,zip);
   if(token!==epoch)throw new Error('File selection superseded.');
   catalog=candidate;matcher=new DialogueMatcher(candidate.rows);voices=incoming;
   result={catalog,available:[...voices.keys()],selectedBytes:[...new Set(voices.values())].reduce((n,z)=>n+z.file.size,0),selectedPacks:new Set(voices.values()).size};
  }else if(action==='restore'){catalog=data.catalog;matcher=new DialogueMatcher(catalog.rows);voices.clear();result={catalog,available:[]};}
  else if(action==='match')result=matcher?matcher.match(data.text,data.channel,data.player,data.fragment):{state:'no_library'};
  else if(action==='voice'){const zip=voices.get(data.sha);if(!zip)throw new Error('Reselect the voice ZIPs from On My iPhone.');result=await readVoice(zip,data.sha);}
  else if(action==='forget'){epoch++;catalog=null;matcher=null;voices.clear();result=true;}
  else throw new Error('Unknown library action.');
  self.postMessage({id,result});
 }catch(error){self.postMessage({id,error:error.message});}
};
