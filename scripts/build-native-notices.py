"""Collect pinned native sources/notices without asserting release eligibility.

Run on a prepared build host and pass the result to build-desktop-runtime.py's
--resources-root. No source archive is extracted or executed. The application
never downloads these materials at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import stat
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_payload import digest, no_links

PINS = ROOT / 'packaging/desktop/native-notices.json'
PREFIX = 'third-party/native'
ARCHIVE_LIMIT = 256 * 1024 * 1024
NOTICE_LIMIT = 4 * 1024 * 1024
TOTAL_NOTICE_LIMIT = 64 * 1024 * 1024
MEMBER_LIMIT = 150_000


def safe_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '\\' in value or ':' in value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('Unsafe supplier path.')
    return path


def validate_pins(pins):
    if pins.get('schema') != 'toolkit-native-notice-inputs-v1':
        raise ValueError('Unknown native notice input schema.')
    names, archives = set(), set()
    for pin in pins['components']:
        for key, seen in (('name', names), ('archive', archives)):
            value = pin[key]
            if len(safe_path(value).parts) != 1 or value.casefold() in seen:
                raise ValueError('Duplicate or unsafe supplier input.')
            seen.add(value.casefold())
        url = urllib.parse.urlsplit(pin['url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Supplier inputs require a public HTTPS URL.')
        if not re.fullmatch(r'[a-f0-9]{64}', pin['sha256']):
            raise ValueError('Supplier input requires an exact SHA-256.')
        if pin['format'] not in ('tar', 'zip', 'text'):
            raise ValueError('Unsupported supplier input format.')
        if pin['format'] != 'text':
            if len(safe_path(pin['root']).parts) != 1 or not pin['required_notices']:
                raise ValueError('Archive requires an exact root and notices.')
            for path in pin['required_notices']:
                safe_path(path)


def acquire(pin, cache):
    path = cache / pin['archive']
    no_links(path)
    if not path.exists():
        pending = path.with_name(path.name + '.part')
        no_links(pending)
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1'})
        created = False
        try:
            with urllib.request.urlopen(request, timeout=90,
                    context=ssl.create_default_context(cafile=certifi.where())) as response:
                if urllib.parse.urlsplit(response.url).scheme != 'https':
                    raise ValueError('Supplier redirect requires HTTPS.')
                with pending.open('xb') as stream:
                    created = True
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > ARCHIVE_LIMIT:
                            raise ValueError('Supplier input exceeds its size limit.')
                        stream.write(chunk)
            if digest(pending) != pin['sha256']:
                raise ValueError('Supplier input checksum differs: ' + pin['name'])
            pending.replace(path)
        except BaseException:
            # This single file was created by this acquisition; never remove a
            # preexisting partial file or follow a link during cleanup.
            if created and pending.exists() and not pending.is_symlink():
                pending.unlink()
            raise
    if path.stat().st_size > ARCHIVE_LIMIT or digest(path) != pin['sha256']:
        raise ValueError('Supplier input checksum differs: ' + pin['name'])
    return path


def selected_notice(path):
    return (any(part.casefold() in ('licenses', 'licences') for part in path.parts)
        or path.name.casefold().startswith(('license', 'licence', 'copying', 'notice', 'copyright'))
        or path.name.casefold() in ('thirdpartynotices.txt', 'third_party_notices.txt', 'qt_attribution.json'))


def notices(archive, pin):
    if pin['format'] == 'text':
        if archive.stat().st_size > NOTICE_LIMIT:
            raise ValueError('Supplier notice exceeds its size limit.')
        return [(pin['archive'], archive.read_bytes())]
    found, seen, total = {}, set(), 0

    def accept(name, size, regular, directory, read):
        nonlocal total
        # Directory entries may have one trailing slash; filenames may not.
        path = safe_path(name.rstrip('/') if directory else name)
        if path.parts[0] != pin['root']:
            raise ValueError('Supplier archive has an unexpected root.')
        if directory:
            return
        relative = PurePosixPath(*path.parts[1:])
        key = relative.as_posix()
        if key.casefold() in seen:
            raise ValueError('Supplier archive has duplicate paths.')
        seen.add(key.casefold())
        if not selected_notice(relative) and key not in pin['required_notices']:
            return
        if not regular or size > NOTICE_LIMIT or total + size > TOTAL_NOTICE_LIMIT:
            raise ValueError('Unsafe or oversized supplier notice.')
        data = read()
        if len(data) != size:
            raise ValueError('Supplier notice size differs.')
        total += len(data)
        found[key] = data

    if pin['format'] == 'zip':
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            if len(entries) > MEMBER_LIMIT:
                raise ValueError('Supplier archive has too many members.')
            for member in entries:
                mode = member.external_attr >> 16
                regular = not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode) or stat.S_ISREG(mode))
                accept(member.filename, member.file_size, regular, member.is_dir(),
                    lambda: source.read(member))
    else:
        with tarfile.open(archive) as source:
            for count, member in enumerate(source, 1):
                if count > MEMBER_LIMIT:
                    raise ValueError('Supplier archive has too many members.')
                accept(member.name, member.size, member.isfile(), member.isdir(),
                    lambda: source.extractfile(member).read())
    if any(name not in found for name in pin['required_notices']):
        raise ValueError('Supplier archive is missing a required full notice: ' + pin['name'])
    for supplement in pin.get('supplemental_notices', []):
        relative = safe_path(supplement['path'])
        if relative.parts[:2] != ('packaging', 'frontend-notices') or len(safe_path(supplement['name']).parts) != 1:
            raise ValueError('Supplemental notice is outside the pinned notice collection.')
        path = ROOT / relative
        no_links(path)
        if path.stat().st_size > NOTICE_LIMIT or digest(path) != supplement['sha256']:
            raise ValueError('Supplemental full terms differ from the exact pin.')
        if supplement['name'] in found:
            raise ValueError('Supplemental notice collides with a supplier file.')
        found[supplement['name']] = path.read_bytes()
    return sorted(found.items())


def verify_runtime(pins):
    observed = []
    for package, version in pins['distributions'].items():
        if metadata.version(package) != version:
            raise ValueError('Notice source differs from installed distribution: ' + package)
        observed.append({'name': package, 'version': version})
    import shapely
    if shapely.geos_version_string != pins['geos_version']:
        raise ValueError('GEOS source differs from the installed Shapely library.')
    installed = metadata.distribution('rapidocr-onnxruntime')
    for item in pins['ocr_models']['files']:
        path = Path(installed.locate_file(safe_path(item['installed_path'])))
        no_links(path)
        if not path.is_file() or digest(path) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('OCR model differs from the licensed pinned input: ' + item['name'])
    return observed


def build(output, cache, pins, *, runtime_verifier=verify_runtime):
    validate_pins(pins)
    no_links(output)
    no_links(cache)
    if output.exists():
        raise ValueError('Choose a fresh native-notice resource directory.')
    observed = runtime_verifier(pins)
    cache.mkdir(parents=True, exist_ok=True)
    prepared = []
    for pin in pins['components']:
        print('Checking native source/notices: ' + pin['name'], flush=True)
        archive = acquire(pin, cache)
        prepared.append((pin, archive, notices(archive, pin)))
    # All source/model checks precede output creation. Failed input validation
    # cannot leave a partial directory that looks like an accepted resource.
    root = output / PREFIX
    for pin, archive, records in prepared:
        folder = root / pin['name']
        folder.mkdir(parents=True)
        shutil.copyfile(archive, folder / pin['archive'])
        index = {}
        for name, data in records:
            filename = hashlib.sha256(name.encode()).hexdigest()[:16] + '-' + PurePosixPath(name).name
            destination = folder / 'notices' / filename
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(data)
            index[filename] = {'source_path': name, 'sha256': hashlib.sha256(data).hexdigest()}
        (folder / 'notices/index.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    (root / 'SOURCES.json').write_text(json.dumps(pins, indent=2) + '\n', encoding='utf-8')
    (root / 'README.txt').write_text(
        'These are unmodified, checksum-pinned supplier sources and full notices.\n'
        'Where a supplier declares a license without shipping its terms, SOURCES.json\n'
        'labels the separately attributed standard terms and exact declaration.\n'
        'For oneocr this retains MIT permission/warranty text without inventing\n'
        'a supplier copyright statement or claiming it shipped a LICENSE file.\n'
        'The source archives preserve copyright statements and build instructions.\n'
        'OCR weights remain in the verified RapidOCR wheel; SOURCES.json records\n'
        'their exact supplier bundle, upstream attribution and individual hashes.\n'
        'ASR uses a separate ONNX Runtime 1.28.2, whose notices are included here.\n'
        'Sherpa supplier wheels enable TTS. The collected eSpeak sources include\n'
        'GPLv3 terms; an Apache wrapper label does not replace those terms.\n'
        'Qt Mesa/LLVM and LGPL GEOS retain their independent licenses. Compatible\n'
        'modified LGPL libraries may be substituted; this toolkit does not restrict\n'
        'reverse engineering needed to debug those modifications.\n'
        'This collection records evidence, not blanket redistribution approval.\n'
        'Review the exact target binary inventory and the limitations in SOURCES.json.\n', encoding='utf-8')
    manifest = {'schema': 'toolkit-native-resources-v1', 'version': pins['version'],
        'components': pins['components'], 'observed_distributions': observed,
        'rights_review': 'pending-exact-output', 'limitations': pins['limitations'],
        'files': [{'path': path.relative_to(output).as_posix(), 'sha256': digest(path), 'bytes': path.stat().st_size}
                  for path in sorted(output.rglob('*')) if path.is_file()]}
    (output / 'resource-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    args = parser.parse_args()
    result = build(args.output.absolute(), args.cache.absolute(), json.loads(PINS.read_text(encoding='utf-8')))
    print(json.dumps({'files': len(result['files']), 'bytes': sum(item['bytes'] for item in result['files']),
        'rights_review': result['rights_review']}))


if __name__ == '__main__':
    main()
