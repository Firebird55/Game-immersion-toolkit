import {useEffect, useState} from 'react';
import {desktopApiBase} from './desktop-endpoints';
import {hostPlatform, parseNativeCapabilities} from './native-host-policy.mjs';

export type NativeCapabilities = {
  platform: string;
  library_import: boolean;
  protected_accounts: boolean;
  account_protocol?: string;
  capture_source: string;
  message: string;
  receiver_protocol?: string;
  max_frame_bytes?: number;
};

export function useNativeHost() {
  const android = hostPlatform() === 'android';
  const [capabilities, setCapabilities] = useState<NativeCapabilities | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!android) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(desktopApiBase() + '/api/platform', {cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw Error('Device features are unavailable. Reopen the app and retry.');
        const value = parseNativeCapabilities(await response.json());
        if (!controller.signal.aborted) {setCapabilities(value); setError('');}
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Device features are unavailable.');
      }
    })();
    return () => controller.abort();
  }, [android]);
  return {android, capabilities, error};
}
