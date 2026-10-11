
'use client';
import {createReader, validateAccount} from '@firebird55/lexirise-components';
import type {ComponentProps} from 'react';
import {useEffect,useState} from 'react';
export {DEFAULT_READING_OPTIONS,MIGAKU_TONE_PALETTE,restoreReadingOptions} from '@firebird55/lexirise-components';
export type {ReadingOptions,ReadingScope} from '@firebird55/lexirise-components';
const lineIds=new Map<string,number>();
const reader=createReader({sourceLanguage:'zh',translationLanguage:'en',loadSettings:async()=>{
 const response=await fetch('http://127.0.0.1:8766/api/lexirise/settings',{cache:'no-store'});
 if(!response.ok)throw new Error('Popup settings unavailable.');return validateAccount(await response.json());
},request:async(text,action,params={},init={})=>{
 const id=lineIds.get(text);if(id==null)throw new Error('Transcript line unavailable.');
 const query=new URLSearchParams();if(params.start!=null)query.set('start',String(params.start));
 let path=action==='analysis'?'':action==='save-example'?'/examples/'+params.index+'/save':'/'+action;
 const headers=new Headers(init.headers);if(init.method&&init.method!=='GET')headers.set('X-Proxy-Transcript','lexirise');
 return fetch('http://127.0.0.1:8766/api/lines/'+id+'/reading'+path+(query.size?'?'+query:''),{...init,headers});
}});
export function ReadingText(props:ComponentProps<typeof reader.ReadingText>){
 const [revision,setRevision]=useState(0);
 useEffect(()=>{const changed=()=>{reader.resetReadingCaches();setRevision(n=>n+1);};window.addEventListener('lexirise-account-settings',changed);return()=>window.removeEventListener('lexirise-account-settings',changed);},[]);
 lineIds.set(props.text,props.id);return <reader.ReadingText key={revision} {...props}/>;
}
