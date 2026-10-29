"""Closed .NET helper resources; source SDK behavior is a separate adapter.

Only the authored probe may execute in this prototype. An owned NTE bridge
manifest can supply a source identity, but does not authorize its separately
acquired UEExtractor/native dependencies. Endfield constants remain unreviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from pathlib import PureWindowsPath
import re
import stat
import struct

from .preparation_errors import PreparationFailure
from .runtime_bundle import RuntimeBundleError, discover_layout, relative_resource

SCHEMA = 'proxy-prebuilt-dotnet-reader-v1'
ENTRIES = {'probe': 'ToolkitReaderProbe.exe', 'nte': 'NteReader.exe'}
SDK = '10.0.403'
RUNTIME = '10.0.14'
SHA = re.compile(r'[a-f0-9]{64}')
SDK_SHA512 = '7a114c318fa7f1d9822991b534b2814d0e78386ceda816b371f5141acefe741d87ccb606ede06cadac8f9ac5070e32b708a67bbd1619ff5e5a7858a27874ef48'
PACKAGES = {
    'Microsoft.NETCore.App.Runtime.win-x64': 'mLWGagTP5n7nMfJQI2XpXRYgvPcnyYvAc8ZiDfum8ShM0UcrPDyfW4Lqo45UtlCHCucERUHQuMTI6ybVweCN9A==',
    'Microsoft.NETCore.App.Host.win-x64': 'Kn602fS/n6hsgpCW8HzykOu31D/oNrxhETNlgoou5yj7Zvvw9KWX3GnG7hevtm9R3VKdP1kPEfQ0Y3eo83YafQ==',
}


def _failure(message):
    return PreparationFailure('bundle_toolchain_unavailable', message)


def _no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise _failure('Prebuilt helper resources cannot follow links or reparse points.')


def _identity(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate helper receipt key')
        result[key] = value
    return result


def _x64_image(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError()
    offset = struct.unpack_from('<I', data, 60)[0]
    if (offset + 26 > len(data) or data[offset:offset + 4] != b'PE\0\0'
            or struct.unpack_from('<H', data, offset + 4)[0] != 0x8664
            or struct.unpack_from('<H', data, offset + 24)[0] != 0x20b):
        raise ValueError()


def _source_names(kind):
    stem = 'ToolkitReaderProbe' if kind == 'probe' else 'NteReader'
    return {'scripts/game-readers/' + stem + suffix for suffix in ('.cs', '.csproj')} | {
        'packaging/game-readers/inputs.json', 'packaging/game-readers/global.json', 'scripts/build-game-reader-helpers.ps1'}


@dataclass(frozen=True)
class PrebuiltReader:
    kind: str
    executable: Path
    source_identity: str
    manifest: dict

    def command(self, arguments=()):
        if self.kind != 'probe':
            raise _failure('The owned NTE bridge has no accepted external reader/native toolchain. Keep the source runtime active.')
        if tuple(arguments) != ('--probe',):
            raise _failure('The authored helper only accepts its fixed probe operation.')
        return [str(self.executable), '--probe']

    def runtime_identity_command(self):
        if self.kind != 'nte':
            raise _failure('Runtime identity is a fixed operation of the owned NTE bridge only.')
        return [str(self.executable), '--runtime-identity']


def reader_environment(environ=None):
    """An owned apphost must not inherit compiler, loader or account state."""
    env = {key.upper(): value for key, value in (os.environ if environ is None else environ).items()}
    windows = env.get('WINDIR') or env.get('SYSTEMROOT')
    if not windows or not PureWindowsPath(windows).is_absolute():
        raise _failure('The Windows system runtime location is unavailable.')
    result = {name: env[name] for name in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if env.get(name)}
    result['PATH'] = str(PureWindowsPath(windows) / 'System32') + ';' + windows
    result['DOTNET_MULTILEVEL_LOOKUP'] = '0'
    return result


def prebuilt_reader(kind: str, *, layout=None) -> PrebuiltReader:
    if kind not in ENTRIES:
        raise _failure('Endfield remains blocked by unreviewed embedded constants; unknown helper kinds are not executable.')
    layout = layout or discover_layout()
    if layout.mode != 'bundle':
        raise _failure('The prebuilt reader resolver requires an explicit frozen resource layout.')
    prefix = 'helpers/' + kind + '/'
    try:
        _no_links(layout.resource_root / prefix)
        path = layout.resource(prefix + 'helper-manifest.json')
        _no_links(path)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
        if (value.get('schema') != SCHEMA or value.get('kind') != kind or value.get('entry') != ENTRIES[kind]
                or value.get('platform') != 'win-x64' or value.get('sdk_version') != SDK
                or value.get('runtime_version') != RUNTIME or value.get('source_commit') != layout.source_commit
                or value.get('source_dirty') is not False
                or value.get('purpose') != ('authored-probe-only' if kind == 'probe' else 'owned-bridge-only')):
            raise ValueError()
        files = value['files']
        if not isinstance(files, dict) or not files or len(files) > 2048 or ENTRIES[kind] not in files:
            raise ValueError()
        names = set()
        for name, entry in files.items():
            relative_resource(name)
            if name.casefold() in names or not isinstance(entry, dict) or set(entry) != {'bytes', 'sha256'}:
                raise ValueError()
            names.add(name.casefold())
            if (type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= 128 * 1024 * 1024
                    or not SHA.fullmatch(str(entry['sha256'])) or name.endswith(('.pdb', '.cs', '.dpapi', '.db'))
                    or Path(name).name.casefold().startswith(('ueextractor', 'cue4parse', 'oo2core', 'oodle'))
                    or any(part.casefold() in {'data', 'upstream', 'node_modules', '.git'} for part in Path(name).parts)):
                raise ValueError()
        expected = {prefix + name for name in (*files, 'helper-manifest.json')}
        if {name for name in layout.resources if name.startswith(prefix)} != expected or value.get('build_id') != _identity(files):
            raise ValueError()
        actual, directories = set(), set()
        for candidate in path.parent.rglob('*'):
            _no_links(candidate)
            if candidate.is_file():
                actual.add(candidate.relative_to(path.parent).as_posix())
            elif candidate.is_dir():
                directories.add(candidate.relative_to(path.parent).as_posix())
            else:
                raise ValueError()
        expected_directories = {parent.as_posix() for name in files for parent in Path(name).parents if parent != Path('.')}
        if actual != {*files, 'helper-manifest.json'} or directories != expected_directories or sum(entry['bytes'] for entry in files.values()) > 512 * 1024 * 1024:
            raise ValueError()
        for name, entry in files.items():
            candidate = layout.resource(prefix + name)
            _no_links(candidate)
            if not candidate.is_file() or candidate.stat().st_size != entry['bytes'] or hashlib.sha256(candidate.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError()
        sources = value['source_inputs']
        if not isinstance(sources, dict) or set(sources) != _source_names(kind) or any(not SHA.fullmatch(str(digest)) for digest in sources.values()):
            raise ValueError()
        stem = Path(ENTRIES[kind]).stem
        required = {ENTRIES[kind], stem + '.dll', stem + '.deps.json', stem + '.runtimeconfig.json',
                    'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll', 'System.Private.CoreLib.dll', 'build-receipt.json',
                    'restore-lock.json',
                    'notices/PROJECT-LICENSE.txt', 'notices/sdk-LICENSE.txt', 'notices/sdk-ThirdPartyNotices.txt'}
        if kind == 'probe':
            required.add('probe-resource.txt')
        if not required <= files.keys():
            raise ValueError()
        for package in PACKAGES:
            if not any(name.startswith('notices/' + package + '/') and 'license' in Path(name).name.casefold() for name in files):
                raise ValueError()
        runtime = json.loads((path.parent / (stem + '.runtimeconfig.json')).read_text(encoding='utf-8'))['runtimeOptions']
        if (runtime.get('includedFrameworks') != [{'name': 'Microsoft.NETCore.App', 'version': RUNTIME}]
                or runtime.get('framework') or runtime.get('frameworks')):
            raise ValueError()
        deps = json.loads((path.parent / (stem + '.deps.json')).read_text(encoding='utf-8'))
        if not deps.get('runtimeTarget', {}).get('name', '').endswith('/win-x64'):
            raise ValueError()
        receipt = json.loads((path.parent / 'build-receipt.json').read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
        if (receipt.get('schema') != 'proxy-dotnet-helper-build-receipt-v1' or receipt.get('source_commit') != layout.source_commit
                or receipt.get('source_dirty') is not False
                or receipt.get('source_inputs') != sources or receipt.get('sdk_version') != SDK
                or receipt.get('runtime_version') != RUNTIME or receipt.get('sdk', {}).get('sha512') != SDK_SHA512
                or not SHA.fullmatch(str(receipt.get('dotnet_executable_sha256', '')))
                or not SHA.fullmatch(str(receipt.get('restore_lock_sha256', '')))):
            raise ValueError()
        packages = receipt.get('runtime_packages')
        if (not isinstance(packages, list) or len(packages) != len(PACKAGES)
                or any(not isinstance(item, dict) or item.get('version') != RUNTIME for item in packages)
                or {item['name']: item['sha512_base64'] for item in packages} != PACKAGES
                or value.get('sdk_archive') != receipt['sdk'] or value.get('runtime_packages') != packages
                or value.get('restore_lock_sha256') != receipt['restore_lock_sha256']
                or files['restore-lock.json']['sha256'] != receipt['restore_lock_sha256']
                or value.get('dotnet_executable_sha256') != receipt['dotnet_executable_sha256']):
            raise ValueError()
        for field in ('sdk_installed_files', 'runtime_package_files'):
            entries = receipt.get(field)
            if not isinstance(entries, dict) or not entries:
                raise ValueError()
            for name, digest in entries.items():
                relative_resource(name)
                if not SHA.fullmatch(str(digest)):
                    raise ValueError()
        if receipt['sdk_installed_files'].get('dotnet.exe') != receipt['dotnet_executable_sha256']:
            raise ValueError()
        for name in (ENTRIES[kind], 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll'):
            _x64_image((path.parent / name).read_bytes())
        native_hashes = set(receipt['runtime_package_files'].values())
        for name in ('hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll', 'System.Private.CoreLib.dll'):
            if files[name]['sha256'] not in native_hashes:
                raise ValueError()
        owned = {ENTRIES[kind], stem + '.dll', stem + '.deps.json', stem + '.runtimeconfig.json',
                 'build-receipt.json', 'restore-lock.json'}
        if kind == 'probe':
            owned.add('probe-resource.txt')
        if any('/' not in name and name not in owned and item['sha256'] not in native_hashes for name, item in files.items()):
            raise ValueError()
        source_identity = _identity(sources)
        return PrebuiltReader(kind, path.parent / ENTRIES[kind], source_identity, value)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeBundleError) as error:
        raise _failure('The prebuilt reader resources are missing or incompatible. Re-extract a verified candidate; no SDK or download was started.') from error


def require_game_reader(kind: str) -> None:
    """Never interpret a probe/bridge receipt as rights to run a game chain."""
    if discover_layout().mode == 'bundle':
        reason = 'unreviewed embedded game constants' if kind == 'endfield' else 'unverified external UEExtractor/native dependencies'
        raise _failure('The frozen ' + kind + ' reader remains unavailable due to ' + reason + '. Keep using the source runtime.')


def reader_source_identity(kind: str, *, layout=None) -> str:
    return prebuilt_reader(kind, layout=layout).source_identity
