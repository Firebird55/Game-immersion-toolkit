"""Resolve the same verified audio tools for every packaged game reader.

Only resources bound by the enclosing runtime manifest may execute. This module
does not download tools, consult PATH, approve a release, or repair an install.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import stat
import sys

from .runtime_bundle import RuntimeBundleError, discover_layout, relative_resource

PREFIX = 'codecs/audio/'
SCHEMA = 'toolkit-audio-runtime-v1'
TOOLS = frozenset({'ffmpeg', 'vgmstream'})


def host_target():
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    system = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform)
    return f'{system}-{arch}' if system and arch else None


def packaged_codec_executable(tool: str, *, layout=None) -> Path | None:
    """Return a verified immutable executable, or None for a missing capability.

    Corrupt/incomplete resources are unavailable rather than falling through to
    an unrelated executable in a working directory or developer installation.
    Every companion library is checked before returning the entry point.
    """
    if tool not in TOOLS:
        raise ValueError('Unknown audio tool')
    layout = layout or discover_layout()
    if layout.mode != 'bundle':
        return None
    try:
        def resource(name):
            name = relative_resource(name)
            path = layout.resource_root / name
            for candidate in (path, *path.parents):
                if candidate.is_symlink() or (candidate.exists() and getattr(candidate.lstat(), 'st_file_attributes', 0)
                        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                    raise ValueError('Linked audio resources')
            return layout.resource(name)

        manifest = resource(PREFIX + 'runtime.json')
        if manifest.stat().st_size > 1024 * 1024:
            return None
        value = json.loads(manifest.read_text(encoding='utf-8'))
        if value.get('schema') != SCHEMA or value.get('target') != host_target():
            return None
        entries = value['tools']
        entry = entries.get(tool)
        if entry is None:
            return None
        expected = ('ffmpeg' if tool == 'ffmpeg' else 'vgmstream-cli') + ('.exe' if sys.platform == 'win32' else '')
        if entry != expected or not isinstance(value['files'], dict) or not value['files']:
            return None
        files = value['files']
        if entry not in files or 'NOTICE.txt' not in files:
            return None
        # A stray DLL can change native loading even if all expected files pass.
        root = manifest.parent
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != set(files) | {'runtime.json'}:
            return None
        for name, digest in files.items():
            if name == 'runtime.json' or relative_resource(name) != name:
                return None
            path = resource(PREFIX + name)
            if layout.resources.get(PREFIX + name) != digest:
                return None
        executable = resource(PREFIX + entry)
        with executable.open('rb') as stream:
            header = stream.read(64)
            if sys.platform == 'win32':
                if len(header) != 64 or header[:2] != b'MZ':
                    return None
                stream.seek(int.from_bytes(header[60:64], 'little'))
                if stream.read(6) != b'PE\0\0\x64\x86':
                    return None
            elif sys.platform == 'linux':
                if header[:5] != b'\x7fELF\x02' or header[5] != 1 or int.from_bytes(header[18:20], 'little') != {'x64': 62, 'arm64': 183}[host_target().split('-')[1]]:
                    return None
            else:
                cpu = {'x64': 0x01000007, 'arm64': 0x0100000C}[host_target().split('-')[1]]
                if header[:4] != b'\xcf\xfa\xed\xfe' or int.from_bytes(header[4:8], 'little') != cpu:
                    return None
        return executable
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeBundleError):
        return None
