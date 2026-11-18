// Private app WebView document. The port carries one scoped stage at a time.
(() => {
  const CHUNK = 24 * 1024;
  const MAX_FILE = 128 * 1024 * 1024;
  const MAX_CONTROL = 256 * 1024;
  const hex = /^[a-f0-9]{64}$/;
  let channel, worker, request, started = false;

  function decoded(id) {
    const encoded = document.getElementById(id)?.textContent;
    if (!encoded) throw Error('Missing owned ZZZ software');
    return Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
  }

  function send(value) {
    channel.postMessage(typeof value === 'string' ? value : JSON.stringify(value));
  }

  function stop() {
    worker?.terminate();
    worker = undefined;
    request = undefined;
  }

  function fail() {
    stop();
    send({type: 'failed'});
  }

  async function receive(event) {
    if (typeof event.data !== 'string' || event.data.length > MAX_CONTROL)
      throw Error('Invalid ZZZ stage message');
    const value = JSON.parse(event.data);
    if (value.type === 'cancel') { stop(); return; }
    if (value.type === 'start' && !started) {
      started = true;
      const decoder = new TextDecoder('utf-8', {fatal: true});
      const manifest = decoded('manifest');
      const files = Object.fromEntries(Object.keys(JSON.parse(decoder.decode(manifest)).modules)
        .map(name => [name, decoded('file-' + name)]));
      const url = URL.createObjectURL(new Blob([decoded('worker')], {type: 'text/javascript'}));
      worker = new Worker(url, {type: 'module'});
      worker.onerror = fail;
      worker.onmessage = ({data}) => {
        try {
          if (data.type === 'started') {
            if (data.identity !== value.identity) throw Error('ZZZ software identity changed');
            URL.revokeObjectURL(url);
            send(data);
          } else if (data.type === 'complete' || data.type === 'failed') {
            if (request && data.type === 'complete') throw Error('Unfinished ZZZ stage I/O');
            stop();
            send(data);
          } else {
            if (request || !Number.isSafeInteger(data.id) || !/^[A-Za-z0-9_.-]{1,80}$/.test(data.name))
              throw Error('Invalid ZZZ stage I/O');
            request = {id:data.id, type:data.type, at:0};
            if (data.type === 'write') {
              if (!(data.bytes instanceof Uint8Array) || !data.bytes.length || data.bytes.length > MAX_FILE)
                throw Error('ZZZ output exceeds bound');
              request.bytes = data.bytes;
              send({type:'write', id:data.id, name:data.name, size:data.bytes.length});
            } else if (data.type === 'read') send(data);
            else throw Error('Unknown ZZZ stage I/O');
          }
        } catch { fail(); }
      };
      worker.postMessage({...value, manifest, files});
      return;
    }
    if (!request || value.id !== request.id) throw Error('Stale ZZZ stage message');
    if (request.type === 'write') {
      if (value.type !== 'pull') throw Error('Invalid ZZZ output request');
      const {at, bytes, id} = request;
      if (at === bytes.length) {
        request = undefined;
        worker.postMessage({type:'reply', id});
      } else {
        const part = bytes.subarray(at, at + CHUNK);
        request.at += part.length;
        send({type:'chunk',id,data:btoa(String.fromCharCode(...part))});
      }
      return;
    }
    if (value.type === 'input' && !request.bytes) {
      if (!Number.isSafeInteger(value.size) || value.size <= 0 || value.size > MAX_FILE || !hex.test(value.sha256))
        throw Error('ZZZ input exceeds bound');
      request.bytes = new Uint8Array(value.size);
      request.digest = value.sha256;
    } else if (value.type === 'chunk' && request.bytes && typeof value.data === 'string' && value.data.length <= CHUNK * 4 / 3) {
      const part = atob(value.data);
      if (part.length !== Math.min(CHUNK, request.bytes.length - request.at) || !part.length)
        throw Error('Invalid ZZZ input chunk');
      request.bytes.set(Uint8Array.from(part, char => char.charCodeAt(0)), request.at);
      request.at += part.length;
      if (request.at === request.bytes.length) {
        const complete = request;
        const digest = await crypto.subtle.digest('SHA-256', complete.bytes);
        if (request !== complete || !worker) return;
        const hexDigest = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
        if (hexDigest !== complete.digest) throw Error('ZZZ input checksum differs');
        request = undefined;
        worker.postMessage({type:'reply', id:complete.id, bytes:complete.bytes}, [complete.bytes.buffer]);
        return;
      }
    } else throw Error('Invalid ZZZ input request');
    send({type:'pull', id:request.id});
  }

  window.addEventListener('message', event => {
    if (channel || event.data !== 'toolkit-zzz-catalogue-v1' || event.ports.length !== 1) return;
    channel = event.ports[0];
    channel.onmessage = event => { void receive(event).catch(fail); };
    send({type:'ready'});
  });
})();
