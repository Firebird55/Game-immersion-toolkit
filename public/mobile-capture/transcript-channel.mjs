export const PROTOCOL=1,CHANNEL='proxy-transcript-v1',PAGE_SIZE=8,MAX_MESSAGE=60000,MAX_AUDIO=8*1024*1024;
const games=new Set(['zzz','wuwa','pragmata','cyberpunk','witcher3','nte','hito']);
const str=(v,n)=>typeof v==='string'&&v.length<=n;
const integer=(v,max)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
const fields=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).every(k=>keys.includes(k));
export function rowKey(row){return JSON.stringify([row.source,row.game,String(row.id)]);}
export function validRow(r){return fields(r,['source','game','id','chinese','english','speakerChinese','speakerEnglish','createdAt','audio'])&&/^pc-[a-zA-Z0-9-]{16,64}$/.test(r.source)&&games.has(r.game)&&Number.isSafeInteger(r.id)&&r.id>0&&str(r.chinese,1600)&&str(r.english,1600)&&r.chinese.length+r.english.length<=2400&&str(r.speakerChinese,120)&&str(r.speakerEnglish,120)&&integer(r.createdAt,Number.MAX_SAFE_INTEGER)&&typeof r.audio==='boolean';}
export function parseMessage(raw,session){
 if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_MESSAGE)throw Error('Oversized transcript message.');
 const m=JSON.parse(raw);if(!m||m.v!==PROTOCOL||m.session!==session)throw Error('Transcript protocol or session mismatch. Pair again.');
 const common=['v','session','type'];let valid=false;
 if(m.type==='capabilities')valid=fields(m,[...common,'source','game','pageSize','audio'])&&/^pc-[a-zA-Z0-9-]{16,64}$/.test(m.source)&&games.has(m.game)&&m.pageSize===PAGE_SIZE&&m.audio===true;
 if(m.type==='page-request')valid=fields(m,[...common,'request','before'])&&str(m.request,64)&&m.request.length>0&&(m.before===null||Number.isSafeInteger(m.before)&&m.before>0);
 if(m.type==='page'||m.type==='update')valid=fields(m,[...common,'request','rows','before'])&&Array.isArray(m.rows)&&m.rows.length<=PAGE_SIZE&&m.rows.every(validRow)&&(m.before===null||Number.isSafeInteger(m.before)&&m.before>0)&&(m.type==='update'||str(m.request,64));
 if(m.type==='audio-request')valid=fields(m,[...common,'request','id'])&&str(m.request,64)&&m.request.length>0&&Number.isSafeInteger(m.id)&&m.id>0;
 if(m.type==='audio')valid=fields(m,[...common,'request','index','total','mime','data'])&&str(m.request,64)&&integer(m.index,1023)&&integer(m.total,1024)&&m.total>0&&m.index<m.total&&['audio/mpeg','audio/wav','audio/ogg'].includes(m.mime)&&str(m.data,16384)&&/^[A-Za-z0-9+/]*={0,2}$/.test(m.data);
 if(m.type==='error')valid=fields(m,[...common,'request','message'])&&str(m.request,64)&&str(m.message,180);
 if(!valid)throw Error('Invalid transcript message.');return m;
}
export function createTranscriptChannel(channel,{session,provider,onRows=()=>{},onState=()=>{},onCapabilities=()=>{}}){
 let closed=false,working=false,source=null,game=null,updates=0;const pending=new Map(),abort=new AbortController();
 const state=message=>onState(message);
 function close(message='Disconnected. Local history is still available.'){if(closed)return;closed=true;abort.abort();channel.close();for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('Transcript connection closed. Pair again.'));}pending.clear();state(message);}
 async function send(body){
  const raw=JSON.stringify({v:PROTOCOL,session,...body});if(new TextEncoder().encode(raw).length>MAX_MESSAGE)throw Error('Transcript message exceeds limit.');
  const started=Date.now();while(channel.bufferedAmount>128*1024){if(closed||channel.readyState!=='open'||Date.now()-started>10000)throw Error('Transcript connection stalled.');await new Promise(resolve=>setTimeout(resolve,20));}
  if(closed||channel.readyState!=='open')throw Error('Transcript connection is closed.');channel.send(raw);
 }
 function request(type,body){return new Promise((resolve,reject)=>{
  if(pending.size>=2){reject(Error('Wait for the current transfer.'));return;}
  const request=crypto.randomUUID(),p={resolve,reject,chunks:[],bytes:0,type,timer:setTimeout(()=>{pending.delete(request);reject(Error('Transfer timed out. Reconnect and retry.'));},20000)};
  pending.set(request,p);send({type,request,...body}).catch(error=>{clearTimeout(p.timer);pending.delete(request);reject(error);});
 });}
 function complete(id,error,value){const p=pending.get(id);if(!p)return;clearTimeout(p.timer);pending.delete(id);error?p.reject(error):p.resolve(value);}
 channel.onmessage=async event=>{
  try{
   const m=parseMessage(event.data,session);
   if(provider){
    if(!['page-request','audio-request'].includes(m.type))throw Error('Unsupported receiver request.');
    if(working){await send({type:'error',request:m.request,message:'A transfer is already running. Retry shortly.'});return;}
    working=true;const signal=AbortSignal.any([abort.signal,AbortSignal.timeout(15000)]);
    try{
     if(m.type==='page-request'){const page=await provider.page(m.before,signal);await send({type:'page',request:m.request,...page});}
     else{const blob=await provider.audio(m.id,signal);if(blob.size>MAX_AUDIO||!['audio/mpeg','audio/wav','audio/ogg'].includes(blob.type))throw Error('Unsupported audio.');const bytes=new Uint8Array(await blob.arrayBuffer()),total=Math.ceil(bytes.length/12288);if(!total)throw Error('Empty audio.');for(let index=0;index<total;index++){signal.throwIfAborted();const data=btoa(String.fromCharCode(...bytes.subarray(index*12288,(index+1)*12288)));await send({type:'audio',request:m.request,index,total,mime:blob.type,data});}}
    }catch{if(!closed)await send({type:'error',request:m.request,message:'The requested transcript or audio is unavailable. Reconnect or try another line.'});}finally{working=false;}
   }else{
    if(m.type==='capabilities'){if(source&&source!==m.source)throw Error('Source changed.');source=m.source;game=m.game;onCapabilities(m);void api.page(null).catch(e=>state(e.message));state('Connected to PC transcript.');}
    else if(m.type==='page'||m.type==='update'){
     if(!source||m.rows.some(r=>r.source!==source||r.game!==game))throw Error('Transcript source mismatch.');
     if(m.type==='page'&&!pending.has(m.request))return;
     onRows(m.rows,m);if(m.type==='page')complete(m.request,null,m);
    }else if(m.type==='audio'){
     const p=pending.get(m.request);if(!p||p.type!=='audio-request')return;
     if(m.index!==p.chunks.length||p.total&&p.total!==m.total||p.mime&&p.mime!==m.mime)throw Error('Audio chunk mismatch.');
     p.total=m.total;p.mime=m.mime;const bytes=Uint8Array.from(atob(m.data),c=>c.charCodeAt(0));p.bytes+=bytes.length;if(p.bytes>MAX_AUDIO)throw Error('Audio too large.');p.chunks.push(bytes);
     if(p.chunks.length===p.total)complete(m.request,null,new Blob(p.chunks,{type:p.mime}));
    }else if(m.type==='error')complete(m.request,Error(m.message));else throw Error('Unsupported sender response.');
   }
  }catch{close('Transcript protocol error. Stop and pair again.');}
 };
 channel.onclose=()=>close();channel.onerror=()=>close();
 channel.onopen=()=>{if(provider)void send({type:'capabilities',source:provider.source,game:provider.game,pageSize:PAGE_SIZE,audio:true}).catch(()=>close());};
 const api={close,get closed(){return closed;},page:before=>request('page-request',{before}),audio:(id,expected)=>{if(expected&&(expected.source!==source||expected.game!==game))return Promise.reject(Error('Pair with the PC and game that supplied this line to play its original voice.'));return request('audio-request',{id});},async update(rows){if(++updates>16){updates--;close('Transcript connection fell behind. Reconnect to refresh history.');return;}try{await send({type:'update',rows,before:null});}finally{updates--;}}};
 return api;
}
