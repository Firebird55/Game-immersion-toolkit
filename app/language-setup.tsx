'use client';
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {useInterfaceLanguage} from '@/lib/interface-language';
import {formatBytes,languageName} from '../public/mobile-capture/interface-language.mjs';
const API='http://127.0.0.1:8766';
type Locale={locale:string;language:string;name:string;reader_available:boolean;table_bytes?:number;reclaimable_bytes?:number;voice_state?:string;support?:string;prepared:null|{targets:string[];mapped_lines:number};job?:{state?:string;message?:string;progress?:number}};
type Languages={selected:string|null;locales:Locale[];enabled_languages:string[]|null;targets:Record<string,string>;translation_locales?:string[];expected_targets?:string[];storage?:{tables_bytes:number;audio_cache_bytes:number|null;shared_tools_bytes:number|null;installed_game_bytes:number|null;exports_bytes:number|null}};
export function LanguageSetup({game,onConfigure,onChanged,storageOnly=false}:{game:string;onConfigure:(language:string)=>void;onChanged:()=>void;storageOnly?:boolean}){
 const {t,locale:uiLocale}=useInterfaceLanguage();
 const [data,setData]=useState<Languages|null>(null),[locale,setLocale]=useState(''),[target,setTarget]=useState('en'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[search,setSearch]=useState(''),[confirm,setConfirm]=useState(false);
 useEffect(()=>{
  let active=true;
  async function load(){try{const response=await fetch(API+'/api/setup/games/'+game+'/languages',{cache:'no-store'});if(!response.ok)throw Error('Language setup unavailable.');const value=await response.json() as Languages;if(!active||!Array.isArray(value.locales))return;setData(value);setLocale(previous=>value.locales.some(l=>l.locale===previous)?previous:value.selected??value.locales.find(l=>value.enabled_languages?.includes(l.language))?.locale??value.locales[0]?.locale??'');}catch(e){if(active)setError(e instanceof Error?e.message:'Language setup unavailable.');}}
  setData(null);setLocale('');setConfirm(false);setError('');void load();const timer=setInterval(()=>void load(),5000);
  return()=>{active=false;clearInterval(timer);};
 },[game]);
 const selected=data?.locales.find(item=>item.locale===locale);
 const translation=selected?(data?.targets[selected.language]??target):target;
 async function action(kind:'prepare'|'rebuild'|'select'|'cleanup'){
  setBusy(true);setError('');try{const response=await fetch(API+'/api/setup/games/'+game+'/languages',{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'setup'},body:JSON.stringify({locale,action:kind,...(kind==='prepare'||kind==='rebuild')?{target:translation}:{}})});if(!response.ok){const value=await response.json() as {detail?:string};throw Error(value.detail??'Language action failed.');}const refreshed=await fetch(API+'/api/setup/games/'+game+'/languages',{cache:'no-store'});if(refreshed.ok)setData(await refreshed.json() as Languages);setConfirm(false);onChanged();}catch(e){setError(e instanceof Error?e.message:'Language action failed.');}finally{setBusy(false);}}
 const preparing=selected?.job?.state==='preparing';
 const enabled=!!selected&&(!data?.enabled_languages||data.enabled_languages.includes(selected.language));
 const prepared=!!selected?.prepared?.targets.some(code=>code.toLowerCase()===translation.toLowerCase());
 const choices=data?.translation_locales??['en','zh-Hans','zh-Hant'];
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
 {!storageOnly&&<><label>{t('Translation language')}<select aria-label="Game translation language" disabled={!!data.enabled_languages} value={translation} onChange={e=>setTarget(e.target.value)}>{[...new Set([translation,...choices])].map(code=><option key={code} value={code}>{languageName(code,uiLocale)}{data.expected_targets?.includes(code)?' · '+t('Expected support'):''}</option>)}</select></label>
 {!enabled&&<p>{t('Enable this learning language in Lexirise to use it with this account.')}</p>}
 {selected.prepared&&<p>{selected.prepared.mapped_lines.toLocaleString(uiLocale)} · {selected.prepared.targets.map(code=>languageName(code,uiLocale)).join(', ')}</p>}
 {selected.job?.message&&<p role="status">{selected.job.message}</p>}{preparing&&<progress aria-label="Language preparation progress" value={selected.job?.progress??0} max={100}/>}
 <div className="toolkit-setup-actions"><Button disabled={busy||preparing||!enabled||!selected.reader_available||(prepared&&data.selected===locale)} onClick={()=>void action(prepared?'select':'prepare')}>{t(prepared?'Use this language':selected.prepared?'Prepare translation':'Prepare language')}</Button><Button variant="outline" onClick={()=>onConfigure(selected.language)}>{t('Reading and dictionaries')}</Button></div></>}
 <details open={storageOnly}><summary>{t(storageOnly?'Storage':'Advanced')}</summary><div className="toolkit-setup-actions"><Button variant="outline" disabled={busy||preparing||!enabled||!selected.reader_available} onClick={()=>void action('rebuild')}>{t('Rebuild table')}</Button><Button variant="outline" disabled={busy||preparing||!(selected.table_bytes??0)} onClick={()=>setConfirm(true)}>{t('Remove table and free space')} · {formatBytes(selected.reclaimable_bytes??0,uiLocale)}</Button></div></details>
 {confirm&&<div className="language-cleanup" role="alert"><h4>{t('Remove prepared table?')}</h4><p>{t('Game files, history, favorites and credentials are kept. Prepare the table again to restore original-voice lookup.')}</p><p>{t('This clears the language selection for all local accounts.')}</p><div className="toolkit-setup-actions"><Button disabled={busy} onClick={()=>void action('cleanup')}>{t('Remove')} · {formatBytes(selected.reclaimable_bytes??0,uiLocale)}</Button><Button variant="outline" disabled={busy} onClick={()=>setConfirm(false)}>{t('Cancel')}</Button></div></div>}
 </div>}
 {data.storage&&<><dl className="storage-summary">{([['Language tables',data.storage.tables_bytes],['Shared audio cache',data.storage.audio_cache_bytes],['Shared tools',data.storage.shared_tools_bytes],['External exports',data.storage.exports_bytes]] as [string,number|null][]).map(([label,bytes])=><div key={label}><dt>{t(label)}</dt><dd>{formatBytes(bytes,uiLocale)}</dd></div>)}<div><dt>{t('Game packs')}</dt><dd>{t('Managed by game launcher')}</dd></div></dl><p className="toolkit-setup-note">{t('Shared storage is counted once, not once per language.')}</p></>}
 </>}{error&&<p role="alert" className="toolkit-setup-error">{error}</p>}</section>;
}
