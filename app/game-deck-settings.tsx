import {useEffect,useState} from 'react';
type Deck={id:number;title:string};
export function GameDeckSettings({game,title,current,onConfigured,language="zh"}:{game:string;title:string;current?:Deck;onConfigured:()=>void;language?:string}) {
 const [decks,setDecks]=useState<Deck[]>([]),[selected,setSelected]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function request(method:string,body?:unknown){
  const response=await fetch('http://127.0.0.1:8766/api/lexirise/decks?language='+encodeURIComponent(language),{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise'},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json() as {detail?:unknown;decks?:Deck[]};if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Could not configure destination.');return result;
 }
 async function reload(){setBusy(true);setMessage('');try{const result=await request('GET');setDecks(result.decks??[]);setSelected(current?String(current.id):'');}catch(error){setMessage(error instanceof Error?error.message:'Could not load destinations.');}finally{setBusy(false);}}
 useEffect(()=>{void reload();},[game,language,current?.id]);
 async function save(create:boolean){setBusy(true);setMessage('');try{await request('POST',create?{game,language,create:true}:{game,language,deck_id:Number(selected)});setMessage('Destination saved for this account.');onConfigured();}catch(error){setMessage(error instanceof Error?error.message:'Could not save destination.');}finally{setBusy(false);}}
 return <fieldset className="settings-key"><legend>{title} export destination</legend>
 <p>{current?'Selected: '+current.title:'Select your own ' + language + ' sentence snapshot deck before exporting.'}</p>
 <select aria-label="Game export destination" disabled={busy} value={selected} onChange={event=>setSelected(event.target.value)}><option value="">Choose a deck</option>{decks.map(deck=><option key={deck.id} value={deck.id}>{deck.title}</option>)}</select>
 <div className="settings-key-actions"><button type="button" disabled={busy} onClick={()=>void reload()}>Reload destinations</button><button type="button" disabled={busy||!selected} onClick={()=>void save(false)}>Use selected deck</button><button type="button" disabled={busy} onClick={()=>void save(true)}>Find or create game deck</button></div>
 <p role="status">{message}</p><small>Only these destination actions can create or select a game deck. Reading preferences do not change it.</small></fieldset>;
}
