'use client';
import {useEffect,useRef,useState} from 'react';
import {StatePoll, type StateContext} from './state-sync';
import {Button} from '@/components/ui/button';
import {useInterfaceLanguage} from '@/lib/interface-language';
import {formatBytes,languageName} from '../public/mobile-capture/interface-language.mjs';
const API='http://127.0.0.1:8766';
type Locale={locale:string;language:string;name:string;reader_available:boolean;table_bytes?:number;reclaimable_bytes?:number;voice_state?:string;support?:string;prepared:null|{targets:string[];mapped_lines:number};job?:{state?:string;message?:string;progress?:number}};
type Languages={context:StateContext;selected:string|null;locales:Locale[];enabled_languages:string[]|null;targets:Record<string,string>;translation_locales?:string[];expected_targets?:string[];storage?:{tables_bytes:number;audio_cache_bytes:number|null;shared_tools_bytes:number|null;installed_game_bytes:number|null;exports_bytes:number|null}};
export function LanguageSetup({game,onConfigure,onChanged,storageOnly=false,targetLanguage}:{game:string;onConfigure:(language:string)=>void;onChanged:()=>void;storageOnly?:boolean;targetLanguage?:string}){
 const {t,locale:uiLocale}=useInterfaceLanguage();
 const [data,setData]=useState<Languages|null>(null),[locale,setLocale]=useState(''),[target,setTarget]=useState('en'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[search,setSearch]=useState(''),[confirm,setConfirm]=useState(false);
 const pollOwner=useRef<StatePoll<Languages>|null>(null);
 const actionAbort=useRef<AbortController|null>(null);
 useEffect(()=>{
  const owner=new StatePoll<Languages>(async signal=>{
   const response=await fetch(API+'/api/setup/games/'+game+'/languages',{cache:'no-store',signal});
   if(!response.ok)throw Error('Language setup unavailable.');
   const value=await response.json() as Languages;
   if(!Array.isArray(value.locales))throw Error('Language setup unavailable.');
   return value;
  },value=>{
   setData(value);setError('');
   setLocale(previous=>value.locales.some(l=>l.locale===previous)?previous:value.locales.find(l=>l.language===targetLanguage)?.locale??value.selected??value.locales.find(l=>value.enabled_languages?.includes(l.language))?.locale??value.locales[0]?.locale??'');
  },()=>setError('Language setup unavailable.'));
  pollOwner.current=owner;
  const reset=(event?:Event)=>{
   owner.reset(event?.type==='companion-runtime-reset');actionAbort.current?.abort();
   setData(null);setLocale('');setConfirm(false);setError('');setBusy(false);
   void owner.request();
  };
  reset();const timer=setInterval(()=>void owner.request(),5000);
  window.addEventListener('lexirise-credentials-changed',reset);
  window.addEventListener('companion-runtime-reset',reset);
  return()=>{owner.close();actionAbort.current?.abort();if(pollOwner.current===owner)pollOwner.current=null;clearInterval(timer);window.removeEventListener('lexirise-credentials-changed',reset);window.removeEventListener('companion-runtime-reset',reset);};
 },[game,targetLanguage]);
 const selected=data?.locales.find(item=>item.locale===locale);
 const translation=selected?(data?.targets[selected.language]??target):target;
 async function action(kind:'prepare'|'rebuild'|'select'|'cleanup'){
  const owner=pollOwner.current;if(!owner||actionAbort.current&&!actionAbort.current.signal.aborted)return;
  const scope=owner.generation,controller=new AbortController();actionAbort.current=controller;
  setBusy(true);setError('');
  try{
   const response=await fetch(API+'/api/setup/games/'+game+'/languages',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Proxy-Transcript':'setup'},body:JSON.stringify({locale,action:kind,...(kind==='prepare'||kind==='rebuild')?{target:translation}:{}})});
   if(!owner.owns(scope)||controller.signal.aborted)return;
   if(!response.ok){const value=await response.json() as {detail?:string};throw Error(value.detail??'Language action failed.');}
   // Invalidate the older poll before refreshing the result of this action.
   owner.reset();await owner.request();
   if(controller.signal.aborted||pollOwner.current!==owner)return;
   setConfirm(false);onChanged();
  }catch(e){if(owner.owns(scope)&&!controller.signal.aborted)setError(e instanceof Error?e.message:'Language action failed.');}
  finally{if(actionAbort.current===controller){actionAbort.current=null;if(!controller.signal.aborted)setBusy(false);}}
 }
 const preparing=selected?.job?.state==='preparing';
 const inAccount=!!selected&&!!data?.enabled_languages?.includes(selected.language);
 const prepared=!!selected?.prepared?.targets.some(code=>code.toLowerCase()===translation.toLowerCase());
 const choices=data?.translation_locales??['en','zh-Hans','zh-Hant'];
 const supportedTarget=choices.some(code=>code.toLowerCase()===translation.toLowerCase());
 const rows=data?.locales.filter(row=>`${row.name} ${languageName(row.locale,uiLocale)} ${row.locale}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()))??[];
 return <section className="toolkit-setup-card language-manager"><h3>{t(storageOnly?'Storage':'Languages')}</h3>
 <p>{t('Learning text requires its matching original voice. Prepare only the languages you use.')}</p>
 {!data&&!error&&<p role="status">…</p>}
 {data&&<><label>{t('Search languages')}<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder={t('Search languages')}/></label>
 <div className="language-table-scroll"><table className="language-table"><thead><tr><th>{t('Language')}</th><th>{t('Availability')}</th><th>{t('Original voice')}</th><th>{t('Prepared table')}</th></tr></thead><tbody>
 {rows.map(row=><tr key={row.locale} className={locale===row.locale?'is-selected':''}><td><button type="button" aria-pressed={locale===row.locale} onClick={()=>{setLocale(row.locale);setConfirm(false);}}>{languageName(row.locale,uiLocale)}</button>{data.selected===row.locale&&<small className="language-badge">{t('Selected')}</small>}</td><td><span className={'language-badge '+(row.prepared?'ready':'')}>{t(row.job?.state==='preparing'?'Preparing…':row.prepared?'Ready':row.reader_available?'Expected support':'Unsupported')}</span></td><td>{t(row.voice_state==='present'?'Installed':row.voice_state==='not_checked'?'Choose game folder':'Checked during preparation')}</td><td>{formatBytes(row.table_bytes??0,uiLocale)}</td></tr>)}
 </tbody></table></div>{!rows.length&&<p>{t('No languages match your search.')}</p>}
 <p className="toolkit-setup-note">{t('Expected support uses the same reader format; it does not require an export of every language.')}</p>
 {selected&&<div className="language-detail"><h4>{languageName(locale,uiLocale)}</h4>
 {!storageOnly&&<><label>{t('Translation language')}<select aria-label={t('Translation language')} disabled={inAccount} value={translation} onChange={e=>setTarget(e.target.value)}>{[...new Set([translation,...choices])].map(code=><option key={code} value={code}>{languageName(code,uiLocale)}{data.expected_targets?.includes(code)?' · '+t('Expected support'):''}</option>)}</select></label>
 {!supportedTarget&&<p role="status">{t('This game has no official translation in the selected language.')}</p>}
 {data.enabled_languages&&!inAccount&&<p>{t('This source language is not in your Lexirise account. You can still prepare and play it.')}</p>}
 {targetLanguage&&selected.language!==targetLanguage&&<p>{t('Subtitle source differs from your target language. You can still use this language.')}</p>}
 {selected.prepared&&<p>{selected.prepared.mapped_lines.toLocaleString(uiLocale)} · {selected.prepared.targets.map(code=>languageName(code,uiLocale)).join(', ')}</p>}
 {selected.job?.message&&<p role="status">{selected.job.message}</p>}{preparing&&<progress aria-label={t('Preparing…')} value={selected.job?.progress??0} max={100}/>}
 <div className="toolkit-setup-actions"><Button disabled={busy||preparing||!supportedTarget||!selected.reader_available||(prepared&&data.selected===locale)} onClick={()=>void action(prepared?'select':'prepare')}>{t(prepared?'Use this language':selected.prepared?'Prepare translation':'Prepare language')}</Button><Button variant="outline" onClick={()=>onConfigure(selected.language)}>{t('Reading and dictionaries')}</Button></div></>}
 <details open={storageOnly}><summary>{t(storageOnly?'Storage':'Advanced')}</summary><div className="toolkit-setup-actions"><Button variant="outline" disabled={busy||preparing||!selected.reader_available} onClick={()=>void action('rebuild')}>{t('Rebuild table')}</Button><Button variant="outline" disabled={busy||preparing||!(selected.table_bytes??0)} onClick={()=>setConfirm(true)}>{t('Remove table and free space')} · {formatBytes(selected.reclaimable_bytes??0,uiLocale)}</Button></div></details>
 {confirm&&<div className="language-cleanup" role="alert"><h4>{t('Remove prepared table?')}</h4><p>{t('Game files, history, favorites and credentials are kept. Prepare the table again to restore original-voice lookup.')}</p><p>{t('This clears the language selection for all local accounts.')}</p><div className="toolkit-setup-actions"><Button disabled={busy} onClick={()=>void action('cleanup')}>{t('Remove')} · {formatBytes(selected.reclaimable_bytes??0,uiLocale)}</Button><Button variant="outline" disabled={busy} onClick={()=>setConfirm(false)}>{t('Cancel')}</Button></div></div>}
 </div>}
 {data.storage&&<><dl className="storage-summary">{([['Language tables',data.storage.tables_bytes],['Shared audio cache',data.storage.audio_cache_bytes],['Shared tools',data.storage.shared_tools_bytes],['External exports',data.storage.exports_bytes]] as [string,number|null][]).map(([label,bytes])=><div key={label}><dt>{t(label)}</dt><dd>{formatBytes(bytes,uiLocale)}</dd></div>)}<div><dt>{t('Game packs')}</dt><dd>{data.storage.installed_game_bytes==null?t('Managed by game launcher'):formatBytes(data.storage.installed_game_bytes,uiLocale)}</dd></div></dl><p className="toolkit-setup-note">{t('Shared storage is counted once, not once per language.')}</p></>}
 </>}{error&&<p role="alert" className="toolkit-setup-error">{error}</p>}</section>;
}
