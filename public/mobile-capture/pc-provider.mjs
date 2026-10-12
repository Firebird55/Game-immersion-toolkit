import {PAGE_SIZE,MAX_AUDIO} from './transcript-channel.mjs';
// Only loaded by the local sharing page, never a remotely supplied API path.
export function createPCProvider(game){
 if(!['localhost','127.0.0.1'].includes(location.hostname))throw Error('Start PC sharing from the local desktop companion.');
 let source=localStorage.getItem('proxy-transcript-source');if(!/^pc-[a-zA-Z0-9-]{16,64}$/.test(source??'')){source='pc-'+crypto.randomUUID();localStorage.setItem('proxy-transcript-source',source);}
 const known=new Set();
 const normalize=r=>({source,game,id:r.id,chinese:(r.chinese??'').slice(0,1200),english:(r.english??'').slice(0,1200),speakerChinese:(r.speaker_chinese??'').slice(0,120),speakerEnglish:(r.speaker_english??'').slice(0,120),createdAt:Math.max(0,Date.parse(r.created_at)||0),audio:Boolean(r.has_audio&&r.audio_source==='original')});
 return {source,game,
  subscribe(onRows){
   let stopped=false,socket,timer;
   const connect=()=>{if(stopped)return;socket=new WebSocket('ws://127.0.0.1:8766/api/ws');socket.onmessage=event=>{if(stopped)return;try{const m=JSON.parse(event.data);if(m.type==='line'&&m.line.game===game){const row=normalize(m.line);if(row.audio)known.add(row.id);while(known.size>1000)known.delete(known.values().next().value);onRows([row]);}}catch{}};socket.onclose=()=>{if(!stopped)timer=setTimeout(connect,2000);};};connect();
   return ()=>{stopped=true;clearTimeout(timer);socket?.close();};
  },
  async page(before,signal){
   const query=new URLSearchParams({game,limit:String(PAGE_SIZE)});if(before!==null)query.set('before_id',String(before));
   const response=await fetch('http://127.0.0.1:8766/api/lines?'+query,{signal,cache:'no-store'});if(!response.ok)throw Error('Keep the desktop companion running.');
   const raw=await response.json(),rows=raw.filter(r=>r.game===game).slice(0,PAGE_SIZE).map(normalize);rows.filter(r=>r.audio).forEach(r=>known.add(r.id));while(known.size>1000)known.delete(known.values().next().value);
   return {rows,before:raw.length===PAGE_SIZE?Math.min(...raw.map(r=>r.id)):null};
  },
  async audio(id,signal){
   if(!known.has(id))throw Error('Open this transcript page before requesting its audio.');
   const r=await fetch('http://127.0.0.1:8766/api/lines/'+id+'/audio',{signal,cache:'no-store'});if(!r.ok||Number(r.headers.get('Content-Length'))>MAX_AUDIO)throw Error('Original audio unavailable.');
   const reader=r.body.getReader(),chunks=[];let size=0;try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>MAX_AUDIO){await reader.cancel();throw Error('Audio too large.');}chunks.push(value);}}finally{reader.releaseLock();}
   return new Blob(chunks,{type:r.headers.get('Content-Type')?.split(';')[0]});
  }
 };
}
