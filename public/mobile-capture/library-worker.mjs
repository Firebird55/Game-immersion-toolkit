import {openLibraryFiles,readCatalog,validateVoices,readVoice,refreshHistoryVoices,DialogueMatcher,searchCatalog} from './library.mjs';
import {createLibraryStore} from './retained-library.mjs';
import {get,put} from './storage.mjs';
const retained=createLibraryStore();
let catalog=null, matcher=null, voices=new Map(), epoch=0,sourceFiles=[],selectedLibrary=null;
const cleanup=retained.cleanup().catch(()=>{});
const summary=()=>catalog?{manifest:catalog.manifest,rowCount:catalog.rows.length}:null;
self.onmessage=async({data})=>{
 const {id,action}=data;
 try{
  let result;
  if(action==='open'||action==='open-retained'||action==='restore'){
   const token=++epoch,guard=()=>{if(token!==epoch)throw Error('File opening cancelled.');};
   await cleanup;guard();let retainedItem=null;
   if(action!=='open'){
    try{const stored=await retained.files(data.libraryId);guard();if(stored){data.files=stored.files;retainedItem=stored.item;}}
    catch(error){if(action!=='restore')throw error;result={warning:error.message};}
    if(!data.files){const saved=data.catalog??await get('catalog');guard();if(saved){catalog=saved;matcher=new DialogueMatcher(saved.rows,saved.manifest.game);}voices.clear();self.postMessage({id,result:{...result,catalog:summary(),available:[],libraries:await retained.list()}});return;}
   }
   if(!Array.isArray(data.files)||!data.files.length||data.files.length>1001)throw new Error('Open one mobile library file, or an older catalog with its voice ZIPs.');
   const opened=await openLibraryFiles(data.files,stage=>self.postMessage({id,stage}),()=>{if(token!==epoch)throw new Error('File opening cancelled.');});
   const chosen=opened.filter(z=>z.manifest.kind==='catalog');if(chosen.length>1)throw new Error('Open one game catalog at a time.');
   const packs=opened.filter(z=>z.manifest.kind==='voices');if(new Set(packs.map(p=>p.manifest.id)).size!==packs.length)throw new Error('Select each voice pack only once.');
   const candidate=chosen.length?await readCatalog(chosen[0],count=>{if(token!==epoch)throw new Error('File opening cancelled.');self.postMessage({id,progress:count});}):catalog;
   if(!candidate)throw new Error('These are voice-only ZIPs. Also select the Catalog ZIP, or open the new single Mobile Library ZIP.');
   if(data.expectedGame&&candidate.manifest.game!==data.expectedGame)throw new Error('Stop capture before opening a different game.');
   const incoming=new Map(chosen.length?[]:voices);
   for(const zip of packs)for(const sha of validateVoices(zip,candidate))incoming.set(sha,zip);
   if(token!==epoch)throw new Error('File opening cancelled.');
   self.postMessage({id,stage:'Preparing dialogue lookup…'});
   const lookup=new DialogueMatcher(candidate.rows,candidate.manifest.game);
   let warning=null;
   const allFiles=chosen.length?data.files:[...sourceFiles,...data.files];
   const row=candidate.rows[0]??{},metadata={id:JSON.stringify([candidate.manifest.game,row.sourceLocale??'zh-Hans',row.audioLocale??'zh-Hans',row.translationLocale??'en']),game:candidate.manifest.game,title:candidate.manifest.title,sourceLocale:row.sourceLocale??'zh-Hans',audioLocale:row.audioLocale??'zh-Hans',translationLocale:row.translationLocale??'en',revision:candidate.manifest.revision};
   if(data.keep){try{if(!chosen.length&&!sourceFiles.length)throw Error('Select the catalog and voices together to keep this library.');retainedItem=await retained.save(allFiles,metadata,guard,stage=>self.postMessage({id,stage}));}catch(error){guard();warning='This library works this session, but could not be kept on this device. '+error.message;}}
   guard();if(retainedItem)await retained.select(retainedItem.id);guard();
   catalog=candidate;matcher=lookup;voices=incoming;sourceFiles=allFiles;selectedLibrary=retainedItem?.id??null;
   result={warning,libraries:await retained.list(),selectedLibrary,catalog:summary(),available:[...voices.keys()],selectedBytes:[...new Set(voices.values())].reduce((n,z)=>n+z.file.size,0),selectedPacks:new Set(voices.values()).size};
  }else if(action==='refresh-history'){result=catalog?refreshHistoryVoices(data.history,catalog):data.history;
  }else if(action==='cache'){if(!catalog)throw new Error('Open a catalog first.');await put('catalog',catalog);result=true;}
  else if(action==='list-retained')result=await retained.list();
  else if(action==='remove-retained'){epoch++;await retained.remove(data.libraryId??selectedLibrary);result=await retained.list();}
  else if(action==='search')result=catalog?searchCatalog(catalog.rows,data.text):{rows:[],total:0};
  else if(action==='match')result=matcher?matcher.match(data.text,data.channel,data.player,data.fragment):{state:'no_library'};
  else if(action==='match-candidates')result=matcher?matcher.matchCandidates(data.values,data.channel,data.player,data.fragment):{state:'no_library'};
  else if(action==='context-fragments')result=matcher?matcher.contextFragments(data.values):[];
  else if(action==='scene-matches')result=matcher?matcher.sceneMatches(data.values,data.groups):{matches:[],groups:[]};
  else if(action==='comic-matches')result=matcher?matcher.comicMatches(data.values,data.player):[];
  else if(action==='simultaneous-matches')result=matcher?matcher.simultaneousMatches(data.values,data.player,data.primary):[];
  else if(action==='match-context')result=matcher?matcher.matchContext(data.previous,data.values,data.channel,data.player):{state:'no_library'};
  else if(action==='voice'){const zip=voices.get(data.sha);if(!zip)throw new Error('Reopen your mobile library from Files to play voices. Keep a USB drive connected if used.');result=await readVoice(zip,data.sha);}
  else if(action==='cancel-open'){epoch++;result=true;}
  else if(action==='forget'){epoch++;catalog=null;matcher=null;voices.clear();result=true;}
  else throw new Error('Unknown library action.');
  self.postMessage({id,result});
 }catch(error){self.postMessage({id,error:error.message});}
};
