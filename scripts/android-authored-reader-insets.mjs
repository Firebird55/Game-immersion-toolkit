// Disposable emulator only; retain bounds and flags, never UI text or dumps.
import assert from 'node:assert/strict';

export function authoredReaderBounds(xml, physicalWidth, physicalHeight, packageName) {
  assert.ok(['io.github.firebird55.gameimmersiontoolkit.debug', 'io.github.firebird55.gameimmersiontoolkit'].includes(packageName));
  assert.ok(typeof xml === 'string' && xml.length < 1024 * 1024);
  const rotation = Number(/<hierarchy[^>]*\brotation="([0-3])"/.exec(xml)?.[1]);
  assert.ok(Number.isInteger(rotation));
  const [width, height] = rotation % 2 ? [physicalHeight, physicalWidth] : [physicalWidth, physicalHeight];
  assert.ok(Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0 && Math.max(width, height) <= 8192);
  for (const match of xml.matchAll(/<node\s+([^>]+)>/g)) {
    const attrs = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(value => [value[1], value[2]]));
    if (attrs.package !== packageName || attrs.class !== 'android.webkit.WebView') continue;
    const values = /^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$/.exec(attrs.bounds ?? '');
    if (!values) continue;
    const [, left, top, right, bottom] = values.map(Number);
    assert.ok(right > left && bottom > top && left >= 0 && top >= 0 && right <= width && bottom <= height);
    assert.ok(top > 0 || left > 0, 'The status bar/cutout must not cover the reader');
    assert.ok(bottom < height || right < width, 'The navigation bar must not cover the reader');
    return {rotation, width, height, reader: [left, top, right, bottom]};
  }
  return null;
}

// Preserve only bounded geometry and known-node counts. Never retain UI text,
// resource values, unknown package names or the raw accessibility/window dump.
export function authoredInsetsMetrics(xml, packageName, viewport = {}) {
  assert.ok(typeof xml === 'string' && xml.length < 1024 * 1024);
  const metrics = {hierarchy_rotation:Number(/<hierarchy[^>]*\brotation="([0-3])"/.exec(xml)?.[1]),
    hierarchy_bytes:Buffer.byteLength(xml),nodes:0,owned_nodes:0,webview_nodes:0,system_bar_nodes:0,
    webview_rects:[],surface_rects:[],system_bar_rects:[],viewport:{}};
  if (!Number.isInteger(metrics.hierarchy_rotation)) metrics.hierarchy_rotation=null;
  const rect = value => {
    const found=/^\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]$/.exec(value ?? '');
    const values=found?.slice(1).map(Number);
    return values?.every(n=>Number.isSafeInteger(n)&&Math.abs(n)<=16384)?values:null;
  };
  for (const match of xml.matchAll(/<node\s+([^>]+)>/g)) {
    metrics.nodes++;
    const attrs=Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(value=>[value[1],value[2]]));
    if (attrs.package === packageName) {
      metrics.owned_nodes++;
      if (attrs.class === 'android.webkit.WebView') {
        metrics.webview_nodes++;if(metrics.webview_rects.length<4)metrics.webview_rects.push(rect(attrs.bounds));
      }
      if (attrs.class === 'android.widget.FrameLayout' && metrics.surface_rects.length<4) metrics.surface_rects.push(rect(attrs.bounds));
    }
    if (attrs.package === 'com.android.systemui' && /:id\/(?:status_bar|navigation_bar_frame|navigation_bar)$/.test(attrs['resource-id'] ?? '')) {
      metrics.system_bar_nodes++;if(metrics.system_bar_rects.length<8)metrics.system_bar_rects.push(rect(attrs.bounds));
    }
  }
  for (const key of ['width','height','dpr','visual_width','visual_height','visual_left','visual_top','orientation']) {
    const value=viewport[key];metrics.viewport[key]=typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<=16384?value:null;
  }
  return metrics;
}

export function authoredNativeInsetsMetrics(window, power, packageName) {
  assert.ok(window.length<2*1024*1024 && power.length<2*1024*1024);
  const focus=/mCurrentFocus=([^\n]*)/.exec(window)?.[1];
  const rotation=/\b(?:mRotation=ROTATION_|SurfaceOrientation:\s*)([0-3])/.exec(window)?.[1];
  const keyguard=/\b(?:mKeyguardShowing|keyguardShowing|mShowingLockscreen)=(true|false)/.exec(window)?.[1];
  const awake=/\bmWakefulness=(Awake|Asleep|Dozing|Dreaming)/.exec(power)?.[1];
  const rects=[];
  for(const match of window.matchAll(/\bmType=(statusBars|navigationBars)\b[^\n]*?\bmFrame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\][^\n]*?\bmVisible=(true|false)/g)) {
    const bounds=match.slice(2,6).map(Number);
    const value={type:match[1],bounds,visible:match[6]==='true'};
    if(bounds.every(n=>Number.isSafeInteger(n)&&Math.abs(n)<=16384) && !rects.some(row=>JSON.stringify(row)===JSON.stringify(value)))rects.push(value);
    if(rects.length===8)break;
  }
  return {focus_is_own:focus===undefined?null:focus.includes(packageName+'/'),
    native_rotation:rotation===undefined?null:Number(rotation),
    keyguard_showing:keyguard===undefined?null:keyguard==='true',awake:awake===undefined?null:awake==='Awake',system_bar_insets:rects};
}

export async function verifyAuthoredReaderInsets({adb, page, until, packageName, report = () => {}}) {
  const wm=adb('shell','wm','size');
  const sizes=[...wm.matchAll(/(Physical|Override) size: (\d+)x(\d+)/g)].map(value=>({kind:value[1].toLowerCase(),width:Number(value[2]),height:Number(value[3])}));
  const size = [...wm.matchAll(/(?:Physical|Override) size: (\d+)x(\d+)/g)].at(-1);
  assert.ok(size);const [, width, height] = size.map(Number);
  const automatic = adb('shell', 'settings', 'get', 'system', 'accelerometer_rotation');
  const original = adb('shell', 'settings', 'get', 'system', 'user_rotation');
  assert.match(automatic, /^[01]$/);assert.match(original, /^[0-3]$/);
  const cases = [],started=Date.now();let requested=0,last=null,dumps=0;
  try {
    adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0');
    for (const rotation of [0, 1, 0]) {
      requested=rotation;
      adb('shell', 'settings', 'put', 'system', 'user_rotation', String(rotation));
      await until(() => page.evaluate(landscape => (innerWidth > innerHeight) === landscape, rotation === 1), 'actual native reader orientation');
      cases.push(await until(() => {
        adb('shell', 'uiautomator', 'dump', '/sdcard/toolkit-authored-insets.xml');
        const xml=adb('shell','cat','/sdcard/toolkit-authored-insets.xml');dumps++;
        last=authoredInsetsMetrics(xml,packageName);
        const value = authoredReaderBounds(xml, width, height, packageName);
        return value?.rotation === rotation ? value : null;
      }, 'actual native reader clear of system bars after rotation'));
    }
  } catch(error) {
    let viewport={},native={},actual=null,currentSizes=[];
    try {viewport=await Promise.race([page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,
      visual_width:visualViewport?.width,visual_height:visualViewport?.height,
      visual_left:visualViewport?.offsetLeft,visual_top:visualViewport?.offsetTop,orientation:screen.orientation?.angle})),
      new Promise(resolve=>setTimeout(()=>resolve({}),1000))]);}catch{}
    try {native=authoredNativeInsetsMetrics(adb('shell','toybox','timeout','3','dumpsys','window'),adb('shell','toybox','timeout','3','dumpsys','power'),packageName);}catch{}
    try {const value=adb('shell','settings','get','system','user_rotation');actual=/^[0-3]$/.test(value)?Number(value):null;}catch{}
    try {currentSizes=[...adb('shell','wm','size').matchAll(/(Physical|Override) size: (\d+)x(\d+)/g)]
      .map(value=>({kind:value[1].toLowerCase(),width:Number(value[2]),height:Number(value[3])}))
      .filter(value=>[value.width,value.height].every(n=>Number.isSafeInteger(n)&&n>0&&n<=8192)).slice(0,2);}catch{}
    report({schema:'toolkit-authored-insets-before-restore-v1',requested_rotation:requested,actual_user_rotation:actual,
      elapsed_ms:Date.now()-started,dump_count:dumps,sizes,current_sizes:currentSizes,metrics:last?{...last,viewport:authoredInsetsMetrics('',packageName,viewport).viewport}:null,
      native,passed_cases:cases,before_rotation_restore:true,production_fix_acceptance:false});
    throw error;
  } finally {
    adb('shell', 'settings', 'put', 'system', 'user_rotation', original);
    adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', automatic);
    adb('shell', 'rm', '-f', '/sdcard/toolkit-authored-insets.xml');
  }
  return {api: Number(adb('shell', 'getprop', 'ro.build.version.sdk')), cases, passed: true};
}
