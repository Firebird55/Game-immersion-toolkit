"""Small source/frozen host boundary; resolving a layout performs no writes.

The frozen executable is a dispatcher, never a Python interpreter. All mutable
roots are explicit and application resources have a closed, hash-checked list.
This module intentionally imports only the standard library: the Windows job
bootstrap must join its job before any extraction or native library imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
from typing import Mapping, Sequence

SCHEMA = 'proxy-runtime-host-v1'
MANIFEST_SCHEMA = 'proxy-runtime-bundle-v1'
CHILD_TARGETS = {
    'owned-process': ('module', 'backend.owned_process'),
    'gateway': ('module', 'backend.desktop_gateway'),
    'frontend': ('module', 'backend.desktop_frontend'),
    'api': ('module', 'backend.main'),
    'window-capture': ('module', 'backend.window_capture_worker'),
    'language': ('module', 'backend.language_worker'),
    'game-index': ('module', 'backend.game_index_worker'),
    'mobile-export': ('module', 'backend.mobile_export_worker'),
    'toolkit-update': ('module', 'backend.toolkit_update'),
    'windows-bootstrap': ('bootstrap', 'backend.windows_preparation_process'),
    'asr': ('module', 'backend.agent_transcribe'),
    'agent-fingerprints': ('module', 'scripts.build_agent_fingerprints'),
    'story-fingerprints': ('module', 'scripts.build_story_fingerprints'),
    'capture-readiness': ('script', 'scripts/check-capture-readiness.py'),
    'account-key': ('module', 'scripts.set_lexirise_key'),
    'native-setup': ('module', 'backend.native_setup'),
    'index-pragmata': ('module', 'scripts.index_pragmata_assets'),
    'index-voice': ('module', 'scripts.index_voice_assets'),
    'update-voice': ('module', 'scripts.update_voice_assets'),
}
# The extracted experiment has no live updater. Account entry is a fixed local
# product dialog; verification is GET-only and writes stay in protected storage.
# ASR is accepted only by its own image, with its own native dependency tree.
EXPERIMENT_CHILDREN = tuple(kind for kind in CHILD_TARGETS if kind != 'toolkit-update')
SOURCE_RESOURCES = frozenset({
    'package.json', 'public/mobile-capture/games-data.json',
    'assets/fireredvad/fireredvad_vad.onnx', 'assets/fireredvad/cmvn.ark',
    'assets/fireredvad/PROVENANCE.json', 'assets/fireredvad/LICENSE',
    'assets/fireredvad/NOTICE.md', 'scripts/check-capture-readiness.py',
    'scripts/select-game-folders.ps1', 'scripts/select-export-folder.ps1',
    'scripts/endfield-reader-sources.json', 'scripts/game-readers/NteReader.csproj',
    'scripts/game-readers/EndfieldReader.csproj',
})
_ROOT_FIELDS = ('data_root', 'settings_root', 'cache_root', 'tool_root',
                'work_root', 'state_root', 'default_export_root')


class RuntimeBundleError(RuntimeError):
    """An incomplete or unsafe runtime cannot start the requested operation."""


def relative_resource(value: str) -> str:
    """Accept one portable file name, rejecting Windows aliases on every host."""
    if not isinstance(value, str):
        raise RuntimeBundleError('Invalid runtime resource name.')
    path = PurePosixPath(value)
    if (not value or '\\' in value or path.is_absolute()
            or PureWindowsPath(value).drive or path.as_posix() != value
            or any(part in {'.', '..'} or ':' in part or part.endswith((' ', '.'))
                   or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
                   for part in path.parts)):
        raise RuntimeBundleError('Invalid runtime resource name.')
    return value


def _absolute(value, label):
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeBundleError(f'{label} must be an absolute path.')
    return path.resolve()


def _within(path, root):
    return path == root or root in path.parents


@dataclass(frozen=True)
class RuntimeLayout:
    mode: str
    application_root: Path
    resource_root: Path
    data_root: Path
    settings_root: Path
    cache_root: Path
    tool_root: Path
    work_root: Path
    state_root: Path
    default_export_root: Path
    legacy_root: Path | None = None
    version: str = ''
    source_commit: str = ''
    build_id: str = ''
    schema: str = SCHEMA
    executable: Path = field(default_factory=lambda: Path(sys.executable).resolve())
    resources: Mapping[str, str] = field(default_factory=dict, repr=False)
    children: tuple[str, ...] = ()
    profile: str = 'source'
    storage_epoch: int = 1
    host_protocol: int = 1

    def __post_init__(self):
        if self.schema != SCHEMA or self.mode not in {'source', 'bundle'}:
            raise RuntimeBundleError('Unsupported runtime layout schema or mode.')
        if any(type(value) is not int or value < 1 for value in (self.storage_epoch, self.host_protocol)):
            raise RuntimeBundleError('Invalid runtime storage epoch or host protocol.')
        for name in ('application_root', 'resource_root', 'executable', *_ROOT_FIELDS):
            if self.mode == 'bundle':
                original = Path(getattr(self, name))
                if any(item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                           & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
                       for item in (original, *original.parents)):
                    raise RuntimeBundleError('Frozen runtime roots cannot use links or reparse points.')
                if name in _ROOT_FIELDS and any((item / '.git').exists() for item in (original, *original.parents)):
                    raise RuntimeBundleError('Frozen writable roots cannot be inside a source repository.')
            object.__setattr__(self, name, _absolute(getattr(self, name), name))
        if self.legacy_root is not None:
            object.__setattr__(self, 'legacy_root', _absolute(self.legacy_root, 'legacy_root'))
        if self.mode == 'bundle':
            immutable = (self.application_root, self.resource_root)
            for name in _ROOT_FIELDS:
                path = getattr(self, name)
                if any(_within(path, root) or _within(root, path) for root in immutable):
                    raise RuntimeBundleError(f'{name} overlaps immutable application resources.')
            # Settings intentionally contains the versioned sibling roots. A
            # disposable root may never contain durable data, tools or exports.
            for transient in (self.cache_root, self.work_root):
                for durable in (self.data_root, self.tool_root, self.state_root, self.default_export_root):
                    if _within(durable, transient) or _within(transient, durable):
                        raise RuntimeBundleError('Disposable and durable runtime roots overlap.')
                if _within(self.settings_root, transient):
                    raise RuntimeBundleError('Settings root cannot sit inside disposable cache or work storage.')
            durable = (self.data_root, self.tool_root, self.state_root, self.default_export_root)
            for index, left in enumerate(durable):
                if any(_within(left, right) or _within(right, left) for right in durable[index + 1:]):
                    raise RuntimeBundleError('Durable runtime roots overlap.')

    @property
    def legacy_project_root(self):
        if self.mode == 'bundle':
            raise RuntimeBundleError('This service still requires the source layout; use explicit runtime data roots.')
        return self.legacy_root or self.application_root

    def resource(self, relative_name: str) -> Path:
        name = relative_resource(relative_name)
        allowed = SOURCE_RESOURCES if self.mode == 'source' else self.resources
        if name not in allowed:
            raise RuntimeBundleError('Resource is not allowlisted for this runtime: ' + name)
        path = (self.resource_root / name).resolve()
        if not _within(path, self.resource_root) or not path.is_file():
            raise RuntimeBundleError('Runtime resource is missing or outside its resource tree: ' + name)
        if self.mode == 'bundle':
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != self.resources[name]:
                raise RuntimeBundleError('Runtime resource checksum failed: ' + name)
        return path

    def child_command(self, kind: str, arguments: Sequence[str] = ()) -> list[str]:
        if kind not in CHILD_TARGETS:
            raise RuntimeBundleError('Unknown runtime child kind.')
        if isinstance(arguments, (str, bytes)) or any(not isinstance(arg, str) or '\0' in arg for arg in arguments):
            raise RuntimeBundleError('Runtime child arguments must be a sequence of strings.')
        target_type, target = CHILD_TARGETS[kind]
        if self.mode == 'source':
            if target_type == 'bootstrap':
                return [str(self.executable), str(self.application_root / 'backend/windows_preparation_process.py'), *arguments]
            if target_type == 'script':
                return [str(self.executable), str(self.resource(target)), *arguments]
            return [str(self.executable), '-m', target, *arguments]
        if kind not in self.children:
            raise RuntimeBundleError('This diagnostic bundle does not include child: ' + kind)
        image = self.application_root / 'asr' / ('ProxyTranscriptAsr.exe' if sys.platform == 'win32' else 'ProxyTranscriptAsr') if kind == 'asr' else self.executable
        if not image.is_file():
            raise RuntimeBundleError('Frozen child executable is missing: ' + kind)
        return [str(image), '--runtime-child', kind, '--', *arguments]

    def child_environment(self, kind: str | None = None, environ: Mapping[str, str] | None = None) -> dict[str, str]:
        if kind is not None and kind not in CHILD_TARGETS:
            raise RuntimeBundleError('Unknown runtime child kind.')
        result = dict(os.environ if environ is None else environ)
        result['PROXY_TRANSCRIPT_LAYOUT_SCHEMA'] = self.schema
        if self.mode == 'source':
            # Source entrypoints retain their own --root/constructor argument
            # contracts. Injecting a global DATA_ROOT would override an explicit
            # child --root and could redirect its writes to another installation.
            for name in _ROOT_FIELDS:
                result.pop('PROXY_TRANSCRIPT_' + name.upper(), None)
            result['PROXY_TRANSCRIPT_PROJECT_ROOT'] = str(self.legacy_project_root)
        else:
            for name in _ROOT_FIELDS:
                result['PROXY_TRANSCRIPT_' + name.upper()] = str(getattr(self, name))
            # Each worker has an independent bootloader lifetime. Never reuse a
            # parent's extraction/native state, particularly the ASR helper.
            result['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            result.pop('PROXY_TRANSCRIPT_PROJECT_ROOT', None)
            if kind == 'asr':
                result['PATH'] = os.pathsep.join(entry for entry in result.get('PATH', '').split(os.pathsep)
                    if entry and not _within(Path(entry).resolve(), self.application_root))
        return result


def discover_layout(environ: Mapping[str, str] | None = None) -> RuntimeLayout:
    env = os.environ if environ is None else environ
    if env.get('PROXY_TRANSCRIPT_LAYOUT_SCHEMA', SCHEMA) != SCHEMA:
        raise RuntimeBundleError('Unsupported runtime layout schema.')
    code = Path(__file__).resolve().parents[1]
    frozen = bool(getattr(sys, 'frozen', False))
    app = Path(sys.executable).absolute().parent if frozen else code
    resources = Path(getattr(sys, '_MEIPASS', app)).absolute() if frozen else code
    legacy = _absolute(env.get('PROXY_TRANSCRIPT_PROJECT_ROOT', code), 'legacy_root') if not frozen else None
    if frozen:
        try:
            manifest = json.loads((resources / 'runtime-manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise RuntimeBundleError('Frozen runtime manifest is missing or invalid; re-extract a verified candidate.') from error
        if manifest.get('schema') != MANIFEST_SCHEMA:
            raise RuntimeBundleError('Unsupported frozen runtime manifest.')
        if (manifest.get('profile') not in {'diagnostic', 'frontend-experiment', 'runtime-experiment', 'runtime'}
                or not re.fullmatch(r'\d+\.\d+\.\d+', str(manifest.get('version', '')))
                or not re.fullmatch(r'[a-f0-9]{40}', str(manifest.get('source_commit', '')))
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', str(manifest.get('build_id', '')))):
            raise RuntimeBundleError('Frozen runtime identity is incomplete.')
        files = manifest.get('resources')
        if (not isinstance(files, dict) or any(not isinstance(name, str) or not isinstance(digest, str)
                or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest)
                for name, digest in files.items())):
            raise RuntimeBundleError('Frozen resource inventory is invalid.')
        for name in files:
            relative_resource(name)
        children = manifest.get('children', [])
        if (not isinstance(children, list) or any(not isinstance(kind, str) or kind not in CHILD_TARGETS for kind in children)
                or len(set(children)) != len(children)
                or (manifest['profile'] == 'diagnostic' and children)
                or (manifest['profile'] == 'frontend-experiment' and children != ['frontend'])
                or (manifest['profile'] == 'runtime-experiment' and tuple(children) not in (EXPERIMENT_CHILDREN, ('asr',)))):
            raise RuntimeBundleError('Frozen child inventory is invalid.')
        missing = [name for name in _ROOT_FIELDS if not env.get('PROXY_TRANSCRIPT_' + name.upper())]
        if missing:
            raise RuntimeBundleError('Frozen runtime needs explicitly selected writable roots: ' + ', '.join(missing))
        # Keep the raw selection until RuntimeLayout checks every existing
        # ancestor for links/reparse points and forbidden repository ancestry.
        roots = {name: Path(env['PROXY_TRANSCRIPT_' + name.upper()]) for name in _ROOT_FIELDS}
    else:
        manifest = {}
        if 'LOCALAPPDATA' in env:
            settings = Path(env['LOCALAPPDATA']) / 'Proxy Transcript'
        elif sys.platform == 'darwin':
            settings = Path.home() / 'Library/Application Support/Game Immersion Toolkit'
        else:
            settings = Path(env.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'game-immersion-toolkit'
        defaults = dict(data_root=legacy / 'data', settings_root=settings,
            cache_root=settings / 'cache-v1', tool_root=legacy / 'data',
            work_root=legacy / 'work/voice-assets', state_root=legacy / 'data',
            default_export_root=legacy / 'output/mobile-libraries')
        roots = {name: _absolute(value, name) for name, value in defaults.items()}
        for name, default in roots.items():
            selected = env.get('PROXY_TRANSCRIPT_' + name.upper())
            if selected and _absolute(selected, name) != default:
                raise RuntimeBundleError('The source runtime requires the legacy project layout; separate writable roots are frozen-only.')
        files, children = {}, []
    try:
        package = json.loads((resources / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        package = {}
    return RuntimeLayout(mode='bundle' if frozen else 'source', application_root=app,
        resource_root=resources, legacy_root=legacy, **roots,
        version=manifest.get('version', package.get('version', '')),
        source_commit=manifest.get('source_commit', ''), build_id=manifest.get('build_id', ''),
        resources=files, children=tuple(children), profile=manifest.get('profile', 'source'),
        storage_epoch=manifest.get('storage_epoch', 1), host_protocol=manifest.get('host_protocol', 1))


def child_command(kind: str, arguments: Sequence[str] = (), *, layout: RuntimeLayout | None = None) -> list[str]:
    return (layout or discover_layout()).child_command(kind, arguments)


def resource_path(relative_name: str, *, layout: RuntimeLayout | None = None) -> Path:
    return (layout or discover_layout()).resource(relative_name)


def child_environment(kind: str | None = None, *, layout: RuntimeLayout | None = None,
                      environ: Mapping[str, str] | None = None) -> dict[str, str]:
    return (layout or discover_layout()).child_environment(kind, environ)
