import assert from 'node:assert/strict';
import test from 'node:test';
import {createAndroidReceiver} from '../lib/android-receiver.mjs';

const documentEpoch = 'a'.repeat(32);
const png = () => new Blob(['authored-png-envelope'], {type: 'image/png'});
const flush = async () => {for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve));};
const deferred = () => {let resolve; const promise = new Promise(done => {resolve = done;}); return {promise, resolve};};
const reply = (value, status = 200) => ({ok: status < 400, status, json: async () => value});

function fixture(options = {}) {
 const jobs = new Map(), listeners = new Set(), frames = [], calls = [], accepted = [];
 let timerId = 0, transport = {sessionId: null, status: 'ready', message: 'Ready', width: 0, height: 0};
 let generation = 0, highest = 0, owner = null, sourceNumber = 0, read;
 let accountGeneration = options.accountGeneration;
 const emit = value => {transport = {...transport, ...value}; for (const listener of listeners) listener(transport);};
 const source = {
  getState: () => transport,
  subscribe(fn) {listeners.add(fn); fn(transport); return () => listeners.delete(fn);},
  async connect(kind, value) {assert.equal(kind, 'vdo'); assert.ok(value.url); emit({sessionId: `source-${++sourceNumber}`, status: 'connecting'});},
  readFrame() {return read ? read() : Promise.resolve(frames.shift() ?? null);},
  disconnect() {emit({sessionId: null, status: 'ended', message: 'Disconnected'});},
  dispose() {this.disconnect();},
  pause() {emit({sessionId: null, status: 'paused', message: 'Paused'});},
  async resume() {emit({sessionId: `source-${++sourceNumber}`, status: 'connecting'});},
 };
 async function fetch(path, init = {}) {
  calls.push({path, ...init});
  if (path === '/api/snapshot') return reply({context:{account_generation:accountGeneration},status: {capture: {source_generation: generation}}});
  if (accountGeneration !== undefined && init.headers?.['X-Toolkit-Account-Generation'] !== String(accountGeneration)) return reply({},409);
  if (path === '/api/capture/receiver') {
   const value = JSON.parse(init.body);
   if (options.stopFailure && value.action === 'stop') return reply({}, 500);
   if (init.headers['X-Toolkit-Document-Epoch'] !== (options.hostEpoch ?? documentEpoch)) return reply({}, 409);
   if (value.revision <= highest) return reply({}, 409);
   highest = value.revision;
   if (value.action === 'stop') {if (owner === value.id) {owner = null; generation++;}}
   else {
    if (value.expected_generation !== generation || owner && owner !== value.id) return reply({}, 409);
    owner = value.id; generation++;
   }
   return reply({generation, receiver_id: value.id, receiver_revision: highest, running: !!owner});
  }
  assert.equal(path, '/api/capture/frame');
  if (options.rejectFrame?.()) {generation++; owner = null; return reply({}, 409);}
  assert.equal(init.headers['X-Toolkit-Generation'], String(generation));
  assert.equal(init.headers['X-Toolkit-Receiver-Id'], owner);
  assert.equal(init.headers['X-Toolkit-Receiver-Revision'], String(highest));
  assert.equal(init.headers['X-Toolkit-Document-Epoch'], documentEpoch);
  assert.equal(init.headers['Content-Type'], 'image/png');
  accepted.push(init);
  return reply({}, 202);
 }
 const controller = createAndroidReceiver({source, fetch, encodeFrame: options.encodeFrame ?? (async () => png()),
  documentEpoch, accountGeneration: options.accountGeneration, id: '00000000-0000-4000-8000-000000000001',
  setTimer(fn) {const id = ++timerId; jobs.set(id, fn); return id;}, clearTimer(id) {jobs.delete(id);}});
 return {controller, source, calls, accepted, emit,
  selectAccount(value) {accountGeneration=value;owner=null;generation++;},
  setRead(fn) {read = fn;},
  frame(sequence, width = 1600, height = 900) {
   let released = 0;
   const frame = {sessionId: transport.sessionId, sequence, width, height, release() {released++;}};
   frames.push(frame); emit({status: 'live', width, height, message: 'Receiving frames'});
   return {frame, released: () => released};
  },
  async tick() {const next = jobs.entries().next().value; assert.ok(next, 'a single next read is scheduled'); jobs.delete(next[0]); next[1](); await flush();},
 };
}

test('a received frame reaches only the leased native PNG endpoint with no viewer URL', async () => {
 const f = fixture();
 try {
  await f.controller.connect('https://vdo.ninja/?view=private-fixture&password=private-value');
  const frame = f.frame(1); await f.tick();
  assert.equal(f.accepted.length, 1);
  assert.equal(frame.released(), 1);
  assert.equal(f.accepted[0].body.type, 'image/png');
  assert.equal(f.controller.getState().acceptedFrames, 1);
  assert.ok(!JSON.stringify(f.calls).includes('private-value'));
 } finally {f.controller.dispose(); await flush();}
});

test('a receiver cannot adopt a later account from polling or forward a late encoded frame', async()=>{
 const encoded=deferred(),f=fixture({accountGeneration:0,encodeFrame:()=>encoded.promise});
 try {
  await f.controller.connect('authored-stream');const frame=f.frame(1);await f.tick();
  f.selectAccount(2);encoded.resolve(png());await flush();
  assert.equal(f.accepted.length,0);
  assert.equal(frame.released(),1);
  assert.ok(f.calls.filter(call=>call.path!=='/api/snapshot').every(call=>call.headers['X-Toolkit-Account-Generation']==='0'));
  f.frame(2);await f.tick();
  assert.equal(f.accepted.length,0);
  assert.equal(f.controller.getState().status,'error');
 } finally {f.controller.dispose();await flush();}
});

test('explicit stop fences native capture while a late encoder result is still pending', async () => {
 const encoded = deferred(), f = fixture({encodeFrame: () => encoded.promise});
 try {
  await f.controller.connect('authored-stream'); const frame = f.frame(1); await f.tick();
  const start = f.calls.find(call => call.path === '/api/capture/receiver' && JSON.parse(call.body).action === 'start');
  assert.ok(start);
  await f.controller.stop(); encoded.resolve(png()); await flush();
  assert.equal(f.accepted.length, 0);
  assert.equal(frame.released(), 1);
  assert.equal(f.controller.getState().status, 'ended');
  const controls = f.calls.filter(call => call.path === '/api/capture/receiver').map(call => JSON.parse(call.body));
  assert.ok(controls.at(-1).revision > JSON.parse(start.body).revision);
 } finally {f.controller.dispose(); await flush();}
});

test('reconnect rejects a retired stream frame and starts a fresh native generation', async () => {
 const f = fixture();
 try {
  await f.controller.connect('authored-stream'); f.frame(1); await f.tick();
  const oldGeneration = Number(f.accepted[0].headers['X-Toolkit-Generation']);
  const delayed = deferred(); f.setRead(() => delayed.promise); await f.tick();
  f.emit({sessionId: 'replacement', status: 'reconnecting'});
  let released = 0;
  delayed.resolve({sessionId: 'source-1', sequence: 2, width: 1600, height: 900, release() {released++;}});
  await flush();
  assert.equal(released, 1); assert.equal(f.accepted.length, 1);
  f.setRead(null); f.frame(1); await f.tick();
  assert.equal(f.accepted.length, 2);
  assert.ok(Number(f.accepted[1].headers['X-Toolkit-Generation']) > oldGeneration);
 } finally {f.controller.dispose(); await flush();}
});

test('rotation and foreground resume each renew native matching scope', async () => {
 const f = fixture();
 try {
  await f.controller.connect('authored-stream'); f.frame(1); await f.tick();
  f.frame(2, 900, 1600); await f.tick();
  assert.ok(Number(f.accepted[1].headers['X-Toolkit-Generation']) > Number(f.accepted[0].headers['X-Toolkit-Generation']));
  f.controller.pause(); await flush();
  assert.equal(f.controller.getState().status, 'paused');
  await f.controller.resume(); f.frame(1, 900, 1600); await f.tick();
  assert.equal(f.accepted.length, 3);
  assert.ok(Number(f.accepted[2].headers['X-Toolkit-Generation']) > Number(f.accepted[1].headers['X-Toolkit-Generation']));
 } finally {f.controller.dispose(); await flush();}
});

test('a native source reset recovers through a new fenced generation, never an unscoped start', async () => {
 let reject = true;
 const f = fixture({rejectFrame: () => {const result = reject; reject = false; return result;}});
 try {
  await f.controller.connect('authored-stream'); f.frame(1); await f.tick();
  assert.equal(f.accepted.length, 0);
  f.frame(2); await f.tick();
  assert.equal(f.accepted.length, 1);
  assert.ok(!f.calls.some(call => /capture\/(start|source|stop)$/.test(call.path)));
 } finally {f.controller.dispose(); await flush();}
});

test('an old document never adopts a new document token or forwards frames', async () => {
 const f = fixture({hostEpoch: 'b'.repeat(32)});
 try {
  await f.controller.connect('authored-stream'); f.frame(1); await f.tick();
  assert.equal(f.accepted.length, 0);
  assert.equal(f.controller.getState().status, 'error');
  assert.ok(f.calls.filter(call => call.path === '/api/capture/receiver')
   .every(call => call.headers['X-Toolkit-Document-Epoch'] === documentEpoch));
 } finally {f.controller.dispose(); await flush();}
});

test('a failed stop response is not advertised as confirmed cancellation', async () => {
 const f = fixture({stopFailure: true});
 try {
  await f.controller.connect('authored-stream'); f.frame(1); await f.tick();
  const states = []; f.controller.subscribe(state => states.push(state.status));
  await f.controller.stop();
  assert.equal(f.controller.getState().status, 'error');
  assert.ok(!states.includes('ended'));
 } finally {f.controller.dispose(); await flush();}
});
