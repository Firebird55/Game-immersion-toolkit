import test from 'node:test';
import assert from 'node:assert/strict';
import qrcode from 'qrcode-generator';
import jsQR from 'jsqr';
import {pairingFrames,PairingQrReader} from '../public/mobile-capture/qr-pairing.mjs';
import {pairingMessage} from '../public/mobile-capture/core.mjs';
const identity={sessionId:'session-0123456789',pairingId:'pairing-0123456789',attempt:2};
const message=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:100},(_,i)=>'a=fixture:'+i.toString(16).padStart(8,'0')).join('\r\n')},'zzz',identity);
test('QR round trip decodes rendered pixels and preserves reconnect identity',async()=>{
 const frames=await pairingFrames(message),reader=new PairingQrReader();let result;
 for(const frame of frames.toReversed()){
  const qr=qrcode(0,'M');qr.addData(frame);qr.make();const size=qr.getModuleCount(),scale=5,width=(size+8)*scale,pixels=new Uint8ClampedArray(width*width*4).fill(255);
  for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(qr.isDark(y,x))for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){const at=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;pixels[at]=pixels[at+1]=pixels[at+2]=0;}
  const code=jsQR(pixels,width,width);assert.equal(code.data,frame);result=await reader.accept(code.data,'offer');
 }
 assert.equal(result.message,message);
});
test('multi-frame pairing handles repeated/reordered frames, wrong roles and malformed data',async()=>{
 const large=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:500},(_,i)=>'a=fixture:'+i+':'+Math.sin(i)).join('\r\n')},'zzz',identity),frames=await pairingFrames(large);assert(frames.length>1);
 const reader=new PairingQrReader();await reader.accept(frames[0],'offer');await reader.accept(frames[0],'offer');let result;
 for(const frame of frames.slice(1).toReversed())result=await reader.accept(frame,'offer');assert.equal(result.message,large);
 const wrong=new PairingQrReader();for(const frame of frames.slice(0,-1))await wrong.accept(frame,'answer');await assert.rejects(wrong.accept(frames.at(-1),'answer'),/answer/);
 await assert.rejects(reader.accept('https://example.com/','offer'),/toolkit/);
 await assert.rejects(reader.accept(frames[0].slice(0,-1)+(frames[0].endsWith('A')?'B':'A'),'offer'),/Conflicting/);
});
