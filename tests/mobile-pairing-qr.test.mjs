import test from 'node:test';
import assert from 'node:assert/strict';
import qrcode from 'qrcode-generator';
import jsQR from 'jsqr';
import {pairingFrames,PairingQrReader,encode45,decode45,qrScanRegions} from '../public/mobile-capture/qr-pairing.mjs';
import {deflateSync} from 'fflate';
import {createHash} from 'node:crypto';
import {pairingMessage} from '../public/mobile-capture/core.mjs';
import {readableQr} from '../public/mobile-capture/qr-render.mjs';
const identity={sessionId:'session-0123456789',pairingId:'pairing-0123456789',attempt:2};
const message=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:100},(_,i)=>'a=fixture:'+i.toString(16).padStart(8,'0')).join('\r\n')},'zzz',identity);
test('displayed QR pixels decode across varied compressed payloads and random-looking identities',async()=>{
 for(let i=0;i<80;i++){
  const fixture=createHash('sha256').update('owned-pairing-fixture-'+i).digest('hex');
  const text=pairingMessage({type:i%2?'answer':'offer',sdp:'v=0\r\n'+Array.from({length:70+i%40},(_,n)=>`a=fixture:${n}:${createHash('sha256').update(fixture+n).digest('hex').slice(0,8)}`).join('\r\n')},'zzz',{sessionId:fixture.slice(0,32),pairingId:fixture.slice(32),attempt:1});
  for(const frame of await pairingFrames(text)){
   const image=readableQr(frame),code=jsQR(image.pixels,image.width,image.width,{inversionAttempts:'dontInvert'});
   assert.equal(code?.data,frame);
  }
 }
});
test('QR round trip decodes rendered pixels and preserves reconnect identity',async()=>{
 const frames=await pairingFrames(message),reader=new PairingQrReader();let result;
 for(const frame of frames.toReversed()){
  const qr=qrcode(0,'M');qr.addData(frame,'Alphanumeric');qr.make();const size=qr.getModuleCount(),scale=5,width=(size+8)*scale,pixels=new Uint8ClampedArray(width*width*4).fill(255);
  for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(qr.isDark(y,x))for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){const at=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;pixels[at]=pixels[at+1]=pixels[at+2]=0;}
  const code=jsQR(pixels,width,width);assert.equal(code.data,frame);result=await reader.accept(code.data,'offer');
 }
 assert.equal(result.message,message);
});

test('compact encoding matches published Base45 examples and rejects invalid values',()=>{
 for(const [text,encoded] of [['AB','BB8'],['Hello!!','%69 VD92EX0'],['base-45','UJCLQE7W581']]){
  assert.equal(encode45(new TextEncoder().encode(text)),encoded);
  assert.equal(new TextDecoder().decode(decode45(encoded)),text);
 }
 for(const text of ['A',':::','::','a0','0000','0\n'])assert.throws(()=>decode45(text),/Invalid/);
 const bytes=Uint8Array.from({length:256},(_,i)=>i);
 assert.deepEqual(decode45(encode45(bytes)),bytes);
});

test('an offer and reply that previously needed two frames fit one compact static QR',async()=>{
 const sdp='v=0\r\n'+Array.from({length:90},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n');
 for(const type of ['offer','answer']){
  const text=pairingMessage({type,sdp},'zzz',identity);
  const legacyPayload=Buffer.from(deflateSync(new TextEncoder().encode(text))).toString('base64url');
  assert.equal(Math.ceil(legacyPayload.length/1000),2);
  const frames=await pairingFrames(text);
  assert.equal(frames.length,1);
  const qr=qrcode(0,'M');qr.addData(frames[0],'Alphanumeric');qr.make();
  const byteQr=qrcode(0,'M');byteQr.addData(frames[0]);byteQr.make();
  assert(qr.getModuleCount()<byteQr.getModuleCount(),'Compact mode reduces the physical QR module count');
  assert.equal((await new PairingQrReader().accept(frames[0],type)).message,text);
 }
});

test('legacy frames remain readable and sparse parts stay balanced with missing-frame hints',async()=>{
 const payload=Buffer.from(deflateSync(new TextEncoder().encode(message))).toString('base64url');
 const id=createHash('sha256').update(payload).digest('hex').slice(0,16);
 assert.equal((await new PairingQrReader().accept(`PTQR1:${id}:1:1:${payload}`,'offer')).message,message);
 const large=pairingMessage({type:'answer',sdp:'v=0\r\n'+Array.from({length:500},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n')},'zzz',identity);
 const frames=await pairingFrames(large),lengths=frames.map(f=>f.replace(/^PTQR2:[^:]+:\d+:\d+:/,'').length);
 assert(frames.length>1&&Math.max(...lengths)-Math.min(...lengths)<=1);
 const reader=new PairingQrReader();
 const first=await reader.accept(frames.at(-1),'answer');
 assert.deepEqual(first.missing,Array.from({length:frames.length-1},(_,i)=>i+1));
 reader.started=Date.now()-120000; // A slow camera must not lose an otherwise current partial scan.
 let result;
 for(const frame of frames.slice(0,-1))result=await reader.accept(frame,'answer');
 assert.equal(result.message,large);
});

test('camera crops preserve central QR detail and retain an off-centre fallback in both orientations',()=>{
 for(const [width,height]of [[1920,1080],[1080,1920],[640,480],[1,1]]){
  const regions=qrScanRegions(width,height);
  assert.equal(regions[0].width,regions[0].height);
  for(const r of regions)assert(r.x>=0&&r.y>=0&&r.width>0&&r.height>0&&r.x+r.width<=width&&r.y+r.height<=height);
  assert.deepEqual(regions.at(-1),{x:0,y:0,width,height,maxSize:1280});
 }
 assert.deepEqual(qrScanRegions(0,1080),[]);
});

test('compact metadata, corrupted payloads and expanded-message limits reject untrusted input',async()=>{
 const frame=bytes=>{const payload=encode45(deflateSync(bytes)),id=createHash('sha256').update(payload).digest('hex').slice(0,16).toUpperCase();return `PTQR2:${id}:1:1:${payload}`;};
 for(const value of [[2,'zzz','v=0'],[0,'unsupported','v=0'],[0,'zzz',{}],[0,'zzz','v=0','only-one-id'],[0,'zzz','v=0',identity.sessionId,identity.pairingId,0]]){
  await assert.rejects(new PairingQrReader().accept(frame(new TextEncoder().encode(JSON.stringify(value))),'offer'));
 }
 const [valid]=await pairingFrames(message),damaged=valid.slice(0,-1)+(valid.endsWith('A')?'B':'A');
 await assert.rejects(new PairingQrReader().accept(damaged,'offer'),/checksum/);
 await assert.rejects(new PairingQrReader().accept(frame(new TextEncoder().encode('x'.repeat(129000))),'offer'),/Expanded/);
});
test('multi-frame pairing handles repeated/reordered frames, wrong roles and malformed data',async()=>{
 const large=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:500},(_,i)=>'a=fixture:'+i+':'+Math.sin(i)).join('\r\n')},'zzz',identity),frames=await pairingFrames(large);assert(frames.length>1);
 const reader=new PairingQrReader();await reader.accept(frames[0],'offer');await reader.accept(frames[0],'offer');let result;
 for(const frame of frames.slice(1).toReversed())result=await reader.accept(frame,'offer');assert.equal(result.message,large);
 const wrong=new PairingQrReader();for(const frame of frames.slice(0,-1))await wrong.accept(frame,'answer');await assert.rejects(wrong.accept(frames.at(-1),'answer'),/answer/);
 await assert.rejects(reader.accept('https://example.com/','offer'),/toolkit/);
 await assert.rejects(reader.accept(frames[0].slice(0,-1)+(frames[0].endsWith('A')?'B':'A'),'offer'),/Conflicting/);
});
