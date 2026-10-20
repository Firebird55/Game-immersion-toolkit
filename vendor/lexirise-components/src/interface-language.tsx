'use client';
import {createContext,useContext,type ReactNode} from 'react';
import {interfaceMessages} from './interface-messages.js';

export type InterfaceTranslator = (message:string)=>string;
const InterfaceContext=createContext<InterfaceTranslator>(message=>message);

/** Local interface copy only. Never changes account, study or translation languages. */
export function interfaceTranslation(message:string,locale='en'){
 return interfaceMessages[message]?.[(['nl','zh-Hans','zh-Hant'] as string[]).indexOf(locale)]??message;
}
export function InterfaceLanguageProvider({translate,locale='en',children}:{translate?:InterfaceTranslator;locale?:string;children:ReactNode}){
 return <InterfaceContext.Provider value={translate??(message=>interfaceTranslation(message,locale))}>{children}</InterfaceContext.Provider>;
}
export function useInterfaceTranslation(){return useContext(InterfaceContext);}
