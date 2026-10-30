import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import {createHash} from 'node:crypto';
import {once} from 'node:events';
import {mkdtempSync,writeFileSync,renameSync,mkdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {startRouter} from '../scripts/companion-router.mjs';

const listen=server=>new Promise(resolve=>server.listen(0,'127.0.0.1',()=>resolve(server.address().port)));
const close=server=>new Promise(resolve=>server.close(resolve));
test('router shutdown closes owned preconnected sockets without stopping an unrelated listener',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'companion-router-')),statePath=join(directory,'state.json');
 const backend=http.createServer((_request,response)=>response.end('still available'));
 let router,idle,closing,timer;
 try{
  const port=await listen(backend);writeFileSync(statePath,JSON.stringify({active:{apiPort:port,frontendPort:port}}));
  router=await startRouter({statePath,apiPort:0,frontendPort:0});
  idle=net.connect({host:'127.0.0.1',port:router.apiPort});await once(idle,'connect');
  closing=router.close();
  const result=await Promise.race([closing.then(()=>true),new Promise(resolve=>{timer=setTimeout(()=>resolve(false),1000);})]);
  assert.equal(result,true,'Shutdown retained a preconnected socket with no active request');
  assert.equal(await(await fetch('http://127.0.0.1:'+port)).text(),'still available');
 }finally{
  clearTimeout(timer);idle?.destroy();await closing;await router?.close();await close(backend);
  rmSync(directory,{recursive:true,force:true});
 }
});

for(const finishDuringDrain of [true,false])test(`router shutdown ${finishDuringDrain?'drains a finishing response':'reports its deadline and reaps a stalled response'}`,async()=>{
 const directory=mkdtempSync(join(tmpdir(),'companion-router-')),statePath=join(directory,'state.json');
 let started,response,router,closing;
 const pending=new Promise(resolve=>started=resolve);
 const backend=http.createServer((_request,reply)=>{response=reply;started();});
 try{
  const port=await listen(backend);writeFileSync(statePath,JSON.stringify({active:{apiPort:port,frontendPort:port}}));
  router=await startRouter({statePath,apiPort:0,frontendPort:0,shutdownTimeoutMs:100});
  const answer=fetch('http://127.0.0.1:'+router.apiPort).then(reply=>reply.text()).catch(()=>null);
  await pending;closing=router.close();assert.equal(router.close(),closing,'Concurrent shutdown must share one outcome');
  if(finishDuringDrain){response.end('complete response');assert.equal(await answer,'complete response');await closing;}
  else{await assert.rejects(closing,/shutdown deadline expired/);assert.equal(await answer,null);}
 }finally{
  response?.destroy();await closing?.catch(()=>{});await router?.close().catch(()=>{});
  backend.closeAllConnections();await close(backend);rmSync(directory,{recursive:true,force:true});
 }
});
test('prepared runtime switches without interrupting active responses or losing old interface assets',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'companion-router-')),statePath=join(directory,'state.json'),assets=join(directory,'assets');
 mkdirSync(assets);writeFileSync(join(assets,'old-reader.js'),'old interface asset');
 let finish,started;const pending=new Promise(resolve=>started=resolve);
 const old=http.createServer((request,response)=>{if(request.url==='/slow'){started();finish=()=>response.end('old answer completed');}else response.end('old runtime');});
 const fresh=http.createServer((_request,response)=>response.end('new runtime'));
 let router;
 try{
  const a=await listen(old),b=await listen(fresh);
  writeFileSync(statePath,JSON.stringify({active:{apiPort:a,frontendPort:a}}));
  router=await startRouter({statePath,assetDirectory:assets,apiPort:0,frontendPort:0});
  const base='http://127.0.0.1:'+router.apiPort;
  assert.equal(await(await fetch(base)).text(),'old runtime');
  const answer=fetch(base+'/slow').then(response=>response.text());await pending;
  const temporary=statePath+'.pending';writeFileSync(temporary,JSON.stringify({active:{apiPort:b,frontendPort:b}}));renameSync(temporary,statePath);
  assert.equal(await(await fetch(base)).text(),'new runtime');
  finish();assert.equal(await answer,'old answer completed');
  assert.equal(await(await fetch('http://127.0.0.1:'+router.frontendPort+'/_next/static/old-reader.js')).text(),'old interface asset');
  writeFileSync(statePath,'{incomplete');
  assert.equal(await(await fetch(base)).text(),'new runtime','A broken candidate cannot replace the working route');
 }finally{await router?.close();await Promise.all([close(old),close(fresh)]);assert(resolve(directory).startsWith(resolve(tmpdir())+sep+'companion-router-'));rmSync(directory,{recursive:true,force:true});}
});

test('open readers reconnect their WebSocket to the prepared runtime',async()=>{
 const directory=mkdtempSync(join(tmpdir(),'companion-router-')),statePath=join(directory,'state.json');
 const sockets=new Set();
 function backend(name){
  const server=http.createServer();server.on('upgrade',(request,socket)=>{
   sockets.add(socket);socket.on('close',()=>sockets.delete(socket));
   const accept=createHash('sha1').update(request.headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
   socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n');
   socket.write(Buffer.concat([Buffer.from([0x81,name.length]),Buffer.from(name)]));
  });return server;
 }
 const old=backend('old'),fresh=backend('new');let router,first,second;
 const event=(target,name)=>once(target,name,{signal:AbortSignal.timeout(5000)});
 try{
  const a=await listen(old),b=await listen(fresh);writeFileSync(statePath,JSON.stringify({active:{apiPort:a,frontendPort:a}}));
  router=await startRouter({statePath,apiPort:0,frontendPort:0});
  first=new WebSocket('ws://127.0.0.1:'+router.apiPort+'/ws');
  assert.equal((await event(first,'message'))[0].data,'old');
  const disconnected=event(first,'close');
  writeFileSync(statePath,JSON.stringify({active:{apiPort:b,frontendPort:b}}));await disconnected;
  second=new WebSocket('ws://127.0.0.1:'+router.apiPort+'/ws');
  assert.equal((await event(second,'message'))[0].data,'new');
 }finally{
  first?.close();second?.close();await router?.close();for(const socket of sockets)socket.destroy();
  await Promise.all([close(old),close(fresh)]);assert(resolve(directory).startsWith(resolve(tmpdir())+sep+'companion-router-'));rmSync(directory,{recursive:true,force:true});
 }
});
