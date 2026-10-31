/** Opt-in native launch diagnostic. Normal reader URLs do not run this check. */
export function observeNativeBrowserLaunch() {
  const observe = () => {
    const parameters = new URLSearchParams(location.hash.slice(1));
    const token = parameters.get('toolkit-native-probe');
    const stage = Number(parameters.get('stage'));
    if (location.hostname !== '127.0.0.1' || !/^[a-f0-9]{64}$/.test(token ?? '') || ![1, 2].includes(stage)) return;
    const fragment = location.hash;
    const deadline = performance.now() + 60_000;
    const ready = () => {
      if (location.hash !== fragment || performance.now() > deadline) return;
      const reader = document.querySelector('main.companion-shell:not([aria-busy="true"]) .current-line');
      if (!reader || reader.getBoundingClientRect().width === 0) {
        window.setTimeout(ready, 100);
        return;
      }
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (location.hash !== fragment) return;
        void fetch('/api/native-browser-probe', {method: 'POST', credentials: 'omit',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({token, stage, reader_ready: true})}).catch(() => {});
      }));
    };
    ready();
  };
  observe();
  window.addEventListener('hashchange', observe);
}
