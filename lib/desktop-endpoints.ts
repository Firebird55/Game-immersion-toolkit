/** Preserve installed localhost origins; LAN browsers use their desktop origin. */
export function desktopApiBase(location: Pick<Location, 'hostname'> | undefined = typeof window === 'undefined' ? undefined : window.location) {
  return !location || ['localhost', '127.0.0.1'].includes(location.hostname) ? 'http://127.0.0.1:8766' : '';
}

export function desktopWebSocketUrl(location: Pick<Location, 'hostname' | 'host' | 'protocol'> | undefined = typeof window === 'undefined' ? undefined : window.location) {
  return !location || ['localhost', '127.0.0.1'].includes(location.hostname)
    ? 'ws://127.0.0.1:8766/api/ws'
    : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`;
}
