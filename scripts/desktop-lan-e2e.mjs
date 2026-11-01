// Real browser + real gateway boundary. Only the game/account API is synthetic.
// Catches loopback URLs, missing pairing cookies, WS handoff and media/CSP failures
// that mocked page.route desktop checks cannot observe.
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {spawn, execFileSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';
import {networkInterfaces} from 'node:os';
import {join, resolve} from 'node:path';
import {chromium, firefox, webkit} from 'playwright';
import {startPreview, stopOwnedProcess} from './e2e-preview.mjs';
import {startRouter} from './companion-router.mjs';
import {resolvePython} from './python-runtime.mjs';
import {TONE} from '../tests/mobile-media-fixtures.mjs';

const address=Object.values(networkInterfaces()).flat().find(a=>a?.family==='IPv4'&&!a.internal&&
  /^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(a.address))?.address;
assert(address,'A private interface is required to verify a real LAN client');
execFileSync(process.execPath,['scripts/build-desktop-frontend.mjs'],{stdio:'pipe'});
const preview=await startPreview('desktop-lan'), requests=[], sockets=new Set();
const region={left:.1,top:.6,width:.8,height:.25};
let version=0, rows=[];
const context=()=>({runtime_id:'lan-fixture',state_version:version,account_generation:0});
const line=(id,text)=>({id,text_id:'lan-'+id,game:'zzz',session_id:'fixture',created_at:new Date().toISOString(),
  english:text,chinese:'这是共享的游戏对话。',source_ocr:text,score:100,match_kind:'exact',channel:'dialogue',
  voiced:true,voice_status:'voiced',has_audio:true,audio_source:'original',favorite:false});
const status=()=>({capture:{running:false,phase:'stopped',message:'Synthetic game',active_game:'zzz',visible_text_ids:rows.slice(0,1).map(x=>x.text_id)},
  textmaps:{ready:true,state:'ready',entry_count:2},game_textmaps:{zzz:{ready:true,state:'ready',entry_count:2}},
  settings:{preferred_game:'auto',region,tip_region:region,cinematic_region:region,process_names:[],window_title_contains:[],scan_interval_ms:250,stable_frames:2,fuzzy_threshold:82},
  audio:{ready:true},session:{id:'fixture',line_count:rows.length,total_line_count:rows.length}});
function jsonFrame(value){const body=Buffer.from(JSON.stringify(value)),header=Buffer.alloc(body.length<126?2:4);header[0]=0x81;
  if(body.length<126)header[1]=body.length;else{header[1]=126;header.writeUInt16BE(body.length,2);}return Buffer.concat([header,body]);}
function broadcast(row){version++;for(const socket of sockets)socket.write(jsonFrame({type:'line',line:row,context:context()}));}
function fixture(){
  const server=http.createServer(async(request,response)=>{
    const path=new URL(request.url,'http://fixture').pathname;requests.push(path);
    let result={};
    if(path==='/api/snapshot')result={context:context(),status:status(),lines:rows,lexirise:{configured:false,account:'legacy',decks:{},sent:{}}};
    else if(path==='/api/status')result=status();
    else if(path==='/api/lines')result=rows;
    else if(path==='/api/favorites')result=rows.filter(row=>row.favorite);
    else if(path.endsWith('/favorite')){
      let body='';for await(const chunk of request)body+=chunk;
      const row=rows.find(row=>row.id===Number(path.split('/')[3]));row.favorite=JSON.parse(body).favorite;broadcast(row);result=row;
    }else if(path.endsWith('/audio')){
      const bytes=Buffer.from(TONE,'base64'),range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range??'');
      const start=range?Number(range[1]):0,end=range&&range[2]?Math.min(Number(range[2]),bytes.length-1):bytes.length-1;
      response.writeHead(range?206:200,{'Content-Type':'audio/mpeg','Accept-Ranges':'bytes','Content-Length':end-start+1,
        ...(range?{'Content-Range':`bytes ${start}-${end}/${bytes.length}`}:{})});response.end(bytes.subarray(start,end+1));return;
    }else if(path.endsWith('/reading'))result={text:rows[0].chinese,tokens:[],grammar:[]};
    response.writeHead(200,{'Content-Type':'application/json'});response.end(JSON.stringify(result));
  });
  server.on('upgrade',(request,socket)=>{
    sockets.add(socket);socket.on('error',()=>{});socket.on('close',()=>sockets.delete(socket));
    const accept=createHash('sha1').update(request.headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n');
    socket.on('data',bytes=>{if((bytes[0]&15)===8)socket.end(Buffer.from([0x88,0]));});
  });return server;
}
const first=fixture(),second=fixture();let router,staticChild,browser;
const listen=server=>new Promise(done=>server.listen(0,'127.0.0.1',()=>done(server.address().port)));
const stopServer=server=>new Promise(done=>server.close(done));
async function staticFrontend(){
  staticChild=spawn(resolvePython({root:process.cwd()}).command,['-u','-m','backend.desktop_frontend','--root',resolve('output/desktop-frontend'),'--port','0'],
    {windowsHide:true,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
  return await new Promise((done,reject)=>{
    let text='',errors='';const timer=setTimeout(()=>reject(Error('Static frontend timeout: '+errors)),20000);
    staticChild.stderr.on('data',chunk=>{errors=(errors+chunk).slice(-2000);});
    staticChild.once('error',error=>{clearTimeout(timer);reject(error);});
    staticChild.once('exit',()=>{clearTimeout(timer);reject(Error('Static frontend exited: '+errors));});
    staticChild.stdout.on('data',chunk=>{text+=chunk;for(const entry of text.split('\n'))try{
      const value=JSON.parse(entry);if(value.ready){clearTimeout(timer);done(value.port);return;}
    }catch{}});
  });
}
try{
  const a=await listen(first),b=await listen(second),sourcePort=Number(new URL(preview.origin).port),staticPort=await staticFrontend();
  const statePath=join(preview.output,'runtime.json');
  const activate=(apiPort,frontendPort)=>writeFileSync(statePath,JSON.stringify({active:{apiPort,frontendPort}}));
  activate(a,sourcePort);router=await startRouter({statePath,apiPort:0,frontendPort:0});
  const base=`http://${address}:${router.frontendPort}`;
  const invitation=await(await fetch(`http://127.0.0.1:${router.frontendPort}/api/connection`)).json();
  assert(invitation.urls.includes(base));
  console.log('Source/static hosts and desktop gateway ready');
  for(const[name,engine,width,height]of [['chromium',chromium,390,844],['firefox',firefox,390,844],['webkit',webkit,768,1024]]){
    if(process.argv.some(arg=>arg.startsWith('--engine='))&&!process.argv.includes('--engine='+name))continue;
    rows=[line(1,'Shared desktop dialogue.')];version++;activate(a,sourcePort);
    browser=await preview.launchBrowser(engine,{headless:true});
    const ctx=await browser.newContext({viewport:{width,height}}),page=await ctx.newPage(),errors=[],loopback=[];
    await page.addInitScript(()=>{const OriginalAudio=window.Audio;window.Audio=class extends OriginalAudio{constructor(...args){super(...args);window.__lanAudio=this;}};});
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(/^https?:\/\/(127\.0\.0\.1|localhost)/.test(request.url()))loopback.push(request.url());});
    await page.goto(base);await page.getByLabel('Connection code').fill(invitation.code);
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    console.log(name+': entered pairing code');
    await page.locator('.current-line').getByText('Shared desktop dialogue.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,name+' LAN layout fits');
    const saved=page.waitForResponse(response=>response.url().endsWith('/api/lines/1/favorite'));
    await page.getByRole('button',{name:'Favorite current line',exact:true}).click();
    assert.equal((await saved).status(),200);
    await page.getByRole('button',{name:'Remove current line from favorites',exact:true}).waitFor();
    assert.equal(rows[0].favorite,true,'Phone writes the desktop favorite');
    // Windows WebKit can advertise MP3 yet its test media backend cannot decode
    // even a local owned blob. Probe actual bytes, not a canPlayType hint.
    const mp3=await page.evaluate(tone=>new Promise(resolve=>{
      const bytes=Uint8Array.from(atob(tone),c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:'audio/mpeg'})),audio=new Audio();
      const timer=setTimeout(()=>finish(false),5000);
      function finish(value){clearTimeout(timer);audio.pause();audio.removeAttribute('src');URL.revokeObjectURL(url);resolve(value);}
      audio.onloadeddata=()=>finish(true);audio.onerror=()=>finish(false);audio.src=url;audio.load();
    }),TONE);
    if(!mp3){assert(name==='webkit'&&process.platform==='win32','Unexpected missing MP3 decoder');console.log('Windows WebKit exposes no MP3 decoder; media transport verified below, playback unavailable.');}
    else{await page.getByRole('button',{name:'Play current voice line',exact:true}).click();
      try{await page.waitForFunction(()=>window.__lanAudio?.currentTime>0,{},{timeout:10000});}
      catch(error){console.error(await page.evaluate(()=>({media:window.__lanAudio&&{src:window.__lanAudio.src,code:window.__lanAudio.error?.code,message:window.__lanAudio.error?.message,network:window.__lanAudio.networkState,ready:window.__lanAudio.readyState},errors:[]})),requests.slice(-12),errors);throw error;}}
    const range=await page.evaluate(async()=>{const response=await fetch('/api/lines/1/audio',{headers:{Range:'bytes=0-99'}});return{status:response.status,length:(await response.arrayBuffer()).byteLength};});
    assert.deepEqual(range,{status:206,length:100},'Voice seeking keeps byte ranges');
    rows.unshift(line(2,'The next line arrived live.'));broadcast(rows[0]);
    await page.locator('.current-line').getByText('The next line arrived live.',{exact:true}).waitFor({timeout:4000});
    // Switch to the exact no-Node frontend while leaving the public origin/cookie intact.
    activate(b,staticPort);await page.reload();
    await page.locator('.current-line').getByText('The next line arrived live.',{exact:true}).waitFor();
    await page.locator('.transcript-view-toggle').click();
    await page.locator('.transcript-line').getByText('Shared desktop dialogue.',{exact:true}).waitFor();
    assert.equal((await ctx.cookies()).some(cookie=>cookie.name==='toolkit_device'&&cookie.httpOnly),true,'Pairing survives runtime activation');
    rows.unshift(line(3,'Live after the desktop update.'));broadcast(rows[0]);
    await page.locator('.current-line').getByText('Live after the desktop update.',{exact:true}).waitFor({timeout:4000});
    assert.equal(loopback.length,0,'Remote browser never contacts its own loopback');
    assert.deepEqual(errors,[],name+' source/static runtime has no browser exceptions');
    await page.screenshot({path:join(preview.output,name+'-lan.png')});
    if(name==='chromium'){
      await page.goto(base+'/mobile-capture/');await page.locator('.desktop-connect > summary').click();
      await page.getByLabel('Desktop address and port').fill(base);
      await page.getByRole('button',{name:'Open desktop transcript'}).click();
      await page.locator('.current-line').getByText('Live after the desktop update.',{exact:true}).waitFor();
    }
    await ctx.close();await browser.close();browser=null;console.log(name+': paired LAN, shared favorites/audio, live updates and static frontend passed');
  }
}catch(error){console.error(error);console.error(preview.diagnostics());throw error;}finally{
  await browser?.close();await router?.close();if(staticChild?.exitCode===null)await stopOwnedProcess(staticChild);
  for(const socket of sockets)socket.destroy();await Promise.all([stopServer(first),stopServer(second)]);await preview.stop();
}
