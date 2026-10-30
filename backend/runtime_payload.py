"""Closed native payload validation shared by packaging and desktop updates."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from .runtime_bundle import relative_resource

TARGETS = {'windows-x64', 'linux-x64', 'macos-x64', 'macos-arm64'}


class PackageError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise PackageError('Package paths must not traverse links or reparse points.')


def executable_target(path):
    with path.open('rb') as stream:
        data = stream.read(4096)
    if data.startswith(b'MZ') and len(data) >= 64:
        offset = struct.unpack_from('<I', data, 60)[0]
        if offset + 6 <= len(data) and data[offset:offset + 4] == b'PE\0\0':
            if struct.unpack_from('<H', data, offset + 4)[0] == 0x8664:
                return 'windows-x64'
    if data[:6] == b'\x7fELF\x02\x01' and len(data) >= 20 and struct.unpack_from('<H', data, 18)[0] == 62:
        return 'linux-x64'
    if data[:4] == b'\xcf\xfa\xed\xfe' and len(data) >= 8:
        cpu = struct.unpack_from('<I', data, 4)[0]
        return {0x1000007: 'macos-x64', 0x100000c: 'macos-arm64'}.get(cpu)
    raise PackageError('Runtime executable has an unsupported architecture or invalid header.')


def validate(root, receipt, target, *, candidate=False, installed=False):
    root = root.absolute()
    no_links(root)
    if target not in TARGETS:
        raise PackageError('Unsupported installer target.')
    if receipt.get('schema') != 'proxy-runtime-candidate-v1':
        raise PackageError('Expected the exact runtime candidate inventory.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(receipt.get('version', ''))):
        raise PackageError('Installer needs an exact numeric version.')
    if not re.fullmatch(r'[a-f0-9]{40}', str(receipt.get('source_commit', ''))):
        raise PackageError('Installer needs an exact source commit.')
    eligible = (receipt.get('profile') == 'runtime' and receipt.get('release_eligible') is True
        and receipt.get('redistribution_review') == 'approved' and receipt.get('native_acceptance') == 'approved')
    if not candidate and not eligible:
        raise PackageError('Release packaging requires exact target input, redistribution and native acceptance. Use --candidate for construction tests.')
    expected = {}
    entries = receipt.get('files')
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise PackageError('Invalid file inventory.')
    for entry in entries:
        name = relative_resource(entry.get('path', ''))
        if (name.casefold() in expected or not re.fullmatch(r'[a-f0-9]{64}', str(entry.get('sha256', '')))
                or type(entry.get('bytes')) is not int or entry['bytes'] < 0):
            raise PackageError('Duplicate or invalid inventory entry.')
        expected[name.casefold()] = entry
    if not expected:
        raise PackageError('Empty runtime payload.')
    directories = receipt.get('directories')
    if directories is None and not candidate:
        raise PackageError('Release inventory must bind its exact directories.')
    if directories is not None:
        if (not isinstance(directories, list) or any(relative_resource(name) != name for name in directories)
                or len({name.casefold() for name in directories}) != len(directories)):
            raise PackageError('Duplicate or invalid directory inventory.')
    actual_directories = []
    actual = {}
    for path in sorted(root.rglob('*')):
        linked = path.is_symlink()
        if not linked:
            no_links(path)
        if path.is_dir() and not linked:
            actual_directories.append(path.relative_to(root).as_posix())
            continue
        if not path.is_file() and not linked:
            raise PackageError('Runtime payload must contain regular files.')
        name = relative_resource(path.relative_to(root).as_posix())
        if installed and name == 'PROVENANCE.json' and not linked:
            continue
        if name.casefold() in actual:
            raise PackageError('Aliased runtime file.')
        actual[name.casefold()] = name
        entry = expected.get(name.casefold())
        if linked:
            link = os.readlink(path)
            if (target == 'windows-x64' or os.path.isabs(link) or root.resolve() not in path.resolve().parents
                    or not path.exists() or not entry or entry.get('link') != link):
                raise PackageError('Runtime symbolic link is outside the verified inventory.')
            size, sha = len(link.encode()), hashlib.sha256(link.encode()).hexdigest()
        else:
            size, sha = path.stat().st_size, digest(path)
        if not entry or entry['path'] != name or entry.get('bytes') != size or entry['sha256'] != sha:
            raise PackageError('Runtime inventory differs from the payload: ' + name)
    if set(actual) != set(expected):
        raise PackageError('Runtime inventory has missing files.')
    if directories is not None and sorted(actual_directories) != sorted(directories):
        raise PackageError('Runtime directory inventory differs from the payload.')
    executable = 'ProxyTranscriptRuntime.exe' if target == 'windows-x64' else 'ProxyTranscriptRuntime'
    if executable_target(root / executable) != target:
        raise PackageError('Runtime executable does not match the installer target.')
    manifest = json.loads((root / '_internal/runtime-manifest.json').read_text(encoding='utf-8'))
    for key in ('source_commit', 'version', 'build_id', 'profile', 'storage_epoch', 'host_protocol'):
        if manifest.get(key) != receipt.get(key):
            raise PackageError('Embedded runtime identity differs from candidate provenance.')
    if not (root / 'LICENSE').is_file() or not (root / 'THIRD_PARTY').is_dir():
        raise PackageError('Exact application and dependency notices are required.')
    return eligible


