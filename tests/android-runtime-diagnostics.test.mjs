import assert from 'node:assert/strict';
import test from 'node:test';
import {safeReceiverState, safeMessageMetrics} from '../scripts/android-runtime-diagnostics.mjs';
import {authoredLibraryIdentity, inspectAuthoredLibrary} from '../scripts/android-authored-library-check.mjs';
import {mkdtempSync, realpathSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, join, resolve, sep} from 'node:path';
import {execFileSync} from 'node:child_process';

test('authored receiver diagnostics retain handoff evidence without account or frame payloads', () => {
 const privateValue = 'authored-private-value-must-not-be-serialized';
 const value = safeReceiverState({cookie: privateValue, accounts: [privateValue], context:{state_version: 17},
  lines: [{text_id: 'authored:bridge', source_text: privateValue}],
  status: {capture: {running: true, source_generation: 12, window_bounds: [0, 0, 1600, 240],
   last_ocr: privateValue, last_error: privateValue, viewer_url: privateValue},
   settings:{region:{left:0,top:0,width:1,height:1,private_value:privateValue},stable_frames:2,
    fuzzy_threshold:82,private_value:privateValue}, textmaps:{ready:true,entry_count:1,audio_count:1},audio:{ready:true}}});
 assert.equal(value.authored_line_present, true);
 assert.equal(value.lines, 1);
 assert.equal(value.source_generation, 12);
 assert.deepEqual(value.frame_size, [1600, 240]);
 assert.equal(value.last_ocr_present, true);
 assert.equal(value.last_ocr_matches_fixture, false);
 assert.equal(value.state_version, 17);
 assert.equal(value.stable_frames, 2);
 assert.deepEqual(value.region, [0,0,1,1]);
 assert.equal(value.textmap_voices, 1);
 assert.equal(JSON.stringify(value).includes(privateValue), false);
});

test('third-party frame globals cannot inject text through numeric message metrics', () => {
 const value = safeMessageMetrics({requests: 3, received_frames: 2, png_blobs: 2,
  csp_violations: 'authored-private-value', private_url: 'authored-private-value'});
 assert.deepEqual(value, {requests: 3, received_frames: 2, png_blobs: 2, csp_violations: null});
 assert.equal(safeReceiverState(null).source_generation, null);
 assert.equal(safeMessageMetrics({requests: Infinity}).requests, null);
});

test('exact authored ZIP identity checks only its own active files and persists booleans and counts', () => {
 const temporaryRoot = realpathSync(tmpdir()), directory = mkdtempSync(join(temporaryRoot, 'android-authored-library-'));
 const path = join(directory, 'fixture.zip');
 try {
  const producer = String.raw`
import hashlib,io,json,sys,wave,zipfile
pcm=io.BytesIO()
with wave.open(pcm,'wb') as output:
 output.setparams((1,2,16000,0,'NONE','NONE'));output.writeframes(b'\0\0'*32)
clip=pcm.getvalue();sha=lambda value:hashlib.sha256(value).hexdigest();name='audio/'+sha(clip)+'.wav'
row={'text_id':'authored:bridge','source_text':'Follow the river beyond the bridge.','voice_status':'voiced','audio_locale':'en','audio':{'prepared_clip':name,'locale':'en'}}
text=json.dumps({'game':'zzz','source_locale':'en','records':[row]}).encode()
manifest=json.dumps({'format':'toolkit-prepared-library-v1','game':'zzz','files':{'textmap.json':{'size':len(text),'sha256':sha(text)},name:{'size':len(clip),'sha256':sha(clip)}}}).encode()
with zipfile.ZipFile(sys.argv[1],'w',compression=zipfile.ZIP_STORED) as archive:
 archive.writestr('manifest.json',manifest);archive.writestr('textmap.json',text);archive.writestr(name,clip)
`;
  execFileSync(process.env.PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3'), ['-I','-B','-c',producer,path]);
  const expected = authoredLibraryIdentity(path), calls = [];
  const adb = (...args) => {
   calls.push(args);
   assert.equal(args[0], 'shell');assert.equal(args[1], 'run-as');
   if (args[3] === 'head') return JSON.stringify({revision:expected.revision,text_sha256:expected.text_sha256});
   const text = args.at(-1).endsWith('/textmap.json');
   assert.ok(args.at(-1).startsWith('files/toolkit/libraries/' + expected.revision + '/'));
   return args[3] === 'stat' ? String(text ? expected.text_size : expected.audio_size)
    : (text ? expected.text_sha256 : expected.audio_sha256) + '  authored-owned-path';
  };
  const result = inspectAuthoredLibrary(adb, 'io.github.firebird55.gameimmersiontoolkit.debug', expected);
  assert.equal(result.current_manifest_matches, true);
  assert.equal(result.text_sha256_matches, true);assert.equal(result.audio_sha256_matches, true);
  assert.equal(result.audio_bytes, 108);
  assert.equal(Object.values(result).every(value => typeof value === 'boolean' || typeof value === 'number' || value === null), true);
  const wrongPointer = inspectAuthoredLibrary((...args) => {assert.equal(args[3], 'head');return '{}';},
   'io.github.firebird55.gameimmersiontoolkit.debug', expected);
  assert.equal(wrongPointer.current_manifest_matches, false);
  assert.throws(() => inspectAuthoredLibrary(adb, 'outside-package', expected));
 } finally {
  const target = resolve(directory);
  assert.ok(target.startsWith(resolve(temporaryRoot) + sep) && basename(target).startsWith('android-authored-library-'));
  rmSync(target, {recursive:true,force:true});
 }
});
