"""Acquire and seal one build-host CMake ZIP. Never execute or install it.

Original project LICENSE applies. This is outside the three-file Xiph grant.
CLI preparation is Windows-only; portable functions support authored fixtures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'packaging/build-tools/cmake-4.4.5-windows-x64.json'
RECEIPT = 'PINNED-CMAKE.json'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 192 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('Duplicate metadata field.')
        result[key] = value
    return result


def policy():
    value = json.loads(POLICY.read_bytes(), object_pairs_hook=unique_object)
    if (value['schema'] != 'proxy-pinned-build-cmake-inputs-v1' or value['name'] != 'CMake'
            or value['version'] != '4.4.5' or value['platform'] != 'win-x64'
            or any(value[key] is not False for key in ('native_payload_in_source_review',
                'runtime_collection_allowed', 'production_execution_allowed', 'source_delivery_approved', 'r19_complete'))):
        raise ValueError('Unexpected build-host-only CMake policy.')
    for name, limit in (('archive', MAX_ARCHIVE), ('publisher_checksums', 8192)):
        record = value[name]
        if (canonical(record['filename']) != record['filename'] or '/' in record['filename']
                or type(record['bytes']) is not int or not 0 < record['bytes'] <= limit
                or not re.fullmatch(r'[a-f0-9]{64}', record['sha256'])):
            raise ValueError('Invalid pinned CMake input identity.')
    archive = value['archive']
    if (canonical(archive['root']) != archive['root'] or '/' in archive['root']
            or type(archive['entries']) is not int or not 0 < archive['entries'] <= 12000
            or type(archive['regular_files']) is not int or not 0 < archive['regular_files'] <= archive['entries']
            or type(archive['expanded_bytes']) is not int or not 0 < archive['expanded_bytes'] <= MAX_EXPANDED):
        raise ValueError('Invalid pinned CMake tree bounds.')
    for record in [value['executable'], *value['notices']]:
        if (canonical(record['path']) != record['path'] or not record['path'].startswith(archive['root'] + '/')
                or type(record['bytes']) is not int or not 0 < record['bytes'] <= MAX_EXPANDED
                or not re.fullmatch(r'[a-f0-9]{64}', record['sha256'])):
            raise ValueError('Invalid original executable/notice identity.')
    return value


def no_links(path):
    for item in (path, *path.parents):
        if (item.is_symlink() or getattr(item, 'is_junction', lambda: False)()
                or item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Links and reparse points are not build-tool inputs.')


def canonical(name):
    value = name[:-1] if name.endswith('/') else name
    if (not value or not value.isascii() or '\\' in value or ':' in value
            or value.startswith('/') or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Non-canonical CMake ZIP path.')
    for part in value.split('/'):
        if (part in {'', '.', '..'} or part.endswith((' ', '.'))
                or any(c in '<>"|?*' for c in part)
                or re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part)):
            raise ValueError('Aliased CMake ZIP path.')
    return value


def checked_file(path, record, limit):
    no_links(path)
    if not path.is_file() or path.stat().st_size != record['bytes'] or record['bytes'] > limit:
        raise ValueError('Pinned input size differs.')
    raw = path.read_bytes()
    if digest(raw) != record['sha256']: raise ValueError('Pinned input hash differs.')
    return raw


def checksum_matches(raw, pin):
    lines = raw.decode('ascii').splitlines()
    expected = pin['archive']['sha256'] + '  ' + pin['archive']['filename']
    if lines.count(expected) != 1: raise ValueError('Original publisher checksum does not bind this ZIP.')


def inspect_archive(archive, pin):
    """Validate every header and decompressed CRC/hash before any output write."""
    checked_file(archive, pin['archive'], MAX_ARCHIVE)
    records, directories, aliases, seen = {}, set(), {}, set()
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        if (len(infos) != pin['archive']['entries'] or len(infos) > 12000
                or sum(item.file_size for item in infos) != pin['archive']['expanded_bytes']
                or pin['archive']['expanded_bytes'] > MAX_EXPANDED):
            raise ValueError('Pinned ZIP inventory bounds differ.')
        for item in infos:
            name = canonical(item.filename)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if (name.split('/')[0] != pin['archive']['root'] or item.flag_bits & 1
                    or item.external_attr & 0x400 or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or kind == stat.S_IFDIR and not item.is_dir()
                    or kind == stat.S_IFREG and item.is_dir()
                    or item.file_size > 64*1024*1024 or item.file_size < 0):
                raise ValueError('Unsupported CMake ZIP entry.')
            parts = name.split('/')
            for index in range(1, len(parts)+1):
                parent = '/'.join(parts[:index]); alias = parent.casefold()
                if alias in aliases and aliases[alias] != parent:
                    raise ValueError('Case-aliased CMake ZIP entry.')
                aliases[alias] = parent
            if name in seen:
                raise ValueError('Duplicate CMake ZIP entry.')
            seen.add(name)
            directories.update('/'.join(parts[:index]) for index in range(1, len(parts)))
            if item.is_dir():
                if item.file_size: raise ValueError('Directory ZIP entry contains payload.')
                directories.add(name)
            else:
                h = hashlib.sha256(); count = 0
                with zipped.open(item) as stream:
                    while chunk := stream.read(64*1024):
                        count += len(chunk)
                        if count > item.file_size: raise ValueError('Expanded ZIP entry exceeds its bound.')
                        h.update(chunk)
                if count != item.file_size: raise ValueError('Truncated CMake ZIP entry.')
                records[name] = {'bytes': count, 'sha256': h.hexdigest()}
    if set(records) & directories or len(records) != pin['archive']['regular_files']:
        raise ValueError('File/directory ZIP alias or inventory mismatch.')
    for record in [pin['executable'], *pin['notices']]:
        if records.get(record['path']) != {key: record[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Original CMake executable or notice differs.')
    return records, directories


def tree(root):
    files, directories, pending = {}, set(), [root]
    while pending:
        parent = pending.pop(); no_links(parent)
        for path in parent.iterdir():
            no_links(path); name = path.relative_to(root).as_posix()
            if path.is_dir(): directories.add(name); pending.append(path)
            elif path.is_file(): files[name] = {'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}
            else: raise ValueError('Non-regular prepared build-tool entry.')
    return files, directories


def summary(pin, records, directories):
    material = {'files': records, 'directories': sorted(directories)}
    return {'schema': 'proxy-pinned-build-cmake-v1', 'name': 'CMake', 'version': pin['version'],
        'platform': pin['platform'], 'scope': 'build-host-only; static byte verification, not native execution',
        'policy_sha256': digest(POLICY.read_bytes()),
        'archive': {key: pin['archive'][key] for key in ('filename', 'root', 'bytes', 'sha256',
                    'entries', 'regular_files', 'expanded_bytes')},
        'executable': {key: pin['executable'][key] for key in ('path', 'bytes', 'sha256')},
        'notices': [{key: record[key] for key in ('path', 'bytes', 'sha256')} for record in pin['notices']],
        'tree_sha256': digest(json.dumps(material, sort_keys=True, separators=(',', ':')).encode()),
        'regular_files': len(records), 'directories': len(directories),
        'runtime_collection_allowed': False, 'production_execution_allowed': False,
        'source_delivery_approved': False, 'native_payload_in_source_review': False,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}


def payload_root(root):
    """Path construction only; callers must verify before native execution."""
    return Path(root) / policy()['archive']['root']


def acquire(input_root):
    pin = policy(); input_root = Path(input_root).absolute(); no_links(input_root)
    if input_root.exists(): raise ValueError('Build-tool acquisition needs a fresh input root.')
    found = {}
    for record, limit in ((pin['archive'], MAX_ARCHIVE), (pin['publisher_checksums'], 8192)):
        if not record['url'].startswith('https://github.com/Kitware/CMake/releases/download/v4.4.5/'):
            raise ValueError('Unexpected original CMake acquisition URL.')
        with urllib.request.urlopen(record['url'], timeout=90) as stream: raw = stream.read(limit+1)
        if len(raw) != record['bytes'] or len(raw) > limit or digest(raw) != record['sha256']:
            raise ValueError('Acquired original build-tool bytes differ.')
        found[record['filename']] = raw
    checksum_matches(found[pin['publisher_checksums']['filename']], pin)
    input_root.mkdir(parents=True)
    for name, raw in found.items(): (input_root / name).write_bytes(raw)
    return {'schema': 'proxy-pinned-build-cmake-acquired-v1', 'version': pin['version'],
            'archive_sha256': pin['archive']['sha256'], 'checksum_sha256': pin['publisher_checksums']['sha256'],
            'runtime_collection_allowed': False, 'production_execution_allowed': False,
            'source_delivery_approved': False, 'native_payload_in_source_review': False,
            'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}


def prepare(archive, output):
    pin = policy(); archive = Path(archive).absolute(); output = Path(output).absolute()
    no_links(output)
    if output.exists(): raise ValueError('Prepared build-tool output must be fresh.')
    records, directories = inspect_archive(archive, pin)
    value = summary(pin, records, directories)
    output.mkdir(parents=True)
    retained = output / 'inputs' / pin['archive']['filename']; retained.parent.mkdir()
    shutil.copyfile(archive, retained)
    with zipfile.ZipFile(archive) as zipped:
        for name in sorted(directories): (output / name).mkdir(parents=True, exist_ok=True)
        for name in records:
            with zipped.open(name) as source, (output / name).open('xb') as target:
                shutil.copyfileobj(source, target, 64*1024)
    (output / RECEIPT).write_bytes((json.dumps(value, indent=2) + '\n').encode('utf-8'))
    verify(output)
    return dict(value, operation='prepared')


def verify(root):
    pin = policy(); root = Path(root).absolute(); no_links(root)
    if not root.is_dir(): raise ValueError('Prepared CMake root is unavailable.')
    retained = root / 'inputs' / pin['archive']['filename']
    records, directories = inspect_archive(retained, pin)
    value = summary(pin, records, directories)
    receipt = root / RECEIPT; no_links(receipt)
    expected_receipt = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    if receipt.read_bytes() != expected_receipt:
        raise ValueError('Prepared build-tool receipt differs from its exact inputs.')
    actual_files, actual_dirs = tree(root)
    expected_files = dict(records)
    expected_files['inputs/' + pin['archive']['filename']] = {key: pin['archive'][key] for key in ('bytes', 'sha256')}
    expected_files[RECEIPT] = {'bytes': len(expected_receipt), 'sha256': digest(expected_receipt)}
    if actual_files != expected_files or actual_dirs != directories | {'inputs'}:
        raise ValueError('Prepared build-tool tree is not closed or its bytes changed.')
    return dict(value, operation='verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['acquire', 'prepare', 'verify'])
    parser.add_argument('--input-root', type=Path); parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path); parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'acquire': result = acquire(args.input_root)
        elif args.command == 'prepare':
            if sys.platform != 'win32': raise ValueError('Native tool preparation requires the Windows build host.')
            result = prepare(args.archive, args.output)
        else: result = verify(args.root)
    except Exception:
        print(json.dumps({'schema': 'proxy-pinned-build-cmake-failure-v1', 'status': 'failed',
            'command': args.command, 'reason': 'exact-build-tool-verification-failed',
            'runtime_collection_allowed': False, 'production_execution_allowed': False,
            'source_delivery_approved': False, 'native_payload_in_source_review': False,
            'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))
