import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, mkdirSync, readFileSync, rmSync} from 'node:fs';
import {resolve, join} from 'node:path';

// Run only after validate-artifacts: its archive scan and SHA256SUMS checks are
// the first gate. This second gate exercises the files delivered in the ZIP.
if (process.platform !== 'win32') throw new Error('Candidate package validation requires Windows.');
const root = process.cwd();
const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
assert.match(pkg.version, /^\d+\.\d+\.\d+(?:-[\w.-]+)?$/);
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], {encoding:'utf8'}).trim();
if (process.env.GITHUB_SHA) assert.equal(sourceCommit, process.env.GITHUB_SHA, 'CI must test the checked-out candidate commit');
const expected = JSON.parse(readFileSync('release/PROVENANCE.json', 'utf8'));
assert.equal(expected.sourceCommit, sourceCommit);
assert.equal(expected.version, pkg.version);
mkdirSync('output/checks', {recursive:true});
const destination = mkdtempSync(resolve('output/checks/extracted-candidate-'));
try {
  execFileSync('tar', ['-xf', resolve(`release/Game-immersion-toolkit-${pkg.version}.zip`), '-C', destination], {stdio:'inherit'});
  const extracted = join(destination, `Game-immersion-toolkit-${pkg.version}`);
  assert.deepEqual(JSON.parse(readFileSync(join(extracted, 'PROVENANCE.json'), 'utf8')), expected, 'Embedded provenance must match the checked archive');
  assert.equal(JSON.parse(readFileSync(join(extracted, 'package.json'), 'utf8')).version, pkg.version);
  assert.deepEqual(JSON.parse(readFileSync(join(extracted, 'vendor/lexirise-components/PROVENANCE.json'), 'utf8')), expected.shared);
  execFileSync(process.execPath, ['scripts/setup-build-e2e.mjs', '--built-root', extracted], {cwd:root, stdio:'inherit'});
  console.log(`Extracted candidate verified at ${sourceCommit}; no release was published.`);
} finally {
  rmSync(destination, {recursive:true, force:true});
}
