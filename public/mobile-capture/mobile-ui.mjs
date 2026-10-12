import {get,put,remove,storageStatus,cacheBudget} from './storage.mjs';
import Tesseract from './ocr/tesseract.esm.min.js';
const {createWorker}=Tesseract;
import {crops,extraCrops,cropFrame as drawCrop,recognizeRegion,candidates,regions as captureRegions} from './ocr-pipeline.mjs';
const $=id=>document.getElementById(id), text=(id,message)=>$(id).textContent=message;
const reader=new Worker(new URL('./library-worker.mjs',import.meta.url),{type:'module'}), pending=new Map();
let sequence=0, library=null, available=new Set(), declaredAudio=new Set(), history=[], preferences={}, engine=null, engineLanguage=null, loading=null, resetting=Promise.resolve(), scanning=false, busy=false, epoch=0, streamState=null, stable=null, emitted=new Map(), samples=[];
let selectedBytes=0, selectedPacks=0, openMs=0, audioUrl=null, selection=0,lastMediaTime=-1;
let scanCompletion=Promise.resolve(),voiceBusy=false;
reader.onmessage=({data})=>{const request=pending.get(data.id);if(!request)return;if(data.progress!=null||data.stage){if(request.selection===selection)text('library-status',data.stage??`Reading ${data.progress.toLocaleString()} verified dialogue rows…`);return;}pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data.result);};
reader.onerror=()=>{for(const request of pending.values())request.reject(new Error('Library worker unavailable. Reopen the files.'));pending.clear();};
function request(action,body={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,selection});reader.postMessage({id,action,...body});});}
function currentGame(){return $('game').value;}
function updatePreview(){document.body.classList.toggle('ocr-running',scanning&&$('role').value==='receiver'&&streamState?.state==='connected'&&streamState?.live!==false&&!document.hidden);}
const optionIds=['ocr-language','player-voice','show-english','extra-regions','cinematic-regions','ocr-contrast'];
function setupCrop(){const game=currentGame(),saved=preferences[game]??{},selected=$('calibrate-region').value,keys=['dialogue',...Object.keys(extraCrops[game]??{})];$('calibrate-region').replaceChildren(...keys.map(key=>{const option=document.createElement('option');option.value=key;option.textContent={dialogue:'Dialogue',overhead:'Overhead captions',card:'Centered story card',comic:'Comic panels',panel:'Legacy dialogue panel',compact:'Compact subtitle strip'}[key];return option;}));$('calibrate-region').value=keys.includes(selected)?selected:'dialogue';const key=$('calibrate-region').value,crop=key==='dialogue'?saved.crop??crops[game]:saved.regions?.[key]??extraCrops[game][key];['left','top','width','height'].forEach((field,i)=>$('crop-'+field).value=String(crop[i]*100));$('picture-area').value=saved.picture??'window';for(const id of optionIds)if(saved[id]!=null){if($(id).type==='checkbox')$(id).checked=saved[id];else $(id).value=saved[id];}}
function cropValue(){const values=['left','top','width','height'].map(key=>Number($('crop-'+key).value)/100);if(values.some(v=>!Number.isFinite(v)||v<0||v>1)||values[2]<=0||values[3]<=0||values[0]+values[2]>1.00001||values[1]+values[3]>1.00001)throw new Error('Keep the crop inside the video.');return values;}
async function savePreferences(){epoch++;stable=null;const saved=preferences[currentGame()]??{},key=$('calibrate-region').value,value=cropValue();preferences[currentGame()]={...saved,...key==='dialogue'?{crop:value}:{regions:{...saved.regions,[key]:value}},picture:$('picture-area').value,...Object.fromEntries(optionIds.map(id=>[id,$(id).type==='checkbox'?$(id).checked:$(id).value]))};await put('preferences',preferences).catch(()=>text('storage-status','Calibration is temporary; browser storage is unavailable.'));}
async function reportStorage(requestPersistence=false){const state=await storageStatus(requestPersistence);text('storage-status',`${state.persistent?'Persistent browser storage granted':'Browser cache is best effort; retain your Files copies'}${state.usage!=null?` · ${(state.usage/1024**2).toFixed(1)} MiB cached`:''}${state.quota!=null?` · ${(Math.max(0,state.quota-(state.usage??0))/1024**3).toFixed(2)} GiB browser quota remaining (not device free space)`:''}. Audio packs stay in Files and must be reselected after reopening.`);return state;}
function libraryStatus(){
 if(!library){declaredAudio.clear();text('pack-status','');text('coverage-status','');text('library-status','Open your exported catalog ZIP and optional voice ZIPs from On My iPhone.');return;}
 const coverage=library.manifest.coverage;
 declaredAudio=new Set(library.manifest.packs.flatMap(p=>p.clips));
 text('library-status',`${library.manifest.title} · ${library.rowCount.toLocaleString()} bilingual rows · ${available.size.toLocaleString()} unique voice clips accessible this session${coverage.partial?' · Partial catalog: newer/unmapped scenes remain unsupported':''}. ${available.size?'Audio packs are open.':'Reselect voice ZIPs for playback.'}`);
 text('pack-status',`${selectedPacks} voice packs selected · ${(selectedBytes/1024**3).toFixed(2)} GiB selected. Audio is read per clip, without importing whole packs.`);
 const coverageNotes={zzz:'Comic crops pass synthetic layout checks; real mobile comic footage verification remains pending.',wuwa:'Sampled dialogue and centered cards pass; some resized movie/story captions still miss.',pragmata:'Mobile layout checks use synthetic scenes; real browser footage verification remains pending.',cyberpunk:'Small overhead captions still miss in recorded footage. Verify your subtitle size and crop.',witcher3:'Sampled cutscene captions pass; top-edge NPC captions still miss in recorded footage.',nte:'Sampled movie radio/intro cards pass; wrapped subtitles and some movie variants still miss.',honkai3:'Sampled modern, legacy and multi-page panels pass both tested resolutions. Newer chapters remain outside the verified catalog.',hito:'Fixed catalog rows are text-only. Mobile does not run the desktop grammar generator.'};
 text('coverage-status','Browser OCR coverage: '+coverageNotes[library.manifest.game]);
}
$('library-files').onchange=async event=>{
 const token=++selection;epoch++;stable=null;
 const files=[...event.target.files];if(!files.length)return;
 const start=performance.now();$('library-files').disabled=true;$('cancel-library').hidden=false;text('library-status','Opening selected ZIPs. Keep a USB drive connected and unlocked…');
 try{
  const result=await request('open',{files,expectedGame:$('game').disabled?currentGame():null});if(token!==selection)return;
  if($('game').disabled&&result.catalog.manifest.game!==currentGame())throw new Error('Stop this capture session before opening a different game.');
  library=result.catalog;available=new Set(result.available);selectedBytes=result.selectedBytes;selectedPacks=result.selectedPacks;openMs=performance.now()-start;
  if(!$('game').disabled){$('game').value=library.manifest.game;$('game').dispatchEvent(new Event('change'));}
  libraryStatus();render();$('search-results').replaceChildren();$('cancel-library').hidden=true;
  const state=await reportStorage(),budget=cacheBudget(library.manifest,state);
  if(budget.sufficient===false)text('cache-status',`Not enough browser quota for the estimated ${(budget.needed/1024**2).toFixed(0)} MiB catalog cache. This library works this session; reselect the catalog after reopening. Voices remain in Files.`);
  else try{await request('cache');text('cache-status',`Catalog remembered for reopening · estimated cache budget ${(budget.needed/1024**2).toFixed(0)} MiB. Voice ZIPs are not cached.`);}catch{ text('cache-status','Catalog could not be cached, possibly because device storage is low. This session still works. Check iPhone Storage in Settings and reopen the catalog next time.');}
  void reportStorage(true);

 }catch(error){if(token===selection)text('library-status',error.message);}finally{if(token===selection){$('library-files').disabled=false;$('cancel-library').hidden=true;}event.target.value='';}
};
$('cancel-library').onclick=()=>{selection++;void request('cancel-open');$('library-files').disabled=false;$('library-files').value='';$('cancel-library').hidden=true;text('library-status','File opening cancelled. Your previous library remains available. Select ZIPs again to retry.');};
$('forget-library').onclick=async()=>{selection++;epoch++;scanning=false;updatePreview();stable=null;await request('forget');library=null;available.clear();selectedBytes=selectedPacks=0;await remove('catalog').catch(()=>{});libraryStatus();render();};
function saveHistory(){const favorites=history.filter(r=>r.favorite).slice(-5000),rest=history.filter(r=>!r.favorite).slice(-500);history=[...favorites,...rest].sort((a,b)=>a.createdAt-b.createdAt);return put('history',history).catch(()=>text('storage-status','Transcript history is temporary; storage could not be saved.'));}
function render(){
 const panel=$('transcript');panel.replaceChildren();
 for(const line of history.filter(r=>r.game===currentGame()&&(!$('favorites-only').checked||r.favorite)).slice(-100).reverse()){
  const item=document.createElement('article');item.className='transcript-line';
  if(line.speakerChinese||line.speakerEnglish){const speaker=document.createElement('strong');speaker.textContent=line.speakerChinese??line.speakerEnglish;item.append(speaker);}
  const chinese=document.createElement('p');chinese.lang='zh-Hans';chinese.className='transcript-chinese';chinese.textContent=line.chinese;item.append(chinese);
  if($('show-english').checked){const english=document.createElement('p');english.lang='en';english.textContent=line.english;item.append(english);}
  const status=document.createElement('small');status.textContent=`Catalog match · ${line.matching??'exact'}${line.score!=null?' · '+line.score.toFixed(0)+'%':''}`;item.append(status);
  const actions=document.createElement('div');actions.className='actions';const play=document.createElement('button');play.textContent=line.audio?available.has(line.audio)?'Play original voice':declaredAudio.has(line.audio)?'Reselect voice pack':'Voice absent from this export':line.sourceVoice?'Original audio not exported':'No verified original voice';play.disabled=voiceBusy||!line.audio||!available.has(line.audio);play.onclick=async()=>{if(voiceBusy)return;voiceBusy=true;const token=selection;render();try{const start=performance.now(),blob=await request('voice',{sha:line.audio});if(token!==selection)return;if(audioUrl)URL.revokeObjectURL(audioUrl);audioUrl=URL.createObjectURL(blob);$('voice-player').src=audioUrl;await $('voice-player').play();samples.push({kind:'playback',ms:performance.now()-start});samples=samples.slice(-120);}catch(error){if(token===selection)text('match-status',error.message);}finally{voiceBusy=false;render();}};
  const favorite=document.createElement('button');favorite.textContent=line.favorite?'Unfavorite':'Favorite';favorite.onclick=()=>{line.favorite=!line.favorite;void saveHistory();render();};actions.append(play,favorite);item.append(actions);panel.append(item);
 }
}
for(const id of ['show-english','favorites-only'])$(id).onchange=render;
async function addSearchLine(row){history.push({...row,matching:'manual selection',game:currentGame(),createdAt:Date.now(),favorite:false});await saveHistory();render();text('match-status',row.sourceVoice?'Catalog line ready. Playback requires its matching open voice pack.':'Bilingual text found. No verified original voice is available for this line.');}
$('find-line').onclick=async()=>{
 const token=selection,game=currentGame();try{
  const result=await request('search',{text:$('find-text').value});if(token!==selection||game!==currentGame()||library?.manifest.game!==game)return;
  const panel=$('search-results');panel.replaceChildren();
  if(!result.total){text('match-status','No results in this export. Try a few English or Chinese words. Older exports omit unvoiced text; re-export the library for updated coverage.');return;}
  if(result.total===1){await addSearchLine(result.rows[0]);return;}
  text('match-status',`${result.total.toLocaleString()} catalog results. Choose the scene or voice variant below${result.total>result.rows.length?' (showing the first 20)':''}.`);
  for(const row of result.rows){
   const item=document.createElement('article');item.className='transcript-line';
   for(const [value,lang] of [[row.chinese,'zh-Hans'],[row.english,'en']]){const p=document.createElement('p');p.textContent=value;p.lang=lang;item.append(p);}
   const info=document.createElement('small');info.textContent=[row.speakerEnglish??row.speakerChinese,row.playerVoice?`${row.playerVoice} player voice`:null,row.sourceVoice?'Verified voice binding':'Text only — no verified original voice',row.textId].filter(Boolean).join(' · ');item.append(info);
   const choose=document.createElement('button');choose.textContent='Choose this line';choose.onclick=()=>{if(token!==selection||game!==currentGame())return;void addSearchLine(row);};item.append(choose);panel.append(item);
  }
 }catch(e){if(token===selection)text('match-status',e.message);}
};
$('find-text').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('find-line').click();}});
$('clear-history').onclick=()=>{history=history.filter(r=>r.game!==currentGame());emitted.clear();stable=null;void saveHistory();render();};
for(const key of ['left','top','width','height'])$('crop-'+key).onchange=()=>void savePreferences().catch(e=>text('match-status',e.message));
$('picture-area').onchange=()=>void savePreferences().catch(e=>text('match-status',e.message));
$('calibrate-region').onchange=setupCrop;
$('reset-crop').onclick=()=>{const game=currentGame(),key=$('calibrate-region').value,saved=preferences[game]??{};preferences[game]={...saved,...key==='dialogue'?{crop:crops[game]}:{regions:{...saved.regions,[key]:extraCrops[game][key]}}};setupCrop();void savePreferences();};
$('game').addEventListener('change',()=>{epoch++;stable=null;scanning=false;updatePreview();setupCrop();render();});
const canvas=document.createElement('canvas');
function cropFrame(region){return drawCrop($('preview'),canvas,region,$('picture-area').value);}
$('preview-crop').onclick=()=>{try{const image=cropFrame(cropValue()),preview=$('crop-preview');preview.width=image.width;preview.height=image.height;preview.getContext('2d').drawImage(image,0,0);preview.hidden=false;}catch(e){text('match-status',e.message);}};
async function initEngine(){
 await resetting;
 const base=new URL('./ocr/',import.meta.url),lang=$('ocr-language').value;
 if(engine&&engineLanguage!==lang){await scanCompletion;await engine.terminate();engine=null;}
 if(engine)return engine;if(loading)return loading;
 loading=createWorker(lang,1,{workerPath:new URL('worker.min.js',base).href,corePath:new URL('core/',base).href,langPath:new URL('lang/',base).href,cachePath:'proxy-mobile-ocr-7-best-int-1',workerBlobURL:false,logger:value=>{if(value.status==='loading language traineddata')text('match-status','Preparing private on-device OCR…');}}).then(async value=>{await value.setParameters({tessedit_pageseg_mode:'6',preserve_interword_spaces:'1'});engine=value;engineLanguage=lang;return value;}).finally(()=>loading=null);
 return loading;
}
$('ocr-language').onchange=()=>{epoch++;stable=null;scanning=false;updatePreview();text('match-status','OCR paused. Start with the selected subtitle language.');resetting=resetting.then(async()=>{await scanCompletion;if(loading)await loading.catch(()=>{});const old=engine;engine=null;if(old)await old.terminate();});};
$('ocr-start').onclick=async()=>{const token=++epoch;try{if(!library)throw new Error('Open a game catalog first.');if(library.manifest.game!==currentGame())throw new Error('Open a catalog for the selected game.');text('match-status','Loading on-device OCR…');await initEngine();if(token!==epoch)return;scanning=true;updatePreview();text('match-status','OCR ready. Keep this receiving page open while playing.');}catch(e){text('match-status',e.message);}};
$('ocr-pause').onclick=()=>{scanning=false;updatePreview();epoch++;stable=null;text('match-status','OCR paused.');};
window.addEventListener('mobile-stream',event=>{if(!streamState||streamState.generation!==event.detail.generation||streamState.state!==event.detail.state){epoch++;stable=null;lastMediaTime=-1;}streamState=event.detail;updatePreview();});
document.addEventListener('visibilitychange',()=>{epoch++;stable=null;updatePreview();if(document.hidden)text('match-status','OCR suspended while the phone page is hidden.');});
function regions(){return captureRegions(currentGame(),preferences[currentGame()]?.crop??crops[currentGame()],$('extra-regions').checked,$('cinematic-regions').checked,preferences[currentGame()]?.regions).map(region=>$('ocr-contrast').value==='raw'?{...region,raw:true}:region);}
async function scan(){
 if(busy||!scanning||!engine||document.hidden||!library||library.manifest.game!==currentGame()||$('role').value!=='receiver'||streamState?.state!=='connected'||streamState?.live===false||$('preview').readyState<2||$('preview').currentTime===lastMediaTime)return;
 lastMediaTime=$('preview').currentTime;
 busy=true;let finishScan;scanCompletion=new Promise(resolve=>finishScan=resolve);const token=epoch,start=performance.now();
 try{
  let accepted=null,ambiguous=false,dialogueMenu=false;
  for(const region of regions()){
   if(token!==epoch)return;
   if(region.channel!=='dialogue'&&dialogueMenu)continue;
   const image=cropFrame(region.crop);
   const recognized=await recognizeRegion(engine,image,region,$('ocr-language').value,()=>token===epoch);if(token!==epoch)return;if(!recognized)continue;
   const parsed=candidates(recognized,region,image.width,image.height,currentGame());if(region.channel==='dialogue')dialogueMenu=parsed.menu;
   const match=await request('match-candidates',{values:parsed.values,channel:region.channel,player:$('player-voice').value,fragment:region.fragment});if(token!==epoch)return;
   if(match.state==='ambiguous')ambiguous=true;
   if(match.state==='matched')accepted={...match,channel:region.channel};
   if(accepted)break;
  }
  const elapsed=performance.now()-start;samples.push({kind:'ocr',ms:elapsed});samples=samples.slice(-120);
  if(!accepted){stable=null;text('match-status',ambiguous?'Ambiguous dialogue/voice; skipped.':'No verified match: unsupported scene, incomplete text, or crop needs calibration.');return;}
  const key=accepted.row.id;stable=stable?.key===key?{key,count:stable.count+1}:{key,count:1};
  text('match-status',`Verified ${accepted.channel} match · ${elapsed.toFixed(0)} ms${stable.count<2?' · confirming…':''}`);
  if(stable.count===2&&(!emitted.has(key)||Date.now()-emitted.get(key)>10000)&&!history.some(r=>r.id===key&&Date.now()-r.createdAt<10000)){
   emitted.set(key,Date.now());history.push({...accepted.row,score:accepted.score,matching:accepted.score===100?'exact':'fuzzy',game:currentGame(),createdAt:Date.now(),favorite:false});await saveHistory();render();
   if(emitted.size>2048){const cutoff=Date.now()-10000;for(const [id,time] of emitted)if(time<cutoff)emitted.delete(id);}
  }
 }catch(e){if(token===epoch)text('match-status',`OCR needs attention: ${e.message}`);}finally{busy=false;finishScan();}
}
// One in-flight scan: the next scan always uses the latest video frame.
setInterval(()=>void scan(),600);
$('library-report').onclick=async()=>{
 const observations={device:$('test-device').value,outcome:$('test-outcome').value,...Object.fromEntries(['large','playback','reload','reboot','update','gameplay'].map(name=>[name,$('test-'+name).checked]))};
 const storage=await storageStatus(),data={format:'proxy-mobile-library-report-v1',build:document.documentElement.dataset.buildCommit??null,game:currentGame(),createdAt:new Date().toISOString(),libraryRows:library?.rowCount??0,availableVoices:available.size,selectedBytes,selectedPacks,openMs,storage,samples:samples.slice(-120),transcriptRows:history.filter(r=>r.game===currentGame()).length,observations,physicalDeviceVerified:observations.device==='iphone'&&observations.outcome==='passed'&&['large','playback','reload','reboot','update','gameplay'].every(name=>observations[name])};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='mobile-library-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
async function restore(){const token=selection;try{preferences=await get('preferences')??{};history=await get('history')??[];if(token===selection){const result=await request('restore');if(token!==selection)return;library=result.catalog;if(library&&!$('game').disabled){$('game').value=library.manifest.game;$('game').dispatchEvent(new Event('change'));}libraryStatus();}setupCrop();render();await reportStorage();}catch{setupCrop();text('storage-status','Browser cache unavailable. Open the catalog again from Files.');}}
void restore();
for(const id of ['player-voice','extra-regions','cinematic-regions'])$(id).addEventListener('change',()=>{epoch++;stable=null;});
for(const id of optionIds)$(id).addEventListener('change',()=>void savePreferences().catch(e=>text('match-status',e.message)));
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').then(registration=>{
 $('reload-build').onclick=async()=>{if($('role').disabled)return;await registration.update().catch(()=>{});if(registration.installing)await new Promise(resolve=>{const worker=registration.installing;worker.addEventListener('statechange',()=>{if(['installed','redundant'].includes(worker.state))resolve();});setTimeout(resolve,5000);});if(registration.waiting){const activated=new Promise(resolve=>{navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true});setTimeout(resolve,3000);});registration.waiting.postMessage('activate-update');await activated;}const url=new URL(location.href);url.searchParams.set('v',String(Date.now()));location.replace(url);};
}).catch(()=>{});
