import {openZip,readCatalog,validateVoices,readVoice,DialogueMatcher,searchCatalog} from './library.mjs';
import {get,put} from './storage.mjs';
let catalog=null, matcher=null, voices=new Map(), epoch=0;
const summary=()=>catalog?{manifest:catalog.manifest,rowCount:catalog.rows.length}:null;
self.onmessage=async({data})=>{
 const {id,action}=data;
 try{
  let result;
  if(action==='open'){
   const token=++epoch,opened=[];
   if(!Array.isArray(data.files)||data.files.length>1001)throw new Error('Select one catalog and its matching voice ZIPs.');
   for(let i=0;i<data.files.length;i++){
    self.postMessage({id,stage:`Checking ZIP ${i+1} of ${data.files.length}…`});
    opened.push(await openZip(data.files[i]));
    if(token!==epoch)throw new Error('File opening cancelled.');
   }
   const chosen=opened.filter(z=>z.manifest.kind==='catalog');if(chosen.length>1)throw new Error('Open one game catalog at a time.');
   const packs=opened.filter(z=>z.manifest.kind==='voices');if(new Set(packs.map(p=>p.manifest.id)).size!==packs.length)throw new Error('Select each voice pack only once.');
   const candidate=chosen.length?await readCatalog(chosen[0],count=>self.postMessage({id,progress:count})):catalog;
   if(!candidate)throw new Error('Select the catalog ZIP together with its voices.');
   if(data.expectedGame&&candidate.manifest.game!==data.expectedGame)throw new Error('Stop capture before opening a different game.');
   const incoming=new Map(chosen.length?[]:voices);
   for(const zip of packs)for(const sha of validateVoices(zip,candidate))incoming.set(sha,zip);
   if(token!==epoch)throw new Error('File opening cancelled.');
   self.postMessage({id,stage:'Preparing dialogue lookup…'});
   const lookup=new DialogueMatcher(candidate.rows);
   catalog=candidate;matcher=lookup;voices=incoming;
   result={catalog:summary(),available:[...voices.keys()],selectedBytes:[...new Set(voices.values())].reduce((n,z)=>n+z.file.size,0),selectedPacks:new Set(voices.values()).size};
  }else if(action==='restore'){
   const token=++epoch;
   const saved=data.catalog??await get('catalog');
   if(token!==epoch)throw new Error('Catalog restoration superseded by file selection.');
   if(saved){catalog=saved;matcher=new DialogueMatcher(catalog.rows);}voices.clear();result={catalog:summary(),available:[]};
  }else if(action==='cache'){if(!catalog)throw new Error('Open a catalog first.');await put('catalog',catalog);result=true;}
  else if(action==='search')result=catalog?searchCatalog(catalog.rows,data.text):{rows:[],total:0};
  else if(action==='match')result=matcher?matcher.match(data.text,data.channel,data.player,data.fragment):{state:'no_library'};
  else if(action==='match-candidates')result=matcher?matcher.matchCandidates(data.values,data.channel,data.player,data.fragment):{state:'no_library'};
  else if(action==='context-fragments')result=matcher?matcher.contextFragments(data.values):[];
  else if(action==='scene-matches')result=matcher?matcher.sceneMatches(data.values,data.groups):{matches:[],groups:[]};
  else if(action==='simultaneous-matches')result=matcher?matcher.simultaneousMatches(data.values,data.player,data.primary):[];
  else if(action==='match-context')result=matcher?matcher.matchContext(data.previous,data.values,data.channel,data.player):{state:'no_library'};
  else if(action==='voice'){const zip=voices.get(data.sha);if(!zip)throw new Error('Reselect the voice ZIPs from Files, keeping a USB drive connected if used.');result=await readVoice(zip,data.sha);}
  else if(action==='cancel-open'){epoch++;result=true;}
  else if(action==='forget'){epoch++;catalog=null;matcher=null;voices.clear();result=true;}
  else throw new Error('Unknown library action.');
  self.postMessage({id,result});
 }catch(error){self.postMessage({id,error:error.message});}
};
