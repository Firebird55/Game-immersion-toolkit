"""One portable ZIP; inner packs retain bounded, random-access verification."""
import json
import os
import re
import zipfile
from pathlib import Path

from .mobile_export_layout import file_title

BUNDLE_FORMAT = 'proxy-mobile-bundle-v1'


def bundle_name(game, locales):
    names = {'zh-Hans': 'Mandarin', 'zh-Hant': 'Mandarin', 'zh': 'Mandarin',
             'en': 'English', 'ja': 'Japanese', 'ko': 'Korean', 'nl': 'Dutch',
             'fr': 'French', 'de': 'German', 'es': 'Spanish', 'ru': 'Russian'}
    label = ' + '.join(dict.fromkeys(names.get(code, code) for code in sorted(locales))) or 'Text Only'
    label = re.sub(r'[^\w +()-]', '-', label)
    return f'{file_title(game)} - {label} - Mobile Library.zip'


def write_bundle(catalog, destination, *, guard=lambda: None, progress=lambda value: None):
    """Repackage completed exports without decoding or buffering their audio."""
    catalog, destination = Path(catalog), Path(destination)
    with zipfile.ZipFile(catalog) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        locales = set()
        for segment in manifest['catalog']:
            for line in archive.read(segment['name']).splitlines():
                row = json.loads(line)
                if row.get('audio'):
                    locales.add(row.get('audioLocale', 'zh-Hans'))
    parts = [('library/catalog.zip', catalog)]
    for pack in manifest['packs']:
        path = catalog.parent / pack['name']
        if path.resolve().parent != catalog.parent.resolve() or not re.fullmatch('[a-f0-9]{64}', pack['id']):
            raise ValueError('Unsafe voice pack reference')
        parts.append((f"library/voices/{pack['id']}.zip", path))
    metadata = {'format': BUNDLE_FORMAT, 'kind': 'bundle', 'game': manifest['game'],
                'revision': manifest['revision'], 'audioLocales': sorted(locales),
                'catalog': parts[0][0], 'voices': [name for name, _ in parts[1:]]}
    target = destination / bundle_name(manifest['game'], locales)
    destination.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.zip.pending')
    total, copied, reported = sum(path.stat().st_size for _, path in parts), 0, 0
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
            info = zipfile.ZipInfo('manifest.json', (2026, 1, 1, 0, 0, 0))
            bundle.writestr(info, json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode())
            for name, path in parts:
                guard()
                # Validate prior pack bytes before wrapping them. No re-encoding.
                with zipfile.ZipFile(path) as part:
                    if part.testzip() is not None:
                        raise ValueError('Corrupt library pack; export again to repair it')
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.file_size = path.stat().st_size
                with bundle.open(info, 'w', force_zip64=True) as dest, path.open('rb') as source:
                    while data := source.read(1024 * 1024):
                        guard()
                        dest.write(data)
                        copied += len(data)
                        if copied - reported >= 16 * 1024**2 or copied == total:
                            reported = copied
                            progress({'state': 'exporting', 'progress': 97 + int(2 * copied / max(1, total)),
                                      'message': 'Finishing your single mobile library file'})
        guard()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
