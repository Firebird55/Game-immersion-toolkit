import {DurableObject} from 'cloudflare:workers';
import {ROOM_LIFETIME,validRoom,registration,packet,smallBody} from './protocol.mjs';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health') return Response.json({format:'proxy-mobile-relay-v1', status:'ready'});
    const origin = request.headers.get('Origin');
    if (!origin || !env.ALLOWED_ORIGINS.split(',').includes(origin)) return new Response('Origin not allowed', {status:403});
    const headers = {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Cache-Control':'no-store','Access-Control-Allow-Methods':'POST, GET, OPTIONS','Access-Control-Allow-Headers':'Content-Type'};
    const match = /^\/v1\/rooms\/([a-f0-9]{32})$/.exec(url.pathname);
    if (!match || url.search || !validRoom(match[1])) return new Response('Not found',{status:404,headers});
    if (request.method === 'OPTIONS') return new Response(null,{status:204,headers});
    if (request.method !== 'POST' && !(request.method === 'GET' && request.headers.get('Upgrade')?.toLowerCase() === 'websocket')) return new Response('Method not allowed',{status:405,headers});
    // Admission is separate from room identity so guessed random rooms cannot
    // evade it. IPs stay in Cloudflare's rate limiter; they are not logged/stored.
    const {success} = await env.ADMISSION.limit({key:request.headers.get('CF-Connecting-IP') ?? 'local'});
    if (!success) return new Response('Try again later',{status:429,headers});
    try {
      const response = await env.ROOMS.getByName(match[1]).fetch(request);
      if (response.status === 101) return response;
      const result = new Response(response.body,response); for (const [name,value] of Object.entries(headers)) result.headers.set(name,value);
      return result;
    } catch {
      console.error(JSON.stringify({event:'pairing_service_failure'}));
      return new Response('Service unavailable',{status:503,headers});
    }
  }
};

export class PairingRoom extends DurableObject {
  async fetch(request) {
    const saved = await this.ctx.storage.get('room');
    if (request.method === 'POST') {
      if (saved) return new Response('Room already exists',{status:409});
      let hashes; try { hashes = registration(await smallBody(request)); } catch { return new Response('Invalid registration',{status:400}); }
      const room = {...hashes, expires:Date.now() + ROOM_LIFETIME};
      const created = await this.ctx.storage.transaction(async tx => {
        if (await tx.get('room')) return false;
        await tx.put('room',room); await tx.setAlarm(room.expires); return true;
      });
      if (!created) return new Response('Room already exists',{status:409});
      return Response.json({expires:room.expires},{status:201});
    }
    if (!saved || saved.expires <= Date.now()) return new Response('Room expired',{status:410});
    const sockets = this.ctx.getWebSockets();
    if (sockets.filter(ws => !ws.deserializeAttachment()?.role).length >= 2) return new Response('Try again later',{status:429});
    const [client,server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({joined:Date.now(), window:Date.now(), count:0});
    this.ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping','pong'));
    // One alarm expires abandoned unauthenticated sockets, then returns to TTL.
    await this.ctx.storage.setAlarm(Math.min(saved.expires,Date.now()+10000));
    return new Response(null,{status:101,webSocket:client});
  }
  async webSocketMessage(ws, text) {
    const room = await this.ctx.storage.get('room');
    if (!room || room.expires <= Date.now()) { ws.close(4001,'Room expired'); return; }
    const attached = ws.deserializeAttachment();
    if (typeof text !== 'string' || text.length > 180500 || !attached) { ws.close(4003,'Invalid message'); return; }
    if (Date.now() - attached.window >= 60000) { attached.window = Date.now(); attached.count = 0; }
    if (++attached.count > 30) { ws.close(4008,'Try again later'); return; }
    ws.serializeAttachment(attached);
    if (!attached.role) {
      let value; try { value = JSON.parse(text); } catch { ws.close(4003,'Invalid authentication'); return; }
      if (text.length > 256 || value.kind !== 'auth' || !['sender','receiver'].includes(value.role) || typeof value.proof !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(value.proof)) { ws.close(4003,'Invalid authentication'); return; }
      const provided = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value.proof));
      const expected = Uint8Array.from(room[value.role+'Hash'].match(/../g),v=>parseInt(v,16));
      if (!crypto.subtle.timingSafeEqual(provided,expected)) { ws.close(4003,'Invalid authentication'); return; }
      for (const old of this.ctx.getWebSockets()) if (old !== ws && old.deserializeAttachment()?.role === value.role) old.close(4009,'Session replaced');
      attached.role = value.role; ws.serializeAttachment(attached);
      const partners = this.partners(ws);
      ws.send(JSON.stringify({kind:'ready',partner:partners.length > 0}));
      for (const partner of partners) partner.send(JSON.stringify({kind:'partner',present:true}));
      return;
    }
    try {
      const value = packet(text);
      for (const partner of this.partners(ws)) partner.send(JSON.stringify({...value,from:attached.role}));
    } catch { ws.close(4003,'Invalid message'); }
  }
  partners(ws) { const role = ws.deserializeAttachment()?.role; return this.ctx.getWebSockets().filter(other => other !== ws && other.readyState === 1 && other.deserializeAttachment()?.role && other.deserializeAttachment().role !== role); }
  webSocketClose(ws) {
    const role = ws.deserializeAttachment()?.role;
    if (this.ctx.getWebSockets().some(other => other !== ws && other.readyState === 1 && other.deserializeAttachment()?.role === role)) return;
    for (const partner of this.partners(ws)) partner.send(JSON.stringify({kind:'partner',present:false}));
  }
  webSocketError(ws) { ws.close(1011,'Reconnect'); }
  async alarm() {
    const room = await this.ctx.storage.get('room');
    if (!room || room.expires <= Date.now()) {
      for (const ws of this.ctx.getWebSockets()) ws.close(4001,'Room expired');
      await this.ctx.storage.deleteAll(); return;
    }
    let next = room.expires;
    for (const ws of this.ctx.getWebSockets()) { const meta = ws.deserializeAttachment(); if (!meta?.role) { if (Date.now()-meta.joined >= 10000) ws.close(4003,'Authentication timeout'); else next = Math.min(next,meta.joined+10000); } }
    await this.ctx.storage.setAlarm(next);
  }
}
