import {desktopApiBase} from '../lib/desktop-endpoints';
import {nativeAccountHeaders} from '../lib/native-account-scope.mjs';

import {validateAccount,type SettingsAdapter} from '@firebird55/lexirise-components';
export function createSettingsAdapter(generation?: number | null, current: () => boolean = () => true): SettingsAdapter {
let account='legacy';
async function request(method:string,body?:unknown){
 if(!current())throw Error('The account changed. Reload its preferences.');
 if(method==='GET'){const response=await fetch(desktopApiBase()+'/api/lexirise/accounts',{cache:'no-store',headers:nativeAccountHeaders(generation)});if(!response.ok)throw Error('Reload the selected account before editing preferences.');account=((await response.json()) as {active?:string}).active??'legacy';}
 const response=await fetch(desktopApiBase()+'/api/lexirise/settings',{method,cache:'no-store',headers:nativeAccountHeaders(generation,{'Content-Type':'application/json','X-Proxy-Transcript':'lexirise','X-Proxy-Transcript-Account':account}),body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>null) as {detail?:unknown}|null;throw new Error(typeof error?.detail==='string'?error.detail:'Lexirise settings unavailable.');}
 const result=validateAccount(await response.json());
 if(!current())throw Error('The account changed. Reload its preferences.');
 window.dispatchEvent(new Event('lexirise-account-settings'));
 return result;
}
return {load:()=>request('GET'),patch:changes=>request('PATCH',changes)};
}
export const settingsAdapter = createSettingsAdapter();
