"""Verify an untouched expanded SDK against its exact official ZIP/tar archive.

Build-host only. This does not extract or execute downloaded content.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise ValueError('SDK paths cannot contain links or reparse points')


def verify(archive, root, specification):
    archive, root = Path(archive).absolute(), Path(root).absolute()
    no_links(archive); no_links(root)
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha512').hexdigest() != specification['sha512']:
            raise ValueError('SDK archive differs from its official SHA-512')
    actual_files, actual_directories = set(), set()
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            item = Path(current) / name
            no_links(item)
            relative = item.relative_to(root).as_posix()
            (actual_directories if item.is_dir() else actual_files).add(relative)
    identities, expected_directories, seen = {}, set(), set()
    size = 0

    def member(name, length, directory, opener):
        nonlocal size
        if name.startswith('./'):
            name = name[2:]
        name = name.rstrip('/')
        if not name and directory:
            return
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or '\\' in name or ':' in name
                or any(p in {'', '.', '..'} for p in name.split('/')) or name.casefold() in seen):
            raise ValueError('Unsafe or duplicate SDK archive member')
        seen.add(name.casefold())
        expected_directories.update(p.as_posix() for p in path.parents if p != PurePosixPath('.'))
        if directory:
            expected_directories.add(name)
            return
        size += length
        if length < 0 or length > 512 * 1024 * 1024 or size > 8 * 1024**3 or len(identities) > 100_000:
            raise ValueError('SDK archive exceeds its bounds')
        installed = root / name
        if name not in actual_files or not installed.is_file() or installed.stat().st_size != length:
            raise ValueError('Expanded SDK is missing a supplier file')
        with opener() as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        with installed.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('Expanded SDK bytes differ from the official archive')
        identities[name] = digest

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if entry.orig_filename != entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('SDK archive aliases and links are not accepted')
                member(entry.filename, entry.file_size, entry.is_dir(), lambda e=entry: bundle.open(e))
    else:
        with tarfile.open(archive, 'r:gz') as bundle:
            for entry in bundle:
                if not entry.isdir() and not entry.isfile():
                    raise ValueError('SDK archive links and special members are not accepted')
                member(entry.name, entry.size, entry.isdir(), lambda e=entry: bundle.extractfile(e))
    if set(identities) != actual_files or expected_directories != actual_directories:
        raise ValueError('Expanded SDK contains unlisted files or directories')
    executable = 'dotnet.exe' if specification['artifact'].endswith('.zip') else 'dotnet'
    if executable not in identities or (os.name != 'nt' and not os.access(root / executable, os.X_OK)):
        raise ValueError('Expanded SDK executable is unavailable')
    return {'files': identities, 'dotnet': executable}


def main():
    parser = argparse.ArgumentParser()
    for name in ('archive', 'sdk-root', 'pins', 'rid', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    specification = json.loads(Path(args.pins).read_text())['targets'][args.rid]['sdk']
    result = verify(args.archive, args.sdk_root, specification)
    Path(args.output).write_text(json.dumps(result, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
