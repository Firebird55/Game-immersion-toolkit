// Stateless, fixed-origin transport. Never log request/response material.
const UPSTREAM='https://api.lexirise.app';
const languages=new Set('zh yue nan ja ko en es fr de it pt ru id ar hi ta th vi tr nl pl cs ro hu sv no da fi la grc lzh'.split(' '));
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const string=(v,max=1600)=>typeof v==='string'&&v.length>0&&v.length<=max;
const id=v=>Number.isSafeInteger(v)&&v>0;
function fields(v,allowed,required=[]){if(!object(v)||Object.keys(v).some(k=>!allowed.includes(k))||required.some(k=>!Object.hasOwn(v,k)))throw Error('Invalid fields.');}
function assert(ok){if(!ok)throw Error('Invalid input.');}
function settings(p){
 fields(p,['languages','global','languageSettings']);
 if(p.languages)assert(Array.isArray(p.languages)&&p.languages.length>0&&p.languages.length<=31&&p.languages.every(l=>languages.has(l)));
 if(p.global){fields(p.global,['translationLanguage','interfaceLanguage','disableWordPopups','wordPopupOpenMode','useCustomProficiencyColors','customProficiencyColors']);}
 if(p.languageSettings){assert(object(p.languageSettings));for(const [lang,value] of Object.entries(p.languageSettings)){assert(languages.has(lang));fields(value,'readingAid readingAboveWords script inlineGlossMode coloringMode toneColorPreset customToneColors colorKnownWordsToo emphasizeFrequencyLevel wordSpacing ttsOnWordClick automaticGrammarHighlighting highlightProperNouns customFont fontSize segmentByCharacter dictionariesEnabled dictionaries wordPopup'.split(' '));}}
 // Bound nested data, disallow dangerous object keys; upstream validates its enums.
 const visit=(v,depth=0)=>{assert(depth<8);if(Array.isArray(v)){assert(v.length<=100);v.forEach(x=>visit(x,depth+1));}else if(object(v)){assert(Object.keys(v).length<=64);for(const [k,x] of Object.entries(v)){assert(!['__proto__','constructor','prototype'].includes(k));visit(x,depth+1);}}else assert(v===null||typeof v==='boolean'||typeof v==='number'&&Number.isFinite(v)||typeof v==='string'&&v.length<=256);};visit(p);
}
export function operation(value){
 fields(value,['path','method','payload'],['path','method']);
 const {path,method,payload:p}=value;assert(typeof path==='string'&&path.length<=3000&&['GET','POST','PATCH'].includes(method));
 assert(path.startsWith('/v1/')&&!/[#\\]/.test(path));
 const url=new URL(path,UPSTREAM);assert(url.origin===UPSTREAM&&url.pathname===path.split('?')[0]);
 const route=url.pathname;
 if(method==='GET'){
  assert(p===undefined);assert(['/v1/me','/v1/settings','/v1/decks','/v1/vocabulary'].includes(route)||/^\/v1\/(?:vocabulary|decks)\/[1-9]\d{0,12}$/.test(route));
  for(const [k,v] of url.searchParams){assert(['language','mode','search','limit','offset'].includes(k)&&url.searchParams.getAll(k).length===1);if(k==='language')assert(languages.has(v));if(k==='mode')assert(['words','sentences'].includes(v));if(k==='search')assert(string(v));if(k==='limit')assert(/^\d+$/.test(v)&&+v>=1&&+v<=100);if(k==='offset')assert(/^\d+$/.test(v)&&+v<=1000000);}
 }else{
  assert(!url.search);assert(object(p));
  if(route==='/v1/settings'&&method==='PATCH')settings(p);
  else if(['/v1/analyze/text','/v1/analyze/context','/v1/dictionary/lookup'].includes(route)&&method==='POST'){
   fields(p,route==='/v1/analyze/context'?['text','language','word','question']:route==='/v1/analyze/text'?['text','language','fast']:['text','language'],['text','language']);assert(string(p.text)&&languages.has(p.language));if(p.fast!==undefined)assert(typeof p.fast==='boolean');if(p.word!==undefined)assert(string(p.word,256));if(p.question!==undefined)assert(string(p.question,2000));
  }else if(route==='/v1/vocabulary'&&method==='POST'){
   fields(p,['text','language','mode','translation','notes','tags','audioUrls','proficiency'],['text','language','mode']);assert(string(p.text)&&languages.has(p.language)&&['word','sentence'].includes(p.mode));vocabulary(p);
  }else if(/^\/v1\/vocabulary\/[1-9]\d{0,12}$/.test(route)&&method==='PATCH'){
   fields(p,['proficiency','audioUrls']);assert(Object.keys(p).length>0);vocabulary(p);
  }else if(route==='/v1/decks'&&method==='POST'){
   fields(p,['title','language','unit_type','deck_type','import_items'],['title','language','unit_type','deck_type','import_items']);assert(string(p.title,120)&&languages.has(p.language)&&p.unit_type==='sentence'&&p.deck_type==='snapshot'&&Array.isArray(p.import_items)&&p.import_items.length===0);
  }else if(/^\/v1\/decks\/[1-9]\d{0,12}\/items$/.test(route)&&method==='POST'){
   fields(p,['saved_expression_selection'],['saved_expression_selection']);const s=p.saved_expression_selection;fields(s,['mode','ids'],['mode','ids']);assert(s.mode==='explicit'&&Array.isArray(s.ids)&&s.ids.length>=1&&s.ids.length<=20&&s.ids.every(id));
  }else throw Error('Unsupported operation.');
 }
 return {url:url.href,method,body:method==='GET'?undefined:JSON.stringify(p)};
}
function vocabulary(p){
 if(p.proficiency!==undefined)assert([1,2,3,4].includes(p.proficiency));
 for(const k of ['translation','notes'])if(p[k]!==undefined)assert(typeof p[k]==='string'&&p[k].length<=4000);
 if(p.tags!==undefined)assert(Array.isArray(p.tags)&&p.tags.length<=10&&p.tags.every(t=>string(t,80)));
 if(p.audioUrls!==undefined)assert(Array.isArray(p.audioUrls)&&p.audioUrls.length<=10&&p.audioUrls.every(u=>{try{const x=new URL(u);return u.length<=2048&&x.protocol==='https:'&&!x.username&&!x.password;}catch{return false;}}));
}
async function bounded(stream,max){
 if(!stream)return new Uint8Array();const reader=stream.getReader(),parts=[];let size=0;
 try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>max){await reader.cancel();throw Error('size');}parts.push(value);}}finally{reader.releaseLock();}
 const result=new Uint8Array(size);let at=0;for(const p of parts){result.set(p,at);at+=p.length;}return result;
}
export async function handle(request,env,fetcher=fetch){
 const origin=request.headers.get('Origin'),allowed=(env.ALLOWED_ORIGINS??'').split(',').includes(origin);
 const headers={'Cache-Control':'no-store, private','Pragma':'no-cache','Vary':'Origin','Content-Type':'application/json','X-Content-Type-Options':'nosniff'};
 if(allowed)Object.assign(headers,{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Max-Age':'600'});
 const reply=(status,error)=>new Response(JSON.stringify({error}),{status,headers});
 const route=new URL(request.url).pathname;
 if(route==='/health'&&request.method==='GET')return new Response(JSON.stringify({service:'lexirise-gateway',version:1}),{headers});
 if(!allowed)return reply(403,'Origin is not allowed.');
 if(!['/v1/request','/v1/audio'].includes(route))return reply(404,'Unknown API version or operation.');
 if(request.method==='OPTIONS')return new Response(null,{status:204,headers});
 if(request.method!=='POST')return reply(405,'Use POST.');
 const authorization=request.headers.get('Authorization')??'';
 if(!/^Bearer [\x21-\x7e]{1,4096}$/.test(authorization))return reply(401,'Unlock with a valid API key.');
 // IP admission and one-way account fingerprint contain no account payloads.
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(authorization));
 const fingerprint=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
 if(!env.ADMISSION||!env.ACCOUNT)return reply(503,'Gateway rate limits are unavailable.');
 if(!(await env.ADMISSION.limit({key:request.headers.get('CF-Connecting-IP')??'local'})).success||!(await env.ACCOUNT.limit({key:fingerprint})).success){headers['Retry-After']='60';return reply(429,'Request limit reached. Wait a minute and retry.');}
 const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),25000);
 const stop=()=>abort.abort();request.signal.addEventListener('abort',stop,{once:true});
 try{
  let op;
  try{
   if(route==='/v1/audio'){
    const type=request.headers.get('Content-Type');assert(['audio/mpeg','audio/wav','audio/ogg'].includes(type));
    const data=await bounded(request.body,8*1024*1024);assert(data.length>0);const form=new FormData();form.append('file',new Blob([data],{type}),'voice.'+({'audio/mpeg':'mp3','audio/wav':'wav','audio/ogg':'ogg'}[type]));
    op={url:UPSTREAM+'/v1/vocabulary/audio',method:'POST',body:form};
   }else{assert(request.headers.get('Content-Type')?.split(';')[0]==='application/json');op=operation(JSON.parse(new TextDecoder().decode(await bounded(request.body,32768))));}
  }catch{return reply(400,'Invalid or oversized operation.');}
  const response=await fetcher(op.url,{method:op.method,body:op.body,headers:{Authorization:authorization,...route==='/v1/request'?{'Content-Type':'application/json'}:{}},redirect:'manual',cache:'no-store',signal:abort.signal});
  if(response.status>=300&&response.status<400){await response.body?.cancel();return reply(502,'Upstream redirect rejected.');}
  if(!response.ok){await response.body?.cancel();if([401,403].includes(response.status))return reply(response.status,'Lexirise rejected or expired this key. Reconnect in Settings.');if(response.status===429){headers['Retry-After']='60';return reply(429,'Lexirise is throttling requests. Wait a minute and retry.');}return reply(502,'Lexirise could not complete the operation. Retry after checking its status.');}
  const body=await bounded(response.body,2*1024*1024);JSON.parse(new TextDecoder().decode(body));
  return new Response(body,{status:200,headers});
 }catch{return reply(abort.signal.aborted?504:502,abort.signal.aborted?'Lexirise timed out. Retry when ready.':'Lexirise response unavailable. Retry when ready.');}
 finally{clearTimeout(timer);request.signal.removeEventListener('abort',stop);}
}
export default {fetch:(request,env)=>handle(request,env)};
