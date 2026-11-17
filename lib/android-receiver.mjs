/**
 * @typedef {{sessionId: string, sequence: number, width: number, height: number,
 * image: CanvasImageSource, release: () => void}} ScreenFrame
 * @typedef {{sessionId: string|null, status: string, message: string, width: number, height: number}} ScreenState
 * @typedef {{getState: () => ScreenState, subscribe: (listener: (state: ScreenState) => void) => (() => void),
 * readFrame: (options: {signal: AbortSignal}) => Promise<ScreenFrame|null>,
 * connect: (kind: string, options: {url: string}) => Promise<unknown>, disconnect: () => void,
 * pause: () => void, resume: () => Promise<unknown>, dispose: () => void}} ScreenSource
 */
/**
 * Screen transport feeds the native host; matching/OCR never run in this adapter.
 * @param {{source: ScreenSource, encodeFrame: (frame: ScreenFrame, options: {signal: AbortSignal}) => Promise<Blob>,
 * documentEpoch: string, fetch?: typeof globalThis.fetch, apiBase?: string, id?: string,
 * intervalMs?: number, maxFrameBytes?: number,
 * setTimer?: (callback: () => void, delay: number) => any, clearTimer?: (timer: any) => void}} options
 */
export function createAndroidReceiver({source, encodeFrame, fetch = globalThis.fetch,
 apiBase = '', id = globalThis.crypto.randomUUID(), intervalMs = 400,
 maxFrameBytes = 10 * 1024 ** 2, documentEpoch,
 setTimer = setTimeout, clearTimer = clearTimeout} = {}) {
 if (!source || typeof encodeFrame !== 'function' || !Number.isInteger(maxFrameBytes) || maxFrameBytes < 1)
  throw new TypeError('A bounded screen source and native frame encoder are required.');
 if (typeof documentEpoch !== 'string' || !/^[a-f0-9]{32}$/.test(documentEpoch))
  throw new TypeError('An owned reader document epoch is required.');
 let wanted = false, paused = null, disposed = false, epoch = 0, revision = 0;
 let binding = null, mayOwn = false, active = null, timer = null, busy = false;
 let transport = source.getState(), lastSession = transport.sessionId;
 let state = {status: 'ready', message: 'Connect the game device to begin.', active: false};
 const listeners = new Set();
 const current = token => !disposed && wanted && !paused && token === epoch;
 function publish(next = {}) {
  state = {...state, ...next, active: wanted, paused: !!paused};
  for (const listener of listeners) listener({...state});
 }
 function invalidate() {
  epoch++; binding = null; active?.abort();
  if (timer !== null) clearTimer(timer);
  timer = null;
 }
 async function request(path, options = {}) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
  try {
   const response = await fetch(apiBase + path, {...options, signal: controller.signal});
   let value;
   try { value = await response.json(); } catch { throw Error('The app returned an invalid screen-source response.'); }
   if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('The app returned an invalid screen-source response.');
   return {response, value};
  } finally {clearTimeout(timeout);}
 }
 function control(action, sequence, expected) {
  return request('/api/capture/receiver', {method: 'POST', keepalive: action === 'stop',
   headers: {'Content-Type': 'application/json', 'X-Toolkit-Document-Epoch': documentEpoch},
   body: JSON.stringify({id, revision: sequence, action, ...(action === 'start' ? {expected_generation: expected} : {})})});
 }
 async function stopNative() {
  // A higher revision fences a delayed/lost start, even when stop arrives first.
  const sequence = ++revision;
  mayOwn = false;
  const {response, value} = await control('stop', sequence);
  if (!response.ok) throw Error('The app has not confirmed that this screen source stopped.');
  return value;
 }
 function fence() {
  const needed = mayOwn || binding;
  invalidate();
  if (needed) void stopNative().catch(() => {
   if (!disposed && !paused) publish({message: 'Waiting to confirm the screen-source change.'});
  });
 }
 async function startNative(token, frame) {
  for (let attempt = 0; attempt < 2; attempt++) {
   const sequence = ++revision;
   const {response, value} = await request('/api/snapshot');
   const expected = value.status?.capture?.source_generation;
   if (!response.ok || !Number.isSafeInteger(expected) || expected < 0) throw Error('The app cannot identify its current screen source.');
   if (!current(token)) return null;
   mayOwn = true;
   const result = await control('start', sequence, expected);
   if (!current(token) || sequence !== revision) return null;
   if (result.response.status === 409 && attempt === 0) continue;
   const reply = result.value;
   if (!result.response.ok || reply.receiver_id !== id || reply.receiver_revision !== sequence
       || !Number.isSafeInteger(reply.generation) || reply.generation < 0 || reply.running !== true)
    throw Error('The app could not start this screen source. Reconnect it, or restart the app if its source limit was reached.');
   return {sessionId: frame.sessionId, width: frame.width, height: frame.height,
    generation: reply.generation, revision: sequence};
  }
  return null;
 }
 function schedule() {
  if (!wanted || paused || disposed || timer !== null || busy) return;
  timer = setTimer(() => {timer = null; void tick();}, intervalMs);
 }
 async function tick() {
  if (!wanted || paused || disposed || busy) return;
  busy = true;
  const token = epoch, controller = new AbortController();
  active = controller;
  let frame = null;
  try {
   frame = await source.readFrame({signal: controller.signal});
   if (!frame || !current(token) || frame.sessionId !== source.getState().sessionId) return;
   if (!Number.isSafeInteger(frame.sequence) || frame.sequence < 1
       || !Number.isInteger(frame.width) || !Number.isInteger(frame.height)
       || frame.width < 1 || frame.height < 1 || frame.width > 4096 || frame.height > 4096
       || frame.width * frame.height > 4194304) throw Error('The screen frame is too large. Lower the sender quality and reconnect.');
   if (!binding || binding.sessionId !== frame.sessionId || binding.width !== frame.width || binding.height !== frame.height) {
    binding = await startNative(token, frame);
    if (!binding || !current(token)) return;
   }
   const lease = binding;
   const blob = await encodeFrame(frame, {signal: controller.signal});
   if (!current(token) || controller.signal.aborted || binding !== lease) return;
   if (!(blob instanceof Blob) || blob.type !== 'image/png' || blob.size < 1 || blob.size > maxFrameBytes)
    throw Error('The screen frame could not be prepared within the app limit. Lower the sender quality.');
   let result;
   const timeout = setTimeout(() => controller.abort(), 8000);
   try {
    result = await fetch(apiBase + '/api/capture/frame', {method: 'POST', signal: controller.signal,
     headers: {'Content-Type': 'image/png', 'X-Toolkit-Generation': String(lease.generation),
      'X-Toolkit-Frame': String(frame.sequence), 'X-Toolkit-Receiver-Id': id,
      'X-Toolkit-Receiver-Revision': String(lease.revision), 'X-Toolkit-Document-Epoch': documentEpoch}, body: blob});
   } finally {clearTimeout(timeout);}
   if (!current(token)) return;
   if (result.status === 409) {fence(); return;}
   if (result.status !== 202) throw Error('The app could not accept the screen frame. Reconnect the source.');
   publish({status: transport.status, message: transport.message,
    width: frame.width, height: frame.height, acceptedFrames: (state.acceptedFrames ?? 0) + 1});
  } catch (error) {
   if (current(token)) {
    paused = 'error'; fence(); source.pause();
    publish({status: 'error', message: error instanceof Error ? error.message : 'Screen reading could not continue.'});
   }
  } finally {
   frame?.release();
   if (active === controller) active = null;
   busy = false; schedule();
  }
 }
 const unsubscribe = source.subscribe(next => {
  const scopeChanged = next.sessionId !== lastSession;
  const geometryChanged = binding && next.width > 0 && next.height > 0
   && (binding.width !== next.width || binding.height !== next.height);
  const lost = transport.status === 'live' && next.status !== 'live';
  transport = next; lastSession = next.sessionId;
  if (wanted && (scopeChanged || geometryChanged || lost)) fence();
  if (wanted && !paused) {
   if (next.status === 'error') paused = 'error';
   publish({status: next.status, message: next.message});
  }
  schedule();
 });
 return {
  getState: () => ({...state}),
  subscribe(listener) {listeners.add(listener); listener({...state}); return () => listeners.delete(listener);},
  async connect(url) {
   if (disposed) throw Error('This screen receiver has closed.');
   wanted = true; paused = null; fence();
   publish({status: 'connecting', message: 'Connecting to the game device.'});
   try {await source.connect('vdo', {url});}
   catch {paused = 'error'; publish({status: 'error', message: 'The screen link could not be opened. Check the complete viewer link.'});}
   schedule();
  },
  async stop() {
   wanted = false; paused = null; invalidate(); source.disconnect();
   publish({status: 'stopping', message: 'Disconnecting the screen source.'});
   try {await stopNative(); if (!disposed && !wanted) publish({status: 'ended', message: 'Screen source stopped.'});}
   catch (error) {if (!disposed && !wanted) publish({status: 'error', message: error.message});}
  },
  pause() {
   if (!wanted || paused) return;
   paused = 'background'; fence(); source.pause();
   publish({status: 'paused', message: 'Screen reading pauses while the app is in the background.'});
  },
  async resume() {
   if (!wanted || paused !== 'background' || disposed) return;
   paused = null; invalidate();
   publish({status: 'connecting', message: 'Waiting for fresh screen frames.'});
   await source.resume(); schedule();
  },
  dispose() {
   if (disposed) return;
   wanted = false; disposed = true; invalidate(); unsubscribe(); source.dispose();
   void stopNative().catch(() => {}); listeners.clear();
  },
 };
}
