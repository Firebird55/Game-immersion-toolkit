export const TEST_DURATION_MS = 15 * 60 * 1000;
export function parsePairing(text, expectedType) {
  if (typeof text !== 'string' || text.length > 128_000) throw new Error('Pairing message is too large.');
  let value;
  try { value = JSON.parse(text); } catch { throw new Error('Paste or open a valid pairing message.'); }
  if (value?.format !== 'proxy-mobile-capture-v1' || value.type !== expectedType
    || typeof value.sdp !== 'string' || !value.sdp.startsWith('v=0') || value.sdp.length > 120_000
    || !['zzz', 'wuwa'].includes(value.game)) throw new Error(`Expected a ${expectedType} from the other device.`);
  return { type: value.type, sdp: value.sdp, game: value.game };
}
export function pairingMessage(description, game) {
  return JSON.stringify({ format: 'proxy-mobile-capture-v1', type: description.type, sdp: description.sdp, game });
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
