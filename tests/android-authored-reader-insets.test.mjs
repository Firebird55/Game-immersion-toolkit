import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredReaderBounds,authoredInsetsMetrics,authoredNativeInsetsMetrics,verifyAuthoredReaderInsets} from '../scripts/android-authored-reader-insets.mjs';

const app = 'io.github.firebird55.gameimmersiontoolkit.debug';
const xml = (rotation, bounds) => `<hierarchy rotation="${rotation}"><node package="${app}" class="android.webkit.WebView" bounds="${bounds}" /></hierarchy>`;
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
  assert.deepEqual(value.system_bar_insets,[{type:'statusBars',bounds:[0,0,2400,63],visible:true}]);
  assert.equal(JSON.stringify(value).includes('ignored'),false);
});

test('failed strict bounds are captured before restoring rotations without widening the waiter',async()=>{
  const calls=[];let report;
  const adb=(...args)=>{
    calls.push(args.join(' '));
    if(args.slice(0,3).join(' ')==='shell wm size')return 'Physical size: 1080x2400\nOverride size: 720x1600';
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
  assert.deepEqual(report.sizes,[{kind:'physical',width:1080,height:2400},{kind:'override',width:720,height:1600}]);
  assert.ok(calls.includes('shell settings put system accelerometer_rotation 1'));
  assert.ok(calls.includes('shell rm -f /sdcard/toolkit-authored-insets.xml'));
});
