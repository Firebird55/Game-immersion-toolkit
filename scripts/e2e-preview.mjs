import {spawn} from 'node:child_process';
import {mkdirSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {randomUUID} from 'node:crypto';

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const ownedServers = new Set();
let handlingSignal = false;
const signalHandlers = new Map(['SIGINT', 'SIGTERM'].map(signal => [signal, () => { void stopOnSignal(signal); }]));
function registerOwnedServer(stop) {
  if (!ownedServers.size) for (const [signal, handler] of signalHandlers) process.on(signal, handler);
  ownedServers.add(stop);
}
function unregisterOwnedServer(stop) {
  ownedServers.delete(stop);
  if (!ownedServers.size) for (const [signal, handler] of signalHandlers) process.off(signal, handler);
}
async function stopOnSignal(signal) {
  if (handlingSignal) return;
  handlingSignal = true;
  // Other application handlers already receive this event. Do not replay their
  // callbacks; restore Node's default signal exit only when we own the handling.
  const hasOtherHandler = process.listeners(signal).some(handler => handler !== signalHandlers.get(signal));
  const results = await Promise.allSettled([...ownedServers].map(stop => stop()));
  if (results.some(result => result.status === 'rejected')) console.error('Owned preview cleanup could not be verified; temporary runtime retained.');
  for (const [name, handler] of signalHandlers) process.off(name, handler);
  handlingSignal = false;
  if (!hasOtherHandler) process.kill(process.pid, signal);
}
const unverifiedWindowsCleanup = () => new Error('Windows owned-process cleanup is unverified after its parent exited; temporary runtime retained.');

// Each POSIX child leads its own process group. Never discover or kill a
// process by port: another checkout or the user's companion may own it.
export async function stopOwnedProcess(child, {graceMs = 1500, platform = process.platform, spawnProcess = spawn} = {}) {
  if (!child?.pid) return;
  if (platform === 'win32') {
    // Without a live parent, taskkill cannot prove ownership of any orphaned
    // descendants. Fail closed instead of claiming the process tree was gone.
    if (child.exitCode !== null || child.signalCode !== null) throw unverifiedWindowsCleanup();
    await new Promise((resolve, reject) => {
      const killer = spawnProcess('taskkill', ['/PID', String(child.pid), '/T', '/F'], {stdio: 'ignore'});
      killer.once('error', reject);
      killer.once('exit', code => code === 0 ? resolve() : reject(unverifiedWindowsCleanup()));
    });
    return;
  }
  const alive = () => {
    try { process.kill(-child.pid, 0); return true; }
    catch (error) { if (error.code === 'ESRCH') return false; throw error; }
  };
  for (const signal of ['SIGTERM', 'SIGKILL']) {
    try { process.kill(-child.pid, signal); }
    catch (error) { if (error.code === 'ESRCH') return; throw error; }
    const deadline = Date.now() + graceMs;
    while (alive() && Date.now() < deadline) await delay(25);
    if (!alive()) return;
  }
  throw new Error('Owned test process group did not stop');
}

// Wrangler's pinned CLI forwards DEV_SERVER_READY over Node IPC. Port zero
// lets its listener retain the allocated port, avoiding reserve/close races.
export async function startOwnedServer({name, command = process.execPath, args,
  cwd = process.cwd(), env = process.env, timeoutMs = 30000}) {
  if (handlingSignal) throw new Error('Cannot start a server after preview signal cleanup started');
  if (!/^[a-z0-9-]+$/.test(name)) throw new Error('Invalid test server name');
  const runtime = mkdtempSync(join(tmpdir(), `toolkit-${name}-`));
  const output = resolve(cwd, 'output/e2e', `${name}-${randomUUID()}`);
  let child, stdout = '', stderr = '', stopped;
  const cleanups = new Set();
  const clean = text => String(text).replaceAll(runtime, '<fixture>').replaceAll(cwd, '<repository>');
  const addCleanup = cleanup => {
    if (stopped || handlingSignal) throw new Error('Cannot register resources after preview cleanup started');
    if (typeof cleanup !== 'function') throw new Error('Preview cleanup must be a function');
    cleanups.add(cleanup);
  };
  const launchBrowser = (engine, options = {}) => {
    // Register before launch begins so a signal during startup still waits for
    // the browser to resolve and close. Playwright must not exit the harness
    // from its own signal handler before the owned server has been stopped.
    if (stopped || handlingSignal) throw new Error('Cannot launch a browser after preview cleanup started');
    const pending = Promise.resolve().then(() => engine.launch({...options, handleSIGINT: false, handleSIGTERM: false}));
    addCleanup(async () => {
      const browser = await pending.catch(() => null);
      await browser?.close();
    });
    return pending;
  };
  const stop = () => stopped ??= (async () => {
    try {
      // Always attempt every cleanup, even when browser close or server teardown
      // rejects. Waiting concurrently also lets the server stop if close stalls.
      const results = await Promise.allSettled([
        ...[...cleanups].map(cleanup => Promise.resolve().then(cleanup)),
        Promise.resolve().then(() => stopOwnedProcess(child)),
      ]);
      const failures = results.filter(result => result.status === 'rejected');
      if (failures.length === 1) throw failures[0].reason;
      if (failures.length) throw new AggregateError(failures.map(result => result.reason), 'Owned preview cleanup could not be verified; temporary runtime retained.');
      rmSync(runtime, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
    } finally { unregisterOwnedServer(stop); }
  })();
  registerOwnedServer(stop);
  try {
    mkdirSync(output, {recursive: true});
    child = spawn(command, typeof args === 'function' ? args(runtime) : args, {
      cwd, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
      env: {...env, WRANGLER_SEND_METRICS: 'false', WRANGLER_WRITE_LOGS: 'false',
        MINIFLARE_REGISTRY_PATH: join(runtime, 'registry')},
    });
    child.stdout.on('data', data => { stdout = (stdout + clean(data)).slice(-8000); });
    child.stderr.on('data', data => { stderr = (stderr + clean(data)).slice(-8000); });
    const port = await new Promise((resolve, reject) => {
      const finish = (error, value) => {
        clearTimeout(timer); child.off('message', message); child.off('error', failed); child.off('exit', exited);
        error ? reject(error) : resolve(value);
      };
      const failed = () => finish(new Error('Test server could not start'));
      const exited = () => finish(new Error('Test server exited before readiness: ' + stderr));
      const message = raw => {
        let event;
        try { event = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return; }
        if (event?.event !== 'DEV_SERVER_READY') return;
        if (event.ip !== '127.0.0.1' || !Number.isInteger(event.port) || event.port < 1 || event.port > 65535)
          return finish(new Error('Invalid owned test server address'));
        finish(null, event.port);
      };
      const timer = setTimeout(() => finish(new Error('Test server readiness timed out: ' + stderr)), timeoutMs);
      child.on('message', message); child.once('error', failed); child.once('exit', exited);
    });
    return {child, port, origin: `http://127.0.0.1:${port}`, output, stop, addCleanup, launchBrowser,
      diagnostics: () => ({stdout, stderr, exitCode: child.exitCode, signal: child.signalCode})};
  } catch (error) {
    await stop();
    throw error;
  }
}

export function startPreview(name, options = {}) {
  const cwd = options.cwd ?? process.cwd();
  return startOwnedServer({...options, name, cwd,
    args: runtime => [resolve(cwd, 'node_modules/wrangler/bin/wrangler.js'), 'dev',
      '--config', resolve(cwd, 'dist/server/wrangler.json'), '--ip', '127.0.0.1',
      '--port', '0', '--inspector-port', '0', '--persist-to', join(runtime, 'persist')],
  });
}
