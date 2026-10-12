import qrcode from './pairing/qrcode.mjs';
import jsQR from './pairing/jsqr.mjs';
import {pairingFrames,PairingQrReader} from './qr-pairing.mjs';
const $=id=>document.getElementById(id);
let frames=[],frame=0,displayToken=0,camera=null,scanToken=0;
const reader=new PairingQrReader(),canvas=document.createElement('canvas');
function draw(){
 if(!frames.length)return;
 const qr=qrcode(0,'M');qr.addData(frames[frame]);qr.make();
 const target=$('pairing-qr'),context=target.getContext('2d'),size=qr.getModuleCount(),scale=Math.max(2,Math.floor(640/(size+8)));
 target.width=target.height=(size+8)*scale;context.fillStyle='#fff';context.fillRect(0,0,target.width,target.height);context.fillStyle='#000';
 for(let y=0;y<size;y++)for(let x=0;x<size;x++)if(qr.isDark(y,x))context.fillRect((x+4)*scale,(y+4)*scale,scale,scale);
 $('qr-description').textContent=`Scan this ${$('role').value==='sender'?'offer on the receiving phone':'answer on the sending device'}${frames.length>1?` · QR ${frame+1} of ${frames.length}, changing automatically`:''}. Keep the scanning camera pointed here until all frames are read.`;
}
function stopCamera(){scanToken++;if(camera)for(const track of camera.getTracks())track.stop();camera=null;$('qr-camera').srcObject=null;$('qr-scan-panel').hidden=true;$('scan-pairing').disabled=false;}
window.addEventListener('mobile-pairing-message',async event=>{
 const token=++displayToken;frames=[];$('qr-panel').hidden=true;
 if(!event.detail.message){stopCamera();return;}
 try{const next=await pairingFrames(event.detail.message);if(token!==displayToken)return;frames=next;frame=0;$('qr-panel').hidden=false;draw();}catch(error){if(token===displayToken)$('qr-feedback').textContent=error.message;}
});
setInterval(()=>{if(frames.length>1&&!document.hidden){frame=(frame+1)%frames.length;draw();}},1000);
$('stop-scan').onclick=stopCamera;
$('scan-pairing').onclick=async()=>{
 stopCamera();reader.reset();const token=scanToken;$('qr-feedback').textContent='Allow camera access to scan the other device’s pairing QR.';$('scan-pairing').disabled=true;
 try{
  const opened=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});
  if(token!==scanToken){opened.getTracks().forEach(t=>t.stop());return;}camera=opened;$('qr-camera').srcObject=camera;$('qr-scan-panel').hidden=false;await $('qr-camera').play();
  let lastFrame=0;
  const scan=async()=>{
   if(token!==scanToken||document.hidden)return;
   const video=$('qr-camera');
   if(video.readyState>=2&&Date.now()-lastFrame>200){
    lastFrame=Date.now();const scale=Math.min(1,960/video.videoWidth);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(video,0,0,canvas.width,canvas.height);
    const decoded=jsQR(context.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height,{inversionAttempts:'dontInvert'});
    if(decoded)try{
     const result=await reader.accept(decoded.data,$('role').value==='receiver'?'offer':'answer');if(token!==scanToken)return;
     $('qr-feedback').textContent=`Read ${result.received} of ${result.total} QR frames…`;
     if(result.message){$('incoming').value=result.message;stopCamera();$('qr-feedback').textContent='Pairing QR read. Accepting the message…';$('apply').click();return;}
    }catch(error){$('qr-feedback').textContent=error.message;}
   }
   if(token===scanToken)setTimeout(()=>void scan(),150);
  };void scan();
 }catch(error){if(token===scanToken){stopCamera();$('qr-feedback').textContent='Camera scan unavailable. Allow camera access, or use Copy message / Open pairing file below.';}}
};
for(const event of ['pagehide','freeze'])window.addEventListener(event,stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCamera();});
