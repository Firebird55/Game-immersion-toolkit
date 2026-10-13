// No application protocol or mocks: serialize native SDP between separate pages.
// A same-page echo can pass with runtime-internal candidates that cannot reach
// another page/process, so it is not sufficient evidence of usable WebRTC.
export async function probeDataChannel(sender,receiver){
 const pages=[sender,receiver];
 try{
  for(const page of pages)await page.evaluate(()=>{
   const peer=new RTCPeerConnection({iceServers:[]});let finish;
   const received=new Promise(resolve=>finish=resolve);
   const state={peer,received,finish,timer:setTimeout(()=>finish(false),25000)};
   peer.ondatachannel=event=>{event.channel.onmessage=()=>event.channel.send('echo');};
   window.__nativeRTCProbe=state;
  });
  const describe=async(page,type)=>page.evaluate(async type=>{
   const {peer}=window.__nativeRTCProbe;
   if(type==='offer'){
    const channel=peer.createDataChannel('native-runtime-probe');
    channel.onopen=()=>channel.send('probe');
    channel.onmessage=()=>window.__nativeRTCProbe.finish(true);
   }
   await peer.setLocalDescription(await(type==='offer'?peer.createOffer():peer.createAnswer()));
   if(peer.iceGatheringState!=='complete')await new Promise(resolve=>{
    const timer=setTimeout(done,4000);
    function done(){clearTimeout(timer);peer.removeEventListener('icegatheringstatechange',check);resolve();}
    function check(){if(peer.iceGatheringState==='complete')done();}
    peer.addEventListener('icegatheringstatechange',check);check();
   });
   return {type:peer.localDescription.type,sdp:peer.localDescription.sdp};
  },type);
  const offer=await describe(sender,'offer');
  await receiver.evaluate(description=>window.__nativeRTCProbe.peer.setRemoteDescription(description),offer);
  const answer=await describe(receiver,'answer');
  await sender.evaluate(description=>window.__nativeRTCProbe.peer.setRemoteDescription(description),answer);
  const connected=await sender.evaluate(()=>window.__nativeRTCProbe.received);
  return {connected,offerCandidates:(offer.sdp.match(/a=candidate:/g)||[]).length,answerCandidates:(answer.sdp.match(/a=candidate:/g)||[]).length};
 }catch(error){return {connected:false,error:error.name};}
 finally{for(const page of pages)await page.evaluate(()=>{const probe=window.__nativeRTCProbe;if(probe){clearTimeout(probe.timer);probe.finish(false);probe.peer.close();delete window.__nativeRTCProbe;}}).catch(()=>{});}
}
