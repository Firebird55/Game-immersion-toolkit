"""Original publisher APK bootstrap candidates; never a legacy key feed.

Authenticated modules are data. A recovered output remains a candidate until
the ordinary PAK reader checks both complete original encrypted indices.
"""
from dataclasses import dataclass, field
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import ssl
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit
import zlib

import certifi

from .export_lock import ExportLock
from .atomic_files import replace
from .preparation_errors import PreparationFailure
from .publisher_apk import ApkLayout, verify_stream
from .wuthering_elf_bootstrap import MAX_MODULE, default_output
from . import wuthering_metadata as metadata


POLICY = 'kuro-official-arm64-default/1'
CATALOGUE = ('https://download.kurogames.com/'
             'mc_WnGtDn85y8lJB4mTmYHYuNjIl9n6YGVm/official/cn/zh-Hans/android_app.json')
MAX_METADATA = 2 * 1024**2
_GATE = threading.RLock()


def _check(value):
    if not value:
        raise ValueError('Unsupported or inconsistent original Wuthering bootstrap source.')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path):
    _check(not path.is_symlink())
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024**2), b''):
            digest.update(part)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _url(value):
    _check(isinstance(value, str) and len(value) <= 4096)
    u = urlsplit(value)
    _check(u.scheme == 'https' and u.netloc == u.hostname and not u.fragment and not u.query and
           re.fullmatch(r'[a-z0-9-]+\.aki-game\.com', u.hostname or '') and
           u.path.startswith('/client/download/') and unquote(u.path).endswith('.apk') and
           '..' not in unquote(u.path).split('/'))
    return value


def reference(value):
    _check(isinstance(value, dict) and set(value) == {
        'policy', 'catalogue', 'catalogue_sha256', 'version', 'url', 'bytes', 'etag', 'apk_sha256', 'v2_digest', 'signers', 'module'})
    _check(value['policy'] == POLICY and value['catalogue'] == CATALOGUE and
           re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value['version']) and
           type(value['bytes']) is int and 0 < value['bytes'] <= 4 * 1024**3 and
           isinstance(value['etag'], str) and 0 < len(value['etag']) <= 256)
    _url(value['url'])
    for name in ('apk_sha256', 'v2_digest', 'catalogue_sha256'):
        _check(isinstance(value[name], str) and re.fullmatch('[0-9a-f]{64}', value[name]))
    _check(isinstance(value['signers'], list) and 1 <= len(value['signers']) <= 8 and
           all(isinstance(x, str) and re.fullmatch('[0-9a-f]{64}', x) for x in value['signers']))
    m = value['module']
    _check(isinstance(m, dict) and set(m) == {'name', 'sha256', 'compressed_sha256', 'compressed_bytes', 'plain_bytes', 'crc32'} and
           re.fullmatch(r'lib/arm64-v8a/lib[A-Za-z0-9_]+\.so', m['name']) and
           type(m['plain_bytes']) is int and 0 < m['plain_bytes'] <= MAX_MODULE and
           type(m['compressed_bytes']) is int and 0 < m['compressed_bytes'] < value['bytes'] and
           re.fullmatch('[0-9a-f]{8}', m['crc32']) and
           all(isinstance(m[k], str) and re.fullmatch('[0-9a-f]{64}', m[k]) for k in ('sha256', 'compressed_sha256')))
    return json.loads(_canonical(value))


def identity(value):
    return _hash(_canonical(reference(value)))


def _root(tools):
    return Path(tools) / 'wuwa-publisher' / 'native-bootstrap'


def _module(tools, source):
    return _root(tools) / 'modules' / source['module']['sha256'] / 'module.so'


def _registry_path(tools):
    return _root(tools) / 'verified-source-owners.dpapi'


def _validated_record(value):
    _check(isinstance(value, dict) and set(value) == {'schema', 'sources', 'owners', 'regions'} and
           type(value['schema']) is int and value['schema'] == 1)
    sources, owners, regions = (value[k] for k in ('sources', 'owners', 'regions'))
    _check(isinstance(sources, dict) and len(sources) <= 64 and isinstance(owners, dict) and len(owners) <= 256 and
           isinstance(regions, dict) and set(regions) <= {'global', 'cn'})
    _check(all(identity(v) == k for k, v in sources.items()))
    _check(all(isinstance(k, str) and re.fullmatch('[0-9a-f]{64}', k) and v in sources for k, v in owners.items()))
    _check(all(v in sources for v in regions.values()))
    return value


def _registry(tools):
    path = _registry_path(tools)
    raw = metadata._read(path)
    if raw is None:
        if path.exists():
            raise PreparationFailure('publisher_bootstrap_cache_invalid',
                'The protected original bootstrap-source record is invalid. Restore it or download the game data again; previous data is retained.')
        return {'schema': 1, 'sources': {}, 'owners': {}, 'regions': {}}
    try:
        return _validated_record(json.loads(raw))
    except (ValueError, TypeError, KeyError):
        raise PreparationFailure('publisher_bootstrap_cache_invalid',
            'The protected original bootstrap provenance is inconsistent; previous data is retained.') from None


def _save(tools, value):
    _validated_record(value)
    path = _registry_path(tools)
    pending = path.with_name(path.name + '.' + secrets.token_hex(8) + '.pending')
    raw = _canonical(value)
    try:
        # Verify the protected pending envelope before replacing any prior
        # source/owner record. A failed write/readback leaves that record intact.
        if not metadata._write(pending, raw) or metadata._read(pending) != raw:
            raise PreparationFailure('publisher_key_cache_failed',
                'The verified original bootstrap ownership could not be retained safely; previous data is retained.')
        replace(pending, path)
        if _registry(tools) != value:
            raise PreparationFailure('publisher_key_cache_failed',
                'The retained original bootstrap ownership did not read back correctly; previous library data is retained.')
    finally:
        _check(pending.resolve().parent == path.resolve().parent)
        pending.unlink(missing_ok=True)


def _owner(info, region):
    _check(region in ('global', 'cn') and isinstance(info, (tuple, list)) and len(info) == 3)
    u, size, digest = info
    # Launcher owners publish MD5; resource/video owners publish SHA-1. These
    # are immutable owner identities here, not guessed member/key hashes.
    _check(isinstance(u, str) and type(size) is int and size > 0 and isinstance(digest, str) and
           re.fullmatch(r'(?:[0-9a-f]{32}|[0-9a-f]{40})', digest))
    return _hash(_canonical([region, u, size, digest]))


@dataclass
class Candidate:
    source: dict
    parameter: bytes = field(repr=False)
    region: str = 'global'
    verified: bool = False
    owner_id: str | None = None

    def __repr__(self):
        return '<Original Wuthering bootstrap candidate>'


class Parameters(tuple):
    def __new__(cls, candidate):
        result = super().__new__(cls, (candidate.parameter,))
        result.bootstrap = candidate
        return result

    def __repr__(self):
        return '<Original Wuthering bootstrap inputs>'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('The original Wuthering bootstrap source redirected.')


def _open(url, *, method='GET', headers=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=context))
    return opener.open(urllib.request.Request(url, method=method, headers={'Accept-Encoding': 'identity', **(headers or {})}), timeout=90)


def _read(url, maximum):
    with _open(url) as response:
        _check(response.status == 200 and response.geturl() == url)
        raw = response.read(maximum + 1)
        expected = response.headers.get('Content-MD5')
        if expected is not None:
            _check(hashlib.md5(raw).digest() == base64.b64decode(expected, validate=True))
    _check(len(raw) <= maximum)
    return raw


class _Zip:
    def __init__(self, url, total, etag):
        self.url, self.total, self.etag = url, total, etag
        self.metadata_bytes = 0
        self.witnesses = []
        tail = self.range(max(0, total - 65557), min(65557, total))
        at = tail.rfind(b'PK\x05\x06')
        _check(at >= 0 and at + 22 <= len(tail))
        self.eocd = tail[at:]
        disk, cd_disk, on_disk, entries, size, offset, comment = struct.unpack_from('<4H2IH', self.eocd, 4)
        _check(disk == cd_disk == 0 and 0 < entries == on_disk < 65535 and comment == len(self.eocd) - 22 and
               0 < size <= 1024**2 and offset + size + len(self.eocd) == total)
        tail_start = total - len(tail)
        missing = max(0, min(offset + size, tail_start) - offset)
        self.cd = self.range(offset, missing) if missing else b''
        self.cd += tail[max(offset, tail_start) - tail_start:offset + size - tail_start]
        _check(len(self.cd) == size)
        self.entries = {}
        pos = 0
        for _ in range(entries):
            _check(self.cd[pos:pos + 4] == b'PK\x01\x02' and pos + 46 <= len(self.cd))
            flags, method = struct.unpack_from('<HH', self.cd, pos + 8)
            crc, packed, plain = struct.unpack_from('<III', self.cd, pos + 16)
            nl, xl, cl = struct.unpack_from('<HHH', self.cd, pos + 28)
            local, = struct.unpack_from('<I', self.cd, pos + 42)
            _check(pos + 46 + nl + xl + cl <= len(self.cd))
            name = self.cd[pos + 46:pos + 46 + nl].decode('utf8' if flags & 2048 else 'cp437')
            _check(name not in self.entries and not name.startswith('/') and '..' not in name.split('/') and local + 30 + packed < offset)
            self.entries[name] = dict(flags=flags, method=method, crc=crc, packed=packed, plain=plain, local=local)
            pos += 46 + nl + xl + cl
        _check(pos == len(self.cd))
        footer = self.range(offset - 24, 24)
        block_size, = struct.unpack_from('<Q', footer)
        _check(footer[8:] == b'APK Sig Block 42' and 24 <= block_size <= 1024**2)
        signing = offset - block_size - 8
        block = self.range(signing, block_size - 16) + footer
        self.layout = ApkLayout(total, signing, block, self.cd, self.eocd, allow_signed_zero_tail=True)
        self.layout.validate()

    def range(self, start, count):
        _check(0 < count <= MAX_METADATA and 0 <= start <= self.total - count and self.metadata_bytes + count <= MAX_METADATA)
        with _open(self.url, headers={'Range': f'bytes={start}-{start + count - 1}', 'If-Range': self.etag}) as response:
            _check(response.status == 206 and response.geturl() == self.url and response.headers.get('ETag') == self.etag and
                   response.headers.get('Content-Range') == f'bytes {start}-{start + count - 1}/{self.total}')
            raw = response.read(count + 1)
        _check(len(raw) == count)
        self.metadata_bytes += count
        return raw

    def member(self, name, *, read=False, maximum=MAX_MODULE):
        e = self.entries[name]
        _check(e['flags'] & ~2048 == 0 and e['method'] in (0, 8) and 0 < e['plain'] <= maximum)
        header = self.range(e['local'], 30)
        _check(header[:4] == b'PK\x03\x04')
        flags, method = struct.unpack_from('<HH', header, 6)
        crc, packed, plain, nl, xl = struct.unpack_from('<IIIHH', header, 14)
        _check((flags, method, crc, packed, plain) == (e['flags'], e['method'], e['crc'], e['packed'], e['plain']) and nl <= 4096)
        extra = self.range(e['local'] + 30, nl + xl + (packed if read else 0))
        _check(extra[:nl] == name.encode('utf8'))
        offset = e['local'] + 30 + nl + xl
        self.witnesses.append((e['local'], header + extra))
        if not read:
            return offset, packed
        raw = extra[nl + xl:]
        value = _inflate_bytes(raw, plain) if method == 8 else raw
        _check(len(value) == plain and zlib.crc32(value) & 0xffffffff == crc)
        return value


def _inflate_bytes(raw, maximum):
    decoder = zlib.decompressobj(-15)
    value = decoder.decompress(raw, maximum + 1)
    _check(len(value) <= maximum and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
    return value


def _library(axml):
    _check(len(axml) >= 8 and struct.unpack_from('<HHI', axml) == (3, 8, len(axml)))
    strings, stack, libraries = [], [], []
    package = None

    def text(index):
        _check(0 <= index < len(strings))
        return strings[index]

    def length(at, wide):
        x = struct.unpack_from('<H' if wide else '<B', axml, at)[0]
        bit, width = (32768, 2) if wide else (128, 1)
        if x & bit:
            y = struct.unpack_from('<H' if wide else '<B', axml, at + width)[0]
            return ((x & (bit - 1)) << (16 if wide else 8)) | y, at + width * 2
        return x, at + width

    at = 8
    while at < len(axml):
        kind, header, size = struct.unpack_from('<HHI', axml, at)
        _check(8 <= header <= size and at + size <= len(axml))
        if kind == 1:
            count, _, flags, start, _ = struct.unpack_from('<5I', axml, at + 8)
            _check(not strings and 0 < count <= 65536 and header >= 28 and header + count * 4 <= size)
            for i in range(count):
                pos = at + start + struct.unpack_from('<I', axml, at + header + i * 4)[0]
                _, pos = length(pos, not bool(flags & 256))
                if flags & 256:
                    n, pos = length(pos, False)
                    strings.append(axml[pos:pos + n].decode('utf8'))
                    _check(pos + n < at + size and axml[pos + n] == 0)
                else:
                    n, _ = length(at + start + struct.unpack_from('<I', axml, at + header + i * 4)[0], True)
                    strings.append(axml[pos:pos + n * 2].decode('utf-16le'))
                    _check(pos + n * 2 + 2 <= at + size and axml[pos + n * 2:pos + n * 2 + 2] == b'\0\0')
        elif kind == 0x102:
            _, name, attr_start, attr_size, count = struct.unpack_from('<IIHHH', axml, at + 16)
            name, attrs = text(name), {}
            _check(attr_size == 20)
            for i in range(count):
                pos = at + 16 + attr_start + i * 20
                _check(pos + 20 <= at + size)
                namespace, key, raw = struct.unpack_from('<III', axml, pos)
                value_size, zero, typ, value = struct.unpack_from('<HBBI', axml, pos + 12)
                _check(value_size == 8 and zero == 0)
                namespace = None if namespace == 0xffffffff else text(namespace)
                key = ('android:' if namespace == 'http://schemas.android.com/apk/res/android' else
                       namespace + ':' if namespace is not None else '') + text(key)
                _check(key not in attrs)
                attrs[key] = text(raw) if raw != 0xffffffff else text(value) if typ == 3 else None
            if name == 'manifest':
                _check(package is None)
                package = attrs.get('package')
            if name == 'meta-data' and attrs.get('android:name') == 'android.app.lib_name':
                _check(any(x[0] == 'activity' and x[1].get('android:name') == 'com.epicgames.ue4.GameActivity' for x in stack))
                libraries.append(attrs.get('android:value'))
            stack.append((name, attrs))
        elif kind == 0x103:
            name, = struct.unpack_from('<I', axml, at + 20)
            _check(stack and stack.pop()[0] == text(name))
        at += size
    _check(at == len(axml) and not stack and package == 'com.kurogame.mingchao' and len(libraries) == 1 and
           isinstance(libraries[0], str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', libraries[0]))
    return 'lib/arm64-v8a/lib' + libraries[0] + '.so'


def _decode_module(compressed, decoded, entry, *, check=lambda: None):
    """The same bounded passive Deflate/CRC loop for ordinary and staged IO."""
    _check(type(entry['plain']) is int and 0 < entry['plain'] <= MAX_MODULE and
           type(entry['packed']) is int and 0 < entry['packed'] <= 4 * 1024**3 and
           compressed.stat().st_size == entry['packed'])
    decoder, size, crc, digest, stored = zlib.decompressobj(-15), 0, 0, hashlib.sha256(), hashlib.sha256()
    with compressed.open('rb') as src, decoded.open('xb') as dst:
        for part in iter(lambda: src.read(65536), b''):
            check()
            stored.update(part)
            pending = part
            while pending:
                check()
                value = decoder.decompress(pending, min(1024**2, entry['plain'] - size + 1))
                previous, pending = len(pending), decoder.unconsumed_tail
                _check(value or len(pending) < previous)
                size += len(value)
                _check(size <= entry['plain'] and not decoder.unused_data)
                dst.write(value)
                crc = zlib.crc32(value, crc)
                digest.update(value)
        _check(not decoder.flush() and decoder.eof and not decoder.unused_data and size == entry['plain'] and
               crc & 0xffffffff == entry['crc'])
    return size, crc & 0xffffffff, digest.hexdigest(), stored.hexdigest()


def _acquire(tools, progress=lambda _message: None, *, existing=()):
    catalogue_raw = _read(CATALOGUE + '?_t=' + str(int(time.time() // 60)), 64 * 1024)
    catalogue = json.loads(catalogue_raw)
    _check(isinstance(catalogue, dict) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', catalogue['version']))
    url = _url(catalogue['primary'])
    with _open(url, method='HEAD') as response:
        _check(response.status == 200 and response.geturl() == url)
        total, etag = int(response.headers['Content-Length']), response.headers['ETag']
    _check(0 < total <= 4 * 1024**3 and etag and len(etag) <= 256)
    for previous in existing:
        previous = reference(previous)
        if (previous['url'], previous['bytes'], previous['etag'], previous['version'], previous['catalogue_sha256']) == (
                url, total, etag, catalogue['version'], _hash(catalogue_raw)):
            module = _module(tools, previous)
            if module.stat().st_size != previous['module']['plain_bytes'] or _file_hash(module) != previous['module']['sha256']:
                raise PreparationFailure('publisher_bootstrap_cache_invalid',
                    'The retained original native module is corrupt. Download the game data again; previous data is retained.')
            return previous
    archive = _Zip(url, total, etag)
    manifest = archive.member('AndroidManifest.xml', read=True, maximum=2 * 1024**2)
    name = _library(manifest)
    offset, packed = archive.member(name)
    entry = archive.entries[name]
    _check(entry['method'] == 8)
    progress(f'Verifying the official bootstrap download ({total:,} bytes).')
    root = _root(tools)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='pending-') as folder:
        folder = Path(folder)
        _check(folder.resolve().is_relative_to(root.resolve()))
        compressed, decoded = folder / 'selected.deflate', folder / 'module.so'

        class WitnessStream:
            def __init__(self, response):
                self.response, self.at = response, 0

            def read(self, count):
                raw = self.response.read(count)
                for start, expected in archive.witnesses:
                    left, right = max(self.at, start), min(self.at + len(raw), start + len(expected))
                    if left < right:
                        _check(raw[left - self.at:right - self.at] == expected[left - start:right - start])
                self.at += len(raw)
                return raw

        with _open(url, headers={'If-Match': etag}) as response, compressed.open('xb') as sink:
            _check(response.status == 200 and response.geturl() == url and response.headers.get('ETag') == etag and
                   response.headers.get('Content-Length') == str(total) and not response.headers.get('Content-Encoding'))
            verified = verify_stream(WitnessStream(response), archive.layout, member=(offset, packed), member_sink=sink)
        size, crc, plain_sha, packed_sha = _decode_module(compressed, decoded, entry)
        source = reference(dict(policy=POLICY, catalogue=CATALOGUE, catalogue_sha256=_hash(catalogue_raw),
            version=catalogue['version'], url=url, bytes=total,
            etag=etag, apk_sha256=verified['apk_sha256'], v2_digest=verified['v2_content_digest'], signers=verified['certificate_sha256'],
            module=dict(name=name, sha256=plain_sha, compressed_sha256=packed_sha,
                        compressed_bytes=packed, plain_bytes=size, crc32=f'{crc & 0xffffffff:08x}')))
        default_output(decoded, source['module']['sha256'])
        target = _module(tools, source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            _check(_file_hash(target) == source['module']['sha256'])
        else:
            decoded.replace(target)
        return source


def parameters(tools, info, region='global', *, refresh=False, retained=None, progress=lambda _message: None):
    """Use explicit original provenance; this route never reads the initial seed."""
    with _GATE:
        return _parameters(tools, info, region, refresh=refresh, retained=retained, progress=progress)


def _parameters(tools, info, region, *, refresh, retained, progress):
    owner = _owner(info, region)
    lock = ExportLock(_root(tools) / 'source.lock')
    try:
        if not lock.acquire():
            raise PreparationFailure('publisher_bootstrap_busy', 'Another original bootstrap download is active. Retry preparation; previous data is retained.')
        record = _registry(tools)
        if retained is not None:
            source = reference(retained)
            sid = identity(source)
            _check(record['sources'].get(sid) == source)
        else:
            sid = record['owners'].get(owner) or record['regions'].get(region)
            source = record['sources'].get(sid) if sid and not refresh else None
            if source is None:
                source = _acquire(tools, progress, existing=record['sources'].values())
                sid = identity(source)
                record['sources'][sid] = source
                record['regions'][region] = sid
                _save(tools, record)
        module = _module(tools, source)
        if module.stat().st_size != source['module']['plain_bytes'] or _file_hash(module) != source['module']['sha256']:
            raise PreparationFailure('publisher_bootstrap_cache_invalid',
                'The retained original native module is corrupt. Download the game data again; previous data is retained.')
        result = default_output(module, source['module']['sha256'])
        return Parameters(Candidate(source, result.parameter, region, record['owners'].get(owner) == identity(source), owner))
    except PreparationFailure:
        raise
    except OSError as error:
        raise PreparationFailure('publisher_bootstrap_unavailable',
            'The original bootstrap source or local module is unavailable. Retry the download; previous data is retained.') from error
    except (ValueError, TypeError, KeyError, IndexError, struct.error) as error:
        raise PreparationFailure('publisher_bootstrap_source_unsupported',
            'The original bootstrap source could not be verified or its native producer is unsupported; previous data is retained.') from error
    finally:
        lock.close()


def remember_owner(tools, candidate, info):
    """Call only after complete ordinary original PAK index/hash validation."""
    with _GATE:
        return _remember_owner(tools, candidate, info)


def _remember_owner(tools, candidate, info):
    _check(isinstance(candidate, Candidate))
    lock = ExportLock(_root(tools) / 'source.lock')
    try:
        if not lock.acquire():
            raise PreparationFailure('publisher_bootstrap_busy', 'Another bootstrap owner check is active; previous data is retained.')
        record = _registry(tools)
        sid = identity(candidate.source)
        _check(record['sources'].get(sid) == candidate.source)
        owner = _owner(info, candidate.region)
        _check(candidate.owner_id is None or candidate.owner_id == owner)
        if record['owners'].get(owner) != sid:
            record['owners'][owner] = sid
            _save(tools, record)
        candidate.verified = True
        candidate.owner_id = owner
    except OSError as error:
        raise PreparationFailure('publisher_key_cache_failed',
            'The verified original bootstrap owner could not be written; previous data is retained.') from error
    finally:
        lock.close()
