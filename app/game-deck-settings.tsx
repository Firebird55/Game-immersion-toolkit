import {useInterfaceTranslation} from '../lib/interface-language';
import {useEffect,useRef,useState} from 'react';
type Deck={id:number;title:string};
const API='http://127.0.0.1:8766';
export function GameDeckSettings({game,title,current,onConfigured,language="zh"}:{game:string;title:string;current?:Deck;onConfigured:()=>void;language?:string}) {
 const uiText=useInterfaceTranslation();
 const [decks,setDecks]=useState<Deck[]>([]),[selected,setSelected]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const generation=useRef(0),account=useRef<string|null>(null),saving=useRef(false);
 async function request(accountId:string,method:string,body?:unknown){
  const response=await fetch(API+'/api/lexirise/decks?language='+encodeURIComponent(language),{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise','X-Proxy-Transcript-Account':accountId},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json() as {detail?:unknown;decks?:Deck[]};if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Could not configure destination.');return result;
 }
 async function reload(){
  const mine=++generation.current;account.current=null;setBusy(true);setMessage('');setDecks([]);setSelected('');
  try{
   const response=await fetch(API+'/api/lexirise/accounts',{cache:'no-store'});if(!response.ok)throw Error('Reload the account before configuring destinations.');
   const value=await response.json() as {active?:string};if(mine!==generation.current)return;
   const accountId=value.active??'legacy',result=await request(accountId,'GET');if(mine!==generation.current)return;
   account.current=accountId;setDecks(result.decks??[]);setSelected(current&&result.decks?.some(deck=>deck.id===current.id)?String(current.id):'');
  }catch(error){if(mine===generation.current)setMessage(error instanceof Error?error.message:'Could not load destinations.');}
  finally{if(mine===generation.current)setBusy(false);}
 }
 useEffect(()=>{
  void reload();const changed=()=>void reload();window.addEventListener('lexirise-credentials-changed',changed);
  return()=>{generation.current++;account.current=null;window.removeEventListener('lexirise-credentials-changed',changed);};
 },[game,language,current?.id]);
 async function save(create:boolean){
  if(saving.current||account.current===null)return;
  const mine=generation.current,accountId=account.current;saving.current=true;setBusy(true);setMessage('');
  try{
   await request(accountId,'POST',create?{game,language,create:true}:{game,language,deck_id:Number(selected)});
   if(mine!==generation.current)return;setMessage('Destination saved for this account.');onConfigured();
  }catch(error){if(mine===generation.current)setMessage(error instanceof Error?error.message:'Could not save destination.');}
  finally{saving.current=false;if(mine===generation.current)setBusy(false);}
 }
 return <fieldset className="settings-key"><legend>{title} {uiText("export destination")}</legend>
 <p>{current?'Selected: '+current.title:'Select your own ' + language + ' sentence snapshot deck before exporting.'}</p>
 <select aria-label={uiText("Game export destination")} disabled={busy} value={selected} onChange={event=>setSelected(event.target.value)}><option value="">{uiText("Choose a deck")}</option>{decks.map(deck=><option key={deck.id} value={deck.id}>{deck.title}</option>)}</select>
 <div className="settings-key-actions"><button type="button" disabled={busy} onClick={()=>void reload()}>{uiText("Reload destinations")}</button><button type="button" disabled={busy||!selected} onClick={()=>void save(false)}>{uiText("Use selected deck")}</button><button type="button" disabled={busy||account.current===null} onClick={()=>void save(true)}>{uiText("Find or create game deck")}</button></div>
 <p role="status">{message}</p><small>{uiText("Only these destination actions can create or select a game deck. Reading preferences do not change it.")}</small></fieldset>;
}
