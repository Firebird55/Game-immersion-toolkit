// Consumer ownership of account, source and effective target context. Shared
// sessions fix their target at construction, so settings must resolve first.
export function effectiveTarget(settings, language) {
 const target=settings.languageSettings?.[language]?.effectiveTranslationLanguage || settings.global?.effectiveTranslationLanguage;
 if(typeof target!=='string'||!target.trim())throw Error('Reload Lexirise settings to determine the translation language.');
 return target;
}
function validateSettings(value) {
 if(!value||!Array.isArray(value.languages)||!value.global||typeof value.global!=='object'||!value.languageSettings||typeof value.languageSettings!=='object')throw Error('Lexirise returned invalid settings.');
 return structuredClone(value);
}
export function createMobileReaderContext({request,createSession,createReader,onChange=()=>{}}) {
 let generation=0,revision=0,settings=null,controller=new AbortController(),pending=null;
 const pairs=new Map();
 const stale=()=>new DOMException('Reading context changed.','AbortError');
 function clear() {
  revision++;controller.abort();controller=new AbortController();pending=null;
  for(const pair of pairs.values()){pair.session.dispose();pair.reader.resetReadingCaches();}
  pairs.clear();settings=null;onChange();
 }
 function assertCurrent(token){if(token!==revision)throw stale();}
 async function readSettings(method='GET',payload) {
  if(method==='GET'&&pending)return pending;
  clear();const token=revision,signal=controller.signal;
  const task=(async()=>{
   const response=await request('/v1/settings',method,payload,signal);assertCurrent(token);
   if(response.status<200||response.status>=300)throw Error('Lexirise settings could not be loaded. Retry in account settings.');
   const value=validateSettings(response.responseText?JSON.parse(response.responseText):response.response);
   for(const language of value.languages)effectiveTarget(value,language);
   assertCurrent(token);settings=value;onChange();return value;
  })();pending=task;
  try{return await task;}finally{if(pending===task)pending=null;}
 }
 return {
  get ready(){return settings!==null;},
  get generation(){return generation;},
  reset(){generation++;clear();},
  reload:()=>readSettings(),
  patch:changes=>readSettings('PATCH',changes),
  pair({game='',sourceLocale='zh-Hans',sourceLanguage='zh'}={}) {
   if(!settings)return null;
   let target;try{target=effectiveTarget(settings,sourceLanguage);}catch{return null;}
   const settingsVersion=JSON.stringify([settings.global,settings.languageSettings,settings.languages]);
   const key=JSON.stringify([generation,game,sourceLocale,sourceLanguage,target,settingsVersion]);
   if(!pairs.has(key)) {
    const token=revision,value=settings,signal=controller.signal;
    const session=createSession({sourceLanguage,translationLanguage:target,request:async(path,method,payload,sessionSignal)=>{
     assertCurrent(token);
     const result=await request(path,method,payload,AbortSignal.any([signal,sessionSignal]));
     assertCurrent(token);return result;
    }});
    const reader=createReader({sourceLanguage,translationLanguage:target,loadSettings:async()=>{assertCurrent(token);return value;},request:async(...args)=>{
     assertCurrent(token);const result=await session.requestReading(...args);assertCurrent(token);return result;
    }});
    pairs.set(key,{session,reader,key,translationLanguage:target});
   }
   return pairs.get(key);
  }
 };
}
