import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parsePairing, pairingMessage, samePairing, privateTrackState, privateRtcSample, frameHealth, imageSignature } from '../public/mobile-capture/core.mjs';

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

test('Quantic games pair for capture and transcript reading with the existing protocol',()=>{
 for(const game of ['beyond','heavyrain'])for(const mode of [undefined,'transcript']){
  const value=parsePairing(pairingMessage(description,game,{...identity,...(mode?{mode}:{})}),'offer');
  assert.equal(value.game,game);assert.equal(value.mode,mode);
 }
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
test('track diagnostics expose capture health and dimensions without device identifiers', () => {
  const track = {
    kind: 'video', enabled: true, muted: false, readyState: 'live',
    id: 'private-track-id', label: 'private display name', deviceId: 'private-device',
    getSettings: () => ({ width: 1920, height: 1080, frameRate: 30, deviceId: 'private-device',
      groupId: 'private-group', label: 'private name', displaySurface: 'monitor', facingMode: 'user' }),
  };
  assert.deepEqual(privateTrackState(track), { kind: 'video', enabled: true, muted: false,
    readyState: 'live', width: 1920, height: 1080, frameRate: 30 });
  assert.deepEqual(privateTrackState({ ...track, getSettings: () => ({ width: Infinity, height: '1080', frameRate: NaN }) }),
    { kind: 'video', enabled: true, muted: false, readyState: 'live' });
  assert.deepEqual(privateTrackState({ ...track, getSettings: () => { throw new Error('unavailable'); } }),
    { kind: 'video', enabled: true, muted: false, readyState: 'live' });
  assert.equal(privateTrackState(null), null);
});
test('RTC diagnostics retain finite video RTP counters and discard identifying data', () => {
  const report = new Map([
    ['send', { type: 'outbound-rtp', kind: 'video', bytesSent: 100, packetsSent: 2, framesEncoded: 3,
      framesSent: 3, retransmittedPacketsSent: 0, frameWidth: 1920, frameHeight: 1080, framesPerSecond: 30,
      id: 'private-stream', ssrc: 12345, trackIdentifier: 'private-track', codecId: 'private-codec',
      transportId: 'private-transport', remoteId: 'private-remote', address: '192.0.2.1',
      candidateType: 'host', url: 'private-url', label: 'private display', arbitrary: 'private' }],
    ['receive', { type: 'inbound-rtp', mediaType: 'video', bytesReceived: 200, packetsReceived: 4,
      packetsLost: 0, framesReceived: 6, framesDecoded: 5, framesDropped: 1, keyFramesDecoded: 2,
      jitter: 0.02, totalDecodeTime: 0.5, totalFreezesDuration: 1.2, freezeCount: 1,
      frameWidth: Infinity, frameHeight: '1080', framesPerSecond: NaN, id: 'private-stream' }],
    ['source', { type: 'media-source', kind: 'video', width: 1920, height: 1080, frames: 100,
      framesPerSecond: 30, id: 'private-source', trackIdentifier: 'private-track', ssrc: 12345,
      deviceId: 'private-device', label: 'private-display', bytesSent: 999 }],
    ['audio-source', { type: 'media-source', kind: 'audio', frames: 999 }],
    ['audio', { type: 'inbound-rtp', kind: 'audio', bytesReceived: 900 }],
    ['audio-send', { type: 'outbound-rtp', kind: 'audio', bytesSent: 900 }],
    ['candidate', { type: 'local-candidate', kind: 'video', bytesReceived: 999, address: '192.0.2.2' }],
    ['pair', { type: 'candidate-pair', kind: 'video', bytesSent: 999, localCandidateId: 'private-candidate' }],
  ]);
  assert.deepEqual(privateRtcSample(report, 'sender'), [{ direction: 'outbound', bytesSent: 100,
    packetsSent: 2, framesEncoded: 3, framesSent: 3, retransmittedPacketsSent: 0,
    frameWidth: 1920, frameHeight: 1080, framesPerSecond: 30 },
    { direction: 'source', width: 1920, height: 1080, frames: 100, framesPerSecond: 30 }]);
  assert.deepEqual(privateRtcSample(report, 'receiver'), [{ direction: 'inbound', bytesReceived: 200,
    packetsReceived: 4, packetsLost: 0, framesReceived: 6, framesDecoded: 5, framesDropped: 1,
    keyFramesDecoded: 2, jitter: 0.02, totalDecodeTime: 0.5, totalFreezesDuration: 1.2, freezeCount: 1 }]);
  assert.deepEqual(privateRtcSample(report, 'unexpected'), []);
  assert.deepEqual(privateRtcSample(null, 'sender'), []);
  const many = Array.from({ length: 100 }, () => ({ type: 'inbound-rtp', kind: 'video', framesReceived: 0 }));
  assert.equal(privateRtcSample(many, 'receiver').length, 8);
});
test('frame health distinguishes startup, missing frames and later stalls', () => {
  assert.equal(frameHealth(null, 2000, 0), 'Waiting for frames');
  assert.equal(frameHealth(null, 6000, 0), 'No frames received');
  assert.equal(frameHealth(1000, 5000, 0), 'Receiving frames');
  assert.equal(frameHealth(1000, 6001, 0), 'Frame delivery stalled');
});
test('image checks distinguish changing images and black frames', () => {
  const black = new Uint8ClampedArray([0, 0, 0, 255, 0, 0, 0, 255]);
  const white = new Uint8ClampedArray([255, 255, 255, 255, 255, 255, 255, 255]);
  assert.equal(imageSignature(black).dark, true);
  assert.equal(imageSignature(white).dark, false);
  assert.notEqual(imageSignature(black).hash, imageSignature(white).hash);
});
