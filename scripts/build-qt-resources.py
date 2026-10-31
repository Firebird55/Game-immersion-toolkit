"""Retain pinned Qt/PySide sources and their complete license/attribution files.

This build-host step produces an input for --resources-root. It never downloads
at application startup, changes source archives or approves a desktop release.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import shutil
import ssl
import sys
import tarfile
import urllib.request

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_payload import digest, no_links

PINS = ROOT / 'packaging/desktop/qt-sources.json'
PREFIX = 'third-party/qt'
ARCHIVE_LIMIT = 100 * 1024 * 1024
NOTICE_LIMIT = 4 * 1024 * 1024


def acquire(pin, cache):
    path = cache / pin['archive']
    no_links(path)
    if not path.exists():
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1'})
        with urllib.request.urlopen(request, timeout=90,
                context=ssl.create_default_context(cafile=certifi.where())) as response, path.open('xb') as stream:
            count = 0
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > ARCHIVE_LIMIT:
                    raise ValueError('Qt source archive exceeds its size limit.')
                stream.write(chunk)
    if path.stat().st_size > ARCHIVE_LIMIT or digest(path) != pin['sha256']:
        raise ValueError('Qt source archive checksum differs: ' + pin['archive'])
    return path


def notices(archive, prefix):
    """Read only regular, bounded text members; never extract archive paths."""
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
                or relative.name.casefold().startswith(('license', 'copying', 'notice')))
            if not selected or member.isdir():
                continue
            key = relative.as_posix()
            if not member.isfile() or member.size > NOTICE_LIMIT or key.casefold() in result:
                raise ValueError('Unsafe or duplicate Qt notice.')
            data = source.extractfile(member).read()
            result[key.casefold()] = (key, data)
    if 'licenses/lgpl-3.0-only.txt' not in result:
        raise ValueError('Qt source is missing its full LGPL license.')
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
        prepared.append((pin, archive, notices(archive, pin['archive'].removesuffix('.tar.xz'))))
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
