import {createContext, useContext} from 'react';

export const NativeAccountContext = createContext<number | null | undefined>(undefined);
export const useNativeAccountGeneration = () => useContext(NativeAccountContext);
