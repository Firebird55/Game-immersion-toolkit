export const SUPPORTED_GAMES = ['zzz', 'wuwa', 'pragmata', 'cyberpunk', 'witcher3', 'nte', 'beyond', 'heavyrain', 'starrail', 'genshin', 'endfield', 'riseofthetombraider', 'shadowofthetombraider'];
const PAIRING_FIELDS = ['sessionId', 'pairingId', 'attempt'];
const PAIRING_ID = /^[A-Za-z0-9_-]{16,64}$/;
export function parseRelay(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== 'endpoint,expires,room,secret'
    || typeof value.endpoint !== 'string' || value.endpoint.length > 256 || !/^[a-f0-9]{32}$/.test(value.room)
    || typeof value.secret !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(value.secret)
    || !Number.isSafeInteger(value.expires) || value.expires < 1) throw Error('Invalid recovery session.');
  const url = new URL(value.endpoint);
  if (url.origin !== value.endpoint || url.username || url.password || url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1','localhost'].includes(url.hostname))) throw Error('Invalid recovery service address.');
  return {endpoint:value.endpoint, room:value.room, secret:value.secret, expires:value.expires};
}
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
  const identity = pairingIdentity(value);
  if (Object.hasOwn(value,'relay') && !identity.sessionId) throw Error('Recovery requires a session identity.');
  if(value.mode!==undefined&&value.mode!=='transcript')throw Error('Unsupported pairing mode.');
  if(value.mode==='transcript'&&!identity.sessionId)throw Error('Transcript pairing requires a session.');
  return { type: value.type, sdp: value.sdp, game: value.game, ...(value.mode?{mode:value.mode}:{}), ...identity, ...(Object.hasOwn(value,'relay') ? {relay:parseRelay(value.relay)} : {}) };
}
export function pairingMessage(description, game, identity = {}) {
  const parsedIdentity = pairingIdentity(identity);
  if (Object.hasOwn(identity,'relay') && !parsedIdentity.sessionId) throw Error('Recovery requires a session identity.');
  return JSON.stringify({ format: 'proxy-mobile-capture-v1', type: description.type, sdp: description.sdp, game, ...(identity.mode==='transcript'?{mode:'transcript'}:{}), ...parsedIdentity, ...(Object.hasOwn(identity,'relay') ? {relay:parseRelay(identity.relay)} : {}) });
}
export function samePairing(a, b) {
  try {
    const left = pairingIdentity(a), right = pairingIdentity(b);
    return PAIRING_FIELDS.every(field => Object.hasOwn(left, field) && Object.hasOwn(right, field)
      && left[field] === right[field]);
  } catch { return false; }
}
