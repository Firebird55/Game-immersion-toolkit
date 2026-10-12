import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseRelay,parsePairing,pairingMessage} from '../public/mobile-capture/core.mjs';
import {seal,unseal,proof,digest,encode64} from '../public/mobile-capture/relay.mjs';
import {pairingFrames,PairingQrReader} from '../public/mobile-capture/qr-pairing.mjs';
import {registration,packet,smallBody} from '../services/pairing/protocol.mjs';
const descriptor={endpoint:'https://pairing.example.org',room:'a'.repeat(32),secret:encode64(crypto.getRandomValues(new Uint8Array(32))),expires:Date.now()+3600000};
test('encrypted connection messages authenticate the room, role, secret and payload',async()=>{
 const value={kind:'pairing',message:'private SDP fixture'},encrypted=await seal(descriptor.secret,descriptor.room,'sender',value);
 assert.deepEqual(await unseal(descriptor.secret,descriptor.room,'sender',encrypted),value);
 assert(!JSON.stringify(encrypted).includes(value.message));
 for(const [key,room,role] of [[encode64(crypto.getRandomValues(new Uint8Array(32))),descriptor.room,'sender'],[descriptor.secret,'b'.repeat(32),'sender'],[descriptor.secret,descriptor.room,'receiver']])await assert.rejects(unseal(key,room,role,encrypted));
 await assert.rejects(unseal(descriptor.secret,descriptor.room,'sender',{...encrypted,data:(encrypted.data[0]==='A'?'B':'A')+encrypted.data.slice(1)}));
 assert.notEqual(await proof(descriptor.secret,'sender'),await proof(descriptor.secret,'receiver'));
 await assert.rejects(seal(descriptor.secret,descriptor.room,'sender',{data:'中'.repeat(50000)}),/large/);
});
test('QR and pairing round trips retain the recovery descriptor and reject unsafe endpoints',async()=>{
 const identity={sessionId:'session-recovery-fixture',pairingId:'pairing-recovery-fixture',attempt:1,relay:descriptor};
 const message=pairingMessage({type:'offer',sdp:'v=0\r\nprivate fixture'},'zzz',identity),frames=await pairingFrames(message),reader=new PairingQrReader();
 let result;for(const frame of frames)result=await reader.accept(frame,'offer');assert.equal(result.message,message);assert.deepEqual(parsePairing(message,'offer').relay,descriptor);
 for(const endpoint of ['http://example.org','https://example.org/path','https://user:pass@example.org','https://example.org?key=value','file:///test'])assert.throws(()=>parseRelay({...descriptor,endpoint}));
 for(const value of [{...descriptor,room:'bad'},{...descriptor,secret:'bad'},{...descriptor,expires:1.2},{...descriptor,extra:true}])assert.throws(()=>parseRelay(value));
});
test('relay registration and packet limits prevent plaintext, invalid roles and oversized bodies',async()=>{
 const senderHash=await digest(await proof(descriptor.secret,'sender')),receiverHash=await digest(await proof(descriptor.secret,'receiver'));
 assert.deepEqual(registration({senderHash,receiverHash}),{senderHash,receiverHash});
 assert.throws(()=>registration({senderHash,receiverHash:senderHash}));assert.throws(()=>registration({senderHash,receiverHash,sdp:'private'}));
 const encrypted=await seal(descriptor.secret,descriptor.room,'sender',{kind:'recover'});
 assert.deepEqual(packet(JSON.stringify({kind:'signal',...encrypted})),{kind:'signal',...encrypted});
 assert.throws(()=>packet(JSON.stringify({kind:'signal',iv:encrypted.iv,data:'v=0 SDP'})));assert.throws(()=>packet(JSON.stringify({kind:'signal',...encrypted,from:'sender'})));
 assert.throws(()=>packet('x'.repeat(180501)));
 assert.deepEqual(await smallBody(new Request('https://example.org',{method:'POST',body:JSON.stringify({senderHash,receiverHash})})),{senderHash,receiverHash});
 await assert.rejects(smallBody(new Request('https://example.org',{method:'POST',body:'x'.repeat(513)})),/large/);
});
