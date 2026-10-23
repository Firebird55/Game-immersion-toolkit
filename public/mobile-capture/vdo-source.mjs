import { FRAME_LIMITS, createFrameLifecycle, frameFingerprint, frameSessionId, validFrameSize } from './frame-source.mjs';

// Reviewed against hosted main.js?ver=1092, lib.js?ver=14213 and Meshcast's
// servers.json on 2026-10-23. These are service endpoints, never user endpoints.
const meshcastHosts = new Set(['usw2.meshcast.io', 'de1.meshcast.io', 'cn1.meshcast.io']);
const viewerParameters = new Set('view pull password p pw hash room salt codec bitrate buffer scale quality cleanoutput clean autostart autoplay muted mute speaker noaudio na volume stereo fullscreen hideplaybutton whepplay whep whepplaytoken wheptoken wss wss2'.split(' '));

function unsupported(message) { return new Error(message); }

/** Keep every accepted parameter intact; reject unknown routes instead of guessing. */
export function parseVdoViewerUrl(value) {
 if (typeof value !== 'string' || value.length > 4096 || /[\u0000-\u001f\u007f]/.test(value)) throw unsupported('Paste the complete official VDO.Ninja viewer link.');
 let url;
 try { url = new URL(value.trim()); } catch { throw unsupported('Paste a complete HTTPS viewer link.'); }
 if (url.hostname === 'meshcast.io') {
  // meshcast.io/view.js?v=20 uses ADDRESS + '/' + id + '/whep'.
  // Do not infer routes for other Meshcast pages or silently discard options.
  const keys = new Set(['id', 'geo', 'api', 'muted', 'mute', 'noaudio', 'na']), seen = new Set();
  for (const [key] of url.searchParams) {
   if (!keys.has(key) || seen.has(key)) throw unsupported('This Meshcast viewer option is not supported. Use its complete official VDO.Ninja WHEP viewer link.');
   seen.add(key);
  }
  const id = url.searchParams.get('id'), regions = ['geo', 'api'].filter(key => url.searchParams.has(key));
  const region = regions.length === 1 ? url.searchParams.get(regions[0]) : '';
  if (url.protocol !== 'https:' || url.port || url.username || url.password || url.hash || url.pathname !== '/view.html' || !/^[a-zA-Z0-9_-]{1,256}$/.test(id ?? '') || !meshcastHosts.has(`${region}.meshcast.io`)) throw unsupported('This Meshcast route or server has not been reviewed. Use a supported official VDO.Ninja WHEP viewer link.');
  const viewer = new URL('https://vdo.ninja/');
  viewer.searchParams.set('whepplay', `https://${region}.meshcast.io/${id}/whep`);
  for (const [key, item] of url.searchParams) if (!['id', 'geo', 'api'].includes(key)) viewer.searchParams.set(key, item);
  return Object.freeze({ ...parseVdoViewerUrl(viewer.href), originalUrl: url.href });
 }
 if (url.hostname === 'app.meshcast.io') throw unsupported('This Meshcast page does not provide the reviewed frame API. Use its complete official VDO.Ninja WHEP viewer link.');
 if (url.protocol !== 'https:' || url.hostname !== 'vdo.ninja' || url.port || url.username || url.password || !['/', '/index.html'].includes(url.pathname) || url.hash) throw unsupported('Only the reviewed HTTPS VDO.Ninja viewer routes are supported.');
 const params = url.searchParams, seen = new Set();
 for (const [key, item] of params) {
  if (!viewerParameters.has(key) || seen.has(key) || item.length > 2048 || /[\u0000-\u001f\u007f]/.test(item)) throw unsupported('This viewer link contains unsupported or repeated options. Keep the complete link and use a supported viewer route.');
  seen.add(key);
 }
 const views = ['view', 'pull'].filter(key => params.has(key));
 const wheps = ['whepplay', 'whep'].filter(key => params.has(key));
 if (views.length + wheps.length !== 1) throw unsupported('Use a single-stream viewer link, not a room, publisher, or mixed viewer route.');
 for (const key of ['wss', 'wss2']) {
  if (!params.has(key)) continue;
  let server;
  try { server = new URL(params.get(key).startsWith('wss://') ? params.get(key) : `wss://${params.get(key)}`); } catch { throw unsupported('The signaling server is not supported.'); }
  if (server.protocol !== 'wss:' || server.hostname !== 'wss.vdo.ninja' || !['', '443'].includes(server.port) || server.pathname !== '/' || server.search || server.hash || server.username || server.password) throw unsupported('Only the reviewed official signaling server is supported.');
 }
 if (params.has('wss') && params.has('wss2')) throw unsupported('Use only one signaling server option.');
 if (views.length) {
  const streamId = params.get(views[0]);
  if (!/^[a-zA-Z0-9_-]{1,128}$/.test(streamId)) throw unsupported('The viewer link must select one valid stream ID.');
  if (params.has('whepplaytoken') || params.has('wheptoken')) throw unsupported('WHEP access parameters require a WHEP viewer link.');
  return Object.freeze({ url: url.href, origin: url.origin, route: 'view', streamId });
 }
 let endpoint;
 try { endpoint = new URL(params.get(wheps[0])); } catch { throw unsupported('The WHEP endpoint must be a complete official HTTPS URL.'); }
 // The official viewer decodes this value a second time. Reject percent escapes
 // rather than permitting a second interpretation of the allowlisted endpoint.
 if (endpoint.protocol !== 'https:' || !meshcastHosts.has(endpoint.hostname) || endpoint.port || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || !/^(?:\/whep\/[a-zA-Z0-9_-]{1,256}|\/[a-zA-Z0-9_-]{1,256}\/whep)$/.test(endpoint.pathname) || params.get(wheps[0]).includes('%')) throw unsupported('This WHEP server or route has not been reviewed. Use the supported official Meshcast VDO.Ninja viewer link.');
 if (params.has('whepplaytoken') && params.has('wheptoken')) throw unsupported('Use only one WHEP access token option.');
 return Object.freeze({ url: url.href, origin: url.origin, route: 'whep', streamId: null });
}

async function pngDimensions(blob) {
 const bytes = new Uint8Array(await blob.slice(0, 33).arrayBuffer());
 const signature = [137, 80, 78, 71, 13, 10, 26, 10];
 if (bytes.length !== 33 || signature.some((value, i) => bytes[i] !== value)) throw new Error('Invalid PNG.');
 const data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
 if (data.getUint32(8) !== 13 || data.getUint32(12) !== 0x49484452) throw new Error('Invalid PNG header.');
 const width = data.getUint32(16), height = data.getUint32(20);
 if (!validFrameSize(width, height)) throw new Error('Frame dimensions exceed receiver limits.');
 return { width, height };
}

/** Official viewer bridge. No peer, SDK, capture track or iframe DOM access. */
export function createVdoFrameSource({ container, window = globalThis.window, document = globalThis.document, now = Date.now, requestTimeoutMs = 4000, stallAfterMs = 8000, reconnectBaseMs = 1000, reconnectMaxMs = 30000, freezeReconnectMs = 30000, startupGraceMs = 15000, decodeImage = blob => globalThis.createImageBitmap(blob) } = {}) {
 if (!container || !window || !document) throw new TypeError('A viewer container and browser document are required.');
 const life = createFrameLifecycle({ now, stallAfterMs });
 let iframe = null, route = null, connected = false, disposed = false, pending = null, decoding = false, whepUUID = null;
 let fingerprintCanvas = null, wanted = false, reconnectTimer = null, recoveryTimer = null, retryCount = 0, startedAt = 0, lastFingerprint = null, loaded = false;
 function finish(request, frame = null) {
  if (request.done) { frame?.release(); return; }
  request.done = true;
  clearTimeout(request.timer);
  request.signal?.removeEventListener('abort', request.abort);
  if (pending === request) pending = null;
  request.resolve(frame);
 }
 function current(request) { return !request.done && connected && !disposed && !document.hidden && request.sessionId === life.getState().sessionId && pending === request; }
 function detach() {
  connected = false;
  clearTimeout(recoveryTimer); recoveryTimer = null;
  if (pending) finish(pending);
  window.removeEventListener('message', onMessage);
  iframe?.removeEventListener('load', onLoad);
  iframe?.removeEventListener('error', onError);
  iframe?.remove(); iframe = null; whepUUID = null;
  if (fingerprintCanvas) fingerprintCanvas.width = fingerprintCanvas.height = 1;
  fingerprintCanvas = null;
 }
 function stop(status = 'ended', message = 'Screen source stopped.') {
  wanted = false; clearTimeout(reconnectTimer); reconnectTimer = null;
  detach(); route = null;
  document.removeEventListener('visibilitychange', visibility);
  life.stop(status, message);
 }
 function scheduleReconnect(message = 'The screen broadcast is interrupted. Reconnecting automatically.') {
  if (!wanted || disposed || document.hidden || reconnectTimer !== null) return;
  const target = route;
  detach();
  // Invalidate consumer frames and pending OCR before scheduling another peer.
  life.start('reconnecting');
  if (!wanted || disposed || route !== target) return;
  life.stop('reconnecting', message);
  if (!wanted || disposed || route !== target) return;
  const delay = Math.min(reconnectMaxMs, reconnectBaseMs * 2 ** Math.min(retryCount++, 10));
  reconnectTimer = setTimeout(() => { reconnectTimer = null; if (wanted && !disposed && !document.hidden) attach('reconnecting'); }, delay);
  reconnectTimer.unref?.();
 }
 function armRecovery() {
  clearTimeout(recoveryTimer);
  // Repeated PNG responses of a disconnected/frozen last video frame must not
  // keep the dead viewer forever. Static screens remain honestly unconfirmed.
  recoveryTimer = setTimeout(() => {
   // OCR owns the only snapshot: lack of another sample during that work says
   // nothing about transport health. Connection errors still reconnect at once.
   if (life.occupied()) { armRecovery(); return; }
   scheduleReconnect('No visible screen progress. Reconnecting automatically; a static screen may also cause this.');
  }, freezeReconnectMs);
  recoveryTimer.unref?.();
 }
 function attach(status = 'connecting') {
  const target = route;
  connected = true; loaded = false; lastFingerprint = null; startedAt = now(); life.start(status);
  if (!wanted || !connected || disposed || route !== target) return;
  iframe = document.createElement('iframe');
  iframe.title = 'VDO.Ninja screen viewer';
  iframe.allow = "autoplay; fullscreen; camera 'none'; microphone 'none'; display-capture 'none'";
  iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
  iframe.referrerPolicy = 'no-referrer';
  iframe.addEventListener('load', onLoad); iframe.addEventListener('error', onError);
  window.addEventListener('message', onMessage);
  const viewerUrl = new URL(route.url);
  if (!viewerUrl.searchParams.has('scale')) viewerUrl.searchParams.set('scale', '100');
  iframe.src = viewerUrl.href;
  container.appendChild(iframe); armRecovery();
 }
 function visibility() { if (document.hidden) stop('paused', 'Screen reading pauses while this page is hidden. Reconnect to resume.'); }
 function onLoad() {
  // A reload navigates the same WindowProxy: a new session and new cib prevent
  // old responses from being accepted even if the browser retains that proxy.
  if (!connected) return;
  // A WHEP video can be announced before the document's first load event.
  // Preserve that announcement; only a subsequent navigation invalidates it.
  if (!loaded) { loaded = true; if (life.getState().status === 'connecting') life.update({ status: 'reconnecting' }); return; }
  if (pending) finish(pending);
  whepUUID = null; lastFingerprint = null; startedAt = now(); life.start('reconnecting');
  if (connected && wanted && !disposed) armRecovery();
 }
 function onError() { scheduleReconnect('The official viewer could not load. Retrying automatically.'); }
 async function onMessage(event) {
  if (!connected || document.hidden || event.origin !== route?.origin || event.source !== iframe?.contentWindow) return;
  const data = event.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return;
  if (data.action === 'view-connection' && data.value === false && (route.route === 'view' ? data.streamID === route.streamId : data.UUID === whepUUID)) {
   scheduleReconnect(); return;
  }
  if (route.route === 'whep' && data.action === 'video-element-created') {
   if (typeof data.UUID === 'string' && /^whep_[a-zA-Z0-9]{25}$/.test(data.UUID) && data.value === `videosource_${data.UUID}`) whepUUID = data.UUID;
   return;
  }
  const request = pending, value = data.value;
  if (!request || decoding || data.action !== 'image-frame-capture' || !value || typeof value !== 'object' || Array.isArray(value) || value.cib !== request.cib) return;
  if (route.route === 'view' ? value.streamID !== route.streamId : value.UUID !== request.UUID) return;
  if (value.imageType !== 'png' || !(value.imageData instanceof (window.Blob ?? Blob)) || value.imageData.type !== 'image/png' || value.imageData.size < 33 || value.imageData.size > FRAME_LIMITS.maxBytes) {
   finish(request); scheduleReconnect('The viewer returned an unsupported or oversized frame. Retrying automatically.'); return;
  }
  decoding = true;
  let image = null;
  try {
   const { width, height } = await pngDimensions(value.imageData);
   if (!current(request)) return;
   image = await decodeImage(value.imageData);
   if (!current(request)) return;
   if (image.width !== width || image.height !== height) throw new Error('Decoded dimensions mismatch.');
   fingerprintCanvas ??= document.createElement('canvas');
   fingerprintCanvas.width = width; fingerprintCanvas.height = height;
   const context = fingerprintCanvas.getContext('2d', { willReadFrequently: true });
   context.drawImage(image, 0, 0);
   const fingerprint = frameFingerprint(context, width, height);
   if (fingerprint !== lastFingerprint) { if (lastFingerprint !== null) retryCount = 0; lastFingerprint = fingerprint; armRecovery(); }
   const owned = image;
   const frame = life.accept({ image, width, height, fingerprint, release: () => owned.close?.() });
   image = null;
   finish(request, frame);
  } catch {
   if (current(request)) { finish(request); scheduleReconnect('The browser could not decode this viewer frame safely. Retrying automatically.'); }
  } finally {
   image?.close?.(); decoding = false;
   // Keep the single decode slot occupied until its promise settles, including
   // after timeout/disconnect. Cancellation cannot abort native ImageBitmap work.
   if (!request.done) finish(request);
  }
 }
 return {
  getState: life.getState, subscribe: life.subscribe,
  connect({ url } = {}) {
   if (disposed) throw new Error('This screen source has been disposed.');
   stop();
   try { route = parseVdoViewerUrl(url); } catch (error) { life.stop('error', error.message); throw error; }
   if (document.hidden) { life.start(); stop('paused', 'Screen reading pauses while this page is hidden. Reconnect to resume.'); return life.getState(); }
   wanted = true; retryCount = 0;
   document.addEventListener('visibilitychange', visibility);
   attach();
   return life.getState();
  },
  disconnect: stop,
  dispose() { disposed = true; stop(); life.dispose(); },
  readFrame({ signal } = {}) {
   if (!connected || disposed || document.hidden || signal?.aborted || pending || decoding || life.occupied() || (route.route === 'whep' && !whepUUID)) return Promise.resolve(null);
   return new Promise(resolve => {
    const request = { resolve, signal, sessionId: life.getState().sessionId, cib: frameSessionId(), UUID: whepUUID, done: false, timer: null, abort: null };
    request.abort = () => finish(request);
    pending = request;
    signal?.addEventListener('abort', request.abort, { once: true });
    request.timer = setTimeout(() => {
     const valid = current(request); finish(request);
     if (!valid) return;
     if (now() - startedAt >= startupGraceMs) scheduleReconnect('No fresh viewer frame arrived. Reconnecting automatically.');
     else life.update({ status: 'stalled', message: 'Waiting for fresh viewer frames. Recovery is automatic if the broadcast remains unavailable.' });
    }, requestTimeoutMs);
    const payload = { getVideoFrame: true, cib: request.cib, ...(route.route === 'view' ? { streamID: route.streamId } : { UUID: whepUUID }) };
    try { iframe.contentWindow.postMessage(payload, route.origin); } catch { finish(request); scheduleReconnect('The viewer frame request failed. Retrying automatically.'); }
   });
  },
 };
}
