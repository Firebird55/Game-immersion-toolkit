import jsQR from './pairing/jsqr.mjs';
import {pairingFrames,PairingQrReader,qrScanRegions} from './qr-pairing.mjs';
import {readableQr} from './qr-render.mjs';
const $=id=>document.getElementById(id);
const panel=$('qr-panel'),home=panel.parentNode,anchor=panel.nextSibling,dialog=$('qr-large-dialog');
const reader=new PairingQrReader(),canvas=document.createElement('canvas'),images=new Map();
let frames=[],frame=0,paused=false,nextFrameAt=0,displayToken=0,camera=null,scanToken=0,readerRole=null,assisted=false;
function draw(){
 if(!frames.length)return;
 let image=images.get(frame);
 if(!image){
  const verified=readableQr(frames[frame],frames.length===1?'L':'M');
  image=document.createElement('canvas');image.width=image.height=verified.width;
  image.getContext('2d').putImageData(new ImageData(verified.pixels,verified.width,verified.width),0,0);
  images.set(frame,image);
  if(images.size>3)images.delete(images.keys().next().value);
 }
 const target=$('pairing-qr');target.width=image.width;target.height=image.height;target.getContext('2d').drawImage(image,0,0);
 target.dataset.frame=String(frame+1);target.dataset.total=String(frames.length);
 const kind=$('role').value==='sender'?'offer':'answer';
 $('qr-description').textContent=`${kind==='offer'?assisted?'Scan this offer once on the receiving phone. Its answer returns automatically.':'Step 1: scan this offer on the receiving phone.':assisted?'The answer is sent automatically. This QR is available for manual transfer if needed.':'Step 2: scan this answer on the sending device.'} QR ${frame+1} of ${frames.length}${frames.length>1?paused?' · paused':' · changes every 3 seconds':''}.`;
 $('qr-pause').textContent=paused?'Resume QR rotation':'Pause QR rotation';
 for(const id of ['qr-previous','qr-next','qr-pause'])$(id).disabled=frames.length<2;
 nextFrameAt=Date.now()+3000;
}
function closeLarge(){if(dialog.open)dialog.close();}
dialog.addEventListener('close',()=>{home.insertBefore(panel,anchor);$('qr-enlarge').textContent='Larger QR';$('qr-enlarge').focus();});
$('qr-enlarge').onclick=()=>{if(dialog.open){closeLarge();return;}dialog.append(panel);$('qr-enlarge').textContent='Close large QR';dialog.showModal();};
for(const [id,direction]of [['qr-previous',-1],['qr-next',1]])$(id).onclick=()=>{if(!frames.length)return;paused=true;frame=(frame+direction+frames.length)%frames.length;draw();};
$('qr-pause').onclick=()=>{paused=!paused;draw();};
setInterval(()=>{if(frames.length>1&&!paused&&!document.hidden&&Date.now()>=nextFrameAt){frame=(frame+1)%frames.length;draw();}},250);
function stopCamera(){
 scanToken++;if(camera)for(const track of camera.getTracks())track.stop();camera=null;
 $('qr-camera').srcObject=null;$('qr-scan-panel').hidden=true;$('scan-pairing').disabled=false;
}
window.addEventListener('mobile-pairing-message',async event=>{
 const token=++displayToken;closeLarge();frames=[];images.clear();panel.hidden=true;
 if(!event.detail.message){stopCamera();reader.reset();readerRole=null;return;}
 try{const next=await pairingFrames(event.detail.message);if(token!==displayToken)return;assisted=Boolean(JSON.parse(event.detail.message).relay);frames=next;frame=0;paused=false;draw();panel.hidden=false;}
 catch(error){if(token===displayToken){panel.hidden=true;$('qr-feedback').textContent=error.message;}}
});
$('role').addEventListener('change',()=>{stopCamera();reader.reset();readerRole=null;});
$('stop-scan').onclick=()=>{stopCamera();$('qr-feedback').textContent=reader.parts.size?`Scan paused. ${reader.parts.size} of ${reader.count} frames kept; scan again to continue.`:'Camera stopped.';};
$('scan-pairing').onclick=async()=>{
 stopCamera();const expectedType=$('role').value==='receiver'?'offer':'answer';
 if(readerRole!==expectedType){reader.reset();readerRole=expectedType;}
 const token=scanToken;
 $('qr-feedback').textContent=reader.parts.size?`Continuing: ${reader.parts.size} of ${reader.count} QR frames kept. Point at the missing frames.`:'Allow camera access. Centre the other device’s QR in the camera; move closer if it looks small.';
 $('scan-pairing').disabled=true;$('qr-scan-panel').hidden=false;
 try{
  const opened=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080},frameRate:{ideal:15,max:30}},audio:false});
  if(token!==scanToken){opened.getTracks().forEach(t=>t.stop());return;}
  camera=opened;$('qr-camera').srcObject=camera;await $('qr-camera').play();
  if(token!==scanToken)return;
  const openedAt=Date.now();
  $('qr-feedback').textContent=reader.parts.size?`Continuing: ${reader.parts.size} of ${reader.count} frames kept.`:'Camera ready. Keep the whole QR, including its white border, centred in the camera.';
  const scan=async()=>{
   if(token!==scanToken||document.hidden)return;
   const video=$('qr-camera');
   if(video.readyState>=2&&video.videoWidth&&video.videoHeight){
    let decoded;
    for(const region of qrScanRegions(video.videoWidth,video.videoHeight)){
     const scale=Math.min(region.upscale?2:1,region.maxSize/Math.max(region.width,region.height));
     canvas.width=Math.max(1,Math.round(region.width*scale));canvas.height=Math.max(1,Math.round(region.height*scale));
     const context=canvas.getContext('2d',{willReadFrequently:true});
     context.imageSmoothingEnabled=false;
     context.drawImage(video,region.x,region.y,region.width,region.height,0,0,canvas.width,canvas.height);
     decoded=jsQR(context.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height,{inversionAttempts:'dontInvert'});
     if(decoded)break;
    }
    if(!decoded&&!reader.parts.size&&Date.now()-openedAt>4000)$('qr-feedback').textContent='No QR read yet. Use Larger QR on the other device and move the camera closer until the code fills most of the preview. Keep its whole white border visible.';
    if(decoded)try{
     const result=await reader.accept(decoded.data,expectedType);if(token!==scanToken)return;
     $('qr-feedback').textContent=`Read ${result.received} of ${result.total} QR frames${result.missing?.length?`. Still need QR ${result.missing.join(', ')}. On the other device, use Pause and Next QR to hold a missing frame.`:'…'}`;
     if(result.message){$('incoming').value=result.message;stopCamera();$('qr-feedback').textContent='Pairing QR read. Accepting the message…';$('apply').click();return;}
    }catch(error){if(token===scanToken)$('qr-feedback').textContent=error.message;}
   }
   if(token===scanToken)setTimeout(()=>void scan().catch(scanFailed),250);
  };
  const scanFailed=()=>{if(token===scanToken){stopCamera();$('qr-feedback').textContent='Camera reading stopped. Scan again to continue, or transfer the pairing file.';}};
  void scan().catch(scanFailed);
 }catch(error){if(token===scanToken){stopCamera();$('qr-feedback').textContent='Camera scan unavailable. Allow camera access, or use Copy message / Open pairing file below.';}}
};
for(const event of ['pagehide','freeze'])window.addEventListener(event,stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCamera();});

export const pairingLifecycle={stop:stopCamera};
