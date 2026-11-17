import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredPickerNode, authoredPickerState} from '../scripts/android-authored-document-picker.mjs';
import {selectAuthoredAndroidDocument} from '../scripts/android-authored-document-picker.mjs';
import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve, basename} from 'node:path';

test('authored native picker coordinates require bounded genuine DocumentsUI nodes', () => {
  const node = '<hierarchy><node package="com.google.android.documentsui" text="toolkit-authored.json" enabled="true" bounds="[20,40][120,80]" /></hierarchy>';
  assert.deepEqual(authoredPickerNode(node, 'toolkit-authored.json'), [70, 60]);
  assert.equal(authoredPickerNode(node.replace('enabled="true"', 'enabled="false"'), 'toolkit-authored.json'), null);
  assert.equal(authoredPickerNode(node.replace('[120,80]', '[99999,80]'), 'toolkit-authored.json'), null);
  assert.throws(() => authoredPickerNode(node.replace('com.google.android.documentsui', 'another.application'), 'toolkit-authored.json'));
  assert.throws(() => authoredPickerNode(node, 'private-user-file.json'));
  assert.throws(() => authoredPickerNode(node.repeat(10000), 'toolkit-authored.json'));
});

test('returning from the picker keeps its original document alive for asynchronous upload and commit', async () => {
  const root = mkdtempSync(join(tmpdir(), 'toolkit-authored-picker-')), commands = [];
  try {
    const xml = '<hierarchy>' + ['Show roots', 'Downloads', 'toolkit-authored.zip'].map(text =>
      `<node package="com.google.android.documentsui" resource-id="android:id/title" text="${text}" enabled="true" bounds="[20,40][120,80]" />`).join('') + '</hierarchy>';
    await selectAuthoredAndroidDocument({output: root, extension: 'zip', bytes: Buffer.from('bounded authored ZIP sentinel'),
      page: {evaluate: async () => true}, trigger: async () => {}, until: async read => assert.ok(await read()),
      adb: (...args) => {commands.push(args);return args[0] === 'shell' && args[1] === 'cat' ? xml : '';}});
    assert.deepEqual(commands.filter(args => args.includes('rm')), [['shell', 'rm', '/sdcard/toolkit-authored-picker.xml']]);
    assert.equal(commands.filter(args => args[0] === 'push').length, 1);
  } finally {
    const exact = resolve(root);
    assert.equal(resolve(tmpdir()), resolve(root, '..'));assert.ok(basename(exact).startsWith('toolkit-authored-picker-'));
    rmSync(exact, {recursive: true});
  }
});

test('the current Downloads breadcrumb cannot replace the actual drawer root', () => {
  const xml = '<hierarchy><node package="com.google.android.documentsui" text="Downloads" ' +
    'resource-id="com.google.android.documentsui:id/breadcrumb_text" enabled="true" bounds="[100,0][200,50]" />' +
    '<node text="Downloads" resource-id="android:id/title" enabled="true" bounds="[40,400][180,450]" /></hierarchy>';
  assert.deepEqual(authoredPickerNode(xml, 'Downloads'), [110, 425]);
  assert.equal(authoredPickerNode(xml.replace('resource-id="android:id/title"', 'resource-id="other:id/title"'), 'Downloads'), null);
});

test('picker diagnostics admit only fixed authored labels and original system resource identifiers', () => {
  const xml = '<hierarchy><node package="com.google.android.documentsui" text="toolkit-authored.json" resource-id="android:id/title" enabled="false" />' +
    '<node text="private-user-name" resource-id="private-provider-id" /><node text="Downloads" resource-id="secret-provider-value" /></hierarchy>';
  assert.deepEqual(authoredPickerState(xml), {documents_ui: true, nodes: [
    {label: 'toolkit-authored.json', id: 'android:id/title', enabled: false, clickable: false},
    {label: 'Downloads', id: null, enabled: false, clickable: false}]});
  assert.doesNotMatch(JSON.stringify(authoredPickerState(xml)), /private-user|private-provider|secret-provider/);
});
