'use client';
import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useContext } from 'react';
import { interfaceMessages } from './interface-messages.js';
const InterfaceContext = createContext(message => message);
/** Local interface copy only. Never changes account, study or translation languages. */
export function interfaceTranslation(message, locale = 'en') {
    return interfaceMessages[message]?.[['nl', 'zh-Hans', 'zh-Hant'].indexOf(locale)] ?? message;
}
export function InterfaceLanguageProvider({ translate, locale = 'en', children }) {
    return _jsx(InterfaceContext.Provider, { value: translate ?? (message => interfaceTranslation(message, locale)), children: children });
}
export function useInterfaceTranslation() { return useContext(InterfaceContext); }
