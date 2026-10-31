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
