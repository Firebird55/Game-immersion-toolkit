import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredPickerNode} from '../scripts/android-authored-document-picker.mjs';

test('authored native picker coordinates require bounded genuine DocumentsUI nodes', () => {
  const node = '<hierarchy><node package="com.google.android.documentsui" text="toolkit-authored.json" enabled="true" bounds="[20,40][120,80]" /></hierarchy>';
  assert.deepEqual(authoredPickerNode(node, 'toolkit-authored.json'), [70, 60]);
  assert.equal(authoredPickerNode(node.replace('enabled="true"', 'enabled="false"'), 'toolkit-authored.json'), null);
  assert.equal(authoredPickerNode(node.replace('[120,80]', '[99999,80]'), 'toolkit-authored.json'), null);
  assert.throws(() => authoredPickerNode(node.replace('com.google.android.documentsui', 'another.application'), 'toolkit-authored.json'));
  assert.throws(() => authoredPickerNode(node, 'private-user-file.json'));
  assert.throws(() => authoredPickerNode(node.repeat(10000), 'toolkit-authored.json'));
});
