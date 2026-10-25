import {createReceiverSource} from './receiver-source.mjs';
import {createVdoFrameSource,parseVdoViewerUrl} from './vdo-source.mjs';
import {get,put,remove} from './storage.mjs';
const $=id=>document.getElementById(id);
export const receiverSource=createReceiverSource({vdo:()=>createVdoFrameSource({container:$('vdo-viewer')})});
let pc=null,pcLoading=null,pairing=null;
let viewerRevision=0,viewerWrites=Promise.resolve(),lastViewer='';
const saveViewer=fn=>{const pending=viewerWrites.catch(()=>{}).then(fn);viewerWrites=pending;return pending;};
const viewerError=()=>{$('source-status').textContent='Could not save the connection on this device.';};
$('vdo-url').addEventListener('input',()=>{viewerRevision++;});
$('vdo-remember').onchange=()=>{viewerRevision++;const enabled=$('vdo-remember').checked;void saveViewer(async()=>{if(!enabled)return remove('vdo-remembered');const input=$('vdo-url').value.trim()||lastViewer;if(input)await put('vdo-remembered',{version:1,url:parseVdoViewerUrl(input).url});}).catch(viewerError);};
$('vdo-forget').onclick=()=>{viewerRevision++;lastViewer='';$('vdo-url').value='';$('vdo-remember').checked=false;stop();void saveViewer(()=>remove('vdo-remembered')).catch(viewerError);};
void (async()=>{const token=viewerRevision;try{const saved=await get('vdo-remembered');if(token!==viewerRevision||!saved)return;lastViewer=parseVdoViewerUrl(saved.url).url;$('vdo-url').value=lastViewer;$('vdo-remember').checked=true;}catch{viewerError();}})();
export function ensurePC(){
 return pcLoading??=Promise.all([import('./pc-connection.mjs'),import('./qr-ui.mjs')]).then(([module,qr])=>{pairing=qr.pairingLifecycle;return pc=module.pcConnection;});
}
function update(){
 const source=receiverSource.getState(),native=$('source').value==='mobile';
 document.body.dataset.frameSource=native?'vdo':'pc';
 $('native-setup').hidden=!native;$('vdo-viewer').hidden=!native||!receiverSource.active;$('video-surface').hidden=!native||!receiverSource.active;
 $('vdo-connect').disabled=receiverSource.active;$('vdo-stop').hidden=!receiverSource.active;$('vdo-stop').disabled=!receiverSource.active;
 if(native){
  $('source-status').textContent=source.message+(source.width?` · ${source.width} × ${source.height}`:'');$('status').textContent=source.message;
  $('game').disabled=receiverSource.active;$('reload-build').disabled=receiverSource.active;
  window.dispatchEvent(new CustomEvent('mobile-stream',{detail:{transport:'vdo',generation:source.revision,game:$('game').value,role:'receiver',state:source.status==='live'?'connected':source.status,live:source.status==='live'}}));
 }
}
export async function connectVdo(){
 const viewer=parseVdoViewerUrl($('vdo-url').value.trim());
 lastViewer=viewer.url;viewerRevision++;
 if($('vdo-remember').checked)await saveViewer(()=>put('vdo-remembered',{version:1,url:viewer.url}));
 // The code is delivered only in memory; the vault owns any encrypted binding.
 window.dispatchEvent(new CustomEvent('mobile-viewer-code',{detail:{code:viewer.streamId}}));
 await receiverSource.connect('vdo',{url:viewer.url});if(!$('vdo-remember').checked)$('vdo-url').value='';
 if(document.hidden)receiverSource.pause();
 if(receiverSource.getState().status==='error')throw Error(receiverSource.getState().message);
}
function stop(){receiverSource.disconnect();pc?.stop();pairing?.stop();update();}
$('vdo-connect').onclick=()=>connectVdo().catch(error=>{$('source-status').textContent=error.message;});
$('vdo-stop').onclick=stop;
$('source').addEventListener('change',()=>{stop();window.dispatchEvent(new CustomEvent('mobile-source-changed'));if($('source').value==='pc')void ensurePC().catch(error=>{$('status').textContent=error.message;});});
$('reload-build').onclick=()=>{const url=new URL(location.href);url.searchParams.set('v',String(Date.now()));location.replace(url);};
receiverSource.subscribe(update);
document.addEventListener('visibilitychange',()=>{if(document.hidden)receiverSource.pause();else void receiverSource.resume();});
document.addEventListener('freeze',()=>receiverSource.pause());
document.addEventListener('resume',()=>{if(!document.hidden)void receiverSource.resume();});
window.addEventListener('pageshow',()=>{if(!document.hidden)void receiverSource.resume();});
window.addEventListener('pagehide',stop);
if($('source').value==='pc')await ensurePC();
const build=document.documentElement.dataset;
if(build.buildCommit)$('build-info').textContent=`Build ${build.buildCommit.slice(0,8)} · ${build.buildTime}`;
export const captureLifecycle={stop,get active(){return receiverSource.active||Boolean(pc?.active);},
 older:before=>{if(!pc)throw Error('Pair with the PC first.');return pc.older(before);},
 audio:row=>{if(!pc)throw Error('Pair with the PC first.');return pc.audio(row);}};
