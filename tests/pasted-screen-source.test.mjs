import test from 'node:test';
import assert from 'node:assert/strict';
import {createPastedScreenSource} from '../lib/pasted-screen-source.mjs';
const link = id => `https://vdo.ninja/?view=${id}`;
function fixture() {
  let next = 0, stops = 0, changed = 0, finish;
  const timers = new Map(), connections = [], errors = [];
  const receiver = {stop: async () => {stops++;}, connect: value => {connections.push(value); return new Promise(resolve => {finish = resolve;});}};
  const source = createPastedScreenSource({receiver, onChanged: () => changed++, onError: text => errors.push(text),
    setTimer: callback => {const id = ++next; timers.set(id, callback); return id;}, clearTimer: id => timers.delete(id)});
  return {source, connections, errors, get stops() {return stops;}, get changed() {return changed;},
    fire: () => {const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback());}, finish: () => finish?.()};
}
test('paste starts without a button; edits and clearing fence immediately', async () => {
  const f = fixture(); f.source.replace(link('first')); assert.equal(f.stops, 1);
  f.source.replace(link('second')); assert.equal(f.stops, 2); f.fire();
  assert.deepEqual(f.connections, [link('second')]);
  f.source.replace(''); assert.equal(f.stops, 3); f.finish(); await Promise.resolve();
  assert.equal(f.changed, 0); f.fire(); assert.equal(f.connections.length, 1);
});
test('background, missing data and disposal reject pending connects', () => {
  for (const action of [f => f.source.replace(link('first'), {enabled: false}), f => f.source.dispose()]) {
    const f = fixture(); f.source.replace(link('first')); action(f); f.fire(); assert.deepEqual(f.connections, []);
  }
});
test('unsupported URLs stop the old source and never echo private parameters', () => {
  const f = fixture(); f.source.replace('https://unknown.example/?password=PRIVATE_SENTINEL'); f.fire();
  assert.equal(f.stops, 1); assert.equal(f.connections.length, 0); assert.equal(f.errors.length, 1);
  assert.equal(JSON.stringify(f.errors).includes('PRIVATE_SENTINEL'), false);
});
