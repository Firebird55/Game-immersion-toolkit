import {existsSync} from 'node:fs';
import {join} from 'node:path';

// Development commands never borrow the installed companion's environment.
// Keep the command private: reports should expose only the source enum.
export function resolvePython({root = process.cwd(), env = process.env, platform = process.platform, exists = existsSync} = {}) {
  if (env.PYTHON?.trim()) return {command: env.PYTHON, source: 'override'};
  const directory = join(root, '.venv');
  const command = join(directory, ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']));
  // An incomplete project venv is an actionable error, not permission to use a
  // different environment whose dependencies happen to be installed.
  if (exists(directory) || exists(command)) return {command, source: 'project-venv'};
  return {command: platform === 'win32' ? 'python' : 'python3', source: 'path'};
}
