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
