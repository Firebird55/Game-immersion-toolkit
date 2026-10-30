import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import { parsePairing, pairingMessage, samePairing } from '../public/mobile-capture/core.mjs';

test('local capture server loads native source modules without opening private routes or extra frame origins', { timeout: 15000 }, async t => {
  const reservation = createServer();
  reservation.listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const child = spawn(process.execPath, [fileURLToPath(new URL('../scripts/serve-mobile-capture.mjs', import.meta.url)), '--local', '--port', String(port)], { stdio: ['ignore', 'pipe', 'pipe'] });
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) {
      const stopped = once(child, 'exit');
      child.kill();
      await stopped;
    }
  });
  let errors = '';
  child.stderr.on('data', data => { errors += data; });
  await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', code => reject(new Error(`Capture server exited (${code}): ${errors}`)));
    child.stdout.on('data', data => { if (String(data).includes('Mobile capture test:')) resolve(); });
  });
  const get = (path, options = {}) => fetch(`http://127.0.0.1:${port}${path}`, { ...options, signal: AbortSignal.timeout(5000) });
  const page = await get('/');
  assert.equal(page.status, 200);
  const directives = new Map(page.headers.get('content-security-policy').split(';').map(value => value.trim().split(/\s+/)).filter(parts => parts[0]).map(([name, ...values]) => [name, values]));
  assert.deepEqual(directives.get('frame-src'), ['https://vdo.ninja']);
  assert.deepEqual(directives.get('script-src'), ["'self'", "'wasm-unsafe-eval'"]);
  assert.ok(!directives.get('connect-src').some(value => /vdo|meshcast|\*/.test(value)));
  await page.text();
  for (const name of ['frame-source.mjs', 'vdo-source.mjs', 'receiver-source.mjs']) {
    const response = await get('/' + name);
    assert.equal(response.status, 200, name);
    assert.match(response.headers.get('content-type'), /javascript/);
    assert.match(await response.text(), /export /);
  }
  for (const path of ['/package.json', '/.git/config', '/output/checks/private.json']) {
    const response = await get(path);
    assert.equal(response.status, 404, path);
    await response.text();
  }
  const write = await get('/frame-source.mjs', { method: 'POST' });
  assert.equal(write.status, 404);
  await write.text();
});

test('manual pairing rejects malformed, oversized and wrong-role descriptions', () => {
  const offer = pairingMessage({ type: 'offer', sdp: 'v=0\r\nfixture' }, 'zzz');
  assert.deepEqual(parsePairing(offer, 'offer'), { type: 'offer', sdp: 'v=0\r\nfixture', game: 'zzz' });
  assert.throws(() => parsePairing(offer, 'answer'), /Expected a answer/);
  assert.throws(() => parsePairing('{', 'offer'), /valid pairing/);
  assert.throws(() => parsePairing('x'.repeat(128001), 'offer'), /too large/);
  assert.throws(() => parsePairing(pairingMessage({ type: 'offer', sdp: 'bad' }, 'zzz'), 'offer'));
  assert.throws(() => parsePairing(pairingMessage({ type: 'offer', sdp: 'v=0' }, 'other'), 'offer'));
});
const identity = { sessionId: 'session_1234567890', pairingId: 'pairing-1234567890', attempt: 1 };
const description = { type: 'offer', sdp: 'v=0\r\nfixture' };

test('supported games pair for capture and transcript reading with the existing protocol',()=>{
 for(const game of ['beyond','heavyrain','starrail','genshin','endfield'])for(const mode of [undefined,'transcript']){
  const value=parsePairing(pairingMessage(description,game,{...identity,...(mode?{mode}:{})}),'offer');
  assert.equal(value.game,game);assert.equal(value.mode,mode);
 }
 assert.throws(()=>parsePairing(pairingMessage(description,'hito',identity),'offer'));
});
test('reconnect metadata round trips without changing the legacy pairing format', () => {
  const message = pairingMessage(description, 'zzz', identity);
  assert.equal(JSON.parse(message).format, 'proxy-mobile-capture-v1');
  assert.deepEqual(parsePairing(message, 'offer'), { ...description, game: 'zzz', ...identity });
  const answer = pairingMessage({ ...description, type: 'answer' }, 'zzz', identity);
  assert.deepEqual(parsePairing(answer, 'answer'), { ...description, type: 'answer', game: 'zzz', ...identity });
  assert.deepEqual(parsePairing(pairingMessage(description, 'zzz'), 'offer'), { ...description, game: 'zzz' });
  const bounded = { sessionId: 'a'.repeat(16), pairingId: 'Z_-'.repeat(21) + 'x', attempt: 10000 };
  assert.deepEqual(parsePairing(pairingMessage(description, 'zzz', bounded), 'offer'), { ...description, game: 'zzz', ...bounded });
});
test('pairing rejects partial, malformed and out-of-range reconnect identities', () => {
  const invalid = [
    { sessionId: identity.sessionId }, { pairingId: identity.pairingId }, { attempt: 1 },
    { ...identity, sessionId: null }, { ...identity, pairingId: 123 },
    { ...identity, sessionId: 'a'.repeat(15) }, { ...identity, pairingId: 'a'.repeat(65) },
    { ...identity, sessionId: 'contains spaces here' }, { ...identity, pairingId: '含有中文的标识符1234567890' },
    ...[0, -1, 1.5, 10001, Number.MAX_SAFE_INTEGER + 1, '1', null].map(attempt => ({ ...identity, attempt })),
  ];
  for (const candidate of invalid) {
    assert.throws(() => pairingMessage(description, 'zzz', candidate), /Invalid pairing identity/);
    const raw = JSON.stringify({ format: 'proxy-mobile-capture-v1', ...description, game: 'zzz', ...candidate });
    assert.throws(() => parsePairing(raw, 'offer'), /Invalid pairing identity/);
  }
  for (const candidate of [null, [], 'identity', 1]) {
    assert.throws(() => pairingMessage(description, 'zzz', candidate), /Invalid pairing identity/);
  }
});
test('pairing matches only complete current session, pairing and attempt fields', () => {
  assert.equal(samePairing(identity, { ...identity }), true);
  assert.equal(samePairing(identity, { ...identity, sessionId: 'another-session-123' }), false);
  assert.equal(samePairing(identity, { ...identity, pairingId: 'another-pairing-123' }), false);
  assert.equal(samePairing(identity, { ...identity, attempt: 2 }), false);
  assert.equal(samePairing({}, {}), false);
  assert.equal(samePairing(identity, {}), false);
  assert.equal(samePairing({ sessionId: identity.sessionId }, { sessionId: identity.sessionId }), false);
  assert.equal(samePairing({ ...identity, attempt: 0 }, { ...identity, attempt: 0 }), false);
  assert.equal(samePairing(null, identity), false);
});
