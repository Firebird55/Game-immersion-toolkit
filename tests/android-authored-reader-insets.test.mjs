import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredReaderBounds,authoredInsetsMetrics,authoredNativeInsetsMetrics,authoredNativeReaderBounds,authoredAnrEvents,verifyAuthoredReaderInsets} from '../scripts/android-authored-reader-insets.mjs';

const app = 'io.github.firebird55.gameimmersiontoolkit.debug';
const xml = (rotation, bounds) => `<hierarchy rotation="${rotation}"><node package="${app}" class="android.webkit.WebView" bounds="${bounds}" /></hierarchy>`;
const nativeSample = rotation => ({pid: 110, rotation, foreground: true, status_visible: true, navigation_visible: true,
  window: rotation ? [0, 0, 2400, 1080] : [0, 0, 1080, 2400],
  reader: rotation ? [0, 60, 2300, 1080] : [0, 60, 1080, 2300],
  insets: rotation ? [0, 60, 100, 0] : [0, 60, 0, 100]});

test('uses the attached foreground reader and fresh native safe bounds', () => {
  const sample = nativeSample(0);
  assert.deepEqual(authoredNativeReaderBounds(sample, '110', 0, 1080, 2400).reader, sample.reader);
  assert.equal(authoredNativeReaderBounds(sample, '109', 0, 1080, 2400), null);
  assert.equal(authoredNativeReaderBounds(sample, '110', 1, 1080, 2400), null);
  assert.equal(authoredNativeReaderBounds({...sample, foreground: false}, '110', 0, 1080, 2400), null);
  assert.equal(authoredNativeReaderBounds({...sample, navigation_visible: false}, '110', 0, 1080, 2400), null);
  for (const reader of [[0, 12, 1080, 2300], [0, 60, 1080, 2310], [0, 60, 0, 2300]]) {
    assert.throws(() => authoredNativeReaderBounds({...sample, reader}, '110', 0, 1080, 2400));
  }
});

test('native rotation acceptance requires actual foreground samples for all three cases', async () => {
  let rotation = 0;
  const calls = [];
  const adb = (...args) => {
    calls.push(args.join(' '));
    if (args.includes('wm')) return 'Physical size: 1080x2400';
    if (args.includes('pidof')) return '110';
    if (args.includes('get')) return '0';
    if (args.includes('put') && args.includes('user_rotation')) rotation = Number(args.at(-1));
    if (args.includes('run-as')) return JSON.stringify(nativeSample(rotation));
    return '';
  };
  const result = await verifyAuthoredReaderInsets({adb, page: {evaluate: async () => true},
    until: operation => operation(), packageName: app, nativeWindowEvidence: true});
  assert.deepEqual(result.cases.map(value => value.rotation), [0, 1, 0]);
  assert.ok(result.cases.every(value => value.evidence === 'focused-native-reader'));
  assert.ok(calls.every(value => !value.includes('uiautomator')));
});
test('native insets proof rejects obscured, impossible or foreign reader bounds', () => {
  assert.deepEqual(authoredReaderBounds(xml(0, '[0,60][1080,2300]'), 1080, 2400, app).reader, [0, 60, 1080, 2300]);
  assert.deepEqual(authoredReaderBounds(xml(1, '[0,60][2300,1080]'), 1080, 2400, app).reader, [0, 60, 2300, 1080]);
  for (const bounds of ['[0,0][1080,2400]', '[0,60][1080,2400]', '[0,0][1080,2300]', '[0,60][9999,2300]'])
    assert.throws(() => authoredReaderBounds(xml(0, bounds), 1080, 2400, app));
  assert.equal(authoredReaderBounds(xml(0, '[0,60][1080,2300]').replace(app, 'another.application'), 1080, 2400, app), null);
  assert.throws(() => authoredReaderBounds(xml(0, '[0,60][1080,2300]'), 1080, 2400, 'another.application'));
});

test('missing accessibility nodes remain observable without recording text or foreign packages',()=>{
  const value=authoredInsetsMetrics('<hierarchy rotation="0"><node package="another.secret" class="private.Class" text="Private caption" bounds="[0,0][1,1]" /></hierarchy>',app,
    {width:1080,height:2209,dpr:2.75,visual_width:1080,caption:'Private caption',orientation:0});
  assert.equal(value.nodes,1);assert.equal(value.owned_nodes,0);assert.deepEqual(value.webview_rects,[]);
  assert.equal(value.viewport.dpr,2.75);
  for(const secret of ['another.secret','private.Class','Private caption'])assert.equal(JSON.stringify(value).includes(secret),false);
});

test('native evidence contains only bounded known insets and focus/lock booleans',()=>{
  const value=authoredNativeInsetsMetrics(`mCurrentFocus=Window{ignored ${app}/MainActivity}\nmRotation=ROTATION_1\nmKeyguardShowing=false\nInsetsSource: mType=statusBars mFrame=[0,0][2400,63] mVisible=true\n`,
    'mWakefulness=Awake\nPrivate unrelated window',app);
  assert.equal(value.focus_is_own,true);assert.equal(value.native_rotation,1);assert.equal(value.keyguard_showing,false);assert.equal(value.awake,true);
  assert.equal(value.focus_category,'own');
  assert.deepEqual(value.system_bar_insets,[{type:'statusBars',bounds:[0,0,2400,63],visible:true}]);
  assert.equal(JSON.stringify(value).includes('ignored'),false);
});

test('focus classification is closed and never retains foreign activities or dialog text',()=>{
 const cases=[[app,'own'],['com.android.systemui','systemui'],['com.android.launcher3','launcher'],
  ['com.google.android.apps.nexuslauncher','launcher'],['com.android.permissioncontroller','permission-controller'],
  ['com.google.android.permissioncontroller','permission-controller'],['private.secret.application','other']];
 for(const [name,category] of cases){
  const value=authoredNativeInsetsMetrics(`mCurrentFocus=Window{private-hash u0 ${name}/private.Activity}`, '', app);
  assert.equal(value.focus_category,category);
  for(const secret of ['private-hash','private.Activity','private.secret.application'])assert.equal(JSON.stringify(value).includes(secret),false);
 }
 assert.equal(authoredNativeInsetsMetrics('mCurrentFocus=null','',app).focus_category,'none');
 assert.equal(authoredNativeInsetsMetrics('','',app).focus_category,null);
 assert.equal(authoredNativeInsetsMetrics('mCurrentFocus=Window{Application Error: private.name}','',app).focus_category,'other');
});

test('only exact Android error-dialog resource IDs set the ANR and crash-resource flags',()=>{
 const value=authoredInsetsMetrics('<hierarchy rotation="0">'+
  '<node package="android" resource-id="android:id/aerr_wait" text="Private application name" />'+
  '<node package="android" resource-id="android:id/aerr_close" />'+
  '<node package="android" resource-id="android:id/aerr_restart" /></hierarchy>',app);
 assert.equal(value.anr_wait_resource,true);assert.equal(value.error_close_resource,true);assert.equal(value.error_restart_resource,true);
 assert.equal(JSON.stringify(value).includes('Private application name'),false);
 const foreign=authoredInsetsMetrics('<hierarchy rotation="0"><node package="private.name" resource-id="android:id/aerr_wait" /></hierarchy>',app);
 assert.equal(foreign.anr_wait_resource,false);assert.equal(foreign.error_close_resource,false);
});

test('native ANR attribution reports process counts and trigger categories without retaining event details', () => {
  const logs = [
    'I/am_anr  (  815): [0,108,private.secret,32,Input dispatching timed out private input]',
    'I/am_anr  (  815): [0,109,' + app + ':worker,32,executing service private worker]',
    'I/am_anr  (  815): [0,110,' + app + ',32,Input dispatching timed out private reader]',
    'I/am_anr  (  815): [0,110,' + app + '.other,32,private unrelated app]',
  ].join('\n');
  const value = authoredAnrEvents(logs, app, '110');
  assert.deepEqual(value, {own_process: 2, current_process: 1, other_process: 2, latest_own_trigger: 'input'});
  for (const privateValue of ['private', app, '110', '815'])
    assert.equal(JSON.stringify(value).includes(privateValue), false);
});

test('failed strict bounds are captured before restoring rotations without widening the waiter',async()=>{
  const calls=[];let report;
  const adb=(...args)=>{
    calls.push(args.join(' '));
    if(args.slice(0,3).join(' ')==='shell wm size')return 'Physical size: 1080x2400\nOverride size: 720x1600';
    if(args.includes('pidof'))return '110';
    if(args[0]==='logcat')return 'I/am_anr  (  815): [0,110,'+app+',32,Input dispatching timed out private reader]';
    if(args.includes('get'))return args.at(-1)==='accelerometer_rotation'?'1':'0';
    if(args.includes('cat'))return '<hierarchy rotation="0"><node package="other" class="android.view.View" /></hierarchy>';
    if(args.includes('window'))return `mCurrentFocus=Window{${app}/MainActivity}\nmRotation=ROTATION_0`;
    if(args.includes('power'))return 'mWakefulness=Awake';
    return '';
  };
  let waits=0;
  const until=async(operation,_label,...timeout)=>{
    assert.deepEqual(timeout,[]);waits++;
    const result=await operation();if(result)return result;throw Error('Unchanged strict deadline');
  };
  const page={evaluate:async(_fn,arg)=>arg!==undefined?true:{width:720,height:1400,dpr:2}};
  await assert.rejects(verifyAuthoredReaderInsets({adb,page,until,packageName:app,report:value=>{
    report=value;assert.equal(calls.includes('shell settings put system accelerometer_rotation 1'),false);
  }}),/Unchanged strict deadline/);
  assert.equal(waits,2);assert.equal(report.metrics.webview_nodes,0);assert.equal(report.before_rotation_restore,true);
  assert.deepEqual(report.anr,{own_process:1,current_process:1,other_process:0,latest_own_trigger:'input'});
  assert.deepEqual(report.sizes,[{kind:'physical',width:1080,height:2400},{kind:'override',width:720,height:1600}]);
  assert.ok(calls.includes('shell settings put system accelerometer_rotation 1'));
  assert.ok(calls.includes('shell rm -f /sdcard/toolkit-authored-insets.xml'));
});
