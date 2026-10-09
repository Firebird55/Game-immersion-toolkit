
import {validateAccount,type SettingsAdapter} from '@firebird55/lexirise-components';
async function request(method:string,body?:unknown){
 const response=await fetch('http://127.0.0.1:8766/api/lexirise/settings',{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise'},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>null) as {detail?:unknown}|null;throw new Error(typeof error?.detail==='string'?error.detail:'Lexirise settings unavailable.');}
 return validateAccount(await response.json());
}
export const settingsAdapter:SettingsAdapter={load:()=>request('GET'),patch:changes=>request('PATCH',changes)};
