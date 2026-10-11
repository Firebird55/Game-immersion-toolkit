export const TEST_DURATION_MS = 15 * 60 * 1000;
export const SUPPORTED_GAMES = ['zzz', 'wuwa', 'pragmata', 'cyberpunk', 'witcher3', 'nte', 'honkai3', 'hito'];
const PAIRING_FIELDS = ['sessionId', 'pairingId', 'attempt'];
const PAIRING_ID = /^[A-Za-z0-9_-]{16,64}$/;
function pairingIdentity(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid pairing identity.');
  const present = PAIRING_FIELDS.filter(field => Object.hasOwn(value, field));
  if (!present.length) return {};
  if (present.length !== PAIRING_FIELDS.length
    || typeof value.sessionId !== 'string' || !PAIRING_ID.test(value.sessionId)
    || typeof value.pairingId !== 'string' || !PAIRING_ID.test(value.pairingId)
    || !Number.isSafeInteger(value.attempt) || value.attempt < 1 || value.attempt > 10000) {
    throw new Error('Invalid pairing identity. Create a fresh pairing message on the sending device.');
  }
  return { sessionId: value.sessionId, pairingId: value.pairingId, attempt: value.attempt };
}
export function parsePairing(text, expectedType) {
  if (typeof text !== 'string' || text.length > 128_000) throw new Error('Pairing message is too large.');
  let value;
  try { value = JSON.parse(text); } catch { throw new Error('Paste or open a valid pairing message.'); }
  if (value?.format !== 'proxy-mobile-capture-v1' || value.type !== expectedType
    || typeof value.sdp !== 'string' || !value.sdp.startsWith('v=0') || value.sdp.length > 120_000
    || !SUPPORTED_GAMES.includes(value.game)) throw new Error(`Expected a ${expectedType} from the other device.`);
  return { type: value.type, sdp: value.sdp, game: value.game, ...pairingIdentity(value) };
}
export function pairingMessage(description, game, identity = {}) {
  return JSON.stringify({ format: 'proxy-mobile-capture-v1', type: description.type, sdp: description.sdp, game, ...pairingIdentity(identity) });
}
export function samePairing(a, b) {
  try {
    const left = pairingIdentity(a), right = pairingIdentity(b);
    return PAIRING_FIELDS.every(field => Object.hasOwn(left, field) && Object.hasOwn(right, field)
      && left[field] === right[field]);
  } catch { return false; }
}
export function privateTrackState(track) {
  if (!track) return null;
  const state = {
    kind: ['audio', 'video'].includes(track.kind) ? track.kind : 'unknown',
    enabled: Boolean(track.enabled),
    muted: Boolean(track.muted),
    readyState: ['live', 'ended'].includes(track.readyState) ? track.readyState : 'unknown',
  };
  let settings;
  try { settings = track.getSettings?.(); } catch { settings = null; }
  for (const field of ['width', 'height', 'frameRate']) {
    if (typeof settings?.[field] === 'number' && Number.isFinite(settings[field])) state[field] = settings[field];
  }
  return state;
}
const PRIVATE_RTC_FIELDS = [
  'bytesSent', 'packetsSent', 'framesEncoded', 'framesSent', 'retransmittedPacketsSent',
  'bytesReceived', 'packetsReceived', 'packetsLost', 'framesReceived', 'framesDecoded',
  'framesDropped', 'keyFramesDecoded', 'jitter', 'totalDecodeTime', 'totalFreezesDuration',
  'freezeCount', 'frameWidth', 'frameHeight', 'framesPerSecond',
];
export function privateRtcSample(report, role) {
  const type = role === 'sender' ? 'outbound-rtp' : role === 'receiver' ? 'inbound-rtp' : null;
  if (!type || !report?.values) return [];
  const records = [];
  for (const entry of report.values()) {
    const source = role === 'sender' && entry?.type === 'media-source';
    if ((!source && entry?.type !== type) || (entry.kind ?? entry.mediaType) !== 'video') continue;
    const record = { direction: source ? 'source' : role === 'sender' ? 'outbound' : 'inbound' };
    for (const field of source ? ['width', 'height', 'frames', 'framesPerSecond'] : PRIVATE_RTC_FIELDS) {
      if (typeof entry[field] === 'number' && Number.isFinite(entry[field])) record[field] = entry[field];
    }
    records.push(record);
    if (records.length === 8) break;
  }
  return records;
}
export function frameHealth(lastFrameAt, now, startedAt) {
  if (lastFrameAt === null) return now - startedAt > 5000 ? 'No frames received' : 'Waiting for frames';
  return now - lastFrameAt > 5000 ? 'Frame delivery stalled' : 'Receiving frames';
}
export function imageSignature(pixels) {
  let hash = 2166136261, brightness = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    hash = Math.imul(hash ^ pixels[i], 16777619);
    hash = Math.imul(hash ^ pixels[i + 1], 16777619);
    hash = Math.imul(hash ^ pixels[i + 2], 16777619);
    brightness += pixels[i] + pixels[i + 1] + pixels[i + 2];
  }
  return { hash: hash >>> 0, dark: brightness / (pixels.length / 4 * 3) < 3 };
}
