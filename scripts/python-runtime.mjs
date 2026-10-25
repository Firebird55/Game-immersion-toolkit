import {existsSync, lstatSync} from 'node:fs';
import {join} from 'node:path';

// Development commands never borrow the installed companion's environment.
// Keep the command private: reports should expose only the source enum.
export function resolvePython({root = process.cwd(), env = process.env, platform = process.platform, exists = existsSync, lstat = lstatSync} = {}) {
  if (env.PYTHON?.trim()) return {command: env.PYTHON, source: 'override'};
  const directory = join(root, '.venv');
  const command = join(directory, ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']));
  // An incomplete project venv is an actionable error, not permission to use a
  // different environment whose dependencies happen to be installed.
  let entryPresent = exists(directory) || exists(command);
  if (!entryPresent) {
    // existsSync follows symlinks; a broken .venv link still expresses the
    // project's selected environment and must never silently fall back to PATH.
    try { lstat(directory); entryPresent = true; }
    catch (error) { entryPresent = !['ENOENT', 'ENOTDIR'].includes(error.code); }
  }
  if (entryPresent) return {command, source: 'project-venv'};
  return {command: platform === 'win32' ? 'python' : 'python3', source: 'path'};
}
