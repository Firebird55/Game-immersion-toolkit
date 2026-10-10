import { TEST_DURATION_MS, parsePairing, pairingMessage, frameHealth, imageSignature } from './core.mjs';

const $ = id => document.getElementById(id);
const build = document.documentElement.dataset.buildCommit ? {
  commit: document.documentElement.dataset.buildCommit,
  branch: document.documentElement.dataset.buildBranch,
  builtAt: document.documentElement.dataset.buildTime,
} : null;
if (build) $('build-info').textContent = `Build ${build.commit.slice(0, 8)} · ${build.branch} · ${build.builtAt}`;
let peer = null, stream = null, generation = 0, frameCallback = null;
let connectedAt = null, lastFrameAt = null, delivered = 0, changed = 0, dark = false;
let lastHash = null, lastMediaTime = -1, observation = null, events = [];
let pendingCapture = false, busyPairing = false, previousSampleAt = null;
let sessionGame = null, sessionRole = null;
const canvas = document.createElement('canvas');
canvas.width = 64; canvas.height = 36;
const context = canvas.getContext('2d', { willReadFrequently: true });
const capability = () => ({ secure: isSecureContext, screenCapture: typeof navigator.mediaDevices?.getDisplayMedia === 'function', webRTC: typeof RTCPeerConnection === 'function', userAgent: navigator.userAgent });
function event(kind) { events.push({ at: new Date().toISOString(), kind }); events = events.slice(-300); }
function status(message) { $('status').textContent = message; }
function updateRole() {
  const sender = $('role').value === 'sender', caps = capability();
  $('capability').textContent = `Secure context: ${caps.secure ? 'yes' : 'no'} · Screen capture API: ${caps.screenCapture ? 'available (background capture unverified)' : 'unavailable'} · WebRTC: ${caps.webRTC ? 'available' : 'unavailable'} · ${caps.userAgent}`;
  $('instructions').textContent = sender ? 'Share the iPad screen and send the offer to the phone. Paste the phone’s answer back here, then open the game.' : 'Paste the iPad’s offer below. Accept it, send the generated answer back to the iPad, and keep this page open.';
  $('start').hidden = !sender;
  $('start').disabled = Boolean(peer) || pendingCapture || busyPairing || !caps.secure || !caps.screenCapture || !caps.webRTC;
  $('apply').disabled = pendingCapture || busyPairing || !caps.secure || !caps.webRTC;
  $('role').disabled = Boolean(peer) || pendingCapture || busyPairing; $('game').disabled = Boolean(peer) || pendingCapture || busyPairing;
  $('reload-build').disabled = Boolean(peer) || pendingCapture || busyPairing;
}
function cleanup(message = 'Stopped.') {
  generation++;
  pendingCapture = false;
  if (frameCallback !== null && $('preview').cancelVideoFrameCallback) $('preview').cancelVideoFrameCallback(frameCallback);
  frameCallback = null;
  if (peer) { peer.onconnectionstatechange = null; peer.ontrack = null; peer.close(); }
  peer = null;
  if (stream) for (const track of stream.getTracks()) { track.onended = null; track.stop(); }
  stream = null; $('preview').srcObject = null;
  $('play-preview').hidden = true;
  $('metrics').textContent = `Stopped · ${delivered} delivered frames · ${changed} visible changes`;
  $('stop').disabled = true; $('begin-test').disabled = true;
  $('outgoing').value = ''; $('copy').disabled = true; $('save-pairing').disabled = true;
  if (observation && !observation.endedAt) observation.endedAt = Date.now();
  event('stopped'); status(message); updateRole();
}
function newPeer() {
  // No STUN/TURN or signaling service: local network candidates only.
  peer = new RTCPeerConnection({ iceServers: [] });
  const active = peer;
  active.onconnectionstatechange = () => {
    if (peer !== active) return;
    event(`connection_${active.connectionState}`);
    status(`Connection: ${active.connectionState}${active.connectionState === 'failed' ? '. Try the same Wi-Fi without client isolation, then stop and pair again.' : ''}`);
    if (active.connectionState === 'connected' && connectedAt === null) connectedAt = Date.now();
  };
  active.ontrack = async e => {
    if (peer !== active) return;
    stream = e.streams[0] ?? new MediaStream([e.track]);
    $('preview').srcObject = stream;
    e.track.onended = () => cleanup('Screen stream ended.');
    e.track.onmute = () => event('track_muted');
    e.track.onunmute = () => event('track_unmuted');
    try { await $('preview').play(); } catch { if (peer === active) { $('play-preview').hidden = false; status('Tap Play preview to start the video.'); } }
    if (peer !== active) return;
    monitorFrames();
    $('begin-test').disabled = false;
  };
  $('stop').disabled = false; updateRole();
  return active;
}
function resetMetrics() {
  connectedAt = null; lastFrameAt = null; delivered = 0; changed = 0; dark = false;
  lastHash = null; lastMediaTime = -1; observation = null; events = [];
  sessionGame = $('game').value; sessionRole = $('role').value;
  $('result').value = 'not_verified';
  $('notes').value = '';
}
function gatherIce(active, token) {
  if (active.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error('Local network discovery timed out. Stop and try again.')), 20_000);
    const interval = setInterval(() => { if (generation !== token) finish(new Error('Pairing cancelled.')); }, 100);
    function finish(error) { clearTimeout(timer); clearInterval(interval); active.removeEventListener('icegatheringstatechange', check); error ? reject(error) : resolve(); }
    function check() { if (active.iceGatheringState === 'complete') finish(); }
    active.addEventListener('icegatheringstatechange', check); check();
  });
}
async function outputDescription(active, description, token) {
  await active.setLocalDescription(description);
  await gatherIce(active, token);
  if (generation !== token) return;
  $('outgoing').value = pairingMessage(active.localDescription, $('game').value);
  $('copy').disabled = false; $('save-pairing').disabled = false;
  status('Pairing message ready. Send it to the other device.');
}
$('start').onclick = async () => {
  const token = ++generation;
  pendingCapture = true; updateRole(); $('start').disabled = true; $('stop').disabled = false;
  try {
    const captured = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    if (generation !== token) { captured.getTracks().forEach(t => t.stop()); return; }
    pendingCapture = false;
    resetMetrics(); stream = captured;
    const active = newPeer();
    stream.getVideoTracks().forEach(track => { active.addTrack(track, stream); track.onended = () => cleanup('Screen sharing ended.'); });
    $('preview').srcObject = stream;
    await outputDescription(active, await active.createOffer(), token);
    event('screen_share_started');
  } catch (error) { if (generation === token) cleanup(`Cannot start capture: ${error.message}`); }
};
$('apply').onclick = async () => {
  busyPairing = true; updateRole();
  let token = generation;
  try {
    const sender = $('role').value === 'sender';
    const message = parsePairing($('incoming').value, sender ? 'answer' : 'offer');
    if (sender) {
      if (!peer || peer.signalingState !== 'have-local-offer') throw new Error('Create an offer on this iPad first.');
      if (message.game !== $('game').value) throw new Error('Answer belongs to a different game.');
      await peer.setRemoteDescription({ type: message.type, sdp: message.sdp });
      status('Answer accepted. Open the game and watch the phone preview.');
    } else {
      cleanup(); token = generation; $('game').value = message.game; resetMetrics();
      const active = newPeer();
      await active.setRemoteDescription({ type: message.type, sdp: message.sdp });
      await outputDescription(active, await active.createAnswer(), token);
    }
  } catch (error) { if (generation === token) { if ($('role').value === 'receiver') cleanup(); status(error.message); } }
  finally { busyPairing = false; updateRole(); }
};
$('play-preview').onclick = async () => {
  try { await $('preview').play(); $('play-preview').hidden = true; } catch (error) { status(`Cannot play preview: ${error.message}`); }
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
  if (!video.requestVideoFrameCallback) return;
  const tick = (_, metadata) => {
    if (token !== generation) return;
    receivedFrame(metadata.mediaTime);
    frameCallback = video.requestVideoFrameCallback(tick);
  };
  frameCallback = video.requestVideoFrameCallback(tick);
}
setInterval(() => {
  if (!peer || $('role').value !== 'receiver') return;
  const now = Date.now(), video = $('preview');
  if (!video.requestVideoFrameCallback && video.readyState >= 2 && video.currentTime !== lastMediaTime) receivedFrame(video.currentTime);
  if (video.readyState >= 2 && video.videoWidth && context) {
    context.drawImage(video, 0, 0, 64, 36);
    const signature = imageSignature(context.getImageData(0, 0, 64, 36).data);
    dark = signature.dark;
    if (lastHash !== null && signature.hash !== lastHash) { changed++; if (observation && !observation.endedAt) observation.changes++; }
    lastHash = signature.hash;
  }
  const health = frameHealth(lastFrameAt, now, connectedAt ?? now);
  if (observation && !observation.endedAt) {
    observation.maxSamplingGapMs = Math.max(observation.maxSamplingGapMs, now - (previousSampleAt ?? now));
    previousSampleAt = now;
    if (document.hidden) observation.hiddenSamples++;
    else { observation.samples++; if (health !== 'Receiving frames') observation.stalledSamples++; if (dark) observation.darkSamples++; }
    if (now - observation.startedAt >= TEST_DURATION_MS) { observation.endedAt = now; event('observation_complete'); }
  }
  $('metrics').textContent = `${health} · ${video.videoWidth} × ${video.videoHeight} · ${delivered} delivered frames · ${changed} visible changes${dark ? ' · Image appears black' : ''}${observation ? ` · ${Math.floor(((observation.endedAt ?? now) - observation.startedAt) / 1000)} / 900 seconds${observation.endedAt ? ' · Observation ended' : ''}` : ''}`;
}, 500);
$('begin-test').onclick = () => {
  previousSampleAt = Date.now();
  observation = { startedAt: previousSampleAt, endedAt: null, frames: 0, changes: 0, samples: 0, stalledSamples: 0, darkSamples: 0, hiddenSamples: 0, maxSamplingGapMs: 0 };
  $('begin-test').disabled = true; event('observation_started');
};
$('report').onclick = () => download(JSON.stringify({ format: 'proxy-mobile-capture-report-v1', createdAt: new Date().toISOString(), build, role: sessionRole ?? $('role').value, game: sessionGame ?? $('game').value, capability: capability(), connectionState: peer?.connectionState ?? 'closed', frameMeasurement: $('preview').requestVideoFrameCallback ? 'video-frame-callback' : 'media-time-fallback', deliveredFrames: delivered, visibleChanges: changed, observation, userObservation: $('result').value, notes: $('notes').value.slice(0, 4000), events, backgroundCaptureVerified: false, explanation: 'Manual device test evidence only. Review the game preview and observation; frame delivery alone cannot verify game capture.' }, null, 2), 'mobile-capture-report.json');
document.addEventListener('visibilitychange', () => event(document.hidden ? 'page_hidden' : 'page_visible'));
window.addEventListener('pagehide', () => { if (peer) event('page_unloaded'); });
updateRole();
