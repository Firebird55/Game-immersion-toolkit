export const ROOM_LIFETIME = 4 * 3600000;
export const validRoom = value => /^[a-f0-9]{32}$/.test(value);
export function registration(value) {
  if (!value || Object.keys(value).sort().join() !== 'receiverHash,senderHash' || ![value.senderHash,value.receiverHash].every(v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)) || value.senderHash === value.receiverHash) throw Error('Invalid registration');
  return {senderHash:value.senderHash, receiverHash:value.receiverHash};
}
export function packet(text) {
  if (typeof text !== 'string' || text.length > 180500) throw Error('Invalid packet');
  const value = JSON.parse(text);
  if (value?.kind !== 'signal' || Object.keys(value).sort().join() !== 'data,iv,kind' || typeof value.iv !== 'string' || !/^[A-Za-z0-9_-]{16}$/.test(value.iv) || typeof value.data !== 'string' || !/^[A-Za-z0-9_-]{22,170688}$/.test(value.data)) throw Error('Invalid packet');
  return {kind:'signal', iv:value.iv, data:value.data};
}
export async function smallBody(request) {
  if (!request.body) throw Error('Missing body');
  const reader = request.body.getReader(); const parts = []; let length = 0;
  try { for (;;) { const {done,value} = await reader.read(); if (done) break; length += value.length; if (length > 512) throw Error('Body too large'); parts.push(value); } }
  finally { await reader.cancel(); }
  const bytes = new Uint8Array(length); let offset = 0; for (const part of parts) { bytes.set(part,offset); offset += part.length; }
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
