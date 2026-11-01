"""Fixed app-local Node resources; no npm, TypeScript, PATH or game fallback.

The historical authored probe remains separate from the production reader.
Production commands require a closed resource inventory and the shared pinned
Node runtime; probe receipts and approval-like strings cannot authorize them.
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
        raise _failure('This historical resolver accepts only the authored probe. Production games require their verified reader resources.')
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


ZZZ_PREFIX = 'toolchains/zzz/'
ZZZ_SCHEMA = 'toolkit-zzz-reader-v1'
ZZZ_SCRIPTS = ('extract_voice_links.mjs', 'extract_cinematic_links.mjs', 'scene-catalog.mjs',
               'cinematic-links.mjs', 'comic-links.mjs', 'zzz-dialogue.mjs')
ZZZ_DEPENDENCIES = {
    'ooz/package.json': '44a8f84d67fe48d832560bdb0d6d1b853092cb2b20dff5683fb7b904b4501be1',
    'ooz/index.js': '042a89949156d960ccb4ab67026edb35fd9f116b78852d44c7d92889685f4562',
    # Owned Emscripten 6.0.13 build from the retained GPL preferred source.
    'ooz/build/ooz.js': 'b49c334cb0ecfeb632ae3696744eef794200b953218e69066f11b216e9c9bf83',
    'ooz/LICENSE': '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986',
    'xxhash/package.json': 'f2c48d47dbdef2f9a3e0fb1025a1394726a1028ddee21f5c38452de50d00bcf2',
    'xxhash/esm/xxhash-wasm.js': 'e3be9143c10d60a015448de1ceef383b8f2ea1fd2773a5a5c69973ed52d8325a',
    'xxhash/LICENSE.md': '6f6b3afa109ea0d073b8e3cf0feea0aba07d357fcdebeef54dd34b3c0b3f9ac5',
}


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@dataclass(frozen=True)
class ZzzReader:
    executable: Path
    root: Path
    identity: str
    work_root: Path

    def command(self, mode, *, game_data, work):
        """Only owned scene operations, reading a game and writing private work."""
        if mode not in {'dialogue', 'comic', 'cinematic'}:
            raise _failure('Unsupported ZZZ reader operation.')
        game_data, work = Path(game_data), Path(work)
        for path in (game_data, work):
            if not path.is_absolute() or path != path.resolve():
                raise _failure('ZZZ game and work paths must be explicit absolute normalized paths.')
            _no_links(path)
        if (not game_data.is_dir() or not work.is_dir() or work == self.work_root
                or not _within(work, self.work_root) or _within(work, game_data)
                or _within(game_data, work) or _within(work, self.root)):
            raise _failure('ZZZ preparation requires a separate private work directory outside the game.')
        # Existing metadata/output names cannot redirect generated data elsewhere.
        for candidate in work.rglob('*'):
            _no_links(candidate)
        compiled = str(self.root / 'upstream/galgame-perform.mjs')
        if mode == 'cinematic':
            return [str(self.executable), str(self.root / 'scripts/extract_cinematic_links.mjs'),
                    str(game_data), str(work), compiled]
        return [str(self.executable), str(self.root / 'scripts/extract_voice_links.mjs'),
                str(game_data), str(work), mode, 'language-links-' + mode + '.json', compiled]

    environment = staticmethod(PrebuiltNodeReader.environment)


def production_zzz_reader(*, layout=None) -> ZzzReader:
    """Verify real packaged reader bytes; never use mutable/PATH code fallbacks."""
    from .game_tools import READER_REVISION, READER_SHA
    from .node_tools import ARCHIVES, NODE_VERSION, host_platform
    layout = layout or discover_layout()
    try:
        if layout.mode != 'bundle' or layout.profile != 'runtime':
            raise ValueError('Production profile required')

        def resource(name):
            _no_links(layout.resource_root / name)
            return layout.resource(name)

        manifest = resource(ZZZ_PREFIX + 'runtime.json')
        if manifest.stat().st_size > 256 * 1024:
            raise ValueError('Oversized reader manifest')
        value = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
        target = host_platform()
        if (value.get('schema') != ZZZ_SCHEMA or value.get('platform') != target
                or value.get('source_commit') != layout.source_commit or value.get('source_dirty') is not False
                or value.get('upstream_revision') != READER_REVISION or value.get('upstream_sha256') != READER_SHA):
            raise ValueError('Incompatible reader identity')
        files = value['files']
        required = {'upstream/galgame-perform.ts', 'upstream/galgame-perform.mjs', 'upstream/LICENSE',
                    'inputs.json', 'BUILD-RECIPE.json', 'TOOLKIT-LICENSE', 'sources/ooz-build/ooz-build.json',
                    *('scripts/' + name for name in ZZZ_SCRIPTS),
                    *('dependencies/' + name for name in ZZZ_DEPENDENCIES)}
        if not isinstance(files, dict) or not required.issubset(files):
            raise ValueError('Incomplete reader inventory')
        for name, entry in files.items():
            relative_resource(name)
            if (name not in required and not name.startswith(('sources/', 'notices/'))
                    or not isinstance(entry, dict) or set(entry) != {'bytes', 'sha256'}
                    or type(entry['bytes']) is not int or not 1 <= entry['bytes'] <= 150 * 1024 * 1024
                    or not SHA.fullmatch(str(entry['sha256']))):
                raise ValueError('Unexpected reader resource')
        identity = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if value.get('build_id') != identity:
            raise ValueError('Reader inventory identity differs')
        expected = {*files, 'runtime.json'}
        if {name.removeprefix(ZZZ_PREFIX) for name in layout.resources if name.startswith(ZZZ_PREFIX)} != expected:
            raise ValueError('Unbound reader files')
        root = layout.resource_root / ZZZ_PREFIX
        allowed_dirs = {parent.as_posix() for name in expected for parent in Path(name).parents if parent != Path('.')}
        actual = set()
        for candidate in root.rglob('*'):
            _no_links(candidate)
            name = candidate.relative_to(root).as_posix()
            if candidate.is_dir():
                if name not in allowed_dirs:
                    raise ValueError('Unexpected reader directory')
            elif candidate.is_file():
                actual.add(name)
            else:
                raise ValueError('Unsupported reader file type')
        if actual != expected:
            raise ValueError('Reader files differ')
        for name, entry in files.items():
            path = resource(ZZZ_PREFIX + name)
            if path.stat().st_size != entry['bytes'] or _digest(path) != entry['sha256']:
                raise ValueError('Reader resource differs')
        if files['upstream/galgame-perform.ts']['sha256'] != READER_SHA or any(
                files['dependencies/' + name]['sha256'] != digest for name, digest in ZZZ_DEPENDENCIES.items()):
            raise ValueError('Supplier reader bytes differ')
        if value.get('inputs_sha256') != files['inputs.json']['sha256']:
            raise ValueError('Supplier inputs identity differs')
        if value.get('ooz_build_sha256') != files['sources/ooz-build/ooz-build.json']['sha256']:
            raise ValueError('Source-built decoder receipt identity differs')
        node_manifest = resource('toolchains/node/runtime.json')
        if node_manifest.stat().st_size > 16384:
            raise ValueError('Oversized Node manifest')
        node = json.loads(node_manifest.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
        executable_name = 'node.exe' if target.startswith('win-') else 'node'
        if (target not in ARCHIVES or node.get('schema') != 'toolkit-node-runtime-v1'
                or node.get('platform') != target or node.get('version') != NODE_VERSION
                or node.get('executable') != executable_name or node.get('archive_sha256') != ARCHIVES[target][1]):
            raise ValueError('Incompatible Node runtime')
        executable = resource('toolchains/node/' + executable_name)
        if _digest(executable) != node.get('executable_sha256'):
            raise ValueError('Node executable identity differs')
        resource('toolchains/node/LICENSE')
        return ZzzReader(executable, root, identity, layout.work_root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeBundleError) as error:
        raise _failure('The bundled ZZZ scene reader or Node runtime is missing or incompatible. Repair the toolkit installation; no system Node.js, npm or compiler fallback was started.') from error


def require_zzz_reader():
    """Source behavior stays separate; a probe can never authorize a game."""
    layout = discover_layout()
    return production_zzz_reader(layout=layout) if layout.mode == 'bundle' else None
