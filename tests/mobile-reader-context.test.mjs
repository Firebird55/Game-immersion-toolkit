import test from 'node:test';
import assert from 'node:assert/strict';
import {createReadingSession} from '../vendor/lexirise-components/dist/session.js';
import {createMobileReaderContext,effectiveTarget} from '../mobile/reader-context.mjs';
const settings=()=>({languages:['zh','nl','de'],global:{effectiveTranslationLanguage:'en'},languageSettings:{nl:{effectiveTranslationLanguage:'zh-hans'},de:{effectiveTranslationLanguage:'nl'}}});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function fixture(){
 let value=settings(),blocked=null;
 const calls=[];
 const owner=createMobileReaderContext({createSession:createReadingSession,createReader:adapter=>({...adapter,resetReadingCaches(){}}),request:async(path,method,payload,signal)=>{
  calls.push({path,method,payload,signal});
  if(blocked?.path===path){const hold=blocked;blocked=null;await hold.promise;}
  const data=path==='/v1/settings'?structuredClone(value):path==='/v1/analyze/text'?{occurrences:[{word:'Een',charStart:0,charEnd:3,isWordLike:true,entryId:1}],entryMetaById:{1:{gloss:'fixture'}}}:{translations:[{target_lang:'en',translation:'English choice'},{target_lang:'zh-hans',translation:'中文选择'},{target_lang:'nl',translation:'Nederlandse keuze'}]};
  return {status:200,response:data};
 }});
 return {owner,calls,setSettings:next=>value=next,hold(path){const d=deferred();blocked={path,...d};return d;}};
}
const row={game:'beyond',sourceLocale:'nl',sourceLanguage:'nl'};
async function lookup(pair){return (await pair.session.requestReading('Een','lookup',{start:0})).json();}
test('pinned shared session resolves per-language target before creation, including multiple lookup targets',async()=>{
 const f=fixture();assert.equal(f.owner.pair(row),null);await f.owner.reload();
 for(const [language,target,meaning] of [['nl','zh-hans','中文选择'],['de','nl','Nederlandse keuze'],['zh','en','English choice']]){
  const pair=f.owner.pair({...row,sourceLanguage:language});const result=await lookup(pair);
  assert.equal(pair.translationLanguage,target);assert.equal(result.translationLanguage,target);assert.equal(result.translations[0].meaning,meaning);
 }
 f.owner.reset();
});
test('cache/session ownership includes source locale, game, account generation and effective settings',async()=>{
 const f=fixture();await f.owner.reload();const a=f.owner.pair(row);
 assert.equal(f.owner.pair(row),a);assert.notEqual(f.owner.pair({...row,game:'heavyrain'}),a);assert.notEqual(f.owner.pair({...row,sourceLocale:'de'}),a);
 const oldGeneration=f.owner.generation;f.owner.reset();assert.equal(f.owner.pair(row),null);await f.owner.reload();assert.notEqual(f.owner.generation,oldGeneration);assert.notEqual(f.owner.pair(row),a);
 f.owner.reset();
});
test('target changes cancel an actual pending shared lookup even if transport ignores abort',async()=>{
 const f=fixture();await f.owner.reload();const old=f.owner.pair(row),hold=f.hold('/v1/dictionary/lookup');
 const pending=lookup(old);const rejected=assert.rejects(pending,/changed|locked/i);
 while(!f.calls.some(c=>c.path==='/v1/dictionary/lookup'))await new Promise(r=>setImmediate(r));
 const next=settings();next.languageSettings.nl.effectiveTranslationLanguage='nl';f.setSettings(next);await f.owner.reload();
 hold.resolve();await rejected;const current=f.owner.pair(row);assert.notEqual(current,old);assert.equal((await lookup(current)).translationLanguage,'nl');
 f.owner.reset();
});
test('lock/account replacement rejects late settings and permits a fresh same-language session',async()=>{
 const f=fixture(),hold=f.hold('/v1/settings');const first=f.owner.reload(),rejected=assert.rejects(first,{name:'AbortError'});
 f.owner.reset();await f.owner.reload();const replacement=f.owner.pair(row);hold.resolve();await rejected;assert.equal(f.owner.pair(row),replacement);f.owner.reset();
});
test('missing effective target is actionable and never silently replaced by English',()=>{
 assert.throws(()=>effectiveTarget({global:{},languageSettings:{}},'nl'),/Reload/);
 assert.equal(effectiveTarget(settings(),'nl'),'zh-hans');
});
