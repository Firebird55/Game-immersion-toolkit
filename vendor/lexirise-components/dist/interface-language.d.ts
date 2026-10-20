import { type ReactNode } from 'react';
export type InterfaceTranslator = (message: string) => string;
/** Local interface copy only. Never changes account, study or translation languages. */
export declare function interfaceTranslation(message: string, locale?: string): string;
export declare function InterfaceLanguageProvider({ translate, locale, children }: {
    translate?: InterfaceTranslator;
    locale?: string;
    children: ReactNode;
}): import("react/jsx-runtime").JSX.Element;
export declare function useInterfaceTranslation(): InterfaceTranslator;
