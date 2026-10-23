import test from 'node:test';
import assert from 'node:assert/strict';
import {createReceiverSource} from '../public/mobile-capture/receiver-source.mjs';
import {cropFrame,recognizeRegion} from '../public/mobile-capture/ocr-pipeline.mjs';

function fixture(){
 const instances=[];let next=0;
 const factory=()=>{
  let state={sessionId:null,status:'ready',width:0,height:0,lastFrameTimestamp:null,message:'Ready'},listener=null,resolveRead;
  const source={disposed:0,options:null,signal:null,
   connect(options){source.options=options;state={...state,sessionId:String(++next),status:'connecting'};listener?.(state);},
   disconnect(){},dispose(){source.disposed++;},subscribe(fn){listener=fn;fn(state);return()=>{listener=null;};},getState:()=>state,
   readFrame({signal}){source.signal=signal;return new Promise(resolve=>resolveRead=resolve);},
   resolve(sessionId=state.sessionId){const frame={sessionId,sequence:1,timestamp:Date.now(),width:10,height:20,image:{},releases:0,release(){this.releases++;}};resolveRead(frame);return frame;}
  };instances.push(source);return source;
 };
 return {receiver:createReceiverSource({browser:factory,synthetic:factory}),instances};
}
test('switching source aborts and releases a late frame without blocking a replacement',async()=>{
 const {receiver,instances}=fixture();await receiver.connect('browser');const before=receiver.getState().revision,oldRead=receiver.readFrame();
 assert.equal(await receiver.readFrame(),null,'no queue for an occupied source');
 await receiver.connect('synthetic');assert(instances[0].signal.aborted);assert.equal(instances[0].disposed,1);
 const freshRead=receiver.readFrame(),late=instances[0].resolve();assert.equal(await oldRead,null);assert.equal(late.releases,1);
 const fresh=instances[1].resolve();assert.equal(await freshRead,fresh);assert(receiver.getState().revision>before);fresh.release();receiver.dispose();
});
test('pause/resume has new identity, preserves private options only in memory and stop cancels intent',async()=>{
 const {receiver,instances}=fixture(),states=[];receiver.subscribe(state=>states.push(state));
 await receiver.connect('synthetic',{url:'private-fixture'});const session=receiver.getState().sessionId,pending=receiver.readFrame();receiver.pause();
 assert.equal(receiver.getState().status,'paused');assert.equal(await receiver.readFrame(),null);const old=instances[0].resolve();assert.equal(await pending,null);assert.equal(old.releases,1);
 await receiver.resume();assert.notEqual(receiver.getState().sessionId,session);assert.equal(instances[1].options.url,'private-fixture');
 receiver.disconnect();await receiver.resume();assert.equal(instances.length,2);assert.equal(receiver.active,false);assert(!JSON.stringify(states).includes('private-fixture'));
});
test('caller cancellation and wrong-session frames never reach a consumer',async()=>{
 const {receiver,instances}=fixture();await receiver.connect('browser');const abort=new AbortController(),pending=receiver.readFrame({signal:abort.signal});abort.abort();const frame=instances[0].resolve();assert.equal(await pending,null);assert.equal(frame.releases,1);
 const wrong=receiver.readFrame(),other=instances[0].resolve('other-session');assert.equal(await wrong,null);assert.equal(other.releases,1);receiver.dispose();
});
test('normalized crop follows frame dimensions across rotation and never receives a transport object',()=>{
 const calls=[],canvas={getContext:()=>({drawImage:(...args)=>calls.push(args)})},image={kind:'drawable'};
 for(const [width,height]of [[1920,1080],[1080,1920],[1280,720]]){
  cropFrame({image,width,height},canvas,[.1,.7,.8,.2]);const call=calls.at(-1);assert.equal(call[0],image);assert.deepEqual(call.slice(1,5),[width*.1,height*.7,width*.8,height*.2]);assert(canvas.width<=2304&&canvas.height<=1024);
 }
 assert.throws(()=>cropFrame({image,width:10,height:10},canvas,[.9,.9,.2,.2]),/inside/);
});
test('invalidated OCR does not issue a worker job after asynchronous parameter setup',async()=>{
 const previous=globalThis.document;globalThis.document={createElement:()=>({getContext:()=>({drawImage(){}})})};
 let current=true,jobs=0;
 const canvas={width:1,height:1,getContext:()=>({getImageData:()=>({data:new Uint8ClampedArray(4)})})};
 try{const result=await recognizeRegion({setParameters:async()=>{current=false;},recognize:async()=>{jobs++;}},canvas,{channel:'dialogue',raw:true},'eng',()=>current);assert.equal(result,null);assert.equal(jobs,0);}finally{globalThis.document=previous;}
});
