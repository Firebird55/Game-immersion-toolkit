import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parsePairing, pairingMessage, frameHealth, imageSignature } from '../public/mobile-capture/core.mjs';

test('manual pairing rejects malformed, oversized and wrong-role descriptions', () => {
  const offer = pairingMessage({ type: 'offer', sdp: 'v=0\r\nfixture' }, 'zzz');
  assert.deepEqual(parsePairing(offer, 'offer'), { type: 'offer', sdp: 'v=0\r\nfixture', game: 'zzz' });
  assert.throws(() => parsePairing(offer, 'answer'), /Expected a answer/);
  assert.throws(() => parsePairing('{', 'offer'), /valid pairing/);
  assert.throws(() => parsePairing('x'.repeat(128001), 'offer'), /too large/);
  assert.throws(() => parsePairing(pairingMessage({ type: 'offer', sdp: 'bad' }, 'zzz'), 'offer'));
  assert.throws(() => parsePairing(pairingMessage({ type: 'offer', sdp: 'v=0' }, 'other'), 'offer'));
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
