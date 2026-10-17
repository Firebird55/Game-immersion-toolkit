'use client';
import {useEffect,useState} from 'react';
const API='http://127.0.0.1:8766';
type Accounts={active:string;profiles:{id:string;name:string}[]};
export function AccountSwitcher({onChanged}:{onChanged:()=>void}){
 const [accounts,setAccounts]=useState<Accounts>({active:'legacy',profiles:[]}),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function reload(){const response=await fetch(API+'/api/lexirise/accounts',{cache:'no-store'});if(!response.ok)throw Error('Could not load saved accounts.');const value=await response.json() as Partial<Accounts>;setAccounts({active:value.active??'legacy',profiles:value.profiles??[]});}
 useEffect(()=>{void reload().catch(()=>setMessage('Could not load saved accounts.'));},[]);
 async function select(id:string){setBusy(true);setMessage('');try{
  const response=await fetch(API+'/api/lexirise/accounts/select',{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise'},body:JSON.stringify({id})});
  if(!response.ok){const error=await response.json() as {detail?:string};throw Error(error.detail??'Could not switch accounts.');}
  await reload();window.dispatchEvent(new Event('lexirise-credentials-changed'));onChanged();setMessage('Selected account loaded.');
 }catch(error){setMessage(error instanceof Error?error.message:'Could not switch accounts.');}finally{setBusy(false);}}
 async function add(){setBusy(true);try{const response=await fetch(API+'/api/setup/native/lexirise',{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'setup'},body:'{}'});if(!response.ok)throw Error('Could not open the local account prompt.');setMessage('Enter the key in the hidden-input prompt on this PC, then reload accounts.');}catch(error){setMessage(error instanceof Error?error.message:'Could not add account.');}finally{setBusy(false);}}
 return <fieldset className="settings-key"><legend>Lexirise accounts on this PC</legend>
 <label>Active account<select aria-label="Active Lexirise account" value={accounts.active} disabled={busy} onChange={e=>void select(e.target.value)}>
 <option value="legacy">Existing local credential</option>{accounts.profiles.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
 </select></label><div className="settings-key-actions"><button type="button" disabled={busy} onClick={()=>void add()}>Add account securely</button><button type="button" disabled={busy} onClick={()=>void reload().then(()=>{window.dispatchEvent(new Event('lexirise-credentials-changed'));onChanged();}).catch(()=>setMessage('Could not reload accounts.'))}>Reload accounts</button></div>
 <p role="status">{message}</p><small>Keys remain encrypted on this PC. Switching does not change Lexirise settings or create decks.</small></fieldset>;
}
