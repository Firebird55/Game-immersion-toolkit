'use client';
import {createReader, validateAccount, isStudyLanguage, type AccountSettings, type ReadingOptions} from '@firebird55/lexirise-components';
import type {ComponentProps} from 'react';
import {useEffect,useMemo,useState} from 'react';
export {DEFAULT_READING_OPTIONS,MIGAKU_TONE_PALETTE,restoreReadingOptions} from '@firebird55/lexirise-components';
export type {ReadingOptions,ReadingScope} from '@firebird55/lexirise-components';
type Context={account:string;settings:AccountSettings};
let revision=0;
let contextPromise:Promise<Context>|null=null;
const API='http://127.0.0.1:8766';
function context(){
 return contextPromise??=Promise.all([fetch(API+'/api/lexirise/accounts',{cache:'no-store'}),fetch(API+'/api/lexirise/settings',{cache:'no-store'})]).then(async([a,s])=>{
  if(!s.ok)throw Error('Reload Lexirise account settings.');
  const account=a.ok?await a.json() as {active?:string}:{};
  return {account:account.active??'legacy',settings:validateAccount(await s.json())};
 }).catch(error=>{contextPromise=null;throw error;});
}
if(typeof window!=='undefined')for(const event of ['lexirise-account-settings','lexirise-credentials-changed'])window.addEventListener(event,()=>{revision++;contextPromise=null;});
export function accountReadingOptions(local:ReadingOptions,account:AccountSettings,source:string):ReadingOptions{
 const p=account.languageSettings[source]??{};
 const scope=(value:unknown)=>value==='always'||value==='all'?'all':value==='unknown'?'unknown':'off';
 return {...local,meanings:scope(p.inlineGlossMode),pinyin:p.readingAid&&p.readingAid!=='none'&&p.readingAid!=='zhuyin'?'all':'off',
  zhuyin:p.readingAid==='zhuyin'?'all':'off',toneColors:p.coloringMode==='tone'?'all':'off'};
}
type ReaderProps=ComponentProps<ReturnType<typeof createReader>['ReadingText']>;
export function ReadingText({sourceLanguage='zh',...props}:ReaderProps&{sourceLanguage?:string}){
 const [loaded,setLoaded]=useState<Context|null>(null),[version,setVersion]=useState(revision);
 useEffect(()=>{
  let active=true,generation=0;
  const load=()=>{const mine=++generation;setLoaded(null);setVersion(revision);void context().then(value=>{if(active&&mine===generation)setLoaded(value);}).catch(()=>undefined);};
  const local=()=>setVersion(v=>v+1);window.addEventListener('lexirise-local-reading-options',local);
  load();for(const name of ['lexirise-account-settings','lexirise-credentials-changed'])window.addEventListener(name,load);
  return()=>{active=false;window.removeEventListener('lexirise-local-reading-options',local);for(const name of ['lexirise-account-settings','lexirise-credentials-changed'])window.removeEventListener(name,load);};
 },[]);
 const source=isStudyLanguage(sourceLanguage)?sourceLanguage:'zh';
 const profile=loaded?.settings.languageSettings[source];
 const target=String(profile?.effectiveTranslationLanguage??loaded?.settings.global.effectiveTranslationLanguage??loaded?.settings.global.translationLanguage??'en');
 const accountGeneration=revision;
 const reader=useMemo(()=>createReader({sourceLanguage:source,translationLanguage:target,loadSettings:async()=>{
  if(!loaded)throw Error('Account settings unavailable.');return loaded.settings;
 },request:async(_text,action,params={},init={})=>{
  if(!loaded)throw Error('Account settings unavailable.');
  const query=new URLSearchParams();if(params.start!=null)query.set('start',String(params.start));
  const path=action==='analysis'?'':action==='save-example'?'/examples/'+params.index+'/save':'/'+action;
  const headers=new Headers(init.headers);headers.set('X-Proxy-Transcript-Account',loaded.account);
  if(init.method&&init.method!=='GET')headers.set('X-Proxy-Transcript','lexirise');
  const response=await fetch(API+'/api/lines/'+props.id+'/reading'+path+(query.size?'?'+query:''),{...init,headers});
  if(accountGeneration!==revision)throw Error('Account changed. Retry with the selected account.');
  if(!response.ok){const error=await response.clone().json().catch(()=>null) as {detail?:unknown}|null;throw Error(typeof error?.detail==='string'?error.detail:'Lexirise request unavailable.');}
  return response;
 }}),[source,target,loaded,version,props.id,accountGeneration]);
 if(!loaded)return <p lang={source} className={props.current?'current-chinese':undefined}>{props.text}</p>;
 let options=accountReadingOptions(props.options,loaded.settings,source);
 try{const saved=localStorage.getItem('proxy-transcript-reading-options:'+loaded.account+':'+source);if(saved)options={...options,...JSON.parse(saved)};}catch{}
 return <reader.ReadingText {...props} options={options}/>;
}
