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

export async function verifyAuthoredReaderInsets({adb, page, until, packageName}) {
  const size = [...adb('shell', 'wm', 'size').matchAll(/(?:Physical|Override) size: (\d+)x(\d+)/g)].at(-1);
  assert.ok(size);const [, width, height] = size.map(Number);
  const automatic = adb('shell', 'settings', 'get', 'system', 'accelerometer_rotation');
  const original = adb('shell', 'settings', 'get', 'system', 'user_rotation');
  assert.match(automatic, /^[01]$/);assert.match(original, /^[0-3]$/);
  const cases = [];
  try {
    adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0');
    for (const rotation of [0, 1, 0]) {
      adb('shell', 'settings', 'put', 'system', 'user_rotation', String(rotation));
      await until(() => page.evaluate(landscape => (innerWidth > innerHeight) === landscape, rotation === 1), 'actual native reader orientation');
      cases.push(await until(() => {
        adb('shell', 'uiautomator', 'dump', '/sdcard/toolkit-authored-insets.xml');
        const value = authoredReaderBounds(adb('shell', 'cat', '/sdcard/toolkit-authored-insets.xml'), width, height, packageName);
        return value?.rotation === rotation ? value : null;
      }, 'actual native reader clear of system bars after rotation'));
    }
  } finally {
    adb('shell', 'settings', 'put', 'system', 'user_rotation', original);
    adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', automatic);
    adb('shell', 'rm', '-f', '/sdcard/toolkit-authored-insets.xml');
  }
  return {api: Number(adb('shell', 'getprop', 'ro.build.version.sdk')), cases, passed: true};
}
