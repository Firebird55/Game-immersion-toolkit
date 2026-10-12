import {test} from 'node:test';import assert from 'node:assert/strict';
import {parseMessage,createTranscriptChannel,rowKey,PROTOCOL,PAGE_SIZE} from '../public/mobile-capture/transcript-channel.mjs';
import {pairingFrames,PairingQrReader} from '../public/mobile-capture/qr-pairing.mjs';
import {pairingMessage,parsePairing} from '../public/mobile-capture/core.mjs';
const source='pc-01234567-89ab-cdef-0123-456789abcdef',session='test-session';
const row={source,game:'zzz',id:1,chinese:'你好',english:'Hello',speakerChinese:'',speakerEnglish:'',createdAt:1,audio:true};
const message=value=>JSON.stringify({v:PROTOCOL,session,...value});
test('QR preserves transcript-only mode with and without a relay',async()=>{
 const value=pairingMessage({type:'offer',sdp:'v=0\r\n'},'zzz',{sessionId:'transcript-session-123',pairingId:'transcript-pairing-123',attempt:1,mode:'transcript'});
 const frames=await pairingFrames(value),reader=new PairingQrReader();let result;for(const frame of frames)result=await reader.accept(frame,'offer');assert.equal(parsePairing(result.message,'offer').mode,'transcript');
});
test('transcript identifiers and strict allowlist reject stale, malformed and privileged requests',()=>{
 assert.notEqual(rowKey(row),rowKey({...row,source:'mobile-ocr'}));assert.notEqual(rowKey(row),rowKey({...row,game:'wuwa'}));
 assert.equal(parseMessage(message({type:'page-request',request:'a',before:null}),session).type,'page-request');
 for(const v of [{v:2,type:'page-request',request:'a',before:null},{session:'old',type:'page-request',request:'a',before:null},{type:'fetch',path:'/api/lexirise'},{type:'audio-request',request:'a',id:'../../key'},{type:'page',request:'a',before:null,rows:[{...row,path:'private'}]}])assert.throws(()=>parseMessage(message(v),session));
 assert.throws(()=>parseMessage('x'.repeat(60001),session));
});
test('paired channels exchange bounded pages and chunked original audio; stop rejects pending access',async()=>{
 const a={readyState:'open',bufferedAmount:0,close(){this.readyState='closed';}},b={readyState:'open',bufferedAmount:0,close(){this.readyState='closed';}};
 a.send=value=>queueMicrotask(()=>b.onmessage?.({data:value}));b.send=value=>queueMicrotask(()=>a.onmessage?.({data:value}));
 const bytes=new Uint8Array(50000).map((_,i)=>i%255),seen=[];
 const sender=createTranscriptChannel(a,{session,provider:{source,game:'zzz',page:async()=>({rows:[row],before:null}),audio:async()=>new Blob([bytes],{type:'audio/wav'})}});
 const receiver=createTranscriptChannel(b,{session,onRows:rows=>seen.push(...rows)});
 a.onopen();await new Promise(r=>setTimeout(r,5));assert.equal(seen.length,1);
 const audio=await receiver.audio(1);assert.deepEqual(new Uint8Array(await audio.arrayBuffer()),bytes);
 await sender.update([{...row,id:2}]);await new Promise(r=>setTimeout(r,5));assert.equal(seen.at(-1).id,2);
 sender.close();receiver.close();await assert.rejects(receiver.page(null));assert.equal(a.readyState,'closed');
});
