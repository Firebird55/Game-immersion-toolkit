import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {request as httpRequest} from 'node:http';
import {Miniflare, convertV4MiniflareOptions} from 'miniflare';
import {build} from 'esbuild';
import retired from '../services/retired-mobile-service.mjs';

function edgeRequest(url, method, headers) {
  return new Promise((resolve, reject) => {
    const request = httpRequest(url, {method, headers, agent: false}, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => resolve({status: response.statusCode, text: Buffer.concat(chunks).toString()}));
      response.on('error', reject);
    });
    request.on('upgrade', (_response, socket) => {socket.destroy(); reject(Error('A retired service accepted a socket.'));});
    request.on('error', reject);
    request.setTimeout(10000, () => request.destroy(Error('Retired service response timed out.')));
    request.end();
  });
}

test('retirement never reads credentials, bodies, bindings or an upstream service', async () => {
  const request = new Proxy({method: 'POST'}, {get(target, name) {
    if (name === 'method') return target.method;
    throw Error('The retired handler must not inspect request material.');
  }});
  const env = new Proxy({}, {get() {throw Error('No retired service binding may be used.');}});
  const response = await retired.fetch(request, env);
  assert.equal(response.status, 410);
  assert.equal((await response.json()).error, 'service_retired');
  assert.equal(response.headers.get('Cache-Control'), 'no-store, private');
});

for (const name of ['pairing', 'lexirise-gateway']) {
  test(`${name} production target refuses health, account, registration and socket traffic`, async t => {
    const root = new URL(`../services/${name}/`, import.meta.url);
    const config = JSON.parse(readFileSync(new URL('wrangler.jsonc', root)));
    assert.equal(config.workers_dev, false);
    assert.equal(config.preview_urls, false);
    const bundle = await build({entryPoints: [fileURLToPath(new URL(config.main, root))],
      bundle: true, write: false, format: 'esm', platform: 'neutral', external: ['cloudflare:*']});
    const worker = new Miniflare(convertV4MiniflareOptions({
      host: '127.0.0.1', port: 0,
      name: `retired-${name}`,
      modules: true,
      script: bundle.outputFiles[0].text,
      compatibilityDate: config.compatibility_date,
      ...(name === 'pairing' ? {durableObjects: {ROOMS: {className: 'PairingRoom', useSQLite: true}}} : {}),
    }));
    t.after(async () => {
      try { await worker.dispose(); }
      catch (error) { throw new Error(`${name} worker cleanup: ${error.message}`, {cause: error}); }
    });
    // Use the real local HTTP edge. Miniflare's RPC proxy has its own Origin
    // admission policy, which is not the Worker's production request handler.
    const endpoint = await worker.ready;
    for (const [path, method, headers] of [
      ['/health', 'GET', {}],
      ['/v1/request', 'POST', {Authorization: 'Bearer authored-fixture'}],
      ['/v1/audio', 'OPTIONS', {Origin: 'https://example.test'}],
      ['/v1/rooms/' + 'a'.repeat(32), 'POST', {}],
      ['/v1/rooms/' + 'a'.repeat(32), 'GET', {Upgrade: 'websocket', Connection: 'Upgrade',
        'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ=='}],
      ['/health', 'HEAD', {}],
    ]) {
      let response;
      try { response = await edgeRequest(new URL(path, endpoint), method, headers); }
      catch (error) { throw new Error(`${name}: ${method} ${path}: ${error.message}`, {cause: error}); }
      assert.equal(response.status, 410, `${name} ${method} ${path} ${headers.Upgrade || ''}`);
      if (method === 'HEAD') assert.equal(response.text, '');
      else assert.equal(JSON.parse(response.text).error, 'service_retired');
    }
  });
}
