/** The standalone host owns a gateway; source development retains its API port. */
function usesDesktopGateway() {
  return typeof document !== 'undefined'
    && document.querySelector('meta[name="toolkit-api-transport"]')?.getAttribute('content') === 'same-origin';
}

export function desktopApiBase(location: Pick<Location, 'hostname'> | undefined = typeof window === 'undefined' ? undefined : window.location,
  sameOrigin = usesDesktopGateway()) {
  return sameOrigin || (location && !['localhost', '127.0.0.1'].includes(location.hostname)) ? '' : 'http://127.0.0.1:8766';
}

export function desktopWebSocketUrl(location: Pick<Location, 'hostname' | 'host' | 'protocol'> | undefined = typeof window === 'undefined' ? undefined : window.location,
  sameOrigin = usesDesktopGateway()) {
  return location && (sameOrigin || !['localhost', '127.0.0.1'].includes(location.hostname))
    ? `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`
    : 'ws://127.0.0.1:8766/api/ws';
}
