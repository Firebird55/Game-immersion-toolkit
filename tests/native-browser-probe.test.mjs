import test from 'node:test';
import assert from 'node:assert/strict';
import {observeNativeBrowserLaunch} from '../desktop/browser-probe.ts';

function fixture(t, {hostname='127.0.0.1', width=0, hash, visibility='visible'}={}) {
  const state={now:0,width,posts:[],timers:[],frames:[],events:{},status:204};
  const location={hostname, hash:hash??`#toolkit-native-probe=${'a'.repeat(64)}&stage=1`};
  const globals={location, performance:{now:()=>state.now},
    document:{visibilityState:visibility,querySelector:()=>state.width?{getBoundingClientRect:()=>({width:state.width})}:null},
    window:{setTimeout:fn=>state.timers.push(fn),addEventListener:(name,fn)=>state.events[name]=fn},
    requestAnimationFrame:fn=>state.frames.push(fn),
    fetch:async(url,options)=>{
      assert.equal(url,'/api/native-browser-probe'); assert.equal(options.credentials,'omit');
      state.posts.push(JSON.parse(options.body));return {ok:state.status===204,status:state.status};
    }};
  for(const [name,value] of Object.entries(globals)) {
    const descriptor=Object.getOwnPropertyDescriptor(globalThis,name);
    Object.defineProperty(globalThis,name,{configurable:true,value});
    t.after(()=>descriptor?Object.defineProperty(globalThis,name,descriptor):delete globalThis[name]);
  }
  state.location=location;
  return state;
}

test('native handshake reports loading without accepting a missing reader',t=>{
  const state=fixture(t);observeNativeBrowserLaunch();
  assert.deepEqual(state.posts.map(x=>x.phase),['client-loaded','waiting-reader']);
  assert(!state.posts.some(x=>x.reader_ready));
  state.now=60001;state.timers.shift()();
  assert.equal(state.posts.at(-1).phase,'reader-timeout');
});

test('suspended animation frames remain diagnostic, never successful navigation',t=>{
  const state=fixture(t,{width:800,visibility:'hidden'});observeNativeBrowserLaunch();
  assert.equal(state.posts.at(-1).phase,'animation-frame-pending');
  assert.equal(state.posts.at(-1).visibility,'hidden');
  assert(!state.posts.some(x=>x.reader_ready));
  state.frames.shift()();assert(!state.posts.some(x=>x.reader_ready));
  state.frames.shift()();assert.equal(state.posts.at(-1).reader_ready,true);
});

test('replaced challenge cannot acknowledge an earlier browser stage',t=>{
  const state=fixture(t,{width:800});observeNativeBrowserLaunch();
  state.location.hash=state.location.hash.replace('stage=1','stage=2');
  state.frames.shift()();state.frames.shift()();
  assert(!state.posts.some(x=>x.reader_ready));
  state.events.hashchange();state.frames.shift()();state.frames.shift()();
  assert.deepEqual(state.posts.filter(x=>x.reader_ready).map(x=>x.stage),[2]);
});

test('normal and LAN readers never send native diagnostics',t=>{
  const state=fixture(t,{hostname:'192.168.1.2',width:800});observeNativeBrowserLaunch();
  assert.deepEqual(state.posts,[]);
  state.location.hostname='127.0.0.1';state.location.hash='';state.events.hashchange();
  assert.deepEqual(state.posts,[]);
});

test('failed acknowledgement reports a fixed network or HTTP phase',async t=>{
  const state=fixture(t,{width:800});state.status=403;observeNativeBrowserLaunch();
  state.frames.shift()();state.frames.shift()();
  await Promise.resolve();await Promise.resolve();
  assert.equal(state.posts.at(-1).phase,'ack-http-failed');
});
