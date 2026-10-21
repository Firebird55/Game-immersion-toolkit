import test from 'node:test';
import assert from 'node:assert/strict';
import {selectChecks} from '../scripts/check-changed.mjs';
import {browserSuites,runBrowserSuite} from '../scripts/check-browser-suite.mjs';
test('documentation avoids application builds',()=>assert.deepEqual(selectChecks(['README.md','docs/beyond-support.md']),['docs']));
test('backend and frontend changes combine their gates',()=>assert.deepEqual(selectChecks(['backend/capture.py','app/companion.tsx']),['desktop','python']));
test('unknown and dependency changes require the full gate',()=>{
  for(const file of ['package-lock.json','.github/workflows/ci-release.yml','new-system/file.ts'])assert.deepEqual(selectChecks([file]),['full']);
});
test('explicit release gate is full even without changes',()=>assert.deepEqual(selectChecks([],true),['full']));
test('isolated browser suites retain every comprehensive check exactly once',()=>{
 const scripts=Object.values(browserSuites).flat();
 assert.equal(new Set(scripts).size,scripts.length);
 assert.deepEqual([...scripts].sort(),['browser-e2e','setup-e2e','language-account-e2e','update-companion-e2e','companion-e2e','mobile-reader-layout-e2e','mobile-capture-e2e','mobile-recovery-e2e','mobile-library-e2e','mobile-update-e2e','mobile-layout-e2e','mobile-games-e2e','ocr-packs-e2e'].sort());
 assert.throws(()=>runBrowserSuite('typo'),/Unknown browser suite/);
});

test('shared interface and support catalog select their consumer checks',()=>{
 assert.deepEqual(selectChecks(['lib/interface-language.tsx']),['desktop','mobile']);
 assert.deepEqual(selectChecks(['public/mobile-capture/games-data.json']),['docs','mobile','python']);
 assert.deepEqual(selectChecks(['scripts/generate-language-docs.mjs']),['docs']);
});
