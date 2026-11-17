import assert from 'node:assert/strict';
import test from 'node:test';
import {waitForAuthoredAdbRoot} from '../scripts/android-authored-adb.mjs';

test('an expected adbd restart is accepted only after the actual shell reports root', async () => {
  let rooted = false, attempts = 0;
  const adb = (...args) => {
    if (args[0] === 'root') {rooted = true;throw Object.assign(Error(), {stderr: 'adb: unable to connect for root: closed'});}
    if (rooted && ++attempts === 1) throw Error('restarting transport');
    return rooted ? '0' : '2000';
  };
  await waitForAuthoredAdbRoot(adb, async (read, _label, timeout) => {
    assert.equal(timeout, 30000);
    for (let i = 0; i < 3; i++) {try {if (read()) return;} catch {}}
    assert.fail('Root was never verified');
  });
  assert.equal(attempts, 2);
  await assert.rejects(() => waitForAuthoredAdbRoot((...args) => {
    if (args[0] === 'root') throw Object.assign(Error('unrelated failure'), {stderr: 'permission denied'});
    return '2000';
  }, async () => {}), /unrelated failure/);
});
