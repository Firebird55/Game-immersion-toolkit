"""Acquire the exact build-host SDK; it is never installed into the product."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('toolkit_sdk_verifier', Path(__file__).with_name('verify-dotnet-sdk.py'))
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha512').hexdigest()


def acquire(cache, pin):
    verifier.no_links(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / pin['artifact']
    verifier.no_links(archive)
    if archive.exists():
        if checksum(archive) != pin['sha512']:
            raise ValueError('Cached SDK differs from its official SHA-512')
        return archive
    for attempt in range(3):
        partial = cache / (pin['artifact'] + '.' + uuid.uuid4().hex + '.partial')
        try:
            with urllib.request.urlopen(pin['source'], timeout=120) as response, partial.open('xb') as out:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024**2:
                        raise ValueError('SDK archive exceeds its acquisition bound')
                    out.write(chunk)
            if checksum(partial) != pin['sha512']:
                raise ValueError('Downloaded SDK differs from its official SHA-512')
            os.replace(partial, archive)
            return archive
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
        finally:
            partial.unlink(missing_ok=True)


def expand(archive, output):
    """Extract regular bounded members only; verification precedes execution."""
    verifier.no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh SDK directory; existing build inputs are preserved')
    output.mkdir(parents=True)
    seen, total = set(), 0

    def entry(name, length, directory, mode, opener):
        nonlocal total
        if name.startswith('./'):
            name = name[2:]
        name = name.rstrip('/')
        if not name and directory:
            return
        relative = PurePosixPath(name)
        if (not name or relative.is_absolute() or '\\' in name or ':' in name
                or any(part in {'', '.', '..'} for part in name.split('/')) or name.casefold() in seen):
            raise ValueError('Unsafe or duplicate SDK member')
        seen.add(name.casefold())
        total += length
        if length < 0 or length > 512 * 1024**2 or total > 8 * 1024**3 or len(seen) > 100_000:
            raise ValueError('SDK extraction exceeds its bounds')
        destination = output / relative
        verifier.no_links(destination)
        if directory:
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with opener() as source, destination.open('xb') as target:
                shutil.copyfileobj(source, target)
            if destination.stat().st_size != length:
                raise ValueError('Truncated SDK archive member')
            destination.chmod(0o755 if mode & 0o111 else 0o644)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                if item.orig_filename != item.filename:
                    raise ValueError('Unsafe normalized SDK member')
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError('SDK archive links are not accepted')
                entry(item.filename, item.file_size, item.is_dir(), mode, lambda i=item: bundle.open(i))
    else:
        with tarfile.open(archive, 'r:gz') as bundle:
            for item in bundle:
                if not item.isdir() and not item.isfile():
                    raise ValueError('SDK archive links and special members are not accepted')
                entry(item.name, item.size, item.isdir(), item.mode, lambda i=item: bundle.extractfile(i))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid', choices=['win-x64', 'linux-x64', 'osx-arm64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    pin = json.loads((ROOT / 'packaging/game-readers/inputs.json').read_text())['targets'][args.rid]['sdk']
    output, cache = args.output.absolute(), args.cache.absolute()
    archive = acquire(cache, pin)
    expand(archive, output)
    verified = verifier.verify(archive, output, pin)
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as stream:
            for name, value in {'sdk_root': output, 'dotnet': output / verified['dotnet'], 'evidence_root': cache}.items():
                stream.write(f'{name}={value}\n')
    print(json.dumps({'sdk': pin['version'], 'rid': args.rid, 'verified_files': len(verified['files'])}))


if __name__ == '__main__':
    main()
