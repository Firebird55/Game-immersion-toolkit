import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import test from 'node:test';

const stage = process.env.TOOLKIT_ZZZ_CATALOGUE_ASSETS;
const origin = 'https://toolkit-zzz-catalogue.invalid/';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

// Requires the separately staged reviewed software only. The browser is offline;
// the test supplies authored catalogue data through the same port as Android.
test('offline ZZZ worker attests exact software and rejects malformed and unauthenticated stage inputs',
  {skip: !stage, timeout:30000}, async () => {
    const {chromium} = await import('playwright');
    const file = name => readFile(join(stage, name));
    const [manifest, worker, host] = await Promise.all(['manifest.json', 'catalogue-worker.mjs', 'catalogue-host.js'].map(file));
    const parsed = JSON.parse(manifest);
    const files = await Promise.all(Object.keys(parsed.modules).map(async name => [name, await file(name)]));
    const fixture = JSON.parse(await readFile(new URL('../packaging/android/zzz-catalogue/authored-operation.json', import.meta.url)));
    const java = await readFile(new URL('../packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/ZzzCatalogueWorker.java',
      import.meta.url), 'utf8');
    const python = await readFile(new URL('../backend/android_zzz_catalogue.py', import.meta.url), 'utf8');
    assert.equal(sha256(manifest), java.match(/IDENTITY = "([a-f0-9]{64})"/)[1]);
    assert.equal(sha256(manifest), python.match(/IDENTITY = '([a-f0-9]{64})'/)[1]);
    for (const [name, receipt] of Object.entries(parsed.sources)) {
      const bytes = await file(join('sources', name));
      assert.equal(bytes.length, receipt.bytes);
      assert.equal(sha256(bytes), receipt.sha256);
    }
    const nonce = 'authored-worker-page';
    const tag = (id, bytes) => '<script type="application/octet-stream" id="' + id + '">' + bytes.toString('base64') + '</script>';
    const html = corrupt => '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' +
      "default-src 'none'; script-src 'nonce-" + nonce + "' blob: 'wasm-unsafe-eval'; " +
      "worker-src blob:; connect-src 'none'; base-uri 'none'; form-action 'none'\">" +
      tag('manifest', manifest) + tag('worker', worker) +
      files.map(([name, bytes]) => tag('file-' + name,
        corrupt && name === 'xxhash.mjs' ? Buffer.alloc(bytes.length) : bytes)).join('') +
      '<script nonce="' + nonce + '">' + host.toString('utf8') + '</script>';
    const browser = await chromium.launch({args:['--disable-background-networking','--no-first-run'], timeout:20000});
    try {
      const context = await browser.newContext({offline:true, serviceWorkers:'block'});
      const page = await context.newPage();
      const external = [];
      let corrupt = false;
      await page.route('**/*', route => {
        const request = route.request();
        if (request.url() === origin && request.method() === 'GET' && request.isNavigationRequest() &&
            request.frame() === page.mainFrame() && !request.redirectedFrom())
          return route.fulfill({status:200, contentType:'text/html; charset=utf-8', headers:{'Cache-Control':'no-store'},
            body:html(corrupt)});
        external.push(route.request().url());
        return route.abort();
      });
      const observed = async ({badDigest = false, cancel = false, valid = false} = {}) => {
        await page.goto(origin);
        const payload = Buffer.alloc(28_000, 0x61);
        const pack = bytes => ({size:bytes.length, sha256:sha256(bytes),
          chunks:Array.from({length:Math.ceil(bytes.length / 24576)}, (_, i) => bytes.subarray(i * 24576, (i + 1) * 24576).toString('base64'))});
        const inputs = valid ? Object.fromEntries(Object.entries(fixture.files).map(([name, row]) =>
          [name, pack(Buffer.from(row.base64, 'base64'))])) : {'design-1.blk':pack(payload)};
        const operation = valid ? {mode:fixture.mode, input:fixture.input} :
          {mode:'scene-plan', input:{design:['design-1.blk'], catalogs:['catalog-1.blk']}};
        return page.evaluate(({identity, inputs, operation, badDigest, cancel}) => new Promise(resolve => {
          const events = [];
          const outputs = {};
          let incoming, outgoing;
          const channel = new MessageChannel();
          const report = () => { clearTimeout(timer); channel.port1.close(); resolve({events, outputs}); };
          const timer = setTimeout(() => { if (!cancel) events.push('timeout'); report(); }, cancel ? 3000 : 8000);
          const send = value => channel.port1.postMessage(JSON.stringify(value));
          channel.port1.onmessage = ({data}) => {
            const {type, id, name, size, data: part, identity: proof} = JSON.parse(data);
            events.push(type);
            if (type === 'ready') send({type:'start', identity, ...operation});
            else if (type === 'started' && proof !== identity) { events.push('wrong-identity'); report(); }
            else if (type === 'read') {
              incoming = inputs[name];
              if (!incoming) { events.push('wrong-role'); report(); return; }
              if (cancel) send({type:'cancel'});
              else send({type:'input', id, size:incoming.size, sha256:badDigest ? '0'.repeat(64) : incoming.sha256});
            } else if (type === 'pull') send({type:'chunk', id, data:incoming.chunks.shift()});
            else if (type === 'write') {
              outgoing = {name, size, text:''};
              send({type:'pull', id});
            } else if (type === 'chunk') {
              outgoing.text += atob(part);
              if (outgoing.size === outgoing.text.length) outputs[outgoing.name] = outgoing.text;
              send({type:'pull', id});
            }
            else if (type === 'failed' || type === 'complete') report();
          };
          window.postMessage('toolkit-zzz-catalogue-v1', location.origin, [channel.port2]);
        }), {identity:sha256(manifest), inputs, operation, badDigest, cancel});
      };
      const valid = await observed({valid:true});
      assert.deepEqual(valid.events, ['ready','started','read','pull','read','pull','write','chunk','complete']);
      assert.deepEqual(Object.keys(valid.outputs), [fixture.output.name]);
      assert.deepEqual(JSON.parse(valid.outputs[fixture.output.name]), fixture.output.data);
      assert.equal(sha256(valid.outputs[fixture.output.name]), fixture.output.sha256);
      assert.deepEqual(await observed({valid:true, badDigest:true}), {events:['ready','started','read','pull','failed'], outputs:{}});
      assert.deepEqual(await observed(), {events:['ready','started','read','pull','pull','failed'], outputs:{}});
      assert.deepEqual(await observed({cancel:true}), {events:['ready','started','read'], outputs:{}});
      corrupt = true;
      assert.deepEqual(await observed(), {events:['ready','failed'], outputs:{}});
      assert.deepEqual(external, []);
    } finally {
      await browser.close();
    }
  });
