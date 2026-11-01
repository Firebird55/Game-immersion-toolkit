"""Bounded Ubuntu archive evidence shared by the build collector and reviewer.

Only the source-pinned Ubuntu archive key authenticates metadata. Installed dpkg
records, supplied receipts and successful downloads are never trust roots.
Nothing here extracts or executes a supplier archive.
"""
from __future__ import annotations

from contextlib import contextmanager
import gzip
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
POLICY = 'packaging/desktop/linux-system-inputs.json'
PREFIX = 'sources/linux-system'
OWNED = (POLICY, 'packaging/runtime-bundle/linux_system.py',
         'packaging/runtime-bundle/linux_system_review.py', 'scripts/build-linux-system-resources.py', 'LICENSE')
MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_INDEX = 1024 * 1024 * 1024
MAX_NOTICE = 8 * 1024 * 1024
IDENTITY = re.compile(r'[a-z0-9][a-z0-9+.-]*\Z')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or '\0' in name or path.is_absolute()
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise ValueError('Unsafe Ubuntu evidence member path.')
    return path.as_posix()


def checked(path, expected, size):
    if (path.is_symlink() or not path.is_file() or not isinstance(size, int)
            or not 0 < size <= MAX_ARCHIVE or path.stat().st_size != size
            or not re.fullmatch('[a-f0-9]{64}', expected) or digest(path) != expected):
        raise ValueError('Ubuntu archive bytes differ from authenticated metadata.')
    return path


def paragraphs(lines):
    """Parse Debian control paragraphs without ambiguous duplicate fields."""
    record, key, size, total = {}, None, 0, 0
    for line in lines:
        total += len(line)
        size += len(line)
        if total > MAX_INDEX or size > 2 * 1024 * 1024 or len(line) > 1024 * 1024:
            raise ValueError('Ubuntu control metadata exceeds bounded limits.')
        line = line.rstrip('\r\n')
        if not line:
            if record:
                yield record
            record, key, size = {}, None, 0
        elif line[:1].isspace():
            if key is None:
                raise ValueError('Unexpected Ubuntu control continuation.')
            record[key] += '\n' + line[1:]
        else:
            if ':' not in line:
                raise ValueError('Invalid Ubuntu control field.')
            key, value = line.split(':', 1)
            if key in record or not re.fullmatch('[A-Za-z0-9-]+', key):
                raise ValueError('Duplicate or invalid Ubuntu control field.')
            record[key] = value.lstrip(' ')
    if record:
        yield record


def one_paragraph(data):
    records = list(paragraphs(data.decode('utf-8').splitlines(keepends=True)))
    if len(records) != 1:
        raise ValueError('Expected one Ubuntu control record.')
    return records[0]


def checksums(value):
    values = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3 or not re.fullmatch('[a-f0-9]{64}', parts[0]):
            raise ValueError('Invalid Ubuntu SHA256 entry.')
        name = relative(parts[2])
        size = int(parts[1])
        if name in values or not 0 <= size <= 16 * MAX_ARCHIVE:
            raise ValueError('Duplicate or oversized Ubuntu SHA256 entry.')
        values[name] = {'sha256': parts[0], 'bytes': size}
    if not values:
        raise ValueError('Ubuntu metadata has no authenticated SHA256 entries.')
    return values


def valid_signature(status, allowed):
    values = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    return bool(values) and all(len(value) >= 12 and value[-1] in allowed for value in values)


def verify_release(path, keyring, policy, suite, *, gpgv='gpgv'):
    checked(keyring, policy['keyring']['sha256'], policy['keyring']['bytes'])
    if path.is_symlink() or not 0 < path.stat().st_size < 4 * 1024 * 1024:
        raise ValueError('Invalid Ubuntu signed release size.')
    # Isolated home and explicit sole keyring prevent the build user's GnuPG
    # configuration or additional trusted keys from authorizing supplier bytes.
    with tempfile.TemporaryDirectory(prefix='toolkit-ubuntu-signature-') as directory:
        work = Path(directory)
        (work / 'archive-keyring.gpg').write_bytes(keyring.read_bytes())
        (work / 'InRelease').write_bytes(path.read_bytes())
        process = subprocess.run([gpgv, '--homedir', '.', '--keyring', './archive-keyring.gpg',
            '--status-fd', '1', '--output', './Release', './InRelease'], cwd=work,
            capture_output=True, timeout=30)
        if process.returncode or not valid_signature(process.stdout.decode('ascii', errors='replace'), policy['signing_keys']):
            raise ValueError('Ubuntu archive signature is not from an allowed archive signing key.')
        record = one_paragraph((work / 'Release').read_bytes())
    if (record.get('Origin') != 'Ubuntu' or record.get('Label') != 'Ubuntu'
            or record.get('Suite') != suite or record.get('Codename') != policy['codename']
            or policy['architecture'] not in record.get('Architectures', '').split()):
        raise ValueError('Signed Ubuntu release identity differs from the selected policy.')
    return record


@contextmanager
def index_lines(path):
    opener = lzma.open if path.suffix == '.xz' else gzip.open if path.suffix == '.gz' else None
    if opener is None:
        raise ValueError('Unsupported Ubuntu index compression.')
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        yield stream


def source_identity(record):
    source = record.get('Source', record['Package'])
    match = re.fullmatch(r'([a-z0-9][a-z0-9+.-]*)(?: \(([^()\s]+)\))?', source)
    if not match:
        raise ValueError('Invalid Ubuntu source package identity.')
    return match[1], match[2] or record['Version']


def metadata(root, policy, selected, *, gpgv='gpgv'):
    """Reverify retained signed indexes and return only selected package rows."""
    binaries, sources = {}, {}
    for suite in policy['suites']:
        release = verify_release(root / 'metadata' / suite / 'InRelease', root / 'archive-keyring.gpg', policy, suite, gpgv=gpgv)
        entries = checksums(release['SHA256'])
        for component in policy['components']:
            for kind in ('binary-' + policy['architecture'] + '/Packages', 'source/Sources'):
                prefix = component + '/' + kind
                name = next((prefix + extension for extension in ('.xz', '.gz') if prefix + extension in entries), None)
                if name is None:
                    raise ValueError('Signed Ubuntu release lacks the required package index.')
                value = entries[name]
                path = checked(root / 'metadata' / suite / name, value['sha256'], value['bytes'])
                with index_lines(path) as lines:
                    for record in paragraphs(lines):
                        package = record.get('Package')
                        if kind.startswith('binary-'):
                            if package not in selected or record.get('Architecture') not in {policy['architecture'], 'all'}:
                                continue
                            if not IDENTITY.fullmatch(package):
                                raise ValueError('Invalid selected Ubuntu package name.')
                            key = (package, record['Version'])
                            previous = binaries.get(key)
                            if previous and any(previous.get(k) != record.get(k) for k in ('SHA256', 'Size', 'Filename', 'Source')):
                                raise ValueError('Conflicting authenticated Ubuntu package versions.')
                            binaries[key] = record
                        elif package in policy['source_packages']:
                            key = (package, record['Version'])
                            previous = sources.get(key)
                            if previous and previous.get('Checksums-Sha256') != record.get('Checksums-Sha256'):
                                raise ValueError('Conflicting authenticated Ubuntu source versions.')
                            sources[key] = record
    return binaries, sources


def ar_members(path):
    """Read the small Debian ar envelope, never unpacking paths on disk."""
    result = {}
    with path.open('rb') as stream:
        if stream.read(8) != b'!<arch>\n':
            raise ValueError('Invalid Debian binary archive.')
        while header := stream.read(60):
            if len(header) != 60 or header[58:] != b'`\n' or len(result) >= 10:
                raise ValueError('Malformed Debian ar member.')
            name = header[:16].decode('ascii').strip().removesuffix('/')
            size = int(header[48:58].strip())
            if '/' in name or name in result or not 0 < size <= MAX_ARCHIVE:
                raise ValueError('Unsafe or oversized Debian ar member.')
            data = stream.read(size)
            if len(data) != size or (size % 2 and stream.read(1) != b'\n'):
                raise ValueError('Truncated Debian ar member.')
            result[name] = data
    if result.get('debian-binary') != b'2.0\n':
        raise ValueError('Unsupported Debian binary archive version.')
    return result


@contextmanager
def tar_stream(data, name):
    raw = io.BytesIO(data)
    if name.endswith('.zst'):
        import zstandard
        if zstandard.get_frame_parameters(data).window_size > MAX_MEMBER:
            raise ValueError('Debian Zstandard frame exceeds the bounded decoding window.')
        with zstandard.ZstdDecompressor(max_window_size=MAX_MEMBER).stream_reader(raw) as stream:
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                yield archive
    else:
        with tarfile.open(fileobj=raw, mode='r|*') as archive:
            yield archive


def deb_evidence(path):
    members = ar_members(path)
    control = [key for key in members if key.startswith('control.tar')]
    payload = [key for key in members if key.startswith('data.tar')]
    if len(control) != 1 or len(payload) != 1:
        raise ValueError('Debian archive requires one control and data stream.')
    info, files, notices = None, {}, {}
    for part in (control[0], payload[0]):
        total, seen = 0, set()
        with tar_stream(members[part], part) as archive:
            for count, member in enumerate(archive):
                if member.isdir() and member.name in {'.', './'}:
                    continue
                name = member.name.removeprefix('./').rstrip('/')
                if not name:
                    continue
                name = relative(name)
                if name in seen or count > 200_000 or member.size > MAX_MEMBER:
                    raise ValueError('Duplicate or oversized Debian payload member.')
                seen.add(name)
                total += member.size
                if total > 4 * MAX_ARCHIVE:
                    raise ValueError('Debian expanded payload exceeds review bounds.')
                if not member.isfile():
                    # Symlinks/hardlinks are inert: never grant their names an
                    # origin or follow them out of the signed archive.
                    continue
                stream = archive.extractfile(member)
                if part == control[0] and name == 'control':
                    if member.size > 1024 * 1024:
                        raise ValueError('Oversized Debian control file.')
                    info = one_paragraph(stream.read())
                elif part == payload[0]:
                    if name.startswith('usr/share/common-licenses/') or name.endswith('/copyright'):
                        if member.size > MAX_NOTICE:
                            raise ValueError('Oversized Debian license notice.')
                        notices[name] = stream.read()
                        files[name] = sha(notices[name])
                    else:
                        files[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    if info is None:
        raise ValueError('Missing Debian package control identity.')
    return info, files, notices


def copyright_notices(archives):
    """Return exact Debian copyright, preferentially from the packaging tar."""
    for path in sorted(archives, key=lambda p: ('.debian.tar.' not in p.name, p.name)):
        if '.tar.' not in path.name:
            continue
        found = {}
        with tarfile.open(path, mode='r|*') as archive:
            for count, member in enumerate(archive):
                if count > 1_000_000:
                    raise ValueError('Ubuntu source archive has too many members.')
                name = member.name.removeprefix('./')
                parts = PurePosixPath(name).parts
                if len(parts) not in {2, 3} or parts[-2:] != ('debian', 'copyright'):
                    continue
                relative(name)
                if not member.isfile() or not 0 < member.size <= MAX_NOTICE:
                    raise ValueError('Invalid Ubuntu source copyright file.')
                if name in found:
                    raise ValueError('Duplicated Ubuntu source copyright member.')
                found[name] = archive.extractfile(member).read()
        if found:
            return {path.name + '/' + key: value for key, value in found.items()}
    raise ValueError('Ubuntu source package lacks its full Debian copyright file.')


def policy_digest(policy):
    return sha(json.dumps(policy, sort_keys=True, separators=(',', ':')).encode())


def verify_closure(root, policy, *, gpgv='gpgv', retain_notices=False):
    from backend.runtime_payload import no_links
    no_links(root)
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Ubuntu supplier evidence cannot contain filesystem links.')
    if (root / 'collection.json').stat().st_size > MAX_NOTICE:
        raise ValueError('Ubuntu collection receipt exceeds its bounded size.')
    receipt = json.loads((root / 'collection.json').read_text(encoding='utf-8'))
    if receipt.get('schema') != 'toolkit-ubuntu-system-collection-v1' or receipt.get('policy_sha256') != policy_digest(policy):
        raise ValueError('Ubuntu collection policy does not match the reviewed source.')
    selected = receipt.get('packages', [])
    if not selected or len(selected) > 160 or len({item['package'] for item in selected}) != len(selected):
        raise ValueError('Ubuntu package selection is empty, duplicated or oversized.')
    binaries, sources = metadata(root, policy, {item['package'] for item in selected}, gpgv=gpgv)
    origins, all_notices, source_versions, exact_files = {}, {}, {}, set()
    for item in selected:
        key = (item['package'], item['version'])
        record = binaries.get(key)
        if record is None:
            raise ValueError('Selected Ubuntu package is absent from authenticated indexes.')
        source = source_identity(record)
        if source[0] not in policy['source_packages'] or source not in sources:
            raise ValueError('Ubuntu source version is outside the reviewed package policy.')
        name = 'binary/' + relative(record['Filename'])
        path = checked(root / name, record['SHA256'], int(record['Size']))
        exact_files.add(name)
        info, members, notices = deb_evidence(path)
        if any(info.get(k) != record.get(k) for k in ('Package', 'Version', 'Architecture')) or source_identity(info) != source:
            raise ValueError('Actual Debian package identity differs from authenticated metadata.')
        for member, value in members.items():
            origins.setdefault(value, []).append({'package': key[0], 'version': key[1], 'archive_sha256': record['SHA256'], 'member': member})
        for member, data in notices.items():
            all_notices['binary/' + key[0] + '/' + member] = data
        source_versions[source] = sources[source]
    for key, record in source_versions.items():
        files = checksums(record['Checksums-Sha256'])
        if not any(name.endswith('.dsc') for name in files) or not any('.tar.' in name for name in files):
            raise ValueError('Ubuntu source record is missing preferred source or package recipe.')
        archives = []
        for filename, item in files.items():
            if '/' in filename:
                raise ValueError('Ubuntu source archive filename is not a basename.')
            name = 'source/' + relative(record['Directory']) + '/' + filename
            archives.append(checked(root / name, item['sha256'], item['bytes']))
            exact_files.add(name)
        for member, data in copyright_notices(archives).items():
            all_notices['source/' + key[0] + '/' + member] = data
    # Full common GPL/LGPL/etc terms are supplied by authenticated base-files,
    # not copied from unverified host paths or reduced to SPDX labels.
    common = [key for key in all_notices if '/usr/share/common-licenses/' in key]
    if not any(key.endswith('/GPL-3') for key in common) or not any(key.endswith('/LGPL-2.1') for key in common):
        raise ValueError('Ubuntu collection is missing the full common license texts.')
    expected_notices = {sha(name.encode()) + '.txt': data for name, data in all_notices.items()}
    expected_index = {sha(name.encode()) + '.txt': name for name in all_notices}
    if retain_notices:
        (root / 'notices').mkdir()
        for name, data in expected_notices.items():
            (root / 'notices' / name).write_bytes(data)
        (root / 'NOTICE-INDEX.json').write_text(json.dumps(expected_index, indent=2) + '\n', encoding='utf-8')
    actual_notices = {path.name: path.read_bytes() for path in (root / 'notices').glob('*.txt')}
    if actual_notices != expected_notices:
        raise ValueError('Retained Ubuntu license text differs from authenticated supplier bytes.')
    if json.loads((root / 'NOTICE-INDEX.json').read_bytes()) != expected_index:
        raise ValueError('Ubuntu copyright attribution differs from exact supplier members.')
    actual_archives = {p.relative_to(root).as_posix() for folder in ('source', 'binary') for p in (root / folder).rglob('*') if p.is_file()}
    if actual_archives != exact_files:
        raise ValueError('Ubuntu collection contains archives outside its exact selected closure.')
    return {'origins': origins, 'packages': len(selected), 'sources': len(source_versions),
            'notices': len(expected_notices), 'archives': len(exact_files)}
