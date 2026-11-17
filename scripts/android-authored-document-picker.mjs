// Only disposable authored emulator documents. Never inspect a user's picker.
import assert from 'node:assert/strict';
import {writeFileSync, mkdirSync, unlinkSync} from 'node:fs';
import {join} from 'node:path';

export function authoredPickerNode(xml, label) {
  assert.equal(typeof xml, 'string');assert.ok(xml.length < 512 * 1024);
  assert.match(xml, /package="com\.(?:google\.android|android)\.documentsui"/);
  assert.match(label, /^(?:Show roots|Downloads|toolkit-authored\.(?:json|zip))$/);
  for (const match of xml.matchAll(/<node\s+([^>]+)>/g)) {
    const attributes = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(value => [value[1], value[2]]));
    if (attributes.text !== label && attributes['content-desc'] !== label) continue;
    // DocumentsUI can expose the current Downloads breadcrumb behind its
    // drawer. Only the actual root-list label selects the Downloads root.
    if (label === 'Downloads' && attributes['resource-id'] !== 'android:id/title') continue;
    if (attributes.enabled !== 'true') continue;
    const bounds = /^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$/.exec(attributes.bounds ?? '');
    if (!bounds) continue;
    const [, left, top, right, bottom] = bounds.map(Number);
    if (right > left && bottom > top && right <= 8192 && bottom <= 8192)
      return [Math.floor((left + right) / 2), Math.floor((top + bottom) / 2)];
  }
  return null;
}

export async function selectAuthoredAndroidDocument({adb, page, until, output, extension, bytes, trigger}) {
  assert.ok(extension === 'json' || extension === 'zip');
  assert.ok(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length < 1024 * 1024);
  const name = `toolkit-authored.${extension}`, temporary = join(output, 'authored-picker-inputs');
  mkdirSync(temporary, {recursive: true});
  const local = join(temporary, name), remote = '/sdcard/Download/' + name;
  writeFileSync(local, bytes);
  try {adb('push', local, remote);} finally {unlinkSync(local);}
  const dump = () => {
    adb('shell', 'uiautomator', 'dump', '/sdcard/toolkit-authored-picker.xml');
    return adb('shell', 'cat', '/sdcard/toolkit-authored-picker.xml');
  };
  await trigger();
  await until(() => {
    const point = authoredPickerNode(dump(), 'Show roots');
    if (!point) return false;
    adb('shell', 'input', 'tap', ...point.map(String));return true;
  }, 'actual Android DocumentsUI roots');
  await until(() => {
    const point = authoredPickerNode(dump(), 'Downloads');
    if (!point) return false;
    adb('shell', 'input', 'tap', ...point.map(String));return true;
  }, 'actual Android Downloads document root');
  await until(() => {
    const point = authoredPickerNode(dump(), name);
    if (!point) return false;
    adb('shell', 'input', 'tap', ...point.map(String));return true;
  }, `actual Android ${extension} document selection`);
  await until(() => page.evaluate(() => document.hasFocus()), 'WebView return after SAF selection');
  // A selected SAF File is backed by this document and read asynchronously.
  // Keep the authored source through upload AND any preview/commit; the
  // disposable emulator owns cleanup after the complete scenario.
  adb('shell', 'rm', '/sdcard/toolkit-authored-picker.xml');
}
