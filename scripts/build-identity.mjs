import {execFileSync} from 'node:child_process';

// CI event SHAs can describe a merge while a job checks out the PR head.
// Provenance must describe the source files that were actually built.
export function sourceCommit(cwd = process.cwd()) {
  const commit = execFileSync('git', ['rev-parse', '--verify', 'HEAD^{commit}'], {cwd, encoding:'utf8'}).trim();
  if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error('Build requires a full Git commit SHA.');
  return commit;
}
