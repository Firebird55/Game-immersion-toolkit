import {desktopApiBase} from '../lib/desktop-endpoints';

import {validateAccount,type SettingsAdapter} from '@firebird55/lexirise-components';
let account='legacy';
async function request(method:string,body?:unknown){
 if(method==='GET'){const response=await fetch(desktopApiBase()+'/api/lexirise/accounts',{cache:'no-store'});if(response.ok)account=((await response.json()) as {active?:string}).active??'legacy';}
 const response=await fetch(desktopApiBase()+'/api/lexirise/settings',{method,cache:'no-store',headers:{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise','X-Proxy-Transcript-Account':account},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>null) as {detail?:unknown}|null;throw new Error(typeof error?.detail==='string'?error.detail:'Lexirise settings unavailable.');}
 const result=validateAccount(await response.json());
 window.dispatchEvent(new Event('lexirise-account-settings'));
 return result;
}
export const settingsAdapter:SettingsAdapter={load:()=>request('GET'),patch:changes=>request('PATCH',changes)};
