import test from 'node:test';
import assert from 'node:assert/strict';
import {selectChecks} from '../scripts/check-changed.mjs';
test('documentation avoids application builds',()=>assert.deepEqual(selectChecks(['README.md','docs/beyond-support.md']),['docs']));
test('backend and frontend changes combine their gates',()=>assert.deepEqual(selectChecks(['backend/capture.py','app/companion.tsx']),['desktop','python']));
test('unknown and dependency changes require the full gate',()=>{
  for(const file of ['package-lock.json','.github/workflows/ci-release.yml','new-system/file.ts'])assert.deepEqual(selectChecks([file]),['full']);
});
test('explicit release gate is full even without changes',()=>assert.deepEqual(selectChecks([],true),['full']));

test('shared interface and support catalog select their consumer checks',()=>{
 assert.deepEqual(selectChecks(['lib/interface-language.tsx']),['desktop','mobile']);
 assert.deepEqual(selectChecks(['public/mobile-capture/games-data.json']),['docs','mobile','python']);
 assert.deepEqual(selectChecks(['scripts/generate-language-docs.mjs']),['docs']);
});
