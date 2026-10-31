import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import test from 'node:test';
import {inspectStaticFrontend} from '../scripts/r19-static-frontend-experiment.mjs';

// These prevent promoting a server build or a lone HTML shell to static proof.
// Existing browser tests mount Wrangler; they cannot detect that false claim.
test('server output without a desktop document disproves a client-tree copy', t => {
  const root = mkdtempSync(join(tmpdir(), 'r19-static-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  for (const dir of ['app', 'dist/client/mobile-capture', 'dist/server/ssr']) mkdirSync(join(root, dir), {recursive: true});
  writeFileSync(join(root, 'app/page.tsx'), 'export default function Home() {}');
  writeFileSync(join(root, 'dist/client/mobile-capture/index.html'), '<p>Separate mobile page</p>');
  writeFileSync(join(root, 'dist/server/wrangler.json'), JSON.stringify({main: 'index.js'}));
  writeFileSync(join(root, 'dist/server/index.js'), 'export default {}');
  writeFileSync(join(root, 'dist/server/ssr/index.js'), 'export default {}');
  const report = inspectStaticFrontend(root);
  assert.equal(report.status, 'disproved-current-output');
  assert.equal(report.decision, 'retain-current-host');
  assert.equal(report.staticActivationAllowed, false);
  assert.deepEqual(report.facts.htmlFiles, ['mobile-capture/index.html']);
  assert.equal(report.evidence.opfs, 'unchanged-unverified');
  const hash = report.facts.clientTreeSha256;
  writeFileSync(join(root, 'dist/client/index.html'), '<p>Unproved shell</p>');
  const shell = inspectStaticFrontend(root);
  assert.equal(shell.status, 'incomplete');
  assert.equal(shell.staticActivationAllowed, false);
  assert.notEqual(shell.facts.clientTreeSha256, hash);
});

test('missing canonical build remains unavailable and preserves origin/profile contract', t => {
  const root = mkdtempSync(join(tmpdir(), 'r19-static-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  const report = inspectStaticFrontend(root);
  assert.equal(report.status, 'unavailable');
  assert.equal(report.contract.frontendOrigin, 'http://127.0.0.1:3000');
  assert.equal(report.contract.apiBase, 'http://127.0.0.1:8766');
  assert.equal(report.contract.websocketUrl, 'ws://127.0.0.1:8766/api/ws');
  assert.equal(report.evidence.ordinaryProfileContinuity, 'unchanged-unverified');
  assert.equal(report.staticActivationAllowed, false);
});
