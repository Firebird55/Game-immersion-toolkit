"""Retain pinned Qt/PySide sources and their complete license/attribution files.

This build-host step produces an input for --resources-root. It never downloads
at application startup, changes source archives or approves a desktop release.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import shutil
import ssl
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_payload import digest, no_links

PINS = ROOT / 'packaging/desktop/qt-sources.json'
PREFIX = 'third-party/qt'
ARCHIVE_LIMIT = 100 * 1024 * 1024
NOTICE_LIMIT = 4 * 1024 * 1024
DOWNLOAD_ATTEMPTS = 3


def transient_download_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (408, 429, 500, 502, 503, 504)
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError,
                              http.client.IncompleteRead))


def acquire(pin, cache):
    path = cache / pin['archive']
    no_links(path)
    if not path.exists():
        pending = path.with_name(path.name + '.part')
        no_links(pending)
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1'})
        for attempt in range(DOWNLOAD_ATTEMPTS):
            created = False
            try:
                with urllib.request.urlopen(request, timeout=90,
                        context=ssl.create_default_context(cafile=certifi.where())) as response:
                    if urllib.parse.urlsplit(response.url).scheme != 'https':
                        raise ValueError('Qt source redirect requires HTTPS.')
                    with pending.open('xb') as stream:
                        created = True
                        count = 0
                        while chunk := response.read(1024 * 1024):
                            count += len(chunk)
                            if count > ARCHIVE_LIMIT:
                                raise ValueError('Qt source archive exceeds its size limit.')
                            stream.write(chunk)
                if digest(pending) != pin['sha256']:
                    raise ValueError('Qt source archive checksum differs: ' + pin['archive'])
                pending.replace(path)
                break
            except BaseException as error:
                if created and pending.exists() and not pending.is_symlink():
                    pending.unlink()
                if attempt + 1 == DOWNLOAD_ATTEMPTS or not transient_download_error(error):
                    raise
                print(f'Qt source download interrupted; retry {attempt + 2}/{DOWNLOAD_ATTEMPTS}: '
                      + pin['archive'], flush=True)
                time.sleep(2 ** (attempt + 1))
    if path.stat().st_size > ARCHIVE_LIMIT or digest(path) != pin['sha256']:
        raise ValueError('Qt source archive checksum differs: ' + pin['archive'])
    return path


def notices(archive, prefix, required_notices=None):
    """Read only regular, bounded text members; never extract archive paths."""
    required_notices = required_notices or ['LICENSES/LGPL-3.0-only.txt']
    result = {}
    with tarfile.open(archive) as source:
        for member in source:
            path = PurePosixPath(member.name)
            if not path.parts or path.parts[0] != prefix:
                raise ValueError('Qt source archive has an unexpected root.')
            relative = PurePosixPath(*path.parts[1:])
            if path.is_absolute() or '..' in path.parts or '\\' in member.name:
                raise ValueError('Unsafe Qt source path.')
            selected = (relative.parts and relative.parts[0] == 'LICENSES'
                or relative.name == 'qt_attribution.json'
                or relative.name.casefold().startswith(('license', 'copying', 'notice'))
                or relative.as_posix() in required_notices)
            if not selected or member.isdir():
                continue
            key = relative.as_posix()
            if not member.isfile() or member.size > NOTICE_LIMIT or key.casefold() in result:
                raise ValueError('Unsafe or duplicate Qt notice.')
            data = source.extractfile(member).read()
            result[key.casefold()] = (key, data)
    if any(name.casefold() not in result for name in required_notices):
        raise ValueError('Qt source is missing a required full license or attribution.')
    return [result[key] for key in sorted(result)]


def build(output, cache, pins):
    no_links(output)
    no_links(cache)
    if output.exists():
        raise ValueError('Choose a fresh Qt resource output directory.')
    cache.mkdir(parents=True, exist_ok=True)
    # Validate every input before creating the resource output. A partial
    # download cannot masquerade as a complete resource-manifest input.
    prepared = []
    for pin in pins['components']:
        archive = acquire(pin, cache)
        prepared.append((pin, archive, notices(archive, pin['archive'].removesuffix('.tar.xz'),
            pin.get('required_notices'))))
    root = output / PREFIX
    for pin, archive, records in prepared:
        folder = root / pin['name']
        folder.mkdir(parents=True)
        shutil.copyfile(archive, folder / pin['archive'])
        index = {}
        for name, data in records:
            # Source examples can live under directories named data or work.
            # Keep notices in a flat public collection with an explicit origin
            # index instead of recreating runtime-looking data directories.
            filename = hashlib.sha256(name.encode()).hexdigest()[:16] + '-' + PurePosixPath(name).name
            target = folder / 'notices' / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            index[filename] = {'source_path': name, 'sha256': hashlib.sha256(data).hexdigest()}
        (folder / 'notices/index.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    (root / 'README.txt').write_text(
        'Game Immersion Toolkit uses the open-source Qt/PySide libraries.\n'
        'The Qt/PySide source archives here are unmodified supplier inputs.\n'
        'Each archive retains its source copyright statements, third-party\n'
        'attributions, build instructions and applicable license alternatives.\n'
        'The notices directories also expose full license and attribution files.\n'
        'Qt/PySide libraries are dynamically loaded and may be replaced with\n'
        'compatible modified versions under their applicable license terms.\n'
        'The toolkit license does not restrict reverse engineering needed to\n'
        'debug modifications to LGPL-covered libraries.\n'
        'This source collection does not certify other bundled dependencies.\n', encoding='utf-8')
    manifest = {'schema': 'toolkit-native-resources-v1', 'version': pins['version'],
        'components': pins['components'], 'rights_review': 'pending-exact-output',
        'files': [{'path': path.relative_to(output).as_posix(), 'sha256': digest(path), 'bytes': path.stat().st_size}
                  for path in sorted(output.rglob('*')) if path.is_file()]}
    (output / 'resource-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    args = parser.parse_args()
    pins = json.loads(PINS.read_text(encoding='utf-8'))
    for package in ('PySide6-Essentials', 'shiboken6'):
        if metadata.version(package) != pins['version']:
            raise ValueError('Qt source pin differs from the installed wheel: ' + package)
    result = build(args.output.absolute(), args.cache.absolute(), pins)
    print(json.dumps({'version': result['version'], 'files': len(result['files']),
        'bytes': sum(item['bytes'] for item in result['files']), 'rights_review': result['rights_review']}))


if __name__ == '__main__':
    main()
