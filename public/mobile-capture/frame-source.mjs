/** Transport-independent, consumer-owned frames. A source never queues reads. */
export const FRAME_LIMITS = Object.freeze({ maxWidth: 4096, maxHeight: 4096, maxPixels: 4194304, maxBytes: 16777216 });

let identities = 0;
export function frameSessionId() {
 return globalThis.crypto?.randomUUID?.() ?? `frame-${Date.now()}-${++identities}`;
}

export function validFrameSize(width, height) {
 return Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0 && width <= FRAME_LIMITS.maxWidth && height <= FRAME_LIMITS.maxHeight && width * height <= FRAME_LIMITS.maxPixels;
}

// Compare decoded pixels, not PNG metadata or a connection/packet counter. Read
// strips to keep temporary pixel storage bounded even on a portrait iPad frame.
export function frameFingerprint(context, width, height) {
 let a = 2166136261, b = 5381;
 for (let y = 0; y < height; y += 32) {
  const data = context.getImageData(0, y, width, Math.min(32, height - y)).data;
  for (let i = 0; i < data.length; i++) { a = Math.imul(a ^ data[i], 16777619); b = Math.imul(b, 33) ^ data[i]; }
 }
 return `${width}:${height}:${a >>> 0}:${b >>> 0}`;
}

/** Shared bookkeeping; transport adapters own cancellation and their resources. */
export function createFrameLifecycle({ now = Date.now, stallAfterMs = 8000 } = {}) {
 let state = Object.freeze({ sessionId: null, status: 'ready', width: 0, height: 0, lastFrameTimestamp: null, message: 'Choose a screen source.' });
 let timer = null, signature = null, sequence = 0, held = null;
 const listeners = new Set();
 function update(patch) {
  state = Object.freeze({ ...state, ...patch });
  for (const listener of [...listeners]) { try { listener(state); } catch { /* A UI observer cannot break cleanup. */ } }
 }
 function clear() { clearTimeout(timer); timer = null; held?.release(); held = null; }
 function arm() {
  clearTimeout(timer);
  timer = setTimeout(() => update({ status: 'stalled', message: 'No visible frame changes. The screen may be static or the broadcast interrupted.' }), stallAfterMs);
  timer.unref?.();
 }
 return {
  getState: () => state,
  subscribe(listener) { listeners.add(listener); listener(state); return () => listeners.delete(listener); },
  start(status = 'connecting') {
   clear(); signature = null; sequence = 0;
   arm();
   update({ sessionId: frameSessionId(), status, width: 0, height: 0, lastFrameTimestamp: null, message: 'Waiting for screen frames.' });
   return state.sessionId;
  },
  stop(status = 'ended', message = 'Screen source stopped.') { clear(); update({ status, width: 0, height: 0, lastFrameTimestamp: null, message }); },
  update,
  occupied: () => !!held,
  accept({ image, width, height, fingerprint, release = () => {} }) {
   const changed = fingerprint !== signature;
   // A fresh observation of stable dialogue can confirm OCR while recent
   // visible progress still proves activity. It never extends the live window.
   if (held || (!changed && state.status !== 'live')) { release(); return null; }
   const first = signature === null;
   signature = fingerprint;
   const timestamp = now(), sessionId = state.sessionId;
   let released = false;
   const frame = Object.freeze({ image, width, height, timestamp, sessionId, sequence: ++sequence, release() {
    if (released) return;
    released = true; release(); if (held === frame) held = null;
   } });
   held = frame;
   if (changed) arm();
   update({ width, height, lastFrameTimestamp: timestamp, status: first ? 'connecting' : 'live', message: first ? 'Frame received; waiting for visible changes.' : 'Visible screen changes received.' });
   return released ? null : frame;
  },
  dispose() { clear(); listeners.clear(); },
 };
}

/** Wrap the existing preview. capture.js still owns its stream, peer and tracks. */
export function createVideoFrameSource({ video, now = Date.now, stallAfterMs = 8000 } = {}) {
 if (!video) throw new TypeError('A preview video is required.');
 const document = video.ownerDocument ?? globalThis.document;
 const life = createFrameLifecycle({ now, stallAfterMs });
 let connected = false, disposed = false, callback = null, progress = 0, consumed = 0, mediaTime = null;
 function cancelCallback() { if (callback !== null) video.cancelVideoFrameCallback?.(callback); callback = null; }
 function watch(sessionId) {
  if (!connected || document?.hidden || !video.requestVideoFrameCallback) return;
  callback = video.requestVideoFrameCallback((_time, metadata) => {
   callback = null;
   if (!connected || life.getState().sessionId !== sessionId || document?.hidden) return;
   if (metadata.mediaTime !== mediaTime) { mediaTime = metadata.mediaTime; progress++; }
   watch(sessionId);
  });
 }
 function disconnect() {
  connected = false; cancelCallback();
  document?.removeEventListener('visibilitychange', visibility);
  video.removeEventListener?.('ended', ended);
  life.stop();
 }
 function ended() { disconnect(); }
 function visibility() {
  if (!connected) return;
  cancelCallback();
  if (document.hidden) life.stop('paused', 'Screen reading pauses while this page is hidden.');
  else { progress = consumed = 0; mediaTime = video.currentTime; watch(life.start('reconnecting')); }
 }
 return {
  getState: life.getState, subscribe: life.subscribe,
  connect() {
   if (disposed) throw new Error('This screen source has been disposed.');
   disconnect(); connected = true; progress = consumed = 0; mediaTime = video.currentTime;
   document?.addEventListener('visibilitychange', visibility);
   video.addEventListener?.('ended', ended);
   const id = life.start();
   if (document?.hidden) life.stop('paused', 'Screen reading pauses while this page is hidden.');
   else watch(id);
   return life.getState();
  },
  disconnect,
  dispose() { disposed = true; disconnect(); life.dispose(); },
  async readFrame({ signal } = {}) {
   if (!connected || disposed || signal?.aborted || document?.hidden || life.occupied()) return null;
   if (video.readyState < 2 || video.ended || video.paused) return null;
   if (!video.requestVideoFrameCallback && video.currentTime !== mediaTime) { mediaTime = video.currentTime; progress++; }
   if (progress === consumed) return null;
   consumed = progress;
   const sourceWidth = video.videoWidth, sourceHeight = video.videoHeight;
   if (!Number.isInteger(sourceWidth) || !Number.isInteger(sourceHeight) || sourceWidth <= 0 || sourceHeight <= 0) return null;
   // Existing desktop capture may be 4K or ultrawide. Bound our snapshot without
   // changing capture.js's video/transport or normalized crop coordinates.
   const scale = Math.min(1, FRAME_LIMITS.maxWidth / sourceWidth, FRAME_LIMITS.maxHeight / sourceHeight, Math.sqrt(FRAME_LIMITS.maxPixels / (sourceWidth * sourceHeight)));
   const width = Math.max(1, Math.floor(sourceWidth * scale)), height = Math.max(1, Math.floor(sourceHeight * scale));
   const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
   try {
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(video, 0, 0, width, height);
    return life.accept({ image: canvas, width, height, fingerprint: frameFingerprint(context, width, height), release() { canvas.width = canvas.height = 1; } });
   } catch {
    canvas.width = canvas.height = 1;
    life.update({ status: 'error', message: 'The browser could not read this screen frame.' });
    return null;
   }
  },
 };
}
