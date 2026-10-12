import {deflateSync,Inflate} from './pairing/fflate.mjs';
import {parsePairing} from './core.mjs';

const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('').slice(0,16);
const base64=bytes=>btoa(Array.from(bytes,b=>String.fromCharCode(b)).join('')).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
export async function pairingFrames(message){
 const value=JSON.parse(message);if(!['offer','answer'].includes(value.type))throw new Error('Expected a toolkit offer or answer.');parsePairing(message,value.type);
 const payload=base64(deflateSync(new TextEncoder().encode(message))),count=Math.ceil(payload.length/1000);
 if(count>16)throw new Error('This pairing message needs too many QR frames. Use the pairing file instead.');
 const id=await hash(payload);
 return Array.from({length:count},(_,i)=>`PTQR1:${id}:${i+1}:${count}:${payload.slice(i*1000,(i+1)*1000)}`);
}
export class PairingQrReader{
 constructor(){this.reset();}
 reset(){this.id=null;this.count=0;this.parts=new Map();this.started=Date.now();}
 async accept(frame,expectedType){
  if(typeof frame!=='string'||frame.length>1100)throw new Error('Not a toolkit pairing QR.');
  const match=/^PTQR1:([a-f0-9]{16}):([1-9]|1[0-6]):([1-9]|1[0-6]):([A-Za-z0-9_-]{1,1000})$/.exec(frame);
  if(!match)throw new Error('Not a toolkit pairing QR.');
  const [,id,n,c,payload]=match,index=Number(n),count=Number(c);
  if(index>count)throw new Error('Invalid QR sequence.');
  if(this.id!==id||Date.now()-this.started>90000)this.reset();
  if(this.id&&this.count!==count||this.parts.has(index)&&this.parts.get(index)!==payload)throw new Error('Conflicting pairing QR frames.');
  this.id=id;this.count=count;this.parts.set(index,payload);
  if(this.parts.size!==count)return {received:this.parts.size,total:count};
  const encoded=Array.from({length:count},(_,i)=>this.parts.get(i+1)).join('');
  if(await hash(encoded)!==id)throw new Error('Pairing QR checksum failed. Scan again.');
  const compressed=Uint8Array.from(atob(encoded.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
  let length=0;const chunks=[],inflate=new Inflate((chunk)=>{length+=chunk.length;if(length>128000)throw new Error('Expanded pairing message is too large.');chunks.push(chunk);});
  inflate.push(compressed,true);
  const bytes=new Uint8Array(length);let at=0;for(const chunk of chunks){bytes.set(chunk,at);at+=chunk.length;}
  const message=new TextDecoder('utf8',{fatal:true}).decode(bytes);parsePairing(message,expectedType);
  return {received:count,total:count,message};
 }
}
