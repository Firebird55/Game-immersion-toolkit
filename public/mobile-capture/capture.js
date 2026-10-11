import { TEST_DURATION_MS, parsePairing, pairingMessage, samePairing, privateTrackState, privateRtcSample, frameHealth, imageSignature } from './core.mjs';

const $ = id => document.getElementById(id);
const build = document.documentElement.dataset.buildCommit ? {
  commit: document.documentElement.dataset.buildCommit,
  branch: document.documentElement.dataset.buildBranch,
  builtAt: document.documentElement.dataset.buildTime,
} : null;
if (build) $('build-info').textContent = `Build ${build.commit.slice(0, 8)} · ${build.branch} · ${build.builtAt}`;
let peer = null, stream = null, generation = 0, frameCallback = null;
let connectedAt = null, attemptStartedAt = null, lastFrameAt = null, delivered = 0, changed = 0, dark = false;
let lastHash = null, lastMediaTime = -1, observation = null, events = [];
let pendingCapture = false, busyPairing = false, previousSampleAt = null;
let sessionGame = null, sessionRole = null;
let identity = null, recoveryAttempts = 0, rtcSamples = [], trackSnapshot = [], statsPending = null;
const canvas = document.createElement('canvas');
canvas.width = 64; canvas.height = 36;
const context = canvas.getContext('2d', { willReadFrequently: true });
const capability = () => ({ secure: isSecureContext, screenCapture: typeof navigator.mediaDevices?.getDisplayMedia === 'function', webRTC: typeof RTCPeerConnection === 'function', userAgent: navigator.userAgent });
function event(kind, details = {}) { events.push({ at: new Date().toISOString(), kind, ...details }); events = events.slice(-300); }
function status(message) { $('status').textContent = message; }
const liveCapture = () => stream?.getVideoTracks().some(track => track.readyState === 'live') ?? false;
function trackStates() { return stream ? stream.getTracks().map(privateTrackState).filter(Boolean) : trackSnapshot; }
function updateDiagnostics() {
  if (stream) trackSnapshot = trackStates();
  const video = trackSnapshot.find(track => track.kind === 'video');
  $('capture-state').textContent = `${sessionRole === 'receiver' || $('role').value === 'receiver' ? 'Incoming video' : 'Capture'}: ${video ? `${video.readyState}${video.muted ? ' · muted' : ''}${video.width ? ` · ${video.width} × ${video.height}` : ''}` : 'not started'}`;
  $('diagnostics').textContent = `Connection: ${peer?.connectionState ?? 'closed'} · ICE: ${peer?.iceConnectionState ?? 'closed'} · ${recoveryAttempts} reconnect attempts · Page: ${document.hidden ? 'background' : 'visible'} · Network: ${navigator.onLine ? 'online' : 'offline'}`;
}
function updateRole() {
  const sender = $('role').value === 'sender', caps = capability();
  $('capability').textContent = `Secure context: ${caps.secure ? 'yes' : 'no'} · Screen capture API: ${caps.screenCapture ? 'available (background capture unverified)' : 'unavailable'} · WebRTC: ${caps.webRTC ? 'available' : 'unavailable'} · ${caps.userAgent}`;
  $('instructions').textContent = sender ? 'Share the game window or screen and send the offer to the receiving device. Paste its answer back here, then open the game.' : 'Paste the gaming device’s offer below. Accept it, send the generated answer back, and keep this page open.';
  if (sender && !caps.screenCapture) $('instructions').textContent = 'This browser cannot share its screen. For your iPad game → iPhone setup, the iPad remains the sender and the iPhone remains the receiver. A native capture helper is needed on the iPad; it is not included yet. Browser pairing cannot start this capture.';
  $('start').hidden = !sender;
  const sessionActive = Boolean(peer) || Boolean(stream) || Boolean(identity);
  $('start').disabled = sessionActive || pendingCapture || busyPairing || !caps.secure || !caps.screenCapture || !caps.webRTC;
  $('reconnect').hidden = !sender;
  $('reconnect').disabled = !liveCapture() || pendingCapture || busyPairing || !caps.secure || !caps.webRTC;
  $('apply').disabled = pendingCapture || busyPairing || !caps.secure || !caps.webRTC;
  $('role').disabled = sessionActive || pendingCapture || busyPairing; $('game').disabled = $('role').disabled;
  $('reload-build').disabled = $('role').disabled;
  $('stop').disabled = !sessionActive && !pendingCapture && !busyPairing;
  updateDiagnostics();
}
function cancelFrameMonitor() {
  if (frameCallback !== null && $('preview').cancelVideoFrameCallback) $('preview').cancelVideoFrameCallback(frameCallback);
  frameCallback = null;
}
function detachConnection(keepCapture = false) {
  // Invalidate old callbacks before closing their peer or received tracks.
  generation++;
  cancelFrameMonitor();
  if (peer) {
    peer.onconnectionstatechange = null; peer.oniceconnectionstatechange = null;
    peer.onicegatheringstatechange = null; peer.onsignalingstatechange = null; peer.ontrack = null;
    peer.close();
  }
  peer = null;
  if (stream) for (const track of stream.getTracks()) {
    track.onended = null; track.onmute = null; track.onunmute = null;
    if (!keepCapture) track.stop();
  }
  if (!keepCapture) { if (stream) trackSnapshot = trackStates(); stream = null; $('preview').srcObject = null; }
  $('play-preview').hidden = true;
  $('begin-test').disabled = true;
  $('outgoing').value = ''; $('copy').disabled = true; $('save-pairing').disabled = true;
  $('incoming').value = '';
  connectedAt = null; attemptStartedAt = Date.now(); lastFrameAt = null; lastMediaTime = -1; lastHash = null; dark = false;
  return generation;
}
function cleanup(message = 'Stopped.') {
  detachConnection(); pendingCapture = false; busyPairing = false;
  identity = null;
  $('metrics').textContent = `Stopped · ${delivered} delivered frames · ${changed} visible changes`;
  $('stop').disabled = true; $('begin-test').disabled = true;
  if (observation && !observation.endedAt) observation.endedAt = Date.now();
  event('stopped'); status(message); updateRole();
}
function current(active, token) { return active === peer && token === generation; }
function watchTracks(active, token) {
  for (const track of stream.getTracks()) {
    const record = kind => { if (current(active, token)) { trackSnapshot = trackStates(); event(kind, { track: privateTrackState(track) }); updateDiagnostics(); } };
    track.onmute = () => record('track_muted'); track.onunmute = () => record('track_unmuted');
    track.onended = () => {
      if (!current(active, token)) return;
      record('track_ended');
      if (sessionRole === 'sender') cleanup('Screen capture ended. Start a new screen share; reconnect cannot restore an ended capture.');
      else {
        // A received track may end with a lost peer while the iPad's capture
        // remains live. Keep the observation and identity for a fresh offer.
        cancelFrameMonitor(); $('begin-test').disabled = true;
        status('Incoming screen stream ended. Return to the iPad and reconnect, or start a new capture if sharing ended.'); updateRole();
      }
    };
    record('track_attached');
  }
}
function newPeer() {
  // No STUN/TURN or signaling service: local network candidates only.
  peer = new RTCPeerConnection({ iceServers: [] });
  const active = peer, token = generation;
  attemptStartedAt = Date.now();
  event('connection_attempt_started', { attempt: identity?.attempt ?? null });
  active.onconnectionstatechange = () => {
    if (!current(active, token)) return;
    event(`connection_${active.connectionState}`);
    const interrupted = ['failed', 'disconnected', 'closed'].includes(active.connectionState);
    status(`Connection: ${active.connectionState}${interrupted ? sessionRole === 'sender' ? '. Capture is kept open. Tap Reconnect & create new offer, then exchange the new messages.' : '. Return to the iPad, tap Reconnect & create new offer, then accept its fresh offer here and send the new answer back.' : ''}`);
    if (active.connectionState === 'connected' && connectedAt === null) connectedAt = Date.now();
    updateRole();
  };
  for (const [handler, kind, state] of [['oniceconnectionstatechange', 'ice_connection', 'iceConnectionState'], ['onicegatheringstatechange', 'ice_gathering', 'iceGatheringState'], ['onsignalingstatechange', 'signaling', 'signalingState']]) {
    active[handler] = () => { if (current(active, token)) { event(kind, { state: active[state] }); updateDiagnostics(); } };
  }
  active.ontrack = async e => {
    if (!current(active, token) || sessionRole !== 'receiver') return;
    stream = e.streams[0] ?? new MediaStream([e.track]);
    $('preview').srcObject = stream;
    watchTracks(active, token);
    try { await $('preview').play(); } catch { if (current(active, token)) { $('play-preview').hidden = false; status('Tap Play preview to start the video.'); } }
    if (!current(active, token) || !liveCapture()) return;
    monitorFrames();
    $('begin-test').disabled = Boolean(observation); updateRole();
  };
  $('stop').disabled = false; updateRole();
  return active;
}
function resetMetrics() {
  connectedAt = null; attemptStartedAt = null; lastFrameAt = null; delivered = 0; changed = 0; dark = false;
  lastHash = null; lastMediaTime = -1; observation = null; events = [];
  identity = null; recoveryAttempts = 0; rtcSamples = []; trackSnapshot = []; previousSampleAt = null;
  sessionGame = $('game').value; sessionRole = $('role').value;
  $('result').value = 'not_verified';
  $('notes').value = '';
  event('session_started', { visible: !document.hidden, online: navigator.onLine });
}
function gatherIce(active, token) {
  if (active.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve, reject) => {
    let finished = false;
    const timer = setTimeout(() => finish(new Error('Local network discovery timed out. Stop and try again.')), 20_000);
    const interval = setInterval(() => { if (generation !== token) finish(new Error('Pairing cancelled.')); }, 100);
    function finish(error) { if (finished) return; finished = true; clearTimeout(timer); clearInterval(interval); active.removeEventListener('icegatheringstatechange', check); error ? reject(error) : resolve(); }
    function check() { if (active.iceGatheringState === 'complete') finish(); }
    active.addEventListener('icegatheringstatechange', check); check();
  });
}
async function outputDescription(active, description, token) {
  if (!current(active, token)) return;
  await active.setLocalDescription(description);
  if (!current(active, token)) return;
  await gatherIce(active, token);
  if (!current(active, token)) return;
  $('outgoing').value = pairingMessage(active.localDescription, sessionGame, identity ?? {});
  $('copy').disabled = false; $('save-pairing').disabled = false;
  status('Pairing message ready. Send it to the other device.');
}
async function createSenderOffer(active, token) {
  stream.getVideoTracks().forEach(track => active.addTrack(track, stream));
  watchTracks(active, token); $('preview').srcObject = stream;
  const offer = await active.createOffer();
  if (!current(active, token)) return;
  await outputDescription(active, offer, token);
}
$('start').onclick = async () => {
  const token = ++generation;
  pendingCapture = true; updateRole(); $('start').disabled = true; $('stop').disabled = false;
  try {
    const captured = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    if (generation !== token) { captured.getTracks().forEach(t => t.stop()); return; }
    pendingCapture = false; busyPairing = true;
    resetMetrics(); stream = captured;
    if (!liveCapture()) throw new Error('No live video track was provided.');
    identity = { sessionId: crypto.randomUUID(), pairingId: crypto.randomUUID(), attempt: 1 };
    const active = newPeer();
    await createSenderOffer(active, token);
    if (current(active, token)) event('screen_share_started');
  } catch (error) { if (generation === token) cleanup(`Cannot start capture: ${error.message}`); }
  finally { if (generation === token) { pendingCapture = false; busyPairing = false; updateRole(); } }
};
$('reconnect').onclick = async () => {
  if (pendingCapture || busyPairing || sessionRole !== 'sender' || !liveCapture()) return;
  let token = detachConnection(true);
  busyPairing = true; recoveryAttempts++;
  identity = { ...identity, pairingId: crypto.randomUUID(), attempt: identity.attempt + 1 };
  event('reconnect_requested', { attempt: identity.attempt });
  status('Capture is kept open. Preparing a fresh offer…'); updateRole();
  try { await createSenderOffer(newPeer(), token); }
  catch {
    if (generation === token) {
      token = detachConnection(true); watchTracks(null, token);
      event('connection_attempt_failed', { attempt: identity?.attempt ?? null });
      status('Reconnect could not prepare an offer. Capture is kept open; tap Reconnect to try again.');
    }
  }
  finally { if (generation === token) { busyPairing = false; updateRole(); } }
};
$('apply').onclick = async () => {
  busyPairing = true; updateRole();
  let token = generation;
  let replacingReceiver = false;
  try {
    const sender = $('role').value === 'sender';
    const message = parsePairing($('incoming').value, sender ? 'answer' : 'offer');
    if (sender) {
      if (!peer || peer.signalingState !== 'have-local-offer') throw new Error('Create an offer on the sharing device first.');
      if (message.game !== $('game').value) throw new Error('Answer belongs to a different game.');
      if (!samePairing(message, identity)) throw new Error('This answer is for an older or different offer. Reload both devices before a new test, or use the answer to the latest offer.');
      const active = peer;
      await active.setRemoteDescription({ type: message.type, sdp: message.sdp });
      if (current(active, token)) status('Answer accepted. Open the game and watch the phone preview.');
    } else {
      const continuing = identity && message.sessionId === identity.sessionId;
      if (identity || peer || stream) {
        if (message.game !== sessionGame) throw new Error('Offer belongs to a different game. Stop this test before changing games.');
        if (!continuing) throw new Error('Offer belongs to a different capture session. Stop this test before accepting it.');
        if (message.attempt <= identity.attempt || message.pairingId === identity.pairingId) throw new Error('This offer was already accepted or is older. Use the latest reconnect offer from the iPad.');
      }
      token = detachConnection(); replacingReceiver = true;
      if (!continuing) { $('game').value = message.game; resetMetrics(); }
      else { recoveryAttempts++; event('reconnect_offer_accepted', { attempt: message.attempt }); }
      identity = message.sessionId ? { sessionId: message.sessionId, pairingId: message.pairingId, attempt: message.attempt } : null;
      const active = newPeer();
      await active.setRemoteDescription({ type: message.type, sdp: message.sdp });
      if (!current(active, token)) return;
      const answer = await active.createAnswer();
      if (!current(active, token)) return;
      await outputDescription(active, answer, token);
    }
  } catch (error) {
    if (generation === token) {
      if (replacingReceiver) { token = detachConnection(); event('pairing_failed'); status('Pairing could not complete. Ask the iPad for a fresh reconnect offer and try again.'); }
      else status(error.message);
    }
  }
  finally { if (generation === token) { busyPairing = false; updateRole(); } }
};
$('play-preview').onclick = async () => {
  const token = generation, source = $('preview').srcObject;
  try { await $('preview').play(); if (token === generation && $('preview').srcObject === source) $('play-preview').hidden = true; }
  catch { if (token === generation && $('preview').srcObject === source) status('Cannot play preview. Tap Play preview to try again.'); }
};
$('stop').onclick = () => cleanup();
$('reload-build').onclick = () => { const url = new URL(location.href); url.searchParams.set('v', String(Date.now())); location.replace(url); };
$('role').onchange = updateRole;
$('copy').onclick = async () => { try { await navigator.clipboard.writeText($('outgoing').value); status('Pairing message copied.'); } catch { $('outgoing').select(); status('Select and copy the message, or download the pairing file.'); } };
function download(value, name) {
  const url = URL.createObjectURL(new Blob([value], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
$('save-pairing').onclick = () => download($('outgoing').value, `mobile-${$('role').value === 'sender' ? 'offer' : 'answer'}.json`);
$('pairing-file').onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  if (file.size > 128_000) { status('Pairing file is too large.'); return; }
  $('incoming').value = await file.text(); status('Pairing file loaded. Tap Accept message.');
};
function receivedFrame(mediaTime) {
  lastMediaTime = mediaTime; lastFrameAt = Date.now(); delivered++;
  if (observation && !observation.endedAt) observation.frames++;
}
function monitorFrames() {
  const video = $('preview'), token = generation;
  cancelFrameMonitor();
  if (!video.requestVideoFrameCallback) return;
  const tick = (_, metadata) => {
    if (token !== generation) return;
    receivedFrame(metadata.mediaTime);
    frameCallback = video.requestVideoFrameCallback(tick);
  };
  frameCallback = video.requestVideoFrameCallback(tick);
}
setInterval(() => {
  updateDiagnostics();
  if (sessionRole !== 'receiver' || !peer && !identity) return;
  const now = Date.now(), video = $('preview');
  if (!video.requestVideoFrameCallback && video.readyState >= 2 && video.currentTime !== lastMediaTime) receivedFrame(video.currentTime);
  if (video.readyState >= 2 && video.videoWidth && context) {
    context.drawImage(video, 0, 0, 64, 36);
    const signature = imageSignature(context.getImageData(0, 0, 64, 36).data);
    dark = signature.dark;
    if (lastHash !== null && signature.hash !== lastHash) { changed++; if (observation && !observation.endedAt) observation.changes++; }
    lastHash = signature.hash;
  }
  const health = frameHealth(lastFrameAt, now, connectedAt ?? attemptStartedAt ?? now);
  if (observation && !observation.endedAt) {
    observation.maxSamplingGapMs = Math.max(observation.maxSamplingGapMs, now - (previousSampleAt ?? now));
    previousSampleAt = now;
    if (document.hidden) observation.hiddenSamples++;
    else { observation.samples++; if (health !== 'Receiving frames') observation.stalledSamples++; if (dark) observation.darkSamples++; }
    if (now - observation.startedAt >= TEST_DURATION_MS) { observation.endedAt = now; event('observation_complete'); }
  }
  $('metrics').textContent = `${health} · ${video.videoWidth} × ${video.videoHeight} · ${delivered} delivered frames · ${changed} visible changes${dark ? ' · Image appears black' : ''}${observation ? ` · ${Math.floor(((observation.endedAt ?? now) - observation.startedAt) / 1000)} / 900 seconds${observation.endedAt ? ' · Observation ended' : ''}` : ''}`;
}, 500);
setInterval(async () => {
  const active = peer, token = generation;
  if (!active || statsPending === active || active.connectionState === 'closed') return;
  statsPending = active;
  try {
    const report = await active.getStats();
    if (!current(active, token)) return;
    rtcSamples.push({ at: new Date().toISOString(), role: sessionRole, attempt: identity?.attempt ?? null, records: privateRtcSample(report, sessionRole) });
    rtcSamples = rtcSamples.slice(-120);
  } catch { if (current(active, token)) event('stats_unavailable'); }
  finally { if (statsPending === active) statsPending = null; }
}, 2000);
$('begin-test').onclick = () => {
  previousSampleAt = Date.now();
  observation = { startedAt: previousSampleAt, endedAt: null, frames: 0, changes: 0, samples: 0, stalledSamples: 0, darkSamples: 0, hiddenSamples: 0, maxSamplingGapMs: 0 };
  $('begin-test').disabled = true; event('observation_started');
};
$('report').onclick = () => download(JSON.stringify({ format: 'proxy-mobile-capture-report-v1', createdAt: new Date().toISOString(), build, role: sessionRole ?? $('role').value, game: sessionGame ?? $('game').value, capability: capability(), connectionState: peer?.connectionState ?? 'closed', frameMeasurement: $('preview').requestVideoFrameCallback ? 'video-frame-callback' : 'media-time-fallback', deliveredFrames: delivered, visibleChanges: changed, observation, userObservation: $('result').value, notes: $('notes').value.slice(0, 4000), events, diagnostics: { tracks: trackStates(), rtcSamples, recoveryAttempts }, backgroundCaptureVerified: false, explanation: 'Manual device test evidence only. Review the game preview and observation; frame delivery alone cannot verify game capture.' }, null, 2), 'mobile-capture-report.json');
document.addEventListener('visibilitychange', () => { event(document.hidden ? 'page_hidden' : 'page_visible'); updateDiagnostics(); });
for (const kind of ['freeze', 'resume']) document.addEventListener(kind, () => event(kind));
for (const kind of ['online', 'offline']) window.addEventListener(kind, () => { event(kind); updateDiagnostics(); });
for (const kind of ['pagehide', 'pageshow']) window.addEventListener(kind, e => event(kind, { persisted: e.persisted }));
updateRole();
