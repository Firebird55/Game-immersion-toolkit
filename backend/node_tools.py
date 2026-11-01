"""Fixed Node operations using the app-local runtime in packaged applications."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys

from .preparation_errors import PreparationFailure
from .runtime_bundle import discover_layout, RuntimeBundleError

NODE_VERSION = '24.22.1'
ACORN_VERSION = '8.18.0'
ENTRY = 'backend/hito-grammar.cjs'
ACORN_FILES = ('package.json', 'LICENSE', 'dist/acorn.js')
ARCHIVES = {
    'win-x64': ('zip', 'd2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5'),
    'linux-x64': ('tar.xz', '6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6'),
    'linux-arm64': ('tar.xz', 'dbabf7a1cbf947e6059ffad2c27b80041db97dea1e553b62afdee7f13fca336e'),
    'darwin-x64': ('tar.gz', 'd132557e7ee2b85af08b0c8c34338e65c6430f2238d01f727728ef42dc83b035'),
    'darwin-arm64': ('tar.gz', '89c682593d76cd44233fa53b1563264e7de9cbb189cad169135c5b4fadfbc0a7'),
}


def host_platform() -> str:
    machine = platform.machine().lower()
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine, machine)
    system = 'win' if sys.platform == 'win32' else sys.platform
    return system + '-' + architecture


def grammar_command(archive: Path, output: Path, *, layout=None):
    """Return the existing grammar protocol command and its loader environment.

    Only this owned entry is executable. Game ASAR files remain explicit local
    inputs; they are not copied into or treated as executable bundle resources.
    """
    layout = layout or discover_layout()
    if layout.mode == 'source':
        node = shutil.which('node')
        if not node:
            raise PreparationFailure('node_missing', 'The source installation needs Node.js to read game grammar. Use the desktop installer to get the bundled runtime.')
        entry = Path(__file__).with_name('hito-grammar.cjs')
        env = os.environ.copy()
        project = Path(env.get('PROXY_TRANSCRIPT_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
        installed = Path(env.get('LOCALAPPDATA', '')) / 'Programs/Proxy Transcript/frontend/node_modules'
        env['NODE_PATH'] = os.pathsep.join([env.get('NODE_PATH', ''), str(installed), str(project / 'node_modules')])
    else:
        try:
            def resource(name):
                raw = layout.resource_root / name
                for candidate in (raw, *raw.parents):
                    if candidate.is_symlink() or (candidate.exists() and getattr(candidate.lstat(), 'st_file_attributes', 0)
                            & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                        raise ValueError('Linked Node resources are not allowed')
                return layout.resource(name)
            manifest = resource('toolchains/node/runtime.json')
            if manifest.stat().st_size > 16384:
                raise ValueError('Node manifest is too large')
            value = json.loads(manifest.read_text(encoding='utf-8'))
            target = host_platform()
            expected = 'node.exe' if target.startswith('win-') else 'node'
            if (value.get('schema') != 'toolkit-node-runtime-v1' or value.get('platform') != target
                    or value.get('version') != NODE_VERSION or value.get('executable') != expected
                    or target not in ARCHIVES or value.get('archive_sha256') != ARCHIVES[target][1]):
                raise ValueError('Incompatible Node runtime')
            node = resource('toolchains/node/' + expected)
            if hashlib.sha256(node.read_bytes()).hexdigest() != value.get('executable_sha256'):
                raise ValueError('Node runtime identity differs')
            resource('toolchains/node/LICENSE')
            entry = resource(ENTRY)
            for name in ACORN_FILES:
                path = resource('backend/node_modules/acorn/' + name)
                if name == 'package.json':
                    package = json.loads(path.read_text(encoding='utf-8'))
                    if package.get('name') != 'acorn' or package.get('version') != ACORN_VERSION:
                        raise ValueError('Incompatible grammar parser')
        except (OSError, ValueError, KeyError, TypeError, RuntimeBundleError) as error:
            raise PreparationFailure('bundle_toolchain_unavailable', 'The bundled grammar runtime or parser is missing or incompatible. Repair the application; no system Node.js or npm fallback was started.') from error
        # Do not inherit require/import loaders, npm settings or arbitrary modules.
        env = {'PATH': '', **{name: value for name, value in os.environ.items()
                             if name.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir', 'lang', 'lc_all'}}}
    return [str(node), str(entry), str(Path(archive).resolve()), str(Path(output).resolve())], env
