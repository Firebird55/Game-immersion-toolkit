import assert from 'node:assert/strict';
import test from 'node:test';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {EventEmitter, once} from 'node:events';
import {existsSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {startOwnedServer, stopOwnedProcess} from '../scripts/e2e-preview.mjs';

const serverCode=[
  "const http=require('node:http');",
  "const server=http.createServer((req,res)=>res.end(JSON.stringify({registry:process.env.MINIFLARE_REGISTRY_PATH})));",
  "server.listen(0,'127.0.0.1',()=>process.send(JSON.stringify({event:'DEV_SERVER_READY',ip:'127.0.0.1',port:server.address().port})));",
].join('\n');

test('concurrent previews own ports, storage and artifacts; cleanup leaves unrelated listeners alive', async () => {
  const cwd=mkdtempSync(join(tmpdir(),'toolkit-preview-test-'));
  const unrelated=http.createServer((req,res)=>res.end('unrelated'));
  await new Promise(resolve=>unrelated.listen(0,'127.0.0.1',resolve));
  let a,b;
  const listeners = ['SIGINT','SIGTERM'].map(signal => process.listenerCount(signal));
  try {
    [a,b]=await Promise.all(['first','second'].map(name=>startOwnedServer({name,args:['-e',serverCode],cwd})));
    assert.notEqual(a.port,b.port);assert.notEqual(a.output,b.output);
    const [one,two]=await Promise.all([a,b].map(async server=>(await fetch(server.origin)).json()));
    assert.notEqual(one.registry,two.registry);
    assert(existsSync(join(one.registry,'..')));assert(existsSync(join(two.registry,'..')));
    await a.stop();assert(!existsSync(join(one.registry,'..')));
    await assert.rejects(fetch(a.origin));assert((await fetch(b.origin)).ok);
    assert.equal(await (await fetch('http://127.0.0.1:'+unrelated.address().port)).text(),'unrelated');
    await b.stop();assert(!existsSync(join(two.registry,'..')));
    await a.stop();
    assert.deepEqual(['SIGINT','SIGTERM'].map(signal => process.listenerCount(signal)), listeners);
  } finally {
    await Promise.all([a?.stop(),b?.stop()]);
    unrelated.closeAllConnections();await new Promise(resolve=>unrelated.close(resolve));
    rmSync(cwd,{recursive:true,force:true});
  }
});

test('startup failure, bad IPC, timeout and missing executable remove owned runtime', async () => {
  const cwd=mkdtempSync(join(tmpdir(),'toolkit-preview-failure-'));
  try {
    for(const scenario of [
      {code:'process.exit(3)',error:/exited before readiness/},
      {code:"process.send({event:'DEV_SERVER_READY',ip:'0.0.0.0',port:1234});setInterval(()=>{},1000)",error:/Invalid owned/},
      {code:'setInterval(()=>{},1000)',error:/timed out/,timeoutMs:100},
      {command:join(cwd,'missing-command'),code:'',error:/could not start/},
    ]) {
      let runtime;
      const exitedOnWindows = process.platform === 'win32' && scenario.code === 'process.exit(3)';
      await assert.rejects(startOwnedServer({name:'failure',cwd,command:scenario.command,
        timeoutMs:scenario.timeoutMs,args:directory=>{runtime=directory;return ['-e',scenario.code];}}),exitedOnWindows ? /cleanup is unverified/ : scenario.error);
      assert.equal(existsSync(runtime), exitedOnWindows);
      // This fixture is known to create no descendants. Production retains it
      // because cleanup after a Windows parent exit cannot be proved safely.
      if (exitedOnWindows) rmSync(runtime,{recursive:true,force:true});
    }
  } finally {rmSync(cwd,{recursive:true,force:true});}
});

test('cleanup terminates an owned descendant that ignores graceful shutdown', {skip:process.platform==='win32'}, async () => {
  const cwd=mkdtempSync(join(tmpdir(),'toolkit-preview-tree-'));
  let runtime,server;
  try {
    const descendant="process.on('SIGTERM',()=>{});"+serverCode;
    const code="const {spawn}=require('node:child_process');"+
      "const child=spawn(process.execPath,['-e',"+JSON.stringify(descendant)+"],{stdio:['ignore','ignore','ignore','ipc']});"+
      "child.on('message',message=>process.send(message));setInterval(()=>{},1000);";
    server=await startOwnedServer({name:'tree',cwd,args:directory=>{runtime=directory;return ['-e',code];}});
    assert((await fetch(server.origin)).ok);
    await server.stop();await assert.rejects(fetch(server.origin));assert(!existsSync(runtime));
  } finally {await server?.stop();rmSync(cwd,{recursive:true,force:true});}
});


test('Windows cleanup fails closed for exited parents and failed taskkill', async () => {
  const child = {pid: 12345, exitCode: 1, signalCode: null};
  let invoked = false;
  await assert.rejects(stopOwnedProcess(child, {platform:'win32', spawnProcess: () => {invoked = true;}}), /cleanup is unverified/);
  assert.equal(invoked, false, 'An expired PID must never be reused as a cleanup target');
  child.exitCode = null;
  await assert.rejects(stopOwnedProcess(child, {platform:'win32', spawnProcess: (command,args) => {
    assert.equal(command, 'taskkill'); assert.deepEqual(args, ['/PID','12345','/T','/F']);
    const killer = new EventEmitter();
    queueMicrotask(() => {child.exitCode = 0; killer.emit('exit',1);});
    return killer;
  }}), /cleanup is unverified/);
});

async function messageFrom(child) {
  let timer;
  try { return await Promise.race([once(child,'message').then(([value])=>value), new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Signal fixture timed out')),10000);})]); }
  finally {clearTimeout(timer);}
}

test('SIGINT and SIGTERM stop owned preview descendants and retain default signal exit', {skip:process.platform==='win32', timeout:20000}, async () => {
  const cwd=mkdtempSync(join(tmpdir(),'toolkit-preview-signals-'));
  const helper = new URL('../scripts/e2e-preview.mjs',import.meta.url).href;
  const unrelated=http.createServer((req,res)=>res.end('unrelated'));
  await new Promise(resolve=>unrelated.listen(0,'127.0.0.1',resolve));
  let harness, preview;
  try {
    for(const signal of ['SIGINT','SIGTERM']) {
      const descendant="process.on('SIGTERM',()=>{});"+serverCode;
      const server="const {spawn}=require('node:child_process');"+
        "const child=spawn(process.execPath,['-e',"+JSON.stringify(descendant)+"],{stdio:['ignore','ignore','ignore','ipc']});"+
        "child.on('message',message=>process.send(message));setInterval(()=>{},1000);";
      const source=`import {startOwnedServer} from ${JSON.stringify(helper)};
        const preview=await startOwnedServer({name:'signal',cwd:process.cwd(),args:['-e',${JSON.stringify(server)}]});
        const body=await (await fetch(preview.origin)).json();
        process.send({origin:preview.origin,runtime:body.registry+'/..',pid:preview.child.pid});`;
      harness=spawn(process.execPath,['--input-type=module','-e',source],{cwd,stdio:['ignore','ignore','pipe','ipc']});
      let stderr='';harness.stderr.on('data',data=>{stderr+=data;});
      preview=await messageFrom(harness);
      assert((await fetch(preview.origin)).ok);
      const exit=once(harness,'exit');harness.kill(signal);
      const [code,actualSignal]=await exit;
      assert.equal(code,null,stderr);assert.equal(actualSignal,signal,stderr);
      assert(!existsSync(preview.runtime));await assert.rejects(fetch(preview.origin));
      assert.equal(await (await fetch('http://127.0.0.1:'+unrelated.address().port)).text(),'unrelated');
      preview=null;harness=null;
    }
  } finally {
    harness?.kill('SIGKILL');
    // Only this test's recorded process group can be cleaned on assertion failure.
    if(preview) await stopOwnedProcess({pid:preview.pid});
    unrelated.closeAllConnections();await new Promise(resolve=>unrelated.close(resolve));
    rmSync(cwd,{recursive:true,force:true});
  }
});
