'use client';
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {translationLanguages} from '@firebird55/lexirise-components';
const API='http://127.0.0.1:8766';
type Locale={locale:string;language:string;name:string;reader_available:boolean;prepared:null|{targets:string[];mapped_lines:number};job?:{state?:string;message?:string;progress?:number}};
type Languages={selected:string|null;locales:Locale[];enabled_languages:string[]|null;targets:Record<string,string>};
export function LanguageSetup({game,onConfigure,onChanged}:{game:string;onConfigure:(language:string)=>void;onChanged:()=>void}){
 const [data,setData]=useState<Languages|null>(null),[locale,setLocale]=useState(''),[target,setTarget]=useState('en'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  let active=true;
  async function load(){try{const response=await fetch(API+'/api/setup/games/'+game+'/languages',{cache:'no-store'});if(!response.ok)throw Error('Language setup unavailable.');const value=await response.json() as Languages;if(!active||!Array.isArray(value.locales))return;setData(value);setLocale(previous=>value.locales.some(l=>l.locale===previous)?previous:value.selected??value.locales.find(l=>value.enabled_languages?.includes(l.language))?.locale??value.locales[0]?.locale??'');}catch(e){if(active)setError(e instanceof Error?e.message:'Language setup unavailable.');}}
  setData(null);setLocale('');setError('');void load();const timer=setInterval(()=>void load(),3000);
  return()=>{active=false;clearInterval(timer);};
 },[game]);
 const selected=data?.locales.find(item=>item.locale===locale);
 const translation=selected?(data?.targets[selected.language]??target):target;
 async function action(kind:'prepare'|'rebuild'|'select'|'remove'){
  setBusy(true);setError('');try{const response=await fetch(API+'/api/setup/games/'+game+'/languages',{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'setup'},body:JSON.stringify({locale,action:kind,...(kind==='prepare'||kind==='rebuild')?{target:translation}:{}})});if(!response.ok){const value=await response.json() as {detail?:string};throw Error(value.detail??'Language action failed.');}const refreshed=await fetch(API+'/api/setup/games/'+game+'/languages',{cache:'no-store'});if(refreshed.ok)setData(await refreshed.json() as Languages);onChanged();}catch(e){setError(e instanceof Error?e.message:'Language action failed.');}finally{setBusy(false);}}
 const preparing=selected?.job?.state==='preparing';
 const enabled=!!selected&&(!data?.enabled_languages||data.enabled_languages.includes(selected.language));
 const currentTargetPrepared=!!selected?.prepared?.targets.includes(translation);
 return <section className="toolkit-setup-card"><h3>Languages</h3><p>Prepare only the languages you want to play. Prepared languages refresh after game updates.</p>
 {data&&<><label>Learning language<select aria-label="Game learning language" value={locale} onChange={e=>setLocale(e.target.value)}>{data.locales.map(l=><option key={l.locale} value={l.locale}>{l.name}{l.prepared?' · prepared':''}</option>)}</select></label>
 <p>Translation for {selected?.name}: <strong>{translation}</strong></p>
 {!data.enabled_languages&&<label>Translation language<select aria-label="Game translation language" value={target} onChange={e=>setTarget(e.target.value)}>{translationLanguages.map(code=><option key={code} value={code}>{code}</option>)}</select></label>}
 {!enabled&&<p>Enable this learning language in Lexirise to use it with this account.</p>}
 {!selected?.reader_available&&<p>This language needs the corresponding multilingual reader update.</p>}
 {selected?.prepared&&<p>{selected.prepared.mapped_lines.toLocaleString()} original voices mapped. Prepared translations: {selected.prepared.targets.join(', ')}.</p>}
 {selected?.prepared&&!selected.prepared.targets.includes(translation)&&<p>Prepare the official translation table for this learning language’s current target.</p>}
 {selected?.job?.message&&<p role="status">{selected.job.message}</p>}
 {preparing&&<progress aria-label="Language preparation progress" value={selected?.job?.progress??0} max={100}/>}
 <div className="toolkit-setup-actions"><Button variant="outline" type="button" disabled={busy||preparing||!enabled||!selected?.reader_available} onClick={()=>void action(currentTargetPrepared?'rebuild':'prepare')}>{currentTargetPrepared?'Rebuild prepared language':selected?.prepared?'Prepare translation table':'Prepare selected language'}</Button>
 <Button variant="outline" type="button" disabled={busy||preparing||!enabled||!selected?.prepared||data.selected===locale} onClick={()=>void action('select')}>Use this language</Button>
 <Button variant="outline" type="button" disabled={busy||preparing||!selected?.prepared} onClick={()=>void action('remove')}>Remove prepared table</Button>
 <Button variant="outline" type="button" disabled={!selected} onClick={()=>selected&&onConfigure(selected.language)}>Configure this language’s reading and dictionaries</Button></div></>}
 {error&&<p role="alert" className="toolkit-setup-error">{error}</p>}</section>;
}
