"""Pinned CPython archive planning and verification; standard library only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import tarfile

PINS = Path(__file__).resolve().parent
PIN_FILES = {'windows-x64': 'python-supplier.json',
             'linux-x64': 'python-supplier-linux-x64.json',
             'macos-arm64': 'python-supplier-macos-arm64.json'}
ARCHIVE_LIMIT = 128 * 1024 * 1024
PAYLOAD_LIMIT = 512 * 1024 * 1024
MEMBER_LIMIT = 50_000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Python paths must not traverse links or reparse points.')


def host_target():
    machine = platform.machine().lower()
    system = platform.system()
    if machine in ('amd64', 'x86_64') and system in ('Windows', 'Linux'):
        return 'windows-x64' if system == 'Windows' else 'linux-x64'
    if machine in ('arm64', 'aarch64') and system == 'Darwin':
        return 'macos-arm64'
    raise ValueError('No pinned desktop Python supplier for this native target.')


def load_pin(target=None):
    target = target or host_target()
    if target not in PIN_FILES:
        raise ValueError('Unsupported desktop Python target.')
    pin = json.loads((PINS / PIN_FILES[target]).read_text(encoding='utf-8'))
    if (pin.get('schema') != 'proxy-runtime-python-supplier-v1' or pin.get('target') != target
            or not re.fullmatch(r'[a-f0-9]{64}', pin.get('sha256', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', pin.get('source_commit', ''))
            or pin.get('immutable_release_observed') is not True
            or type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= ARCHIVE_LIMIT):
        raise ValueError('Incomplete exact Python supplier pin.')
    return pin


def member_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or path.as_posix() != value or '\\' in value
            or ':' in value or any(part in ('.', '..') or part.endswith((' ', '.')) for part in path.parts)):
        raise ValueError('Unsafe Python archive path.')
    return path


def archive_plan(archive, pin):
    """Validate the complete archive graph before creating any output paths."""
    no_links(archive)
    if (archive.stat().st_size > ARCHIVE_LIMIT or digest(archive) != pin['sha256']
            or 'bytes' in pin and archive.stat().st_size != pin['bytes']):
        raise ValueError('Python supplier archive differs from the exact observed pin.')
    target = pin.get('target', 'windows-x64')
    if target not in PIN_FILES:
        raise ValueError('Unsupported desktop Python target.')
    # Linux terminfo deliberately contains distinct upper/lower-case names.
    # Windows and default macOS filesystems must never accept such aliases.
    key = (lambda name: name) if target == 'linux-x64' else str.casefold
    entries, names, total = {}, {}, 0
    with tarfile.open(archive) as package:
        for count, member in enumerate(package, 1):
            if count > MEMBER_LIMIT:
                raise ValueError('Python archive has too many entries.')
            name = member.name.rstrip('/') if member.isdir() else member.name
            path = member_path(name)
            if path.parts[0] != 'python':
                raise ValueError('Python archive has an unexpected root.')
            if name == 'python' and member.isdir():
                continue
            if len(path.parts) < 2 or key(name) in names:
                raise ValueError('Python archive contains aliases or duplicate paths.')
            if not (member.isfile() or member.isdir() or member.issym() and target != 'windows-x64'):
                raise ValueError('Python archive contains unsupported links or special files.')
            if member.mode & 0o7000 or member.size < 0:
                raise ValueError('Python archive has unsafe permissions or sizes.')
            total += member.size
            if total > PAYLOAD_LIMIT:
                raise ValueError('Python archive exceeds its expanded size limit.')
            entries[name] = member
            names[key(name)] = name
    if not entries:
        raise ValueError('Python archive is empty.')
    for name in entries:
        for parent in PurePosixPath(name).parents:
            entry = entries.get(names.get(key(parent.as_posix())))
            if entry is not None and not entry.isdir():
                raise ValueError('Python archive writes through a file or symbolic link.')

    def resolve_link(name, seen):
        if name in seen or len(seen) >= 64:
            raise ValueError('Python archive contains cyclic symbolic links.')
        entry = entries.get(name)
        if entry is None:
            raise ValueError('Python archive contains a broken symbolic link.')
        if entry.isfile():
            return name
        if not entry.issym():
            raise ValueError('Python symbolic links must resolve to regular supplier files.')
        link = entry.linkname
        if not link or link.startswith('/') or '\\' in link or ':' in link:
            raise ValueError('Python archive contains an absolute symbolic link.')
        parts = list(PurePosixPath(name).parent.parts)
        for part in link.split('/'):
            if part in ('', '.'):
                raise ValueError('Python archive contains a noncanonical symbolic link.')
            if part == '..':
                if len(parts) <= 1:
                    raise ValueError('Python symbolic link escapes the supplier root.')
                parts.pop()
            else:
                if part.endswith((' ', '.')):
                    raise ValueError('Python symbolic link contains an aliased path.')
                parts.append(part)
        destination = names.get(key('/'.join(parts)))
        if destination is None:
            raise ValueError('Python archive contains a broken symbolic link.')
        # No intermediate symlink directories are permitted by the parent pass.
        return resolve_link(destination, seen | {name})

    for name, entry in entries.items():
        if entry.issym():
            resolve_link(name, set())
    for relative in pin.get('required_files', ['python312.dll']):
        entry = entries.get('python/' + relative)
        if entry is None or not entry.isfile():
            raise ValueError('Python shared runtime, executable or license is missing.')
    return entries


def mutable_build_file(relative):
    # pip and wheel installation change only these supplier-provided paths.
    # Everything else, including the standard library and native runtime, must
    # still match the archive after dependency preparation.
    return (relative.endswith('.pyc') or relative.startswith(('Lib/site-packages/', 'Scripts/',
            'lib/python3.12/site-packages/')) or relative in ('bin/pip', 'bin/pip3', 'bin/pip3.12'))


def verify_installed(archive, prefix, pin, *, include_build_files=False):
    no_links(prefix)
    entries = archive_plan(archive, pin)
    files = []
    with tarfile.open(archive) as package:
        for name, member in entries.items():
            relative = name[len('python/'):]
            if member.isdir() or not include_build_files and mutable_build_file(relative):
                continue
            path = prefix / relative
            no_links(path.parent)
            if member.issym():
                if (not path.is_symlink() or os.readlink(path) != member.linkname
                        or not path.is_file() or prefix.resolve() not in path.resolve().parents):
                    raise ValueError('Provisioned Python symbolic link differs from the supplier archive: ' + relative)
                files.append({'path': relative, 'link': member.linkname,
                    'sha256': hashlib.sha256(member.linkname.encode()).hexdigest()})
                continue
            no_links(path)
            expected = hashlib.file_digest(package.extractfile(member), 'sha256').hexdigest()
            if not path.is_file() or digest(path) != expected:
                raise ValueError('Provisioned Python differs from the supplier archive: ' + relative)
            if pin.get('target') != 'windows-x64' and os.name != 'nt' and (path.stat().st_mode & 0o111) != (member.mode & 0o111):
                raise ValueError('Provisioned Python executable permissions differ: ' + relative)
            files.append({'path': relative, 'sha256': expected})
    return files


def extract(archive, output, pin):
    """Create only verified regular files, then internal file symlinks."""
    no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh Python output directory; existing files are preserved.')
    entries = archive_plan(archive, pin)
    # A Linux archive cannot be correctly extracted onto a case-folding host.
    if pin['target'] != host_target():
        raise ValueError('Prepare the pinned interpreter on its native target.')
    output.mkdir(parents=True)
    with tarfile.open(archive) as package:
        for name, member in entries.items():
            target = output / name
            no_links(target)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source, target.open('xb') as destination:
                    while data := source.read(1024 * 1024):
                        destination.write(data)
                target.chmod(member.mode & 0o777)
        for name, member in entries.items():
            if member.issym():
                target = output / name
                no_links(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname)
    return verify_installed(archive, output / 'python', pin, include_build_files=True)
