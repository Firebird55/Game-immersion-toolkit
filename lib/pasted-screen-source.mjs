import {parseVdoViewerUrl} from '../public/mobile-capture/vdo-source.mjs';

/**
 * A private link stays in memory; every edit fences the previous receiver immediately.
 * @param {{receiver: {stop: () => Promise<unknown>, connect: (value: string) => Promise<unknown>},
 * onChanged?: () => void, onError?: (message: string) => void,
 * setTimer?: (callback: () => void, delay: number) => any, clearTimer?: (timer: any) => void}} options
 */
export function createPastedScreenSource({receiver, onChanged = () => {}, onError = () => {},
  setTimer = setTimeout, clearTimer = clearTimeout}) {
  let revision = 0, timer = null, disposed = false;
  const clear = () => {if (timer !== null) clearTimer(timer); timer = null;};
  return {
    replace(value, {enabled = true} = {}) {
      if (disposed) return;
      const owner = ++revision;
      clear();
      void receiver.stop().catch(() => {});
      if (!enabled || !value.trim()) return;
      try {parseVdoViewerUrl(value);} catch {onError('Paste a complete VDO.Ninja viewer link.'); return;}
      timer = setTimer(() => {
        timer = null;
        if (disposed || owner !== revision) return;
        void receiver.connect(value).then(() => {
          if (!disposed && owner === revision) onChanged();
        }).catch(() => {if (!disposed && owner === revision) onError('The screen link could not be opened.');});
      }, 250);
    },
    dispose() {if (disposed) return; disposed = true; revision++; clear(); void receiver.stop().catch(() => {});},
  };
}
