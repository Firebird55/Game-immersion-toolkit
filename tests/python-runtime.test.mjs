import test from 'node:test';
import assert from 'node:assert/strict';
import {join} from 'node:path';
import {resolvePython} from '../scripts/python-runtime.mjs';

const root = join('synthetic', 'checkout');
test('explicit PYTHON wins even when its target is unavailable', () => {
  assert.deepEqual(resolvePython({root, env: {PYTHON: 'chosen-python', LOCALAPPDATA: 'private-install'}, platform: 'win32', exists: () => true}), {command: 'chosen-python', source: 'override'});
});
test('project virtual environments use the platform-specific executable', () => {
  for (const platform of ['win32', 'darwin', 'linux']) {
    const command = join(root, '.venv', ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']));
    assert.deepEqual(resolvePython({root, env: {}, platform, exists: path => path === command}), {command, source: 'project-venv'});
  }
});
test('an incomplete project venv cannot silently borrow another interpreter', () => {
  assert.equal(resolvePython({root, env: {}, platform: 'linux', exists: path => path === join(root, '.venv')}).source, 'project-venv');
});
test('PATH fallback never examines an installed companion or LOCALAPPDATA', () => {
  for (const platform of ['win32', 'darwin', 'linux']) {
    const paths = [];
    const result = resolvePython({root, env: {LOCALAPPDATA: 'private-install'}, platform, exists: path => { paths.push(path); return false; }});
    assert.deepEqual(result, {command: platform === 'win32' ? 'python' : 'python3', source: 'path'});
    assert.ok(paths.every(path => path.startsWith(join(root, '.venv'))));
  }
});
