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
    if (attributes.enabled !== 'true') continue;
    const bounds = /^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$/.exec(attributes.bounds ?? '');
    if (!bounds) continue;
    const [, left, top, right, bottom] = bounds.map(Number);
    if (right > left && bottom > top && right <= 8192 && bottom <= 8192)
      return [Math.floor((left + right) / 2), Math.floor((top + bottom) / 2)];
  }
  return null;
}

export function authoredPickerState(xml) {
  assert.ok(typeof xml === 'string' && xml.length < 512 * 1024);
  const known = new Set(['Show roots', 'Downloads', 'toolkit-authored.zip', 'toolkit-authored.json']);
  const nodes = [];
  for (const match of xml.matchAll(/<node\s+([^>]+)>/g)) {
    const attrs = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(value => [value[1], value[2]]));
    const label = known.has(attrs.text) ? attrs.text : known.has(attrs['content-desc']) ? attrs['content-desc'] : null;
    if (!label || nodes.length >= 24) continue;
    const id = /^(?:android|com\.(?:google\.android|android)\.documentsui):id\/[A-Za-z0-9_]{1,80}$/.test(attrs['resource-id'] ?? '') ? attrs['resource-id'] : null;
    nodes.push({label, id, enabled: attrs.enabled === 'true', clickable: attrs.clickable === 'true'});
  }
  return {documents_ui: /package="com\.(?:google\.android|android)\.documentsui"/.test(xml), nodes};
}

export async function selectAuthoredAndroidDocument({adb, page, until, output, extension, bytes, trigger, onState = () => {}}) {
  assert.ok(extension === 'json' || extension === 'zip');
  assert.ok(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length < 1024 * 1024);
  const name = `toolkit-authored.${extension}`, temporary = join(output, 'authored-picker-inputs');
  mkdirSync(temporary, {recursive: true});
  const local = join(temporary, name), remote = '/sdcard/Download/' + name;
  writeFileSync(local, bytes);
  try {adb('push', local, remote);} finally {unlinkSync(local);}
  const dump = () => {
    adb('shell', 'uiautomator', 'dump', '/sdcard/toolkit-authored-picker.xml');
    const xml = adb('shell', 'cat', '/sdcard/toolkit-authored-picker.xml');
    onState(extension, authoredPickerState(xml));return xml;
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
