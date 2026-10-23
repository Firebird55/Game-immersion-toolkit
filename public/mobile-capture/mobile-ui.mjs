import {manifest as ocrManifest,loadModel,modelStatus,removeModel} from './ocr-packs.mjs';
import {translate,languageName,formatBytes,bindStaticTranslation} from './interface-language.mjs';
import {confirmCaptions} from './caption-confirmation.mjs';
import {receiverSource} from './capture.js';
import {get,put,remove,storageStatus,cacheBudget} from './storage.mjs';
import Tesseract from './ocr/tesseract.esm.min.js';
const {createWorker}=Tesseract;
bindStaticTranslation(document.body);
import {crops,extraCrops,cropFrame as drawCrop,recognizeRegion,candidates,regions as captureRegions} from './ocr-pipeline.mjs';
const $=id=>document.getElementById(id), text=(id,message)=>$(id).textContent=translate(message);
const reader=new Worker(new URL('./library-worker.mjs',import.meta.url),{type:'module'}), pending=new Map();
let sequence=0, library=null, available=new Set(), declaredAudio=new Set(), history=[], preferences={}, engine=null, engineLanguage=null, loading=null, resetting=Promise.resolve(), scanning=false, busy=false, epoch=0, sourceState=null, stable=null, emitted=new Map(), samples=[];
let selectedBytes=0, selectedPacks=0, openMs=0, audioUrl=null, selection=0,activeJob=null;
let scanCompletion=Promise.resolve(),voiceBusy=false;
let captionContext={epoch:-1,entries:[],candidate:null,count:0};
let parallelContext={epoch:-1,groups:new Map(),counts:new Map(),stable:new Map()};
reader.onmessage=({data})=>{const request=pending.get(data.id);if(!request)return;if(data.progress!=null||data.stage){if(request.selection===selection)text('library-status',data.stage??`Reading ${data.progress.toLocaleString()} verified dialogue rows…`);return;}pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data.result);};
reader.onerror=()=>{for(const request of pending.values())request.reject(new Error('Library worker unavailable. Reopen the files.'));pending.clear();};
function request(action,body={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,selection});reader.postMessage({id,action,...body});});}
function currentGame(){return $('game').value;}
function invalidate(){epoch++;stable=null;activeJob?.abort();$('crop-preview').hidden=true;return epoch;}
function updatePreview(){document.body.classList.toggle('ocr-running',scanning&&$('role').value==='receiver'&&receiverSource.active&&!['ended','error','paused'].includes(sourceState?.status)&&!document.hidden);}
const optionIds=['ocr-language','player-voice','show-english','extra-regions','cinematic-regions','ocr-contrast'];
function setupCrop(){const game=currentGame(),saved=preferences[game]??{},selected=$('calibrate-region').value,keys=['dialogue',...Object.keys(extraCrops[game]??{})];$('calibrate-region').replaceChildren(...keys.map(key=>{const option=document.createElement('option');option.value=key;option.textContent={dialogue:'Dialogue',overhead:'Overhead captions',card:'Centered story card',comic:'Comic panels',panel:'Legacy dialogue panel',compact:'Compact subtitle strip'}[key];return option;}));$('calibrate-region').value=keys.includes(selected)?selected:'dialogue';const key=$('calibrate-region').value,crop=key==='dialogue'?saved.crop??crops[game]:saved.regions?.[key]??extraCrops[game][key];['left','top','width','height'].forEach((field,i)=>$('crop-'+field).value=String(crop[i]*100));$('picture-area').value=saved.picture??'window';for(const id of optionIds)if(saved[id]!=null){if($(id).type==='checkbox')$(id).checked=saved[id];else $(id).value=saved[id];}}
function cropValue(){const values=['left','top','width','height'].map(key=>Number($('crop-'+key).value)/100);if(values.some(v=>!Number.isFinite(v)||v<0||v>1)||values[2]<=0||values[3]<=0||values[0]+values[2]>1.00001||values[1]+values[3]>1.00001)throw new Error('Keep the crop inside the video.');return values;}
async function savePreferences(){invalidate();const saved=preferences[currentGame()]??{},key=$('calibrate-region').value,value=cropValue();preferences[currentGame()]={...saved,...key==='dialogue'?{crop:value}:{regions:{...saved.regions,[key]:value}},picture:$('picture-area').value,...Object.fromEntries(optionIds.map(id=>[id,$(id).type==='checkbox'?$(id).checked:$(id).value]))};await put('preferences',preferences).catch(()=>text('storage-status','Calibration is temporary; browser storage is unavailable.'));}
async function reportStorage(requestPersistence=false){const state=await storageStatus(requestPersistence);text('storage-status',`${state.persistent?'Persistent browser storage granted':'Browser cache is best effort; retain your Files copies'}${state.usage!=null?` · ${(state.usage/1024**2).toFixed(1)} MiB cached`:''}${state.quota!=null?` · ${(Math.max(0,state.quota-(state.usage??0))/1024**3).toFixed(2)} GiB browser quota remaining (not device free space)`:''}. Audio packs stay in Files and must be reselected after reopening.`);return state;}
function libraryStatus(){
 if(!library){declaredAudio.clear();text('pack-status','');text('coverage-status','');text('library-status','Open your exported catalog ZIP and optional voice ZIPs from On My iPhone.');return;}
 const coverage=library.manifest.coverage;
 declaredAudio=new Set(library.manifest.packs.flatMap(p=>p.clips));
 text('library-status',`${library.manifest.title} · ${library.rowCount.toLocaleString()} bilingual rows · ${available.size.toLocaleString()} unique voice clips accessible this session${coverage.partial?' · Partial catalog: newer/unmapped scenes remain unsupported':''}. ${available.size?'Audio packs are open.':'Reselect voice ZIPs for playback.'}`);
 text('pack-status',`${selectedPacks} voice packs selected · ${(selectedBytes/1024**3).toFixed(2)} GiB selected. Audio is read per clip, without importing whole packs.`);
 const coverageNotes={heavyrain:'Original-voice bindings use installed game assets. Gameplay OCR verification is in progress; untested chapters and branches remain outside verified coverage.',beyond:'Opening narration, police and laboratory overlap segments pass desktop OCR. Later chapters, branches and mobile gameplay footage remain unverified.',zzz:'Comic crops pass synthetic layout checks; real mobile comic footage verification remains pending.',wuwa:'Sampled dialogue and centered cards pass; some resized movie/story captions still miss.',pragmata:'Mobile layout checks use synthetic scenes; real browser footage verification remains pending.',cyberpunk:'Small overhead captions still miss in recorded footage. Verify your subtitle size and crop.',witcher3:'Sampled cutscene captions pass; top-edge NPC captions still miss in recorded footage.',nte:'Sampled movie radio/intro cards pass; wrapped subtitles and some movie variants still miss.',honkai3:'Sampled modern, legacy and multi-page panels pass both tested resolutions. Newer chapters remain outside the verified catalog.',hito:'Fixed catalog rows are text-only. Mobile does not run the desktop grammar generator.'};
 text('coverage-status','Browser OCR coverage: '+coverageNotes[library.manifest.game]);
}
$('library-files').onchange=async event=>{
 const token=++selection;invalidate();
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
$('forget-library').onclick=async()=>{selection++;invalidate();scanning=false;updatePreview();stable=null;await request('forget');library=null;available.clear();selectedBytes=selectedPacks=0;await remove('catalog').catch(()=>{});libraryStatus();render();};
function saveHistory(){const favorites=history.filter(r=>r.favorite).slice(-5000),rest=history.filter(r=>!r.favorite).slice(-500);history=[...favorites,...rest].sort((a,b)=>a.createdAt-b.createdAt);return put('history',history).catch(()=>text('storage-status','Transcript history is temporary; storage could not be saved.'));}
function render(){
 window.dispatchEvent(new CustomEvent('mobile-history',{detail:history.map(r=>({...r,source:'mobile-ocr'}))}));
 const panel=$('transcript');panel.replaceChildren();
 for(const line of history.filter(r=>r.game===currentGame()&&(!$('favorites-only').checked||r.favorite)).slice(-100).reverse()){
  const item=document.createElement('article');item.className='transcript-line';
  if(line.speakerChinese||line.speakerEnglish){const speaker=document.createElement('strong');speaker.textContent=line.speakerChinese??line.speakerEnglish;item.append(speaker);}
  const chinese=document.createElement('p');chinese.lang=line.sourceLocale??'zh-Hans';chinese.className='transcript-chinese';chinese.textContent=line.sourceText??line.chinese;item.append(chinese);
  if($('show-english').checked){const english=document.createElement('p');english.lang=line.translationLocale??'en';english.textContent=line.translationText??line.english;item.append(english);}
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
   for(const [value,lang] of [[row.sourceText??row.chinese,row.sourceLocale??'zh-Hans'],[row.translationText??row.english,row.translationLocale??'en']]){const p=document.createElement('p');p.textContent=value;p.lang=lang;item.append(p);}
   const info=document.createElement('small');info.textContent=[row.speakerEnglish??row.speakerChinese,row.playerVoice?`${row.playerVoice} player voice`:null,row.sourceVoice?'Verified voice binding':'Text only — no verified original voice',row.textId].filter(Boolean).join(' · ');item.append(info);
   const choose=document.createElement('button');choose.textContent='Choose this line';choose.onclick=()=>{if(token!==selection||game!==currentGame())return;void addSearchLine(row);};item.append(choose);panel.append(item);
  }
 }catch(e){if(token===selection)text('match-status',e.message);}
};
$('find-text').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('find-line').click();}});
$('clear-history').onclick=()=>{invalidate();history=history.filter(r=>r.game!==currentGame());emitted.clear();void saveHistory();render();};
for(const key of ['left','top','width','height'])$('crop-'+key).onchange=()=>void savePreferences().catch(e=>text('match-status',e.message));
$('picture-area').onchange=()=>void savePreferences().catch(e=>text('match-status',e.message));
$('calibrate-region').onchange=setupCrop;
$('reset-crop').onclick=()=>{const game=currentGame(),key=$('calibrate-region').value,saved=preferences[game]??{};preferences[game]={...saved,...key==='dialogue'?{crop:crops[game]}:{regions:{...saved.regions,[key]:extraCrops[game][key]}}};setupCrop();void savePreferences();};
$('game').addEventListener('change',()=>{invalidate();scanning=false;updatePreview();setupCrop();render();});
const canvas=document.createElement('canvas');
function cropFrame(frame,region,target=canvas){return drawCrop(frame,target,region,$('picture-area').value);}
$('preview-crop').onclick=async()=>{
 if(busy){text('match-status','Pause OCR before previewing the crop.');return;}
 busy=true;const token=epoch;let frame;
 try{frame=await receiverSource.readFrame();if(token!==epoch)return;if(!frame)throw Error('Wait for a fresh screen frame, then try the crop again.');const preview=$('crop-preview');cropFrame(frame,cropValue(),preview);preview.hidden=false;}
 catch(e){if(token===epoch)text('match-status',e.message);}finally{frame?.release();busy=false;}
};
async function initEngine(){
 await resetting;
 const base=new URL('./ocr/',import.meta.url),lang=$('ocr-language').value;
 if(engine&&engineLanguage!==lang){await scanCompletion;await engine.terminate();engine=null;}
 if(engine)return engine;if(loading)return loading;
 loading=Promise.all(lang.split('+').map(code=>loadModel(code))).then(models=>createWorker(models,1,{workerPath:new URL('verified-worker.js',base).href,corePath:new URL('core/',base).href,langPath:new URL('lang/',base).href,cacheMethod:'none',workerBlobURL:false,logger:value=>{if(value.status==='loading language traineddata')text('match-status','Preparing private on-device OCR…');}})).then(async value=>{await value.setParameters({tessedit_pageseg_mode:'6',preserve_interword_spaces:'1'});engine=value;engineLanguage=lang;return value;}).finally(()=>loading=null);
 return loading;
}
async function refreshPackStatus(){
 try{const models=await Promise.all($('ocr-language').value.split('+').map(modelStatus));text('ocr-pack-status',models.map(m=>`${translate(m.builtin?'Bundled with application':m.installed?'Available offline':'Download required')} · ${formatBytes(m.bytes)}`).join(' + '));$('ocr-pack-download').disabled=models.every(m=>m.installed);$('ocr-pack-remove').disabled=models.every(m=>m.builtin||!m.installed);}catch(e){text('ocr-pack-status',e.message);}
}
void ocrManifest().then(data=>{const present=new Set([...$('ocr-language').options].map(o=>o.value));for(const [locale,code] of Object.entries(data.locales)){if(!present.has(code)){$('ocr-language').add(new Option(languageName(locale),code));present.add(code);}}return refreshPackStatus();}).catch(e=>text('ocr-pack-status',e.message));
$('ocr-pack-download').onclick=async()=>{const codes=$('ocr-language').value.split('+');$('ocr-pack-download').disabled=true;$('ocr-pack-progress').hidden=false;try{for(const code of codes)await loadModel(code,{download:true,onProgress:value=>$('ocr-pack-progress').value=value});}catch(e){text('ocr-pack-status',e.message);return;}finally{$('ocr-pack-download').disabled=false;$('ocr-pack-progress').hidden=true;}await refreshPackStatus();};
$('ocr-pack-remove').onclick=async()=>{scanning=false;invalidate();updatePreview();await resetting;await scanCompletion;if(loading)await loading.catch(()=>{});if(engine){await engine.terminate();engine=null;engineLanguage=null;}try{for(const code of $('ocr-language').value.split('+'))if(!(await modelStatus(code)).builtin)await removeModel(code);await refreshPackStatus();}catch(e){text('ocr-pack-status',e.message);}};
window.addEventListener('toolkit-interface-language',()=>void refreshPackStatus());
$('ocr-language').onchange=()=>{void refreshPackStatus();invalidate();scanning=false;updatePreview();text('match-status','OCR paused. Start with the selected subtitle language.');resetting=resetting.then(async()=>{await scanCompletion;if(loading)await loading.catch(()=>{});const old=engine;engine=null;if(old)await old.terminate();});};
$('ocr-start').onclick=async()=>{const token=invalidate();try{if(!library)throw new Error('Open a game catalog first.');if(library.manifest.game!==currentGame())throw new Error('Open a catalog for the selected game.');text('match-status','Loading on-device OCR…');await initEngine();if(token!==epoch)return;scanning=true;updatePreview();text('match-status','OCR ready. Keep this receiving page open while playing.');}catch(e){if(token===epoch)text('match-status',e.message);}};
$('ocr-pause').onclick=()=>{scanning=false;updatePreview();invalidate();text('match-status','OCR paused.');};
receiverSource.subscribe(value=>{if(!sourceState||sourceState.revision!==value.revision||sourceState.sessionId!==value.sessionId||sourceState.status!==value.status&&['ended','error','paused','stalled'].includes(value.status))invalidate();sourceState=value;updatePreview();});
window.addEventListener('mobile-source-changed',()=>{scanning=false;invalidate();updatePreview();text('match-status','Screen source changed. Connect it, then start OCR.');});
document.addEventListener('visibilitychange',()=>{invalidate();updatePreview();if(document.hidden)text('match-status','OCR suspended while the phone page is hidden.');});
for(const kind of ['freeze','pagehide'])window.addEventListener(kind,()=>{invalidate();updatePreview();});
function regions(){return captureRegions(currentGame(),preferences[currentGame()]?.crop??crops[currentGame()],$('extra-regions').checked,$('cinematic-regions').checked,preferences[currentGame()]?.regions).map(region=>$('ocr-contrast').value==='raw'?{...region,raw:true}:region);}
async function scan(){
 if(busy||!scanning||!engine||document.hidden||!library||library.manifest.game!==currentGame()||$('role').value!=='receiver'||!receiverSource.active)return;
 busy=true;let finishScan,frame;scanCompletion=new Promise(resolve=>finishScan=resolve);const token=epoch,start=performance.now(),controller=new AbortController();activeJob=controller;
 try{
  frame=await receiverSource.readFrame({signal:controller.signal});if(token!==epoch||!frame)return;
  let accepted=null,acceptedMany=null,ambiguous=false,dialogueMenu=false;
  for(const region of regions()){
   if(token!==epoch)return;
   if(region.channel!=='dialogue'&&dialogueMenu)continue;
   const image=cropFrame(frame,region.crop);
   const recognized=await recognizeRegion(engine,image,region,$('ocr-language').value,()=>token===epoch);if(token!==epoch)return;if(!recognized)continue;
   const parsed=candidates(recognized,region,image.width,image.height,currentGame());if(region.channel==='dialogue')dialogueMenu=parsed.menu;
   let match=await request('match-candidates',{values:parsed.values,channel:region.channel,player:$('player-voice').value,fragment:region.fragment});if(token!==epoch)return;
   if(currentGame()==='heavyrain'&&region.channel==='dialogue'){
    if(parallelContext.epoch!==token||parsed.menu)parallelContext={epoch:token,groups:new Map(),counts:new Map(),stable:new Map()};
    const stamp=performance.now();parallelContext.groups=new Map([...parallelContext.groups].filter(([,time])=>stamp-time<=12000));
    if(!parsed.menu){
     let result=await request('scene-matches',{values:parsed.values,groups:[...parallelContext.groups.keys()]});if(token!==epoch)return;
     parallelContext.counts=new Map(result.groups.map(group=>[group,(parallelContext.counts.get(group)??0)+1]));
     for(const[group,count]of parallelContext.counts)if(count>=2)parallelContext.groups.set(group,stamp);
     parallelContext.groups=new Map([...parallelContext.groups].sort((a,b)=>b[1]-a[1]).slice(0,16));
     result=await request('scene-matches',{values:parsed.values,groups:[...parallelContext.groups.keys()]});if(token!==epoch)return;
     acceptedMany=result.matches.map(hit=>({...hit,channel:region.channel}));accepted=acceptedMany[0]??null;
    }
    break;
   }
   if(currentGame()==='beyond'&&region.channel==='dialogue'){
    if(parallelContext.epoch!==token||parsed.menu)parallelContext={epoch:token,groups:new Map(),counts:new Map(),stable:new Map()};
    if(captionContext.epoch!==token||parsed.menu)captionContext={epoch:token,entries:[],candidate:null,count:0};
    const stamp=performance.now();captionContext.entries=captionContext.entries.filter(item=>stamp-item.time<=12000);
    if(!parsed.menu){
     if(captionContext.entries.length){const contextual=await request('match-context',{previous:[...new Set(captionContext.entries.flatMap(item=>item.values))],values:parsed.values,channel:region.channel,player:$('player-voice').value});if(token!==epoch)return;if(contextual.state==='matched')match=contextual;}
     const fragments=await request('context-fragments',{values:parsed.values});if(token!==epoch)return;const key=JSON.stringify(fragments);
     captionContext.count=fragments.length&&captionContext.candidate===key?captionContext.count+1:fragments.length?1:0;captionContext.candidate=fragments.length?key:null;
     if(captionContext.count>=2){captionContext.entries=captionContext.entries.filter(item=>JSON.stringify(item.values)!==key);captionContext.entries.push({time:stamp,values:fragments});captionContext.entries=captionContext.entries.slice(-8);}
     const hits=await request('simultaneous-matches',{values:parsed.values,player:$('player-voice').value,primary:match});if(token!==epoch)return;
     acceptedMany=hits.map(hit=>({...hit,channel:region.channel}));accepted=acceptedMany[0]??null;
    }
    break;
   }
   if(match.state==='ambiguous')ambiguous=true;
   if(match.state==='matched')accepted={...match,channel:region.channel};
   if(accepted)break;
  }
  const elapsed=performance.now()-start;samples.push({kind:'ocr',ms:elapsed});samples=samples.slice(-120);
  if(!accepted){stable=null;if(['heavyrain','beyond'].includes(currentGame()))parallelContext.stable=confirmCaptions(parallelContext.stable,[],performance.now(),currentGame()==='beyond'&&!ambiguous);text('match-status',ambiguous?'Ambiguous dialogue/voice; skipped.':'No verified match: unsupported scene, incomplete text, or crop needs calibration.');return;}
  const matches=acceptedMany??[accepted];let changed=false;
  if(acceptedMany)parallelContext.stable=confirmCaptions(parallelContext.stable,matches.map(hit=>hit.row.id),performance.now(),currentGame()==='beyond');
  for(const hit of matches){
  const key=hit.row.id;stable=acceptedMany?{key,count:parallelContext.stable.get(key)?.count??1}:stable?.key===key?{key,count:stable.count+1}:{key,count:1};
  text('match-status',`Verified ${hit.channel} match · ${elapsed.toFixed(0)} ms${stable.count<2?' · confirming…':''}`);
  if(stable.count===2&&(!emitted.has(key)||Date.now()-emitted.get(key)>10000)&&!history.some(r=>r.id===key&&Date.now()-r.createdAt<10000)){
   emitted.set(key,Date.now());history.push({...hit.row,score:hit.score,matching:hit.score===100?'exact':'fuzzy',game:currentGame(),createdAt:Date.now(),favorite:false});changed=true;
   if(emitted.size>2048){const cutoff=Date.now()-10000;for(const [id,time] of emitted)if(time<cutoff)emitted.delete(id);}
  }
  }
  if(changed){render();await saveHistory();}
 }catch(e){if(token===epoch){parallelContext.epoch=-1;text('match-status',`OCR needs attention: ${e.message}`);}}finally{frame?.release();if(activeJob===controller)activeJob=null;busy=false;finishScan();}
}
// Probe through the same bounded source while OCR is paused, so connecting and
// unchanged-picture status reflects frame observations, not iframe load events.
setInterval(async()=>{
 if(scanning){void scan();return;}
 if(busy||document.hidden||!receiverSource.active)return;
 busy=true;let frame;try{frame=await receiverSource.readFrame();}catch{/* Source owns its safe status. */}finally{frame?.release();busy=false;}
},600);
$('library-report').onclick=async()=>{
 const observations={device:$('test-device').value,outcome:$('test-outcome').value,...Object.fromEntries(['large','playback','reload','reboot','update','gameplay'].map(name=>[name,$('test-'+name).checked]))};
 const storage=await storageStatus(),data={format:'proxy-mobile-library-report-v1',build:document.documentElement.dataset.buildCommit??null,game:currentGame(),createdAt:new Date().toISOString(),libraryRows:library?.rowCount??0,availableVoices:available.size,selectedBytes,selectedPacks,openMs,storage,samples:samples.slice(-120),transcriptRows:history.filter(r=>r.game===currentGame()).length,observations,physicalDeviceVerified:observations.device==='iphone'&&observations.outcome==='passed'&&['large','playback','reload','reboot','update','gameplay'].every(name=>observations[name])};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='mobile-library-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
async function restore(){const token=selection;try{preferences=await get('preferences')??{};history=await get('history')??[];if(token===selection){const result=await request('restore');if(token!==selection)return;library=result.catalog;if(library&&!$('game').disabled){$('game').value=library.manifest.game;$('game').dispatchEvent(new Event('change'));}libraryStatus();}setupCrop();render();await reportStorage();}catch{setupCrop();text('storage-status','Browser cache unavailable. Open the catalog again from Files.');}}
void restore();
for(const id of ['player-voice','extra-regions','cinematic-regions'])$(id).addEventListener('change',()=>{invalidate();});
for(const id of optionIds)$(id).addEventListener('change',()=>void savePreferences().catch(e=>text('match-status',e.message)));
if(!document.getElementById('app-root')&&'serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').then(registration=>{
 $('reload-build').onclick=async()=>{if($('role').disabled)return;await registration.update().catch(()=>{});if(registration.installing)await new Promise(resolve=>{const worker=registration.installing;worker.addEventListener('statechange',()=>{if(['installed','redundant'].includes(worker.state))resolve();});setTimeout(resolve,5000);});if(registration.waiting){const activated=new Promise(resolve=>{navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true});setTimeout(resolve,3000);});registration.waiting.postMessage('activate-update');await activated;}const url=new URL(location.href);url.searchParams.set('v',String(Date.now()));location.replace(url);};
}).catch(()=>{});

export const libraryLifecycle={
 get history(){return history.map(r=>({...r,source:'mobile-ocr'}));},
 get busy(){return $('library-files').disabled||voiceBusy;},
 get ready(){return Boolean(library);},
 stop(){scanning=false;invalidate();updatePreview();$('voice-player').pause();resetting=resetting.then(async()=>{await scanCompletion;if(loading)await loading.catch(()=>{});const previous=engine;engine=null;engineLanguage=null;await previous?.terminate();});},
 async favorite(id,game,value){for(const row of history)if(row.id===id&&row.game===game)row.favorite=value;await saveHistory();render();},
 async voice(row){if(!available.has(row.audio))throw Error('Reselect the original voice ZIP in Library.');return request('voice',{sha:row.audio});},
 search:text=>request('search',{text}),
 choose:addSearchLine
};
