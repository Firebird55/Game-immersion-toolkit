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

import certifi

from .export_lock import ExportLock
from .atomic_files import replace
from .preparation_errors import PreparationFailure
from .publisher_apk import verify_stream
from .publisher_apk_zip import ApkMetadata
from .wuthering_bootstrap_source import (
    POLICY, CATALOGUE, MAX_METADATA, MAX_MODULE, default_output,
    _check, _hash, _file_hash, _canonical, _url, reference, identity,
    _root, _module, _library, _decode_module,
)
from . import wuthering_metadata as metadata


_GATE = threading.RLock()


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


class _Zip(ApkMetadata):
    """Bind the single maintained metadata reader to ordinary publisher IO."""
    def __init__(self, url, total, etag):
        self.url, self.etag = url, etag
        super().__init__(self._read_range, total, allow_signed_zero_tail=True,
                         maximum_metadata=MAX_METADATA)

    def _read_range(self, start, count):
        with _open(self.url, headers={'Range': f'bytes={start}-{start + count - 1}', 'If-Range': self.etag}) as response:
            _check(response.status == 206 and response.geturl() == self.url and response.headers.get('ETag') == self.etag and
                   response.headers.get('Content-Range') == f'bytes {start}-{start + count - 1}/{self.total}')
            raw = response.read(count + 1)
        _check(len(raw) == count)
        return raw


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
    offset, packed = archive.member(name, maximum=MAX_MODULE)
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
