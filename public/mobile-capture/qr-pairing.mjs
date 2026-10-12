import {deflateSync,Inflate} from './pairing/fflate.mjs';
import {parsePairing,pairingMessage} from './core.mjs';

const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('').slice(0,16);
const ALPHABET='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:';
// RFC 9285: use QR's compact alphanumeric mode without modifying WebRTC data.
export function encode45(bytes){
 let result='';
 for(let i=0;i<bytes.length;i+=2){
  let value=bytes[i]* (i+1<bytes.length?256:1)+(i+1<bytes.length?bytes[i+1]:0);
  result+=ALPHABET[value%45];value=Math.floor(value/45);result+=ALPHABET[value%45];
  if(i+1<bytes.length)result+=ALPHABET[Math.floor(value/45)];
 }
 return result;
}
export function decode45(text){
 if(typeof text!=='string'||text.length>18000||text.length%3===1)throw new Error('Invalid compact QR data.');
 const bytes=[];
 for(let i=0;i<text.length;i+=3){
  const digits=Array.from(text.slice(i,i+3),c=>ALPHABET.indexOf(c));
  if(digits.some(d=>d<0))throw new Error('Invalid compact QR data.');
  const value=digits[0]+digits[1]*45+(digits.length===3?digits[2]*2025:0);
  if(value>(digits.length===3?65535:255))throw new Error('Invalid compact QR data.');
  if(digits.length===3)bytes.push(value>>8,value&255);else bytes.push(value);
 }
 return Uint8Array.from(bytes);
}
export async function pairingFrames(message){
 const input=JSON.parse(message);if(!['offer','answer'].includes(input.type))throw new Error('Expected a toolkit offer or answer.');
 const value=parsePairing(message,input.type);
 const compact=[value.type==='offer'?0:1,value.game,value.sdp];
 if(value.sessionId)compact.push(value.sessionId,value.pairingId,value.attempt);
 if(value.relay){if(!value.sessionId)throw Error('Recovery requires a session identity.');compact.push(value.relay);}
 if(value.mode==='transcript'){if(!value.sessionId)throw Error('Transcript requires a session identity.');if(!value.relay)compact.push(null);compact.push('transcript');}
 const payload=encode45(deflateSync(new TextEncoder().encode(JSON.stringify(compact)),{level:9}));
 if(payload.length>18000)throw new Error('This pairing message needs too many QR frames. Use the pairing file instead.');
 const count=payload.length<=3000?1:Math.min(16,Math.ceil(payload.length/480));
 const id=(await hash(payload)).toUpperCase();
 // Balanced parts avoid one easily scanned short QR and an unreadable dense QR.
 return Array.from({length:count},(_,i)=>`PTQR2:${id}:${i+1}:${count}:${payload.slice(Math.floor(i*payload.length/count),Math.floor((i+1)*payload.length/count))}`);
}
export function qrScanRegions(width,height){
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<1||height<1)return [];
 const side=Math.max(1,Math.floor(Math.min(width,height)*.9));
 const focused=Math.max(1,Math.floor(Math.min(width,height)*.55));
 return [{x:Math.floor((width-focused)/2),y:Math.floor((height-focused)/2),width:focused,height:focused,maxSize:1440,upscale:true},
         {x:Math.floor((width-side)/2),y:Math.floor((height-side)/2),width:side,height:side,maxSize:1440},
         {x:0,y:0,width,height,maxSize:1280}];
}
export class PairingQrReader{
 constructor(){this.reset();}
 reset(){this.id=null;this.version=null;this.count=0;this.parts=new Map();this.started=Date.now();}
 async accept(frame,expectedType){
  if(typeof frame!=='string'||frame.length>3100)throw new Error('Not a toolkit pairing QR.');
  const match=/^(PTQR1):([a-f0-9]{16}):([1-9]|1[0-6]):([1-9]|1[0-6]):([A-Za-z0-9_-]{1,1000})$/.exec(frame)
   || /^(PTQR2):([A-F0-9]{16}):([1-9]|1[0-6]):([1-9]|1[0-6]):([0-9A-Z $%*+./:-]{1,3000})$/.exec(frame);
  if(!match)throw new Error('Not a toolkit pairing QR.');
  const [,version,id,n,c,payload]=match,index=Number(n),count=Number(c);
  if(index>count)throw new Error('Invalid QR sequence.');
  if(this.id!==id||Date.now()-this.started>300000)this.reset();
  if(this.id&&(this.count!==count||this.version!==version)||this.parts.has(index)&&this.parts.get(index)!==payload)throw new Error('Conflicting pairing QR frames.');
  if(!this.parts.has(index))this.started=Date.now();
  this.id=id;this.version=version;this.count=count;this.parts.set(index,payload);
  if(this.parts.size!==count)return {received:this.parts.size,total:count,missing:Array.from({length:count},(_,i)=>i+1).filter(i=>!this.parts.has(i))};
  const encoded=Array.from({length:count},(_,i)=>this.parts.get(i+1)).join('');
  if(encoded.length>(version==='PTQR2'?18000:16000)||(await hash(encoded)).toUpperCase()!==id.toUpperCase())throw new Error('Pairing QR checksum failed. Scan again.');
  const compressed=version==='PTQR2'?decode45(encoded):Uint8Array.from(atob(encoded.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
  let length=0;const chunks=[],inflate=new Inflate((chunk)=>{length+=chunk.length;if(length>128000)throw new Error('Expanded pairing message is too large.');chunks.push(chunk);});
  inflate.push(compressed,true);
  const bytes=new Uint8Array(length);let at=0;for(const chunk of chunks){bytes.set(chunk,at);at+=chunk.length;}
  let message=new TextDecoder('utf8',{fatal:true}).decode(bytes);
  if(version==='PTQR2'){
   const value=JSON.parse(message);
   if(!Array.isArray(value)||![3,6,7,8].includes(value.length)||![0,1].includes(value[0])||value.length===8&&value[7]!=='transcript')throw new Error('Invalid compact pairing message.');
   message=pairingMessage({type:value[0]===0?'offer':'answer',sdp:value[2]},value[1],value.length>=6?{sessionId:value[3],pairingId:value[4],attempt:value[5],...(value.length>=7&&value[6]?{relay:value[6]}:{}),...(value.length===8?{mode:value[7]}:{})}:{});
  }
  parsePairing(message,expectedType);
  return {received:count,total:count,message};
 }
}
