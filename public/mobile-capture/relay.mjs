import {parseRelay} from './core.mjs';

const encoder = new TextEncoder();
export const encode64 = bytes => btoa(Array.from(new Uint8Array(bytes), b => String.fromCharCode(b)).join('')).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
export function decode64(text) {
  if (typeof text !== 'string' || !/^[A-Za-z0-9_-]+$/.test(text) || text.length > 180000) throw Error('Invalid encrypted message.');
  return Uint8Array.from(atob(text.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
}
export const digest = async text => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(text))), b => b.toString(16).padStart(2, '0')).join('');
export async function proof(secret, role) {
  const key = await crypto.subtle.importKey('raw', decode64(secret), {name:'HMAC', hash:'SHA-256'}, false, ['sign']);
  return encode64(await crypto.subtle.sign('HMAC', key, encoder.encode('proxy-mobile-relay-v1:' + role)));
}
const aad = (room, role) => encoder.encode('proxy-mobile-relay-v1:' + room + ':' + role);
export async function seal(secret, room, role, value) {
  const text = encoder.encode(JSON.stringify(value));
  if (text.length > 128000) throw Error('Connection message too large.');
  const key = await crypto.subtle.importKey('raw', decode64(secret), 'AES-GCM', false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  return {iv:encode64(iv), data:encode64(await crypto.subtle.encrypt({name:'AES-GCM', iv, additionalData:aad(room, role)}, key, text))};
}
export async function unseal(secret, room, role, packet) {
  const iv = decode64(packet.iv), data = decode64(packet.data);
  if (iv.length !== 12 || data.length > 128016) throw Error('Invalid encrypted message.');
  const key = await crypto.subtle.importKey('raw', decode64(secret), 'AES-GCM', false, ['decrypt']);
  return JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(await crypto.subtle.decrypt({name:'AES-GCM', iv, additionalData:aad(room, role)}, key, data)));
}
export async function createRelay(endpoint, signal) {
  const room = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2,'0')).join('');
  const secret = encode64(crypto.getRandomValues(new Uint8Array(32)));
  const descriptor = parseRelay({endpoint, room, secret, expires:Date.now() + 4 * 3600000});
  const [senderHash, receiverHash] = await Promise.all(['sender','receiver'].map(async role => digest(await proof(secret, role))));
  const response = await fetch(endpoint + '/v1/rooms/' + room, {method:'POST', mode:'cors', credentials:'omit', cache:'no-store', signal,
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({senderHash, receiverHash})});
  if (!response.ok) throw Error('Automatic recovery service unavailable. Disable automatic recovery to use direct QR pairing.');
  const result = await response.json();
  return parseRelay({...descriptor, expires:result.expires});
}

// Session secrets stay in memory. No SDP, room keys or socket URLs enter reports.
export class RelayClient {
  constructor(descriptor, role, {onMessage, onState, onPartner}) {
    this.descriptor = parseRelay(descriptor); this.role = role;
    if (!['sender','receiver'].includes(role)) throw Error('Invalid relay role.');
    this.onMessage = onMessage; this.onState = onState; this.onPartner = onPartner;
    this.socket = null; this.ready = false; this.stopped = false; this.timer = null; this.healthTimer = null;
    this.failures = 0; this.seen = new Set(); this.chain = Promise.resolve(); this.lastPong = 0;
    queueMicrotask(() => this.wake());
  }
  state(value) { this.onState?.(value); }
  wake(force = false) {
    if (this.stopped) return;
    if (Date.now() >= this.descriptor.expires) { this.close(); this.state('expired'); return; }
    if (!force && this.ready && this.socket?.readyState === 1 && Date.now() - this.lastPong < 45000) { this.socket.send('ping'); return; }
    if (this.socket?.readyState === 0) return;
    if (this.socket) { this.socket.onclose = null; this.socket.close(); }
    clearTimeout(this.timer); this.ready = false; this.state('connecting');
    const url = new URL(this.descriptor.endpoint + '/v1/rooms/' + this.descriptor.room);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(url); this.socket = socket;
    socket.onopen = async () => {
      const token = await proof(this.descriptor.secret, this.role);
      if (!this.stopped && this.socket === socket && socket.readyState === 1) socket.send(JSON.stringify({kind:'auth', role:this.role, proof:token}));
    };
    socket.onmessage = event => {
      this.chain = this.chain.then(async () => {
        if (this.stopped || this.socket !== socket) return;
        if (event.data === 'pong') { this.lastPong = Date.now(); return; }
        if (typeof event.data !== 'string' || event.data.length > 180500) throw Error('Invalid relay packet.');
        const value = JSON.parse(event.data);
        if (value.kind === 'ready') {
          this.ready = true; this.failures = 0; this.lastPong = Date.now(); this.state('ready');
          this.onPartner?.(Boolean(value.partner)); return;
        }
        if (!this.ready) return;
        if (value.kind === 'partner') { this.onPartner?.(Boolean(value.present)); return; }
        if (value.kind !== 'signal' || value.from !== (this.role === 'sender' ? 'receiver' : 'sender') || this.seen.has(value.iv)) return;
        const message = await unseal(this.descriptor.secret, this.descriptor.room, value.from, value);
        if (this.stopped || this.socket !== socket) return;
        this.seen.add(value.iv);
        // A room has bounded lifetime; discard old nonces without retaining SDP.
        if (this.seen.size > 512) this.seen.delete(this.seen.values().next().value);
        await this.onMessage?.(message);
      }).catch(() => { if (!this.stopped && this.socket === socket) this.state('message_rejected'); });
    };
    socket.onerror = () => {};
    socket.onclose = event => {
      if (this.stopped || this.socket !== socket) return;
      this.ready = false; clearTimeout(this.healthTimer);
      if ([4001,4003,4009].includes(event.code)) { this.close(); this.state(event.code === 4001 ? 'expired' : 'rejected'); return; }
      this.state('offline');
      this.timer = setTimeout(() => this.wake(), Math.min(30000, 1000 * 2 ** Math.min(this.failures++, 5)));
    };
    clearTimeout(this.healthTimer);
    const check = () => {
      if (this.stopped || this.socket !== socket) return;
      if (!this.ready || Date.now() - this.lastPong > 45000) { socket.close(); return; }
      socket.send('ping'); this.healthTimer = setTimeout(check, 20000);
    };
    this.healthTimer = setTimeout(check, 20000);
  }
  async send(message) {
    const socket = this.socket;
    if (!this.ready || socket?.readyState !== 1 || this.stopped) return false;
    try {
      const packet = await seal(this.descriptor.secret, this.descriptor.room, this.role, message);
      if (this.socket !== socket || !this.ready || this.stopped || socket.readyState !== 1) return false;
      socket.send(JSON.stringify({kind:'signal', ...packet})); return true;
    } catch { return false; }
  }
  close() {
    this.stopped = true; this.ready = false; clearTimeout(this.timer); clearTimeout(this.healthTimer);
    this.socket?.close(); this.socket = null; this.seen.clear();
  }
}
