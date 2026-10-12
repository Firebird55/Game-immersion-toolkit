import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve, sep } from 'node:path';
import {createHash} from 'node:crypto';
import {zipSync,strToU8} from 'fflate';
import {ocrAssets,mime} from './mobile-assets.mjs';
import {pairingMessage} from '../public/mobile-capture/core.mjs';
const { chromium, firefox, webkit } = await import(process.env.PLAYWRIGHT_MODULE_PATH ? pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href : 'playwright');

const root = process.env.MOBILE_PREVIEW_DIR ? pathToFileURL(resolve(process.env.MOBILE_PREVIEW_DIR) + sep) : new URL('../public/mobile-capture/', import.meta.url);
const files = new Map(readdirSync(root).map(name => [`/${name}`, name]));
const ocr=ocrAssets();
files.set('/', 'index.html');
const expectedBuild = files.has('/build.json') ? JSON.parse(readFileSync(new URL('build.json', root), 'utf8')) : null;
const server = http.createServer((req, res) => {
  const file = files.get(new URL(req.url, 'http://localhost').pathname);
  const extra=ocr.get(new URL(req.url,'http://localhost').pathname.slice(1));
  if (!file&&!extra) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', mime(file??req.url));
  res.end(extra??readFileSync(new URL(file, root)));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
const qrModule=[...files.keys()].find(path=>/^\/qr-pairing(?:\.[a-f0-9]+)?\.mjs$/.test(path));
mkdirSync('output/playwright', { recursive: true });
const libraryId='a'.repeat(64),libraryRow={id:libraryId,textId:'reconnect-check',english:'The lantern is bright.',chinese:'灯笼很亮。',sourceVoice:libraryId,audio:null,channels:['dialogue']},libraryRows=strToU8(JSON.stringify(libraryRow)+'\n');
const reconnectLibrary=Buffer.from(zipSync({'manifest.json':strToU8(JSON.stringify({format:'proxy-mobile-library-v1',kind:'catalog',game:'zzz',title:'Synthetic reconnect verification',revision:libraryId,coverage:{dialogue:1},catalog:[{name:'catalog/00000.ndjson',size:libraryRows.length,sha256:createHash('sha256').update(libraryRows).digest('hex')}],packs:[]})),'catalog/00000.ndjson':libraryRows},{level:0}));
async function downloadReport(page) {
  const pending = page.waitForEvent('download');
  await page.click('#report');
  return JSON.parse(readFileSync(await (await pending).path(), 'utf8'));
}
async function verifyQrRendering(page){
  const text=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:90},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n')},'zzz',{sessionId:'qr-render-session-fixture',pairingId:'qr-render-pairing-fixture',attempt:1});
  await page.evaluate(message=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message}})),text);
  await page.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  assert.equal(await page.locator('#pairing-qr').getAttribute('data-total'),'1');
  assert(await page.locator('#qr-pause').isDisabled());
  const decoded=await page.evaluate(async modulePath=>{
    const {default:jsQR}=await import('./pairing/jsqr.mjs'),{PairingQrReader}=await import(modulePath);
    const canvas=document.querySelector('#pairing-qr'),pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height);
    const code=jsQR(pixels.data,canvas.width,canvas.height);if(!code)throw Error('Rendered QR could not decode');
    return (await new PairingQrReader().accept(code.data,'offer')).message;
  },qrModule);
  assert.equal(decoded,text);
  await page.click('#qr-enlarge');
  for(const viewport of [{width:390,height:844},{width:320,height:568},{width:568,height:320}]){
    await page.setViewportSize(viewport);
    assert(await page.locator('#qr-large-dialog').evaluate(d=>d.open&&d.scrollWidth<=d.clientWidth+1));
    const box=await page.locator('#pairing-qr').boundingBox();assert(box&&box.width>200&&box.height>200);
  }
  await page.click('#qr-enlarge');await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:''}})));
}
async function transferQr(source,target){
  await source.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  assert.equal(await source.locator('#pairing-qr').getAttribute('data-total'),'1','Typical real WebRTC offers and replies use one static compact QR');
  await source.click('#qr-enlarge');
  assert(await source.locator('#qr-large-dialog').evaluate(d=>d.open));
  for(const viewport of [{width:390,height:844},{width:320,height:568},{width:568,height:320}]){
    await source.setViewportSize(viewport);
    assert(await source.locator('#qr-large-dialog').evaluate(d=>d.scrollWidth<=d.clientWidth+1),'Large QR fits portrait and landscape without horizontal scrolling');
    const box=await source.locator('#pairing-qr').boundingBox();assert(box&&box.width>200&&box.height>200,'Large QR remains usable on a small phone');
  }
  await source.setViewportSize({width:390,height:844});
  const portrait=await source.locator('#role').inputValue()==='receiver';
  await target.evaluate(portrait=>{
    const canvas=document.createElement('canvas');canvas.width=portrait?1080:1920;canvas.height=portrait?1920:1080;window.syntheticQrCamera=canvas;
    navigator.mediaDevices.getUserMedia=async()=>{const stream=canvas.captureStream(10);window.syntheticCameraTracks=stream.getTracks();return stream;};
  },portrait);
  await target.click('#scan-pairing');
  const expected=await source.locator('#outgoing').inputValue();let complete=false;
  for(let i=0;i<50;i++){
    const image=await source.evaluate(()=>document.querySelector('#pairing-qr').toDataURL());
    if(i===20)assert((await target.locator('#qr-feedback').textContent()).includes('Use Larger QR'),'An unreadable small image gives camera-distance recovery guidance');
    await target.evaluate(async({url,size})=>{const image=new Image();image.src=url;await image.decode();const canvas=window.syntheticQrCamera,context=canvas.getContext('2d');context.fillStyle='#bbb';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,(canvas.width-size)/2,(canvas.height-size)/2,size,size);},{url:image,size:i<20?320:512});
    await target.waitForTimeout(200);
    if(await target.locator('#incoming').inputValue()===expected||await target.locator('#qr-feedback').textContent().then(v=>v.includes('Pairing QR read.'))){complete=true;break;}
  }
  if(!complete)console.error('QR scan diagnostics',await target.evaluate(()=>{const v=document.querySelector('#qr-camera');return {hidden:document.hidden,panelHidden:document.querySelector('#qr-scan-panel').hidden,width:v.videoWidth,height:v.videoHeight,time:v.currentTime,ready:v.readyState};}),await source.evaluate(async()=>{const {default:jsQR}=await import('./pairing/jsqr.mjs'),source=document.querySelector('#pairing-qr'),read=size=>{const c=document.createElement('canvas');c.width=c.height=size;const x=c.getContext('2d');x.drawImage(source,0,0,size,size);return !!jsQR(x.getImageData(0,0,size,size).data,size,size);};return {native:read(source.width),small:read(320),larger:read(384)};}));
  assert(complete,'The camera reads the complete pairing QR: '+await target.locator('#qr-feedback').textContent());
  assert(await target.evaluate(()=>window.syntheticCameraTracks.every(track=>track.readyState==='ended')),'Camera stops after reading the pairing message');
  await source.click('#qr-enlarge');
  assert(await source.locator('#qr-large-dialog').evaluate(d=>!d.open));
}
async function verifyPartialScan(source,target){
  const message=pairingMessage({type:'offer',sdp:'v=0\r\n'+Array.from({length:500},(_,i)=>`a=fixture:${i}:${Math.sin(i)}`).join('\r\n')},'zzz',{sessionId:'partial-session-fixture',pairingId:'partial-pairing-fixture',attempt:1});
  await source.evaluate(message=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message}})),message);
  await source.waitForFunction(()=>!document.querySelector('#qr-panel').hidden);
  const total=Number(await source.locator('#pairing-qr').getAttribute('data-total'));assert(total>1);
  await source.click('#qr-pause');
  await target.evaluate(()=>{
    const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;window.syntheticQrCamera=canvas;
    navigator.mediaDevices.getUserMedia=async()=>{const stream=canvas.captureStream(10);window.syntheticCameraTracks=stream.getTracks();return stream;};
    document.querySelector('#apply').addEventListener('click',event=>{event.stopImmediatePropagation();},{capture:true,once:true}); // This transport-only fixture is not real SDP.
  });
  const show=async()=>{const image=await source.locator('#pairing-qr').evaluate(c=>c.toDataURL());await target.evaluate(async url=>{const image=new Image();image.src=url;await image.decode();const canvas=window.syntheticQrCamera,ctx=canvas.getContext('2d');ctx.fillStyle='#bbb';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,448,168,384,384);},image);};
  await target.click('#scan-pairing');await show();
  await target.waitForFunction(()=>document.querySelector('#qr-feedback').textContent.startsWith('Read 1 of '));
  assert((await target.locator('#qr-feedback').textContent()).includes('Still need QR 2'));
  await target.click('#stop-scan');assert((await target.locator('#qr-feedback').textContent()).includes('1 of '+total+' frames kept'));
  await target.click('#scan-pairing');await show();
  await target.waitForFunction(()=>document.querySelector('#qr-feedback').textContent.startsWith('Read 1 of '));
  const held=await source.locator('#pairing-qr').getAttribute('data-frame');await source.waitForTimeout(3200);
  assert.equal(await source.locator('#pairing-qr').getAttribute('data-frame'),held,'Paused QR stays still long enough for camera focus');
  for(let i=2;i<=total;i++){
    await source.click('#qr-next');await show();
    if(i<total)await target.waitForFunction(n=>document.querySelector('#qr-feedback').textContent.startsWith(`Read ${n} of `),i);
  }
  await target.waitForFunction(message=>document.querySelector('#incoming').value===message,message);
  assert(await target.evaluate(()=>window.syntheticCameraTracks.every(t=>t.readyState==='ended')));
  for(const page of [source,target])await page.evaluate(()=>window.dispatchEvent(new CustomEvent('mobile-pairing-message',{detail:{message:''}})));
}
function assertPrivateDiagnostics(report, role, successfulAttempt) {
  assert.equal(report.format, 'proxy-mobile-capture-report-v1');
  assert.equal(report.role, role);
  assert(Array.isArray(report.diagnostics.tracks) && report.diagnostics.tracks.length > 0, 'Report includes track lifecycle diagnostics');
  assert(Array.isArray(report.diagnostics.rtcSamples) && report.diagnostics.rtcSamples.length > 0, 'Report includes bounded RTC measurements');
  assert(report.diagnostics.rtcSamples.length <= 120, 'RTC history stays bounded');
  assert(report.diagnostics.recoveryAttempts >= 1, 'Report records recovery attempts');
  const inspect = value => {
    if (!value || typeof value !== 'object') return;
    for (const [key, item] of Object.entries(value)) {
      assert(!/^(?:id|trackId|streamId|deviceId|groupId|label|sdp|sessionId|pairingId|address|ip|localAddress|remoteAddress|candidate|localCandidateId|remoteCandidateId|ssrc|codecId|transportId|remoteId|trackIdentifier|url|usernameFragment)$/i.test(key), `Diagnostic excludes connection or device identifier ${key}`);
      inspect(item);
    }
  };
  inspect(report.diagnostics);
  assert(!JSON.stringify(report).includes('v=0'), 'Report excludes SDP');
  for (const sample of report.diagnostics.rtcSamples) {
    assert.equal(typeof sample.at, 'string', 'RTC samples are timestamped');
    assert.equal(sample.role, role);
    assert(Array.isArray(sample.records) && sample.records.length <= 8);
    for (const record of sample.records) for (const [key, value] of Object.entries(record)) {
      if (key !== 'direction') assert.equal(typeof value, 'number', 'Selected RTC measurements contain numeric counters only');
    }
  }
  assert(report.diagnostics.rtcSamples.some(sample => sample.attempt === successfulAttempt && sample.records.some(record => role === 'sender' ? record.bytesSent > 0 : record.bytesReceived > 0)), 'Report measures real video transport after recovery');
}
let browser;
try {
  for (const [name, engine] of [['chromium', chromium], ['firefox', firefox]]) {
    browser = await engine.launch({ headless: true });
    const errors = [];
    const context = await browser.newContext({ acceptDownloads: true });
    context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
    const sender = await context.newPage(), receiver = await context.newPage();
    for (const page of [sender, receiver]) await page.addInitScript(() => {
      const NativePeer = window.RTCPeerConnection;
      window.testPeers = [];
      // Retain the real implementation. These handles only let tests simulate
      // a lost peer and delay one async step without a production test hook.
      window.RTCPeerConnection = class extends NativePeer {
        constructor(options) { super(options); window.testPeer = this; window.testPeers.push(this); }
        async createOffer(options) {
          if (window.failNextOffer) { window.failNextOffer = false; throw new Error('Synthetic offer failure'); }
          return super.createOffer(options);
        }
        async setLocalDescription(description) {
          await super.setLocalDescription(description);
          if (window.stallLocalDescription) {
            window.stallLocalDescription = false;
            window.stalledDescriptionCompleted = false;
            await new Promise(resolve => { window.releaseLocalDescription = resolve; });
            window.stalledDescriptionCompleted = true;
          }
        }
      };
      const nativeRequest = HTMLVideoElement.prototype.requestVideoFrameCallback;
      const nativeCancel = HTMLVideoElement.prototype.cancelVideoFrameCallback;
      if (nativeRequest && nativeCancel) {
        window.pendingFrameCallbacks = new Set(); window.maximumFrameCallbacks = 0;
        HTMLVideoElement.prototype.requestVideoFrameCallback = function(callback) {
          let handle;
          handle = nativeRequest.call(this, (time, metadata) => {
            window.pendingFrameCallbacks.delete(handle); callback(time, metadata);
          });
          window.pendingFrameCallbacks.add(handle);
          window.maximumFrameCallbacks = Math.max(window.maximumFrameCallbacks, window.pendingFrameCallbacks.size);
          return handle;
        };
        HTMLVideoElement.prototype.cancelVideoFrameCallback = function(handle) {
          window.pendingFrameCallbacks.delete(handle); return nativeCancel.call(this, handle);
        };
      }
    });
    // Synthetic capture supplies pixels only. Pairing uses real browser WebRTC.
    await sender.addInitScript(() => {
      window.captureRequests = 0;
      navigator.mediaDevices.getDisplayMedia = async () => {
        window.captureRequests++;
        if (window.denyCapture) throw new DOMException('Permission denied', 'NotAllowedError');
        const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
        const ctx = canvas.getContext('2d'); let i = 0;
        setInterval(() => {
          ctx.fillStyle = window.blackCapture ? '#000' : `rgb(${i++ % 255},100,180)`;
          ctx.fillRect(0, 0, 640, 360);
          if (!window.blackCapture) { ctx.fillStyle = '#fff'; ctx.font = '32px sans-serif'; ctx.fillText('Game subtitle fixture', 60, 280); }
        }, 100);
        window.capturedStream = canvas.captureStream(10);
        return window.capturedStream;
      };
    });
    await sender.goto(url); await receiver.goto(url);
    // An unsupported gaming-device browser must remain a sender with capture
    // disabled; the receiver can still accept a supported sender's offer.
    const unsupported = await context.newPage();
    await unsupported.addInitScript(() => { navigator.mediaDevices.getDisplayMedia = undefined; });
    await unsupported.goto(url);
    assert.equal(await unsupported.locator('#role').inputValue(), 'sender');
    assert.equal(await unsupported.locator('#start').isEnabled(), false);
    assert.equal(await unsupported.locator('#reconnect').isEnabled(), false);
    assert.match(await unsupported.locator('#instructions').innerText(), /native capture helper/i);
    await unsupported.selectOption('#role', 'receiver');
    assert.equal(await unsupported.locator('#start').isVisible(), false);
    assert.equal(await unsupported.locator('#reconnect').isVisible(), false);
    assert.equal(await unsupported.locator('#apply').isEnabled(), true);
    await unsupported.close();
    if (expectedBuild) {
      assert.match(await receiver.locator('#build-info').innerText(), new RegExp(expectedBuild.commit.slice(0, 8)));
      // Google Drive can add desktop.ini to a local package. It is not one of
      // the copied publication files and is absent on the Linux publisher.
      const names = readdirSync(root).filter(name => name !== 'desktop.ini').sort();
      assert.equal(names.length, 22, 'Publication contains only the allowlisted application, QR and OCR assets');
      assert(names.every(name => /^(index\.html|build\.json|\.nojekyll|sw\.js|ocr|pairing|(?:capture|core|relay|recovery-config|qr-pairing|qr-render|qr-ui|style|library|storage|library-worker|mobile-ui|ocr-pipeline|icon|manifest)\.[0-9a-f]{16}\.(?:js|mjs|json|css|svg|png|webmanifest))$/.test(name)));
    }
    for (const [width, height, scale] of [[320, 568, 1], [390, 844, 1], [768, 1024, 1], [1920, 1080, 2]]) {
      await receiver.setViewportSize({ width, height });
      await receiver.evaluate(scale => { document.body.style.zoom = String(scale); }, scale);
      assert(await receiver.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}: layout fits ${width}, zoom ${scale}`);
    }
    await receiver.evaluate(() => { document.body.style.zoom = '1'; });
    await receiver.setViewportSize({ width: 390, height: 844 });
    await receiver.selectOption('#role', 'receiver');
    await receiver.setInputFiles('#library-files',{name:'synthetic.zip',mimeType:'application/zip',buffer:reconnectLibrary});
    await receiver.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('1 bilingual rows'));
    await receiver.fill('#find-text',libraryRow.english);await receiver.click('#find-line');
    await receiver.getByRole('button',{name:'Favorite',exact:true}).click();
    await receiver.fill('#incoming', '{invalid'); await receiver.click('#apply');
    assert.match(await receiver.locator('#status').innerText(), /valid pairing/);
    await sender.evaluate(() => { window.denyCapture = true; });
    await sender.click('#start');
    await sender.getByText('Cannot start capture: Permission denied', { exact: true }).waitFor();
    assert.equal(await sender.locator('#start').isEnabled(), true);
    await sender.evaluate(() => { window.denyCapture = false; });
    await verifyQrRendering(sender);
    await verifyPartialScan(sender,receiver);
    await sender.click('#start');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    const originalOfferText = await sender.locator('#outgoing').inputValue();
    const originalOffer = JSON.parse(originalOfferText);
    assert.equal(typeof originalOffer.sessionId, 'string');
    assert.equal(typeof originalOffer.pairingId, 'string');
    assert.equal(originalOffer.attempt, 1);
    await sender.evaluate(() => { window.originalCaptureTrack = window.capturedStream.getVideoTracks()[0]; });
    await transferQr(sender,receiver);
    await receiver.waitForFunction(() => document.getElementById('outgoing').value.includes('"answer"'));
    const originalAnswerText = await receiver.locator('#outgoing').inputValue();
    const originalAnswer = JSON.parse(originalAnswerText);
    for (const field of ['sessionId', 'pairingId', 'attempt']) assert.equal(originalAnswer[field], originalOffer[field], `Answer echoes ${field}`);
    await transferQr(receiver,sender);
    await receiver.bringToFront();
    assert.equal(await receiver.locator('#reload-build').isEnabled(), false, 'Updating cannot interrupt an active session');
    await receiver.waitForFunction(() => document.getElementById('preview').videoWidth > 0, { timeout: 20000 });
    try {
      await receiver.waitForFunction(() => /Receiving frames/.test(document.getElementById('metrics').textContent));
    } catch (error) {
      console.error(name, await receiver.evaluate(() => ({ metrics: document.getElementById('metrics').textContent, status: document.getElementById('status').textContent, paused: document.getElementById('preview').paused, time: document.getElementById('preview').currentTime, hidden: document.hidden })));
      throw error;
    }
    await receiver.click('#begin-test');
    await receiver.waitForFunction(() => /[1-9][0-9]* visible changes/.test(document.getElementById('metrics').textContent));
    await receiver.fill('#notes', 'Synthetic test: recover the same capture without restarting the observation.');
    await receiver.selectOption('#result', 'game_visible');
    await receiver.evaluate(() => { window.originalReceiverPeer = window.testPeer; window.originalReceivedStream = document.getElementById('preview').srcObject; });
    // Replaying a consumed offer must not tear down an otherwise live stream.
    await receiver.fill('#incoming', originalOfferText); await receiver.click('#apply');
    assert.match(await receiver.locator('#status').innerText(), /older|stale|already|duplicate|newer/i);
    assert(await receiver.evaluate(() => window.testPeer === window.originalReceiverPeer && document.getElementById('preview').srcObject === window.originalReceivedStream));
    assert.equal(await receiver.locator('#begin-test').isEnabled(), false, 'Rejected messages preserve the running observation');
    // Even a newer same-session offer cannot silently switch a live game.
    const wrongGame = { ...originalOffer, game: 'wuwa', attempt: originalOffer.attempt + 1, pairingId: 'wrong-game-pairing-fixture' };
    await receiver.fill('#incoming', JSON.stringify(wrongGame)); await receiver.click('#apply');
    assert.match(await receiver.locator('#status').innerText(), /different game|game.*match|game.*changed/i);
    assert(await receiver.evaluate(() => window.testPeer === window.originalReceiverPeer && document.getElementById('preview').srcObject === window.originalReceivedStream));
    await sender.evaluate(() => {
      Object.defineProperty(window.originalCaptureTrack, 'muted', { configurable: true, value: true });
      window.originalCaptureTrack.dispatchEvent(new Event('mute'));
    });
    assert.match(await sender.locator('#capture-state').innerText(), /muted/i);
    await sender.evaluate(() => {
      Object.defineProperty(window.originalCaptureTrack, 'muted', { configurable: true, value: false });
      window.originalCaptureTrack.dispatchEvent(new Event('unmute'));
    });
    assert.match(await sender.locator('#capture-state').innerText(), /live/i);
    await receiver.screenshot({ path: `output/playwright/mobile-capture-${name}.png`, fullPage: true });
    await sender.evaluate(() => { window.blackCapture = true; });
    await receiver.waitForFunction(() => document.getElementById('metrics').textContent.includes('Image appears black'));
    const report = await downloadReport(receiver);
    assert(report.deliveredFrames > 0 && report.visibleChanges > 0);
    assert(report.observation.frames > 0 && report.observation.darkSamples > 0);
    assert.equal(report.backgroundCaptureVerified, false);
    assert.equal(report.userObservation, 'game_visible');
    assert.equal(report.build?.commit ?? null, expectedBuild?.commit ?? null, 'Report records the version actually loaded');
    assert(!JSON.stringify(report).includes('v=0'), 'Report excludes SDP');
    // A connection loss does not end the source capture. The next offer uses
    // fresh peers and attempt identifiers with the exact same captured track.
    for (const page of [sender, receiver]) await page.evaluate(() => {
      window.testPeer.close(); window.testPeer.dispatchEvent(new Event('connectionstatechange'));
    });
    assert.equal(await sender.locator('#reconnect').isEnabled(), true, 'Recovery remains available after peer loss');
    assert.match(await sender.locator('#capture-state').innerText(), /live/i);
    await sender.evaluate(() => { window.blackCapture = false; });
    await sender.click('#reconnect');
    await sender.waitForFunction(old => {
      const value = document.getElementById('outgoing').value;
      return value && JSON.parse(value).pairingId !== old;
    }, originalOffer.pairingId);
    let recoveryOfferText = await sender.locator('#outgoing').inputValue();
    let recoveryOffer = JSON.parse(recoveryOfferText);
    assert.equal(recoveryOffer.sessionId, originalOffer.sessionId, 'Same capture retains the session');
    assert.equal(recoveryOffer.attempt, originalOffer.attempt + 1);
    assert.notEqual(recoveryOffer.pairingId, originalOffer.pairingId);
    assert(await sender.evaluate(() => window.captureRequests === 2 && window.capturedStream.getVideoTracks()[0] === window.originalCaptureTrack && window.originalCaptureTrack.readyState === 'live'), 'Recovery does not request capture again or replace its track');
    await sender.fill('#incoming', originalAnswerText); await sender.click('#apply');
    assert.match(await sender.locator('#status').innerText(), /older|stale|different|match|previous|latest/i);
    assert(await sender.locator('#outgoing').inputValue() === recoveryOfferText, 'Stale answers preserve the new pending offer without logging connection details');
    // Invalid actual SDP can pass the JSON envelope checks. A failed replace
    // must preserve the session and observation, while keeping setup locked.
    const failedRecoveryOfferText = recoveryOfferText;
    await receiver.fill('#incoming', JSON.stringify({ ...recoveryOffer, sdp: 'v=0\r\nThis is invalid SDP\r\n' }));
    await receiver.click('#apply');
    await receiver.waitForFunction(() => /Pairing could not complete/.test(document.getElementById('status').textContent));
    assert.equal(await receiver.locator('#role').isEnabled(), false);
    assert.equal(await receiver.locator('#game').isEnabled(), false);
    assert.equal(await receiver.locator('#reload-build').isEnabled(), false);
    assert.equal(await receiver.locator('#stop').isEnabled(), true);
    assert(await receiver.evaluate(() => window.testPeer.connectionState === 'closed' && document.getElementById('preview').srcObject === null));
    await receiver.waitForFunction(() => /No frames received|Frame delivery stalled/.test(document.getElementById('metrics').textContent));
    const failedReceiverReport = await downloadReport(receiver);
    assert.equal(failedReceiverReport.observation.startedAt, report.observation.startedAt);
    assert.equal(failedReceiverReport.observation.endedAt, null);
    assert(failedReceiverReport.observation.stalledSamples > report.observation.stalledSamples, 'Failed pairing remains part of the ongoing observation');
    assert.equal(failedReceiverReport.notes, report.notes);
    const failedAttempt = recoveryOffer.attempt;
    await sender.click('#reconnect');
    await sender.waitForFunction(attempt => {
      const value = document.getElementById('outgoing').value;
      return value && JSON.parse(value).attempt > attempt;
    }, failedAttempt);
    recoveryOfferText = await sender.locator('#outgoing').inputValue(); recoveryOffer = JSON.parse(recoveryOfferText);
    assert.equal(recoveryOffer.sessionId, originalOffer.sessionId);
    assert.equal(recoveryOffer.attempt, failedAttempt + 1);
    assert(await sender.evaluate(() => window.captureRequests === 2 && window.capturedStream.getVideoTracks()[0] === window.originalCaptureTrack && window.originalCaptureTrack.readyState === 'live'));
    await receiver.fill('#incoming', recoveryOfferText); await receiver.click('#apply');
    await receiver.waitForFunction(id => {
      const value = document.getElementById('outgoing').value;
      return value && JSON.parse(value).pairingId === id;
    }, recoveryOffer.pairingId);
    const recoveryAnswerText = await receiver.locator('#outgoing').inputValue();
    const recoveryAnswer = JSON.parse(recoveryAnswerText);
    for (const field of ['sessionId', 'pairingId', 'attempt']) assert.equal(recoveryAnswer[field], recoveryOffer[field], `Recovery answer echoes ${field}`);
    await sender.fill('#incoming', recoveryAnswerText); await sender.click('#apply');
    await receiver.bringToFront();
    await receiver.waitForFunction(old => {
      const metrics = document.getElementById('metrics').textContent;
      const frames = Number(metrics.match(/(\d+) delivered frames/)?.[1] ?? 0);
      const changes = Number(metrics.match(/(\d+) visible changes/)?.[1] ?? 0);
      return /Receiving frames/.test(metrics) && frames > old.frames && changes > old.changes && !/Image appears black/.test(metrics);
    }, { frames: report.deliveredFrames, changes: report.visibleChanges }, { timeout: 20000 });
    assert.equal(await receiver.locator('#notes').inputValue(), report.notes, 'Recovery preserves test notes');
    assert.equal(await receiver.locator('#result').inputValue(), 'game_visible', 'Recovery preserves the manual result');
    assert.equal(await receiver.locator('#begin-test').isEnabled(), false, 'Recovery preserves the observation rather than enabling a new one');
    if (await receiver.evaluate(() => Boolean(window.pendingFrameCallbacks))) assert.equal(await receiver.evaluate(() => window.maximumFrameCallbacks), 1, 'Recovery keeps exactly one frame monitor');
    await receiver.evaluate(() => { window.recoveredReceiverPeer = window.testPeer; window.recoveredReceivedStream = document.getElementById('preview').srcObject; });
    for (const duplicate of [originalOfferText, failedRecoveryOfferText, recoveryOfferText]) {
      await receiver.fill('#incoming', duplicate); await receiver.click('#apply');
      assert.match(await receiver.locator('#status').innerText(), /older|stale|already|duplicate|newer/i);
      assert(await receiver.evaluate(() => window.testPeer === window.recoveredReceiverPeer && document.getElementById('preview').srcObject === window.recoveredReceivedStream), 'Old or duplicate offers preserve the recovered stream');
    }
    await sender.waitForFunction(() => /sample|sent|sending|RTC|network/i.test(document.getElementById('diagnostics').textContent));
    await receiver.evaluate(() => document.getElementById('preview').pause());
    await receiver.waitForFunction(() => document.getElementById('metrics').textContent.includes('Frame delivery stalled'));
    await receiver.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
    await receiver.waitForFunction(() => !document.getElementById('preview').paused && document.getElementById('metrics').textContent.includes('Receiving frames'));
    assert(await receiver.evaluate(() => window.testPeer === window.recoveredReceiverPeer && document.getElementById('preview').srcObject === window.recoveredReceivedStream),'Returning resumes live playback without replacing the connection');
    const senderReport = await downloadReport(sender), recoveredReport = await downloadReport(receiver);
    assertPrivateDiagnostics(senderReport, 'sender', recoveryOffer.attempt); assertPrivateDiagnostics(recoveredReport, 'receiver', recoveryOffer.attempt);
    assert(senderReport.events.some(event => event.kind === 'track_muted') && senderReport.events.some(event => event.kind === 'track_unmuted'), 'Capture mute transitions are recorded');
    assert.equal(recoveredReport.observation.startedAt, report.observation.startedAt, 'Recovery retains observation start time');
    assert.equal(recoveredReport.observation.endedAt, null, 'Connection loss does not end the observation');
    assert(recoveredReport.observation.frames > report.observation.frames, 'Observation counts continue after recovery');
    assert(recoveredReport.observation.changes > report.observation.changes, 'Visible changes continue after recovery');
    assert.match(await receiver.locator('#library-status').innerText(),/1 bilingual rows/,'Reconnect preserves the open catalog');
    assert.equal(await receiver.locator('.transcript-chinese').textContent(),libraryRow.chinese,'Reconnect preserves transcript history');
    assert.equal(await receiver.getByRole('button',{name:'Unfavorite',exact:true}).count(),1,'Reconnect preserves favorites');
    const privateValues = [originalOffer.sessionId, originalOffer.pairingId, recoveryOffer.pairingId, await sender.evaluate(() => window.originalCaptureTrack.id)];
    for (const output of [senderReport, recoveredReport]) for (const value of privateValues) assert(!JSON.stringify(output).includes(value), 'Report excludes pairing and capture identifiers');
    await receiver.click('#stop');
    assert.match(await receiver.locator('#metrics').innerText(), /^Stopped/);
    assert.equal(await receiver.locator('#role').isEnabled(), true);
    assert.equal(await receiver.locator('#outgoing').inputValue(), '');
    assert.equal(await receiver.locator('#begin-test').isEnabled(), false);
    assert.equal(await receiver.locator('#reload-build').isEnabled(), true);
    await receiver.click('#reload-build');
    await receiver.waitForURL(/\?v=\d+/);
    await sender.click('#stop');
    assert(await sender.evaluate(() => window.originalCaptureTrack.readyState === 'ended'), 'Stop finishes the retained source capture');
    assert.equal(await sender.locator('#reconnect').isEnabled(), false);
    // Stop must also cancel an in-flight recovery before a late async result.
    await sender.click('#start');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    const secondOffer = JSON.parse(await sender.locator('#outgoing').inputValue());
    assert.notEqual(secondOffer.sessionId, originalOffer.sessionId, 'New capture has a new session');
    assert.equal(secondOffer.attempt, 1);
    await sender.evaluate(() => { window.stallLocalDescription = true; });
    await sender.click('#reconnect');
    await sender.waitForFunction(() => typeof window.releaseLocalDescription === 'function');
    await sender.click('#stop');
    await sender.evaluate(() => { window.releaseLocalDescription(); });
    await sender.waitForFunction(() => window.stalledDescriptionCompleted);
    await sender.waitForFunction(() => window.testPeers.every(peer => peer.connectionState === 'closed'));
    assert.equal(await sender.locator('#outgoing').inputValue(), '', 'Late recovery completion cannot republish a stopped offer');
    assert.match(await sender.locator('#status').innerText(), /stopped/i);
    assert(await sender.evaluate(() => window.capturedStream.getTracks().every(track => track.readyState === 'ended')));
    assert.equal(await sender.locator('#reconnect').isEnabled(), false);
    assert.equal(await sender.locator('#start').isEnabled(), true);
    // Ending the final captured track requires a new capture, not a reconnect.
    await sender.click('#start');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    const endedSession = JSON.parse(await sender.locator('#outgoing').inputValue()).sessionId;
    const requestsBeforeEnding = await sender.evaluate(() => window.captureRequests);
    await sender.evaluate(() => { window.failNextOffer = true; });
    await sender.click('#reconnect');
    await sender.waitForFunction(() => /Reconnect could not prepare an offer/.test(document.getElementById('status').textContent));
    assert.equal(await sender.locator('#outgoing').inputValue(), '');
    assert.equal(await sender.locator('#start').isEnabled(), false);
    assert.equal(await sender.locator('#reconnect').isEnabled(), true);
    assert(await sender.evaluate(() => window.testPeer.connectionState === 'closed' && window.capturedStream.getTracks().every(track => track.readyState === 'live')));
    assert.equal(await sender.evaluate(() => window.captureRequests), requestsBeforeEnding, 'Failed offer still retains capture without a new permission request');
    await sender.evaluate(() => { const track = window.capturedStream.getVideoTracks()[0]; track.stop(); track.dispatchEvent(new Event('ended')); });
    assert.match(await sender.locator('#capture-state').innerText(), /ended/i);
    assert.equal(await sender.locator('#reconnect').isEnabled(), false);
    assert.equal(await sender.locator('#resume-share').isVisible(), true);
    assert.equal(await sender.locator('#resume-share').isEnabled(), true);
    assert.equal(await sender.locator('#outgoing').inputValue(), '');
    const endedSenderReport = await downloadReport(sender);
    assert(endedSenderReport.events.some(event => event.kind === 'connection_attempt_failed'));
    assert(endedSenderReport.events.some(event => event.kind === 'track_ended' && event.track.readyState === 'ended'), 'Capture remains watched even when failed recovery leaves no peer');
    await sender.click('#resume-share');
    await sender.waitForFunction(() => document.getElementById('outgoing').value.includes('"offer"'));
    assert.equal(await sender.evaluate(() => window.captureRequests), requestsBeforeEnding + 1, 'An ended capture resumes through a new permission request');
    assert.equal(JSON.parse(await sender.locator('#outgoing').inputValue()).sessionId, endedSession);
    await sender.click('#stop');
    assert.deepEqual(errors, [], `${name}: no uncaught browser errors`);
    await context.close(); await browser.close(); browser = null;
    console.log(`${name}: mobile layouts, permission errors, real WebRTC recovery without recapture, stale-message rejection, private diagnostics, preserved observation, black frames, stalls and async cleanup passed`);
  }
  browser=await webkit.launch({headless:true});
  const qrErrors=[],qrPage=await browser.newPage();qrPage.on('pageerror',error=>qrErrors.push(error.message));
  await qrPage.goto(url);await verifyQrRendering(qrPage);assert.deepEqual(qrErrors,[]);
  console.log('webkit: real compact QR pixels decode and large-view portrait/landscape controls passed; camera/device reliability remains a physical test');
  await browser.close();browser=null;
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
