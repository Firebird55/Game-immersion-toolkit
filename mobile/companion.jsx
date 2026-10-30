import {useInterfaceTranslation} from '../lib/interface-language';
import {InterfaceLanguage,LocalizedInterface} from '../lib/interface-language';
import React,{useCallback,useEffect,useState,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';
import {createReader,createReadingSession,restoreLocalSettings,ReadingOptionsDialog,SettingsPanel,shouldHideTranslation} from '@firebird55/lexirise-components';
import '@firebird55/lexirise-components/styles.css';
import './companion.css';
import {createMobileReaderContext} from './reader-context.mjs';

const $=id=>document.getElementById(id);
const params=new URLSearchParams(location.search);
if(params.get('pc')==='1'&&['localhost','127.0.0.1'].includes(location.hostname)){$('role').value='sender';$('source').value='pc';}
if([...$('game').options].some(o=>o.value===params.get('game')))$('game').value=params.get('game');
const [capture,library,storage,cryptoVault,protocol]=await Promise.all([
 import(/* @vite-ignore */ new URL('./capture.js',document.baseURI).href),
 import(/* @vite-ignore */ new URL('./mobile-ui.mjs',document.baseURI).href),
 import(/* @vite-ignore */ new URL('./storage.mjs',document.baseURI).href),
 import(/* @vite-ignore */ new URL('./vault.mjs',document.baseURI).href),
 import(/* @vite-ignore */ new URL('./transcript-channel.mjs',document.baseURI).href)
]);
const gateway='https://game-immersion-lexirise.boazbrak.workers.dev';
const keyOf=protocol.rowKey;
let pcHistory=[],saveQueue=Promise.resolve();
const persistPC=()=>{const copy=structuredClone(pcHistory);saveQueue=saveQueue.catch(()=>{}).then(()=>storage.put('pc-history',copy));return saveQueue;};
function mergePC(rows){const map=new Map(pcHistory.map(r=>[keyOf(r),r]));for(const row of rows){const old=map.get(keyOf(row));map.set(keyOf(row),{...row,favorite:old?.favorite??false});}const all=[...map.values()].sort((a,b)=>a.createdAt-b.createdAt);pcHistory=[...all.filter(r=>r.favorite).slice(-5000),...all.filter(r=>!r.favorite).slice(-500)];}

// Keep row and shared-reader component identities stable across App updates.
function Line({row,current=false,Reader,readerContext,mode,unlocked,chinese,english,options,working,connected,voiceReady,voiceStatus,onPlay,onFavorite,onSave}){
 const uiText=useInterfaceTranslation();const [summary,setSummary]=useState(null);
 const onSummary=useCallback(value=>setSummary({...value,readerContext}),[readerContext]);
 const unknownWords=summary?.readerContext===readerContext&&summary?.id===(Number(row.id)||row.createdAt)&&summary?.text===(row.sourceText??row.chinese)?summary.unknownWords:null;
 return <article className={'dialogue '+(current?'current-dialogue':'')}>
  <div className="line-meta"><strong>{[row.speakerChinese,row.speakerEnglish].filter(Boolean).join(' · ')||'Dialogue'}</strong><span>{new Date(row.createdAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span></div>
  {chinese&&(mode==='lexirise'&&unlocked&&Reader?<Reader key={readerContext} id={Number(row.id)||row.createdAt} text={row.sourceText??row.chinese} sourceLanguage={row.sourceLanguage??'zh'} sentenceTranslation={row.translationText??row.english} options={options} current={current} onSummary={onSummary}/>:<p className="current-chinese migaku-sentence" data-migaku-line-id={keyOf(row)} lang={row.sourceLocale??'zh-Hans'}>{row.sourceText??row.chinese}</p>)}
  {english&&!shouldHideTranslation(options.hideEnglishAt,unknownWords)&&<p className="translation" lang={row.translationLocale??'en'}>{row.translationText??row.english}</p>}
  {voiceStatus&&<p className="hint voice-status">{uiText(voiceStatus)}{row.audio&&<button onClick={()=>$('library-files').click()}>{uiText("Open voice library")}</button>}</p>}
  <div className="line-actions"><button onClick={()=>onPlay(row)} disabled={working||!row.audio||!voiceReady}>{uiText("▶ Play voice")}</button><button aria-pressed={Boolean(row.favorite)} onClick={()=>onFavorite(row)}>{row.favorite?uiText("★ Favorited"):uiText("☆ Favorite")}</button>{mode==='lexirise'&&<button disabled={!unlocked||working} onClick={()=>onSave(row)}>{uiText("Save sentence")}</button>}</div>
 </article>;}

function App(){
 const uiText=useInterfaceTranslation();
 const [view,setView]=useState($('role').value==='sender'?'settings':'reader'),[role,setRole]=useState($('role').value),[source,setSource]=useState($('source').value),[game,setGame]=useState($('game').value);
 const [rows,setRows]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[status,setStatus]=useState('Ready to connect'),[filter,setFilter]=useState('history'),[search,setSearch]=useState(''),[limit,setLimit]=useState(30),[before,setBefore]=useState(null),[connected,setConnected]=useState(false),[pcSource,setPCSource]=useState(null);
 const [options,setOptions]=useState(restoreLocalSettings(null)),[mode,setMode]=useState('migaku'),[chinese,setChinese]=useState(true),[english,setEnglish]=useState(true),[optionsOpen,setOptionsOpen]=useState(false),[accountOpen,setAccountOpen]=useState(false),[dev,setDev]=useState(params.get('developer')==='1');
 const [unlocked,setUnlocked]=useState(false),[hasVault,setHasVault]=useState(false),[vaultAction,setVaultAction]=useState(''),[working,setWorking]=useState(false),[revision,setRevision]=useState(0),[decks,setDecks]=useState([]),[deck,setDeck]=useState(''),[deckTitle,setDeckTitle]=useState(''),[update,setUpdate]=useState(null);
 const [rememberKey,setRememberKey]=useState(false);
 const [translationFontSize,setTranslationFontSize]=useState(14),[live,setLive]=useState(false),[ocrActive,setOCRActive]=useState(false);
 const readerPane=useRef(null),readerOwner=useRef(null),activeReaderGeneration=useRef(0);
 // Shared SettingsPanel reloads when adapter identity changes. Keep drafts
 // stable while the owner publishes loading/ready revisions.
 const settingsAdapter=useRef({load:()=>readerOwner.current.reload(),patch:p=>readerOwner.current.patch(p)});
 const session=useRef(null),reader=useRef(null),vault=useRef(null),audioUrl=useRef(null),hydrated=useRef(false),busy=useRef(null),mediaRevision=useRef(0),viewerCode=useRef(null);
 function retireReaderAction(){if(busy.current?.reader){busy.current=null;setWorking(false);}}
 if(!vault.current)vault.current=cryptoVault.createVault(storage,{onLock:()=>{readerOwner.current?.reset();session.current=null;reader.current=null;setUnlocked(false);setAccountOpen(false);setDecks([]);setDeck('');setDeckTitle('');setRevision(r=>r+1);}});
 // Abort may reject before React commits, so retire account actions immediately.
 if(!readerOwner.current)readerOwner.current=createMobileReaderContext({request:transport,createSession:createReadingSession,createReader,onChange:()=>{activeReaderGeneration.current++;retireReaderAction();setRevision(r=>r+1);}});
 const refresh=()=>setRows([...library.libraryLifecycle.history,...pcHistory]);
 const run=async(fn,isCurrent=()=>true,readerAction=false)=>{if(busy.current)return;const action={reader:readerAction};busy.current=action;setWorking(true);setError('');try{await fn();}catch(e){if(busy.current===action&&isCurrent())setError(e.message??'This action could not complete. Retry when ready.');}finally{if(busy.current===action){busy.current=null;setWorking(false);}}};
 // Retired requests may ignore abort. Their completion cannot release a newer
 // action; vault operations keep their gate when they internally lock/reset.
 // Async failures belong to the initiating reader just like successful results.
 const runReader=fn=>{const generation=activeReaderGeneration.current,client=session.current,isCurrent=()=>session.current===client&&activeReaderGeneration.current===generation;return run(()=>fn({client,isCurrent}),isCurrent,true);};
 useEffect(()=>{
  let mounted=true,finishRestore;
  // Replay live PC events after restoration, preserving event order and saved
  // favorites. A late history read must never overwrite newly received lines.
  const restored=new Promise(resolve=>{finishRestore=resolve;});
  const change=()=>{setRole($('role').value);setSource($('source').value);setGame($('game').value);setLimit(30);setBefore(null);refresh();};
  const stop=()=>{mediaRevision.current++;capture.captureLifecycle.stop();library.libraryLifecycle.stop();setConnected(false);if($('role').value==='sender')setView('settings');change();};
  $('role').addEventListener('change',stop);$('source').addEventListener('change',stop);$('game').addEventListener('change',change);
  const history=()=>refresh();window.addEventListener('mobile-history',history);
  const pc=e=>{const detail=e.detail;void restored.then(()=>{if(!mounted)return;mergePC(detail.rows);refresh();if(detail.message.type==='page')setBefore(detail.message.before);void persistPC().catch(()=>setError('PC history is temporary because browser storage is unavailable.'));});};window.addEventListener('pc-transcript',pc);
  const capabilities=e=>setPCSource(e.detail.source);window.addEventListener('pc-capabilities',capabilities);
  const stream=e=>{setConnected(e.detail.state==='connected');setLive(e.detail.live!==false);setGame($('game').value);};window.addEventListener('mobile-stream',stream);
  const ocr=e=>{setOCRActive(e.detail.scanning);if(e.detail.scanning&&$('role').value==='receiver')setView('reader');};window.addEventListener('mobile-ocr-state',ocr);
  const observer=new MutationObserver(()=>setStatus($('status').textContent));observer.observe($('status'),{childList:true,subtree:true,characterData:true});
  const settingsChanged=()=>{if(vault.current.unlocked)void readerOwner.current.reload().catch(e=>{if(e.name!=='AbortError')setError(e.message);});};window.addEventListener('lexirise-account-settings',settingsChanged);
  const viewer=e=>{viewerCode.current=e.detail.code;const code=e.detail.code;if(!code||code.length<4)return;void run(async()=>{
   if(vault.current.unlocked){await vault.current.linkViewer(code);return;}
   if(!await vault.current.exists())return;
   try{await vault.current.unlockViewer(code);await openSession();setNotice('Lexirise unlocked with your stream code.');}
   catch{vault.current.lock();setNotice('Screen connection ready. Unlock Lexirise once in Settings to link this stream code.');}
  });};window.addEventListener('mobile-viewer-code',viewer);
  const visibility=()=>vault.current.visibility(document.hidden),exit=()=>vault.current.lock();document.addEventListener('visibilitychange',visibility);window.addEventListener('pagehide',exit);const resume=event=>{if(event.persisted)void run(async()=>{if(await vault.current.restoreRemembered())await openSession();});};window.addEventListener('pageshow',resume);
  void (async()=>{try{pcHistory=await storage.get('pc-history')??[];const preferences=await storage.get('browser-reading')??{};setOptions(restoreLocalSettings(preferences.options));setTranslationFontSize(Number.isFinite(preferences.translationFontSize)&&preferences.translationFontSize>=10&&preferences.translationFontSize<=32?preferences.translationFontSize:14);setMode(preferences.mode==='lexirise'?'lexirise':'migaku');setChinese(preferences.chinese!==false);setEnglish(preferences.english!==false);setHasVault(await vault.current.exists());if(await vault.current.restoreRemembered()){setRememberKey(true);setUnlocked(true);const signal=vault.current.signal;void openSession().catch(()=>{if(mounted&&!signal.aborted)setError('Saved key restored. Lexirise could not be reached; retry from Account settings when connected.');});}refresh();}catch{setError('Browser storage is unavailable. Reading works this session; reconnect your library to restore local content.');}finally{hydrated.current=true;setLoading(false);finishRestore();}})();
  if(document.documentElement.dataset.buildCommit&&'serviceWorker' in navigator)void (async()=>{const existing=await navigator.serviceWorker.getRegistration();const reg=existing??await navigator.serviceWorker.register('./sw.js');if(reg.waiting)setUpdate(reg);reg.addEventListener('updatefound',()=>{reg.installing?.addEventListener('statechange',()=>{if(reg.waiting)setUpdate(reg);});});if(existing&&navigator.onLine)void reg.update().catch(()=>{});})().catch(()=>{});
  return ()=>{mounted=false;vault.current.lock();observer.disconnect();window.removeEventListener('mobile-viewer-code',viewer);window.removeEventListener('lexirise-account-settings',settingsChanged);$('role').removeEventListener('change',stop);$('source').removeEventListener('change',stop);$('game').removeEventListener('change',change);window.removeEventListener('mobile-history',history);window.removeEventListener('pc-transcript',pc);window.removeEventListener('pc-capabilities',capabilities);window.removeEventListener('mobile-stream',stream);window.removeEventListener('mobile-ocr-state',ocr);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('pagehide',exit);window.removeEventListener('pageshow',resume);};
 },[]);
 useEffect(()=>{document.body.dataset.role=role;document.body.dataset.source=source;document.body.dataset.view=view;document.body.classList.toggle('developer-mode',dev);$('source-control').hidden=role==='sender';for(const panel of document.querySelectorAll('[data-panel]'))panel.hidden=(!dev&&panel.dataset.panel!==view)||Boolean(panel.dataset.role&&panel.dataset.role!==role)||Boolean(panel.dataset.source&&panel.dataset.source!==source);},[view,role,source,dev]);
 useEffect(()=>{document.body.classList.toggle('reader-active',role==='receiver'&&connected&&(source==='pc'||live&&ocrActive));},[role,connected,live,source,ocrActive]);
 useEffect(()=>{if(hydrated.current)void storage.put('browser-reading',{version:1,options,translationFontSize,mode,chinese,english}).catch(()=>setError('Reading preferences could not be saved.'));},[options,translationFontSize,mode,chinese,english]);
 useEffect(()=>{
  // Lookup portals live outside the reader, including when it uses a shadow root.
  // Keep the current line in a separately scrollable upper pane on phones.
  let open=false;
  const sync=()=>{const next=Boolean(document.querySelector('.word-sheet'));if(next===open)return;open=next;readerPane.current?.classList.toggle('lookup-open',open);if(open&&matchMedia('(max-width:650px), (max-height:500px) and (pointer:coarse)').matches&&!readerPane.current?.hidden)readerPane.current?.querySelector('.current-card')?.scrollIntoView({block:'start',behavior:'instant'});};
  const observer=new MutationObserver(sync);observer.observe(document.body,{childList:true,subtree:true});sync();return ()=>observer.disconnect();
 },[]);
 async function transport(path,method,payload,signal){
  const key=vault.current.credential(),response=await fetch(gateway+'/v1/request',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify({path,method,...payload===undefined?{}:{payload}}),cache:'no-store',signal:AbortSignal.any([signal,vault.current.signal,AbortSignal.timeout(30000)])});
  return {status:response.status,responseText:await response.text()};
 }
 function sessionFor(row){return readerOwner.current.pair({game:row?.game??game,sourceLocale:row?.sourceLocale??'zh-Hans',sourceLanguage:row?.sourceLanguage??'zh'});}
 async function openSession(){await readerOwner.current.reload();if(!vault.current.unlocked)return;setUnlocked(true);}
 async function submitVault(event){event.preventDefault();const form=event.currentTarget,data=new FormData(form),action=vaultAction||(!hasVault?'connect':'unlock');const key=data.get('key'),pass=data.get('pass'),confirm=data.get('confirm');form.reset();await run(async()=>{
  if(action==='change'){await vault.current.changePassphrase(pass,confirm);setRememberKey(false);}
  else if(action==='unlock')await vault.current.unlock(pass);
  else if(rememberKey)await vault.current.connectRemembered(key);
  else await vault.current.connect(key,pass,confirm);
  if(action==='unlock'&&rememberKey)await vault.current.remember(true);
  // Persisted vault state survives a temporary settings outage. Retrying only
  // needs the passphrase; reader sessions still wait for resolved settings.
  setHasVault(await vault.current.exists());setVaultAction('');
  if(action!=='change')try{await openSession();}catch(error){if(vault.current.remembered)setUnlocked(true);else vault.current.lock();throw error;}
  if(action!=='change'&&viewerCode.current)await vault.current.linkViewer(viewerCode.current);
  setNotice('Lexirise unlocked for this session.');
 });}
 async function blobFor(row){return row.source==='mobile-ocr'?library.libraryLifecycle.voice(row):capture.captureLifecycle.audio(row);}
 async function play(row){await run(async()=>{const token=mediaRevision.current,blob=await blobFor(row);if(token!==mediaRevision.current)return;if(audioUrl.current)URL.revokeObjectURL(audioUrl.current);audioUrl.current=URL.createObjectURL(blob);$('voice-player').src=audioUrl.current;try{await $('voice-player').play();}catch(error){if(error.name!=='NotAllowedError')throw error;setNotice('Voice ready. Tap play on the audio control below.');}});}
 async function favorite(row){await run(async()=>{if(row.source==='mobile-ocr')await library.libraryLifecycle.favorite(row.id,row.game,!row.favorite);else{pcHistory=pcHistory.map(r=>keyOf(r)===keyOf(row)?{...r,favorite:!r.favorite}:r);await persistPC();refresh();}});}
 async function loadDecks({client,isCurrent}){
  const account=(await client.requestAccount('GET','/v1/me')).user?.id;if(!isCurrent())return;if(account==null)throw Error('Could not verify deck ownership.');const found=[];
  for(let offset=0;offset<10000;offset+=100){const page=(await client.requestAccount('GET','/v1/decks?language='+encodeURIComponent(current?.sourceLanguage??'zh')+'&limit=100&offset='+offset)).decks??[];if(!isCurrent())return;found.push(...page.filter(d=>d.owner_user_id===account&&(d.language??d.lang)===(current?.sourceLanguage??'zh')&&d.unit_type==='sentence'&&d.deck_type==='snapshot'));if(page.length<100)break;}
  if(isCurrent())setDecks(found);
 }
 async function saveSentence(row){await runReader(async({isCurrent})=>{
  if(!session.current)throw Error('Unlock Lexirise in Settings first.');if((row.sourceLanguage??'zh')!==(current?.sourceLanguage??'zh'))throw Error('Select this learning language before choosing a sentence deck.');const client=sessionFor(row).session,signal=vault.current.signal,credential=vault.current.credential();
  const payload={language:row.sourceLanguage??'zh',text:row.sourceText??row.chinese,mode:'sentence',translation:row.translationText??row.english,notes:[row.game,row.speakerChinese||row.speakerEnglish].filter(Boolean).join(' — '),tags:[row.game]};
  if(row.audio){const blob=await blobFor(row);if(!isCurrent())return;const response=await fetch(gateway+'/v1/audio',{method:'POST',headers:{Authorization:'Bearer '+credential,'Content-Type':blob.type},body:blob,cache:'no-store',signal:AbortSignal.any([signal,AbortSignal.timeout(30000)])});if(!isCurrent())return;if(!response.ok)throw Error('Original voice upload failed. Retry saving when ready.');const uploaded=await response.json();if(!isCurrent())return;if(!/^https:\/\//.test(uploaded.publicUrl))throw Error('Audio upload was not confirmed.');payload.audioUrls=[uploaded.publicUrl];}
  const result=await client.requestAccount('POST','/v1/vocabulary',payload);if(!isCurrent())return;const id=result.item?.id??result.item?.saved_expression_id;if(!Number.isSafeInteger(id))throw Error('Sentence save was not confirmed. Retry to check.');
  if(deck){const added=await client.requestAccount('POST','/v1/decks/'+deck+'/items',{saved_expression_selection:{mode:'explicit',ids:[id]}});if(!isCurrent())return;if(!(Number(added.added_count??added.addedCount)>0))throw Error('The sentence was saved, but the deck addition was not confirmed. Check the deck before retrying.');}setNotice('Sentence saved to Lexirise'+(deck?' and added to the selected deck.':'.'));
 });}
 const selected=rows.filter(r=>r.game===game&&(source==='mobile'?r.source==='mobile-ocr':r.source?.startsWith('pc-'))).sort((a,b)=>b.createdAt-a.createdAt||Number(b.id)-Number(a.id));
 const matches=selected.filter(r=>(filter!=='favorites'||r.favorite)&&(!search||[r.sourceText??r.chinese,r.translationText??r.english,r.speakerChinese,r.speakerEnglish].some(t=>t?.toLowerCase().includes(search.toLowerCase()))));
 const current=source==='pc'&&pcSource?selected.find(r=>r.source===pcSource):selected[0];
 useEffect(()=>{activeReaderGeneration.current++;retireReaderAction();const pair=unlocked?sessionFor(current):null;session.current=pair?.session??null;reader.current=pair?.reader??null;setDecks([]);setDeck('');},[unlocked,current?.game,current?.sourceLocale,current?.sourceLanguage,revision]);
 const lineProps=row=>({Reader:unlocked?sessionFor(row)?.reader.ReadingText:null,readerContext:JSON.stringify([revision,mode,sessionFor(row)?.key]),mode,unlocked,chinese,english,options,working,connected,voiceReady:row.source==='mobile-ocr'?library.libraryLifecycle.canPlay(row):connected,voiceStatus:row.source==='mobile-ocr'?library.libraryLifecycle.voiceStatus(row):'',onPlay:play,onFavorite:favorite,onSave:saveSentence});
 const go=next=>{setView(['library','connection'].includes(next)?'settings':next);setError('');};
 const applyUpdate=()=>run(async()=>{if($('role').disabled||capture.captureLifecycle.active||library.libraryLifecycle.busy)throw Error('Stop sharing and finish library operations before updating.');vault.current.lock();const registration=update??await navigator.serviceWorker?.getRegistration();await registration?.update().catch(()=>{});const installing=registration?.installing;if(installing)await new Promise((resolve,reject)=>{const timer=setTimeout(()=>finish(Error('The update is still downloading. Try again shortly.')),15000);const check=()=>{if(['installed','redundant'].includes(installing.state))finish();};function finish(error){clearTimeout(timer);installing.removeEventListener('statechange',check);error?reject(error):resolve();}installing.addEventListener('statechange',check);check();});if(capture.captureLifecycle.active||library.libraryLifecycle.busy)throw Error('Finish sharing and library operations before applying the update.');if(registration?.waiting){navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload(),{once:true});registration.waiting.postMessage('activate-update');}else {const url=new URL(location.href);url.searchParams.set('v',String(Date.now()));location.replace(url);}});
 $('reload-build').onclick=applyUpdate;
 return <>
  <header className="companion-header"><div><p className="eyebrow">{uiText("GAME IMMERSION TOOLKIT")}</p><h1>{uiText("Game immersion toolkit")}</h1><p className="subtitle">{uiText("Stay in the story.")}</p></div><div className={'connection-badge '+(connected?'connected':'')}><span aria-hidden="true">●</span> {uiText(connected?'Connected':'Not connected')}</div></header>
  <nav className="companion-nav" aria-label={uiText("Companion")}>{['reader','settings'].filter(v=>role!=='sender'||v==='settings').map(v=><button key={v} aria-current={view===v?"page":undefined} onClick={()=>go(v)}>{uiText(v==='reader'?'Play':'Settings')}</button>)}</nav>
  {error&&<div className="message error" role="alert">{error}<button onClick={()=>setError('')}>{uiText("Dismiss")}</button></div>}{notice&&<div className="message" role="status">{notice}<button onClick={()=>setNotice('')}>{uiText("Dismiss")}</button></div>}
  {update&&<div className="message" role="status">{uiText("An update is ready. Your library, favorites and calibration will stay on this device.")}<button onClick={applyUpdate} disabled={capture.captureLifecycle.active||library.libraryLifecycle.busy}>{uiText("Update when idle")}</button></div>}
  {createPortal(<div ref={readerPane} className="reader-pane" hidden={view!=='reader'||role!=='receiver'||source==='mobile'&&!rows.length} style={{'--lexirise-font-size':options.fontSize+'px','--translation-font-size':translationFontSize+'px'}}>
   <div className="reader-toolbar"><span className="eyebrow">{source==='pc'?uiText("PAIRED PC"):uiText("MOBILE OCR")} / {game.toUpperCase()}</span><button onClick={()=>setOptionsOpen(true)}>{uiText("Reading options")}</button></div>
   <section className="current-card"><p className="eyebrow">{uiText("CURRENT LINE")}</p>{loading?<p role="status">{uiText("Restoring your transcript…")}</p>:current?<Line row={current} current {...lineProps(current)}/>:<div className="empty"><h2>{uiText("Your next line belongs here.")}</h2><p>{source==='pc'?'On your PC, choose “Share transcript to another device”. Pair here to receive dialogue and original voices.':'Open your game library, connect VDO.Ninja, and tap Start playing to follow the dialogue.'}</p><div className="actions">{source==='pc'&&<button onClick={()=>go('settings')}>{uiText("Connect PC")}</button>}</div></div>}</section>
   <div className="history-toolbar"><div className="tabs">{['history','favorites'].map(t=><button key={t} aria-pressed={filter===t} onClick={()=>{setFilter(t);setLimit(30);}}>{t==='history'?uiText("History"):uiText("Favorites")}</button>)}</div><label className="search-label"><span className="sr-only">{uiText("Search transcript")}</span><input type="search" value={search} onChange={e=>{setSearch(e.target.value);setLimit(30);}} placeholder={uiText("Search")} title={uiText("Search Chinese, English or a speaker")}/></label></div>
   <div className="history-list" aria-label={uiText("Transcript history")}>{matches.slice(0,limit).map(row=><Line key={keyOf(row)} row={row} {...lineProps(row)}/>)}{!loading&&!matches.length&&<p className="empty">{filter==='favorites'?uiText("Favorite a line to keep it here."):search?uiText("No matching lines. Try another phrase or search your library."):uiText("Your dialogue history will appear here.")}</p>}</div>
   <div className="actions">{matches.length>limit&&<button onClick={()=>setLimit(n=>n+30)}>{uiText("Show more history")}</button>}{source==='pc'&&before&&<button disabled={!connected||working} onClick={()=>run(()=>capture.captureLifecycle.older(before))}>{uiText("Load older PC history")}</button>}{source==='mobile'&&<button onClick={()=>go('library')}>{uiText("Search game library")}</button>}</div>
   <p className="reader-status" role="status">{status}</p>{mode==='lexirise'&&!unlocked&&<p className="hint">{uiText("Unlock Lexirise in Settings for analysis and lookups. Your local transcript and original audio remain available.")}</p>}
  </div>,$('reader-root'))}
  {createPortal(<div hidden={view!=='settings'}><InterfaceLanguage/>
   {role==='receiver'&&<section><h2>{uiText("Reading")}</h2><label>{uiText("Reader mode")}<select value={mode} onChange={e=>setMode(e.target.value)}><option value="migaku">{uiText("Migaku / plain transcript")}</option><option value="lexirise">{uiText("Lexirise")}</option></select></label><p className="hint">{uiText("Migaku works independently with your browser extension where supported. Lexirise uses this device’s unlocked key.")}</p><div className="actions"><label><input type="checkbox" checked={chinese} onChange={e=>setChinese(e.target.checked)}/> {uiText("Chinese")}</label><label><input type="checkbox" checked={english} onChange={e=>setEnglish(e.target.checked)}/> {uiText("English")}</label></div>
    <div className="font-size-controls"><label>{uiText("Source language font size")}<input type="range" min="18" max="48" step="1" value={options.fontSize} onChange={e=>setOptions(o=>({...o,fontSize:Number(e.target.value)}))}/><span>{options.fontSize} px · {uiText("Game text")}</span></label><label>{uiText("Target language font size")}<input type="range" min="10" max="32" step="1" value={translationFontSize} onChange={e=>setTranslationFontSize(Number(e.target.value))}/><span>{translationFontSize} px · {uiText("Translation")}</span></label></div>
    <button onClick={()=>setOptionsOpen(true)}>{uiText("Reading options")}</button></section>}
   {role==='receiver'&&<section><div className="section-heading"><h2>{uiText("Lexirise")}</h2><span>{unlocked?uiText("Unlocked"):hasVault?uiText("Locked"):uiText("Not connected")}</span></div><p>{uiText("Works with your PC off. Your key is encrypted on this device with your passphrase. Encryption protects stored credentials, not a compromised page while unlocked.")}</p>
    {(!unlocked||vaultAction)&&<form onSubmit={submitVault} autoComplete="off">{(!hasVault||vaultAction==='connect')&&<label>{uiText("Lexirise API key")}<input name="key" type="password" required maxLength={4096} autoComplete="off"/></label>}{(!rememberKey||hasVault&&vaultAction!=='connect'||vaultAction==='change')&&<><label>{vaultAction==='change'?uiText("New passphrase"):uiText("Passphrase")}<input name="pass" type="password" required minLength={4} maxLength={1024} autoComplete="off"/></label>{(!hasVault||['connect','change'].includes(vaultAction))&&<label>{uiText("Confirm passphrase")}<input name="confirm" type="password" required minLength={4} maxLength={1024} autoComplete="off"/></label>}</>}<button disabled={working}>{working?uiText("Please wait…"):vaultAction==='change'?uiText("Change passphrase"):!hasVault||vaultAction==='connect'?uiText("Connect Lexirise"):uiText("Unlock")}</button></form>}
    <label><input type="checkbox" checked={rememberKey} disabled={working} onChange={e=>{const enabled=e.target.checked;setRememberKey(enabled);if(unlocked||!enabled)void run(async()=>{try{await vault.current.remember(enabled);}catch(error){setRememberKey(!enabled);throw error;}});}}/>{uiText("Remember on this device")}</label><p className="hint">{uiText("When enabled, this site saves your API key on this device without a passphrase. Only enable on a device you trust.")}</p>
    <div className="actions">{unlocked&&<><button onClick={()=>{vault.current.lock();setNotice('Lexirise locked.');}}>{uiText("Lock")}</button><button onClick={()=>setVaultAction('change')}>{uiText("Change passphrase")}</button><button onClick={()=>setAccountOpen(true)}>{uiText("Account settings")}</button></>}{(hasVault||rememberKey||unlocked)&&<><button onClick={()=>{vault.current.lock();setVaultAction('connect');}}>{uiText("Replace key / forgotten passphrase")}</button><button onClick={()=>run(async()=>{await vault.current.forget();setHasVault(false);setRememberKey(false);setVaultAction('');setNotice('Local credentials removed. Revoke the provider key separately if needed.');})}>{uiText("Forget key")}</button></>}</div>
    <p className="hint">{uiText("At least 4 characters. Your VDO.Ninja code can unlock the key; unlock once and connect the screen to link it. Unless Remember on this device is enabled, reopening requires unlocking and five minutes in the background locks the key. Forgotten passphrases require entering your API key again. Forget key removes local credentials; it does not revoke the provider key.")}</p>
    {unlocked&&<details><summary>{uiText("Sentence saving and decks")}</summary><p>{uiText("Saving a sentence uploads its text and, when available, original voice. A deck is created only when you choose Create deck.")}</p><button disabled={working} onClick={()=>runReader(loadDecks)}>{uiText("Load my decks")}</button><label>{uiText("Save destination")}<select value={deck} onChange={e=>setDeck(e.target.value)}><option value="">{uiText("Vocabulary only")}</option>{decks.map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</select></label><label>{uiText("New deck name")}<input value={deckTitle} onChange={e=>setDeckTitle(e.target.value)} maxLength={120}/></label><button disabled={working||!deckTitle.trim()} onClick={()=>runReader(async({client,isCurrent})=>{const result=await client.requestAccount('POST','/v1/decks',{title:deckTitle.trim(),language:current?.sourceLanguage??'zh',unit_type:'sentence',deck_type:'snapshot',import_items:[]});if(!isCurrent())return;if(!result.deck?.id)throw Error('Deck creation was not confirmed. Reload your decks before retrying.');setDecks(d=>[...d,result.deck]);setDeck(String(result.deck.id));setDeckTitle('');})}>{uiText("Create deck")}</button></details>}
   </section>}
   <section><h2>{uiText("This device")}</h2><p>{uiText("History, favorites, settings and retained libraries stay on this device. Clearing site data removes retained libraries and saved credentials.")}</p><label><input type="checkbox" checked={dev} onChange={e=>setDev(e.target.checked)}/> {uiText("Enable developer mode")}</label><p className="hint">{uiText("Shows diagnostics and device verification tools for this session.")}</p></section>
  </div>,$('settings-root'))}
  {optionsOpen&&<ReadingOptionsDialog sourceLanguage={current?.sourceLanguage??'zh'} initial={options} onChange={setOptions} onClose={()=>setOptionsOpen(false)}/>}
  {accountOpen&&unlocked&&<SettingsPanel sourceLanguage={current?.sourceLanguage??'zh'} initial={options} onChange={setOptions} onClose={()=>setAccountOpen(false)} adapter={settingsAdapter.current} showReadingOptions={false} title={uiText("Lexirise account settings")}/>}
  <footer>{uiText("By")} <a href="https://github.com/Firebird55/Game-immersion-toolkit" target="_blank" rel="noreferrer">{uiText("Firebird55")}</a> {uiText("· Game content stays on your devices.")}</footer>
 </>;
}
createRoot($('app-root')).render(<LocalizedInterface><App/></LocalizedInterface>);
