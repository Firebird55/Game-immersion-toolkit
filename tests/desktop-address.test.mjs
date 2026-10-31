import test from 'node:test';
import assert from 'node:assert/strict';
import {desktopAddress} from '../lib/desktop-address.mjs';
import {desktopApiBase, desktopWebSocketUrl} from '../lib/desktop-endpoints.ts';

test('mobile navigation keeps the selected desktop host and port',()=>{
 assert.equal(desktopAddress('192.168.1.20:3000'),'http://192.168.1.20:3000/');
 assert.equal(desktopAddress(' http://192.168.1.20:3100/ '),'http://192.168.1.20:3100/');
 assert.equal(desktopAddress('gamingpc.local'),'http://gamingpc.local:3000/');
 assert.equal(desktopAddress('http://192.168.1.20:80'),'http://192.168.1.20/');
 for(const input of ['', 'javascript:alert(1)', 'file:///tmp/test', 'http://name:secret@example.com', 'http://example.com/api/secret', 'http://example.com/?key=secret', 'http://example.com/#key', '192.168.1.20:65536'])assert.throws(()=>desktopAddress(input));
});

test('LAN reader requests and sockets use the page origin while installed localhost stays stable',()=>{
 for(const hostname of ['127.0.0.1','localhost']) {
  assert.equal(desktopApiBase({hostname}),'http://127.0.0.1:8766');
  assert.equal(desktopWebSocketUrl({hostname,host:hostname+':3000',protocol:'http:'}),'ws://127.0.0.1:8766/api/ws');
 }
 assert.equal(desktopApiBase({hostname:'192.168.1.20'}),'');
 assert.equal(desktopWebSocketUrl({hostname:'192.168.1.20',host:'192.168.1.20:3100',protocol:'http:'}),'ws://192.168.1.20:3100/api/ws');
 assert.equal(desktopWebSocketUrl({hostname:'desktop.local',host:'desktop.local:3100',protocol:'https:'}),'wss://desktop.local:3100/api/ws');
});

test('standalone desktop gateways keep independent custom-port readers on their own service',()=>{
 for(const port of [31017, 42806]) for(const hostname of ['127.0.0.1', 'localhost', '192.168.1.20']) {
  const location={hostname,host:`${hostname}:${port}`,protocol:'http:'};
  assert.equal(desktopApiBase(location,true),'');
  assert.equal(desktopWebSocketUrl(location,true),`ws://${hostname}:${port}/api/ws`);
 }
 assert.equal(desktopWebSocketUrl({hostname:'localhost',host:'localhost:42001',protocol:'https:'},true),'wss://localhost:42001/api/ws');
});

test('only the explicit standalone document marker opts localhost into its gateway',()=>{
 const prior=Object.getOwnPropertyDescriptor(globalThis,'document');
 try {
  const location={hostname:'127.0.0.1',host:'127.0.0.1:39107',protocol:'http:'};
  for(const content of [null,'', 'other', 'same-origin']) {
   Object.defineProperty(globalThis,'document',{configurable:true,value:{querySelector:selector=>{
    assert.equal(selector,'meta[name="toolkit-api-transport"]');
    return content===null?null:{getAttribute:name=>{assert.equal(name,'content');return content;}};
   }}});
   assert.equal(desktopApiBase(location),content==='same-origin'?'':'http://127.0.0.1:8766');
   assert.equal(desktopWebSocketUrl(location),content==='same-origin'?'ws://127.0.0.1:39107/api/ws':'ws://127.0.0.1:8766/api/ws');
  }
 } finally { if(prior) Object.defineProperty(globalThis,'document',prior);else delete globalThis.document; }
});
