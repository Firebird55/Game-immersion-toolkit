'use client';
import {useEffect,useSyncExternalStore,type ReactNode} from 'react';
import {InterfaceLanguageProvider} from '@firebird55/lexirise-components';
import {getInterfaceLanguage,initializeInterfaceLanguage,subscribeInterfaceLanguage,setInterfaceLanguage,translate,interfaceLanguages} from '../public/mobile-capture/interface-language.mjs';
export function useInterfaceLanguage(){
 const locale=useSyncExternalStore(subscribeInterfaceLanguage,getInterfaceLanguage,()=> 'en');
 useEffect(()=>{initializeInterfaceLanguage();setInterfaceLanguage(getInterfaceLanguage());},[]);
 return {locale,t:(message:string)=>translate(message,locale),setLocale:setInterfaceLanguage};
}
export function InterfaceLanguage(){
 const {locale,t,setLocale}=useInterfaceLanguage();
 return <label>{t('Interface language')}<select aria-label={t('Interface language')} value={locale} onChange={e=>setLocale(e.target.value)}>
 {Object.entries(interfaceLanguages).map(([code,name])=><option key={code} value={code}>{name}</option>)}</select></label>;
}
export function useInterfaceTranslation(){return useInterfaceLanguage().t;}

export function LocalizedInterface({children}:{children:ReactNode}){
 const {locale}=useInterfaceLanguage();
 return <InterfaceLanguageProvider locale={locale}>{children}</InterfaceLanguageProvider>;
}
