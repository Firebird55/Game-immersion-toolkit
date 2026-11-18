import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import test from 'node:test';

const stage = process.env.TOOLKIT_ZZZ_CATALOGUE_ASSETS;
const origin = 'https://toolkit-zzz-catalogue.invalid/';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

// Requires the separately staged reviewed software only. The browser is offline;
// the test supplies authored malformed data through the same port as Android.
test('offline ZZZ worker attests exact software and rejects malformed and unauthenticated stage inputs',
  {skip: !stage, timeout:30000}, async () => {
    const {chromium} = await import('playwright');
    const file = name => readFile(join(stage, name));
    const [manifest, worker, host] = await Promise.all(['manifest.json', 'catalogue-worker.mjs', 'catalogue-host.js'].map(file));
    const parsed = JSON.parse(manifest);
    const files = await Promise.all(Object.keys(parsed.modules).map(async name => [name, await file(name)]));
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
        if (route.request().url() === origin)
          return route.fulfill({status:200, contentType:'text/html', body:html(corrupt)});
        external.push(route.request().url());
        return route.abort();
      });
      const observed = async ({badDigest, cancel}) => {
        await page.goto(origin);
        const payload = Buffer.alloc(28_000, 0x61);
        return page.evaluate(({identity, sha256, payload, badDigest, cancel}) => new Promise(resolve => {
          const events = [];
          const chunks = payload.match(/.{1,24576}/g);
          const channel = new MessageChannel();
          const report = () => { clearTimeout(timer); channel.port1.close(); resolve(events); };
          const timer = setTimeout(() => { if (!cancel) events.push('timeout'); report(); }, cancel ? 3000 : 8000);
          const send = value => channel.port1.postMessage(JSON.stringify(value));
          channel.port1.onmessage = ({data}) => {
            const {type, id, name, identity: proof} = JSON.parse(data);
            events.push(type);
            if (type === 'ready') send({type:'start', mode:'scene-plan', identity,
              input:{design:['design-1.blk'], catalogs:['catalog-1.blk']}});
            else if (type === 'started' && proof !== identity) { events.push('wrong-identity'); report(); }
            else if (type === 'read') {
              if (name !== 'design-1.blk') { events.push('wrong-role'); report(); return; }
              if (cancel) send({type:'cancel'});
              else send({type:'input', id, size:payload.length, sha256:badDigest ? '0'.repeat(64) : sha256});
            } else if (type === 'pull') send({type:'chunk', id, data:btoa(chunks.shift())});
            else if (type === 'failed' || type === 'complete') report();
          };
          window.postMessage('toolkit-zzz-catalogue-v1', location.origin, [channel.port2]);
        }), {identity:sha256(manifest), sha256:sha256(payload), payload:payload.toString('ascii'), badDigest, cancel});
      };
      assert.deepEqual(await observed({badDigest:false, cancel:false}), ['ready','started','read','pull','pull','failed']);
      assert.deepEqual(await observed({badDigest:true, cancel:false}), ['ready','started','read','pull','pull','failed']);
      assert.deepEqual(await observed({badDigest:false, cancel:true}), ['ready','started','read']);
      corrupt = true;
      assert.deepEqual(await observed({badDigest:false, cancel:false}), ['ready','failed']);
      assert.deepEqual(external, []);
    } finally {
      await browser.close();
    }
  });
