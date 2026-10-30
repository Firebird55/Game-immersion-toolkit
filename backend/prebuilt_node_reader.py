"""Fixed app-local Node resources; no npm, TypeScript, PATH or game fallback.

Only the authored synthetic probe may execute. The separately acquired ZZZ
reader is deliberately blocked regardless of manifest approval-like strings.
Its upstream constants and combined GPL/source obligations are not closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .preparation_errors import PreparationFailure
from .runtime_bundle import RuntimeBundleError, discover_layout, relative_resource

SCHEMA = 'proxy-prebuilt-node-reader-v1'
VERSION = '24.22.1'
ARCHIVE_SHA256 = 'd2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5'
EXECUTABLE_SHA256 = 'd702daa815eabbff763c7d3808e235cf031cf2ca70211b56847bc72f51e240e5'
FILES = frozenset({'probe.mjs', 'probe-worker.mjs', 'sum.wasm', 'LICENSE', 'NOTICE.md', 'runtime/node.exe', 'runtime/LICENSE'})
PREFIX = 'helpers/zzz-reader-probe/'
SHA = re.compile(r'[a-f0-9]{64}')


def _failure(message):
    return PreparationFailure('bundle_toolchain_unavailable', message)


def _no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise _failure('Prebuilt Node helper paths cannot follow links or reparse points.')


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest key')
        result[key] = value
    return result


def _within(path, root):
    return path == root or root in path.parents


@dataclass(frozen=True)
class PrebuiltNodeReader:
    executable: Path
    entry: Path
    manifest: dict
    work_root: Path

    def command(self, *, work, input_path, output_path):
        """Accept only three explicit paths inside an owned private work folder."""
        work, input_path, output_path = (Path(value) for value in (work, input_path, output_path))
        for path in (work, input_path, output_path):
            if not path.is_absolute():
                raise _failure('Node helper work, input and output must be explicit absolute paths.')
            _no_links(path)
            if path != path.resolve():
                raise _failure('Node helper paths must not contain traversal or aliases.')
        try:
            relative_resource(input_path.name)
            relative_resource(output_path.name)
        except RuntimeBundleError as error:
            raise _failure('Node helper input and output need portable plain filenames.') from error
        _no_links(output_path.with_name(output_path.name + '.pending'))
        if (not _within(work, self.work_root) or work == self.work_root
                or not work.is_dir() or input_path.parent != work or output_path.parent != work
                or input_path == output_path or not input_path.is_file() or output_path.exists()
                or output_path.with_name(output_path.name + '.pending').exists()):
            raise _failure('The authored helper needs a fresh owned work directory with separate input and output.')
        return [str(self.executable), str(self.entry), '--probe', '--work', str(work),
                '--input', str(input_path), '--output', str(output_path)]

    @staticmethod
    def environment(environ=None):
        source = os.environ if environ is None else environ
        # No account roots, loader flags, npm configuration or compile-cache path.
        return {'PATH': '', **{name: value for name, value in source.items()
                              if name.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir'}}}


def prebuilt_node_reader(kind: str, *, layout=None) -> PrebuiltNodeReader:
    if kind != 'authored-probe':
        raise _failure('The frozen ZZZ game reader remains blocked by unreviewed game constants, combined rights and GPL corresponding-source obligations. Keep using the source runtime.')
    layout = layout or discover_layout()
    if layout.mode != 'bundle':
        raise _failure('The prebuilt Node resolver requires an explicit frozen resource layout.')
    try:
        raw_root = layout.resource_root / PREFIX
        _no_links(raw_root)
        path = layout.resource(PREFIX + 'helper-manifest.json')
        if path.stat().st_size > 256 * 1024:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
        runtime = value['runtime']
        if (value.get('schema') != SCHEMA or value.get('kind') != 'authored-probe'
                or value.get('purpose') != 'authored-probe-only' or value.get('platform') != 'win-x64'
                or value.get('source_commit') != layout.source_commit or value.get('source_dirty') is not False or value.get('entry') != 'probe.mjs'
                or value.get('executable') != 'runtime/node.exe' or value.get('game_execution_allowed') is not False
                or runtime.get('version') != VERSION or runtime.get('archive_sha256') != ARCHIVE_SHA256
                or runtime.get('executable_sha256') != EXECUTABLE_SHA256
                or not SHA.fullmatch(str(runtime.get('license_sha256', '')))):
            raise ValueError()
        files = value['files']
        if not isinstance(files, dict) or set(files) != FILES:
            raise ValueError()
        for name, entry in files.items():
            relative_resource(name)
            if (not isinstance(entry, dict) or set(entry) != {'bytes', 'sha256'}
                    or type(entry['bytes']) is not int or not 1 <= entry['bytes'] <= 150 * 1024 * 1024
                    or not SHA.fullmatch(str(entry['sha256']))):
                raise ValueError()
        expected = {PREFIX + name for name in (*files, 'helper-manifest.json')}
        if {name for name in layout.resources if name.startswith(PREFIX)} != expected:
            raise ValueError()
        identity = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if value.get('build_id') != identity:
            raise ValueError()
        actual = set()
        for candidate in raw_root.rglob('*'):
            _no_links(candidate)
            if candidate.is_dir():
                if candidate != raw_root / 'runtime':
                    raise ValueError()
            elif candidate.is_file():
                actual.add(candidate.relative_to(raw_root).as_posix())
            else:
                raise ValueError()
        if actual != {*files, 'helper-manifest.json'}:
            raise ValueError()
        for name, entry in files.items():
            raw_path = raw_root / name
            _no_links(raw_path)
            candidate = layout.resource(PREFIX + name)
            if candidate.stat().st_size != entry['bytes'] or hashlib.sha256(candidate.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError()
        if (files['runtime/node.exe']['sha256'] != EXECUTABLE_SHA256
                or files['runtime/LICENSE']['sha256'] != runtime['license_sha256']):
            raise ValueError()
        executable = raw_root / 'runtime/node.exe'
        with executable.open('rb') as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b'MZ':
                raise ValueError()
            offset = int.from_bytes(header[60:64], 'little')
            if offset > executable.stat().st_size - 6:
                raise ValueError()
            stream.seek(offset)
            if stream.read(6) != b'PE\0\0\x64\x86':
                raise ValueError()
        sources = value['source_inputs']
        if (not isinstance(sources, dict) or set(sources) != {'LICENSE', *('packaging/zzz-reader/' + name
                for name in ('probe.mjs', 'probe-worker.mjs', 'sum.wat', 'sum.wasm.hex', 'NOTICE.md'))}
                or any(not SHA.fullmatch(str(digest)) for digest in sources.values())):
            raise ValueError()
        if sources['LICENSE'] != files['LICENSE']['sha256'] or any(
                sources['packaging/zzz-reader/' + name] != files[name]['sha256']
                for name in ('probe.mjs', 'probe-worker.mjs', 'NOTICE.md')):
            raise ValueError()
        return PrebuiltNodeReader(executable, raw_root / 'probe.mjs', value, layout.work_root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeBundleError) as error:
        raise _failure('The authored prebuilt Node resources are missing or incompatible. Re-extract a verified candidate; no npm, compiler or download was started.') from error


def require_zzz_reader():
    """Source behavior stays separate; a probe can never authorize a game."""
    if discover_layout().mode == 'bundle':
        prebuilt_node_reader('voice-links')
