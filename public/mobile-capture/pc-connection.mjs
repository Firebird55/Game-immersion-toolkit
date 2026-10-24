import {CHANNEL,createTranscriptChannel} from './transcript-channel.mjs';
import {createPCProvider} from './pc-provider.mjs';
import { parsePairing, pairingMessage, samePairing } from './core.mjs';
import {createRelay, RelayClient} from './relay.mjs';
const $ = id => document.getElementById(id);
let transcript=null, provider=null, unsubscribe=null;
const pcSender=()=>new URLSearchParams(location.search).get('pc')==='1'&&['localhost','127.0.0.1'].includes(location.hostname)&&$('role').value==='sender';
const transcriptMode=()=>pcSender()||$('source')?.value==='pc';
let peer = null, generation = 0;
let attemptStartedAt=null;
let events=[];
let pendingCapture=false,busyPairing=false;
let sessionGame = null, sessionRole = null;
let identity=null,recoveryAttempts=0;
let relay = null, relayEndpoint = '', relayAbort = null, lastAutoAttempt = 0;
const relayConfig = fetch('./recovery-config.json', {cache:'no-store'}).then(r => r.ok ? r.json() : {}).then(config => {
  if (typeof config.endpoint === 'string' && config.endpoint && Array.isArray(config.origins) && config.origins.includes(location.origin)) {
    const url = new URL(config.endpoint);
    if (url.origin === config.endpoint && (url.protocol === 'https:' || url.protocol === 'http:' && ['127.0.0.1','localhost'].includes(location.hostname) && ['127.0.0.1','localhost'].includes(url.hostname))) relayEndpoint = config.endpoint;
  }
  $('auto-recovery').disabled = !relayEndpoint;
  $('auto-recovery').checked = Boolean(relayEndpoint);
  $('relay-status').textContent = relayEndpoint ? 'Automatic recovery available. Scan the sender’s QR once; the answer returns automatically. Recovery sessions last four hours.' : 'Automatic recovery is not configured on this build. Returning resumes live playback; a failed connection needs fresh direct pairing.';
}).catch(() => { $('relay-status').textContent = 'Recovery service configuration unavailable. Direct QR pairing is available.'; });
function event(kind, details = {}) { events.push({ at: new Date().toISOString(), kind, ...details }); events = events.slice(-300); }
function status(message) { $('status').textContent = message; }
const liveCapture=()=>Boolean(identity);
function updateDiagnostics(){$('diagnostics').textContent=`PC connection: ${peer?.connectionState??'closed'} · ${recoveryAttempts} reconnect attempts`;}
function updateRole(){
 const sender=pcSender(),active=Boolean(peer||identity||pendingCapture||busyPairing);
 if(typeof RTCPeerConnection!=='function')status('PC transcript sharing is unavailable in this browser. Use VDO.Ninja on Play.');
 $('start').hidden=!sender;$('start').disabled=active||!isSecureContext||typeof RTCPeerConnection!=='function';
 $('reconnect').hidden=!sender;$('reconnect').disabled=!identity||busyPairing;
 $('apply').disabled=busyPairing||!isSecureContext||typeof RTCPeerConnection!=='function';
 $('stop').disabled=!active;$('auto-recovery').disabled=!relayEndpoint||active;
 $('game').disabled=active;$('role').disabled=active;$('source').disabled=active;$('reload-build').disabled=active;
 window.dispatchEvent(new CustomEvent('mobile-stream',{detail:{transport:'pc',generation,game:sessionGame??$('game').value,role:sessionRole??$('role').value,state:peer?.connectionState??'closed',live:peer?.connectionState==='connected'}}));
 updateDiagnostics();
}
function detachConnection(keepCapture = false) {
  // Invalidate old callbacks before closing their peer or received tracks.
  generation++;
  transcript?.close();transcript=null;unsubscribe?.();unsubscribe=null;provider=null;
  if (peer) {
    peer.onconnectionstatechange = null; peer.oniceconnectionstatechange = null;
    peer.onicegatheringstatechange = null; peer.onsignalingstatechange = null; peer.ontrack = null;
    peer.close();
  }
  peer = null;
  $('outgoing').value = ''; $('copy').disabled = true; $('save-pairing').disabled = true;
  window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:''}}));
  $('incoming').value = '';
  attemptStartedAt=Date.now();
  return generation;
}
function cleanup(message = 'Stopped.') {
  relayAbort?.abort(); relayAbort = null; relay?.close(); relay = null;
  detachConnection(); pendingCapture = false; busyPairing = false;
  identity = null;
  $('stop').disabled = true;
  event('stopped'); status(message); updateRole();
}
function current(active, token) { return active === peer && token === generation; }
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
    status(`Connection: ${active.connectionState}${interrupted ? relay ? '. Automatic recovery will retry while both devices are online and sharing is active.' : sessionRole === 'sender' ? '. Tap Reconnect & create new offer, then exchange the new messages.' : '. Ask the sending device for a fresh reconnect offer, then send its new answer back.' : ''}`);
    updateRole();
    if (interrupted) void automaticRecovery();
  };
  for (const [handler, kind, state] of [['oniceconnectionstatechange', 'ice_connection', 'iceConnectionState'], ['onicegatheringstatechange', 'ice_gathering', 'iceGatheringState'], ['onsignalingstatechange', 'signaling', 'signalingState']]) {
    active[handler] = () => { if (current(active, token)) { event(kind, { state: active[state] }); updateDiagnostics(); } };
  }
  if(transcriptMode()){
    const attach=channel=>{
      if(!current(active,token)||channel.label!==CHANNEL){channel.close();return;}
      transcript=createTranscriptChannel(channel,{session:identity.sessionId+':'+identity.pairingId,provider,onState:status,onRows:(rows,message)=>window.dispatchEvent(new CustomEvent('pc-transcript',{detail:{rows,message}})),onCapabilities:capabilities=>window.dispatchEvent(new CustomEvent('pc-capabilities',{detail:capabilities}))});
      if(provider)unsubscribe=provider.subscribe(rows=>{void transcript?.update(rows).catch(()=>status('Transcript update interrupted. Reconnect to refresh history.'));});
    };
    if(pcSender()){provider=createPCProvider(sessionGame);attach(active.createDataChannel(CHANNEL,{ordered:true}));}else active.ondatachannel=e=>attach(e.channel);
  }
  $('stop').disabled = false; updateRole();
  return active;
}
function resetMetrics() {
  attemptStartedAt=null;events=[];
  identity=null;recoveryAttempts=0;
  lastAutoAttempt = 0;
  sessionGame = $('game').value; sessionRole = $('role').value;
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
  $('outgoing').value = pairingMessage(active.localDescription, sessionGame, {...identity,mode:'transcript'});
  window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:$('outgoing').value}}));
  $('copy').disabled = false; $('save-pairing').disabled = false;
  status('Pairing message ready. Send it to the other device.');
  if (relay && await relay.send({kind:'pairing',message:$('outgoing').value}) && current(active, token)) status(sessionRole === 'receiver' ? 'Answer sent automatically. Keep this page open to receive the '+'transcript.' : 'Offer ready. Scan this QR on the receiving device once; its answer returns automatically.');
}
function connectRelay(descriptor, role) {
  relay?.close();
  const client = new RelayClient(descriptor, role, {
    onState(state) {
      if (relay !== client) return;
      event('recovery_service_' + state);
      $('relay-status').textContent = state === 'ready' ? 'Automatic recovery connected. Shared content travels directly between your devices.' : state === 'expired' ? 'Recovery session expired after four hours. Stop and pair again.' : ['rejected','message_rejected'].includes(state) ? 'Recovery session rejected. Stop and pair again, or use direct QR pairing.' : 'Recovery service reconnecting. Your library and transcript are kept open.';
      if (state === 'ready') { const message = $('outgoing').value; if (message) void client.send({kind:'pairing',message}); void automaticRecovery(); }
    },
    onPartner(present) { if (relay === client && present) void automaticRecovery(); },
    async onMessage(value) {
      if (relay !== client || !identity) return;
      if (value.kind === 'recover' && value.sessionId === identity.sessionId && role === 'sender') { await automaticRecovery(true); return; }
      if (value.kind !== 'pairing' || busyPairing || pendingCapture) return;
      const message = parsePairing(value.message, role === 'sender' ? 'answer' : 'offer');
      if (message.sessionId !== identity.sessionId || message.game !== sessionGame || JSON.stringify(message.relay) !== JSON.stringify(identity.relay)) return;
      if (role === 'receiver' && message.attempt <= identity.attempt || role === 'sender' && peer?.signalingState !== 'have-local-offer') return;
      await applyMessage(value.message);
    }
  });
  relay = client;
}
async function automaticRecovery(force = false) {
  if (!relay?.ready || !identity || document.hidden || !navigator.onLine || pendingCapture || busyPairing || Date.now() - lastAutoAttempt < 8000) return;
  const interrupted = !peer || ['failed','disconnected','closed'].includes(peer.connectionState);

  const timedOut = peer?.connectionState !== 'connected' && attemptStartedAt && Date.now() - attemptStartedAt > 20000;
  if (!force && !interrupted && !timedOut) return;
  lastAutoAttempt = Date.now(); event('automatic_recovery_requested');
  if (sessionRole === 'sender') { if (liveCapture()) await reconnectSender(true); }
  else { await relay.send({kind:'recover',sessionId:identity.sessionId}); status('Requesting a fresh connection automatically…'); }
}
function returnToStreaming() {
  if (document.hidden) return;
  relay?.wake(true); void automaticRecovery();
}
async function createSenderOffer(active, token) {
  const offer = await active.createOffer();
  if (!current(active, token)) return;
  await outputDescription(active, offer, token);
}
$('start').onclick = async () => {
  const token = ++generation;
  pendingCapture = true; updateRole(); $('start').disabled = true; $('stop').disabled = false;
  try {
    if(!pcSender())throw Error("Open the desktop companion to share its transcript.");
    if (generation !== token)return;
    pendingCapture = false; busyPairing = true;
    resetMetrics();
    identity = { sessionId: crypto.randomUUID(), pairingId: crypto.randomUUID(), attempt: 1 };
    await relayConfig;
    if (generation !== token) return;
    if ($('auto-recovery').checked && relayEndpoint) {
      relayAbort = new AbortController();
      const descriptor = await createRelay(relayEndpoint, relayAbort.signal);
      if (generation !== token) return;
      identity.relay = descriptor; connectRelay(descriptor,'sender');
    }
    const active = newPeer();
    await createSenderOffer(active, token);
    if (current(active, token)) event('transcript_share_started');
  } catch (error) { if (generation === token) cleanup(`Cannot start ${pcSender()?'sharing':'capture'}: ${error.message}`); }
  finally { if (generation === token) { pendingCapture = false; busyPairing = false; updateRole(); } }
};
async function reconnectSender(automatic = false) {
  if (pendingCapture || busyPairing || sessionRole !== 'sender' || !liveCapture()) return;
  let token = detachConnection(true);
  busyPairing = true; recoveryAttempts++;
  identity = { ...identity, pairingId: crypto.randomUUID(), attempt: identity.attempt + 1 };
  event('reconnect_requested', { attempt: identity.attempt, automatic });
  status('Preparing a fresh sharing offer…'); updateRole();
  try { await createSenderOffer(newPeer(), token); }
  catch {
    if (generation === token) {
      token = detachConnection(true);
      event('connection_attempt_failed', { attempt: identity?.attempt ?? null });
      status('Reconnect could not prepare an offer. Tap Reconnect to try again.');
    }
  }
  finally { if (generation === token) { busyPairing = false; updateRole(); } }
}
$('reconnect').onclick = () => reconnectSender();
async function applyMessage(text) {
  if(!transcriptMode()){status('Choose Paired PC in Settings first.');return;}
  busyPairing = true; updateRole();
  let token = generation;
  let replacingReceiver = false;
  try {
    const sender = $('role').value === 'sender';
    const message = parsePairing(text, sender ? 'answer' : 'offer');
    const hasTranscript=message.mode==='transcript';
    if(!hasTranscript)throw Error('Screen pairing has been removed. Use a PC transcript offer, or VDO.Ninja on Play.');
    if (message.relay && (message.relay.endpoint !== relayEndpoint || message.relay.expires <= Date.now() || message.relay.expires > Date.now() + 4 * 3600000 + 60000)) throw Error('This recovery session is expired or uses a service not configured on this page. Reload both devices or use direct pairing.');
    if (sender) {
      if (!peer || peer.signalingState !== 'have-local-offer') throw new Error('Create an offer on the sharing device first.');
      if (message.game !== $('game').value) throw new Error('Answer belongs to a different game.');
      if (!samePairing(message, identity)) throw new Error('This answer is for an older or different offer. Use the answer to the latest offer, or stop and pair again.');
      if (JSON.stringify(message.relay) !== JSON.stringify(identity?.relay)) throw Error('Answer belongs to a different recovery session.');
      const active = peer;
      await active.setRemoteDescription({ type: message.type, sdp: message.sdp });
      if (current(active, token)) status('Answer accepted. Keep the companion and this sharing page running.');
    } else {
      const continuing = identity && message.sessionId === identity.sessionId;
      if (identity || peer) {
        if (message.game !== sessionGame) throw new Error('Offer belongs to a different game. Stop sharing before changing games.');
        if (!continuing) throw new Error('Offer belongs to a different sharing session. Stop sharing before accepting it.');
        if (message.attempt <= identity.attempt || message.pairingId === identity.pairingId) throw new Error('This offer was already accepted or is older. Use the latest reconnect offer from the sending device.');
        if (JSON.stringify(message.relay) !== JSON.stringify(identity.relay)) throw Error('Offer belongs to a different recovery session.');
      }
      token = detachConnection(); replacingReceiver = true;
      if (!continuing) { $('game').value = message.game; resetMetrics(); }
      else { recoveryAttempts++; event('reconnect_offer_accepted', { attempt: message.attempt }); }
      identity = message.sessionId ? { sessionId: message.sessionId, pairingId: message.pairingId, attempt: message.attempt, ...(message.relay ? {relay:message.relay} : {}) } : null;
      if (message.relay && !relay) connectRelay(message.relay,'receiver');
      const active = newPeer();
      await active.setRemoteDescription({ type: message.type, sdp: message.sdp });
      if (!current(active, token)) return;
      const answer = await active.createAnswer();
      if (!current(active, token)) return;
      await outputDescription(active, answer, token);
    }
  } catch (error) {
    if (generation === token) {
      if (replacingReceiver) { token = detachConnection(); event('pairing_failed'); status('Pairing could not complete. Ask the sending device for a fresh reconnect offer and try again.'); }
      else status(error.message);
    }
  }
  finally { if (generation === token) { busyPairing = false; updateRole(); } }
}
$('apply').onclick = () => applyMessage($('incoming').value);
$('stop').onclick = () => cleanup();
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
document.addEventListener('visibilitychange', () => { event(document.hidden ? 'page_hidden' : 'page_visible'); updateDiagnostics(); if (!document.hidden) returnToStreaming(); });
for (const kind of ['freeze', 'resume']) document.addEventListener(kind, () => { event(kind); if (kind === 'resume') returnToStreaming(); });
for (const kind of ['online', 'offline']) window.addEventListener(kind, () => { event(kind); updateDiagnostics(); if (kind === 'online') returnToStreaming(); });
for (const kind of ['pagehide', 'pageshow']) window.addEventListener(kind, e => { event(kind, { persisted: e.persisted }); if (kind === 'pageshow') returnToStreaming(); });
setInterval(() => { if (!document.hidden) { void automaticRecovery(); } }, 5000);
updateRole();

export const pcConnection={stop:cleanup,get active(){return Boolean(peer||identity||pendingCapture);},older:before=>{if(!transcript)throw Error('Pair with the PC first.');return transcript.page(before);},audio:row=>{if(!transcript)throw Error('Pair with the PC first.');return transcript.audio(row.id,row);}};
window.addEventListener('pagehide',()=>cleanup());
