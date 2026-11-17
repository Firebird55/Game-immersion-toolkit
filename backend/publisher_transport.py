"""Bounded publisher I/O shared by desktop and native game-data providers.

The host context owns permission, account/cancellation fences and cumulative
byte allowances. This adapter never executes source content or imports desktop
helpers. A transport receipt alone is not a verified game/voice binding.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.client import IncompleteRead
import os
from pathlib import Path
import re
import stat
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from .game_data_protocol import GameDataError, MAX_ASSET_BYTES

MAX_URL = 16 * 1024
CHUNK = 64 * 1024
CONTENT_RANGE = re.compile(r'bytes ([0-9]{1,16})-([0-9]{1,16})/([0-9]{1,16})')
HASHES = {'md5', 'sha1', 'sha256', 'sha512'}
STRONG_ETAG = re.compile(r'"[\x21\x23-\x7e]{0,1022}"')


def source_url(value, hosts):
    if (not isinstance(value, str) or not value or len(value) > MAX_URL
            or any(ord(c) < 33 or ord(c) == 127 for c in value)):
        raise GameDataError('invalid_publisher_url', 'The game source returned an invalid download address.')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise GameDataError('invalid_publisher_url', 'The game source returned an invalid download address.') from error
    if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port not in (None, 443)):
        raise GameDataError('invalid_publisher_url', 'The game source returned an unapproved download address.')
    return value


class _PublisherRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, request, response, code, message, headers, target):
        source_url(target, self.hosts)
        if urlsplit(target).hostname != urlsplit(request.full_url).hostname:
            if any(name.lower() in {'authorization', 'cookie'} for name in request.headers):
                raise GameDataError('publisher_redirect_changed', 'The game download source changed unexpectedly.')
        return super().redirect_request(request, response, code, message, headers, target)


@dataclass(frozen=True)
class TransferReceipt:
    source_url_sha256: str
    bytes: int
    sha256: str
    publisher_digests: dict
    original_range: tuple[int, int, int] | None
    response_etag: str | None = None

    def json(self):
        result = {'source_url_sha256': self.source_url_sha256, 'bytes': self.bytes, 'sha256': self.sha256,
                'publisher_digests': dict(self.publisher_digests),
                'original_range': list(self.original_range) if self.original_range is not None else None}
        if self.response_etag is not None:
            result['response_etag'] = self.response_etag
        return result


def _integer(value, *, minimum=0):
    return type(value) is int and value >= minimum


def _expected_hashes(values):
    if values is None:
        return {}
    if not isinstance(values, Mapping) or set(values) - HASHES:
        raise GameDataError('invalid_publisher_digest', 'The game source returned an unsupported checksum.')
    result = {}
    for name, digest in values.items():
        size = hashlib.new(name).digest_size * 2
        if not isinstance(digest, str) or re.fullmatch('[0-9a-fA-F]{' + str(size) + '}', digest) is None:
            raise GameDataError('invalid_publisher_digest', 'The game source returned an invalid checksum.')
        result[name] = digest.lower()
    return result


class PublisherTransport:
    def __init__(self, ctx, *, hosts, opener=None, timeout=30):
        hosts = frozenset(hosts)
        if not hosts or any(not isinstance(host, str) or host != host.lower() or '/' in host or ':' in host for host in hosts):
            raise ValueError('Explicit normalized publisher hosts are required')
        self.ctx, self.hosts, self.timeout = ctx, hosts, timeout
        self.open = opener if opener is not None else build_opener(_PublisherRedirect(hosts)).open

    def _transfer(self, url, sink, *, limit, kind, expected_size, digests, original_range, headers, method, body):
        # Budget checks, body reads and consumption share the service's lock.
        # Two provider threads cannot both spend the same remaining allowance.
        with self.ctx.transfer_lock:
            return self._transfer_locked(url, sink, limit=limit, kind=kind, expected_size=expected_size,
                digests=digests, original_range=original_range, headers=headers, method=method, body=body)

    def _transfer_locked(self, url, sink, *, limit, kind, expected_size, digests, original_range, headers, method, body):
        source_url(url, self.hosts)
        if kind not in {'metadata', 'asset', 'audio'} or not _integer(limit, minimum=1):
            raise ValueError('A positive typed transfer bound is required')
        if expected_size is not None and (not _integer(expected_size) or expected_size > limit):
            raise ValueError('The expected original size must fit its transfer bound')
        expected = _expected_hashes(digests)
        if method not in {'GET', 'POST'} or method == 'GET' and body is not None:
            raise ValueError('Only explicit original metadata/data requests are supported')
        if body is not None and (not isinstance(body, bytes) or len(body) > 64 * 1024):
            raise ValueError('Publisher request data exceeds its bound')
        request_headers = {'User-Agent': 'GameImmersionToolkit', 'Accept-Encoding': 'identity'}
        expected_etag = None
        for key, value in (headers or {}).items():
            if (not isinstance(key, str) or not isinstance(value, str) or not key or len(key) > 128
                    or len(value) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in key + value)
                    or key.lower() in {'host', 'content-length', 'range', 'accept-encoding'}):
                raise ValueError('Invalid explicit publisher request header')
            if key.lower() == 'if-match':
                if expected_etag is not None or STRONG_ETAG.fullmatch(value) is None:
                    raise ValueError('If-Match requires one actual strong publisher ETag')
                expected_etag = value
            request_headers[key] = value
        if original_range is not None:
            if (not isinstance(original_range, tuple) or len(original_range) != 3
                    or not all(_integer(n) for n in original_range[:2])
                    or original_range[2] is not None and not _integer(original_range[2], minimum=1)):
                raise ValueError('An original range needs offset, size and full owner size')
            offset, size, total = original_range
            if (not size or size > limit or expected_size not in (None, size)
                    or total is not None and (offset + size > total or total > MAX_ASSET_BYTES)
                    or total is None and (kind != 'metadata' or offset != 0 or size > CHUNK)):
                raise ValueError('Original range leaves its declared file owner')
            expected_size = size
            request_headers['Range'] = f'bytes={offset}-{offset + size - 1}'
        self.ctx.check()
        self.ctx.consume_bytes(0, kind=kind)  # Validate consent/phase before opening any connection.
        allowance = min(limit, self.ctx.remaining_bytes(kind=kind))
        if allowance <= 0 or expected_size is not None and expected_size > allowance:
            raise GameDataError('download_budget_exhausted', 'Check the download size again before continuing.')
        request = Request(url, data=body, headers=request_headers, method=method)
        hashes = {name: hashlib.new(name) for name in set(expected) | {'sha256'}}
        count = 0
        response_etag = None
        resolved_range = original_range
        try:
            with self.open(request, timeout=self.timeout) as response:
                source_url(response.geturl(), self.hosts)
                status = response.status
                if status != (206 if original_range else 200):
                    raise GameDataError('publisher_response_invalid', 'The game server returned an incomplete download response.')
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise GameDataError('publisher_response_invalid', 'The game download encoding changed unexpectedly.')
                tags = response.headers.get_all('ETag', [])
                if len(tags) > 1:
                    raise GameDataError('publisher_response_invalid', 'The game server returned ambiguous file identity.')
                if tags and STRONG_ETAG.fullmatch(tags[0]) is not None:
                    response_etag = tags[0]
                if expected_etag is not None and response_etag != expected_etag:
                    raise GameDataError('publisher_object_changed', 'The original game file changed. Check the download again.', 409)
                lengths = response.headers.get_all('Content-Length', [])
                if len(lengths) > 1 or lengths and re.fullmatch(r'[0-9]{1,16}', lengths[0]) is None:
                    raise GameDataError('publisher_response_invalid', 'The game download size is inconsistent.')
                declared = int(lengths[0]) if lengths else None
                if declared is not None and (declared > allowance or expected_size is not None and declared != expected_size):
                    raise GameDataError('publisher_size_changed', 'The game download size changed. Check its size again.')
                if original_range:
                    value = CONTENT_RANGE.fullmatch(response.headers.get('Content-Range', ''))
                    actual_range = tuple(map(int, value.groups())) if value else None
                    if (actual_range is None or actual_range[:2] != (offset, offset + size - 1)
                            or not offset + size <= actual_range[2] <= MAX_ASSET_BYTES
                            or total is not None and actual_range[2] != total):
                        raise GameDataError('publisher_range_changed', 'The game server returned a different file range.')
                    # A publisher may omit native member sizes from its outer
                    # manifest. Only a small initial metadata header may learn
                    # that size; every subsequent range pins the learned owner.
                    resolved_range = (offset, size, actual_range[2])
                elif response.headers.get('Content-Range') is not None:
                    raise GameDataError('publisher_response_invalid', 'The game server returned an unexpected file range.')
                # Content-Length frames an entire response. Without it, only
                # actual EOF proves that a verified prefix is the whole file.
                target = declared
                while target is None or count < target:
                    self.ctx.check()
                    remaining = min(allowance - count, self.ctx.remaining_bytes(kind=kind))
                    if target is not None:
                        remaining = min(remaining, target - count)
                    if remaining <= 0:
                        raise GameDataError('download_budget_exhausted', 'The download could not be verified within its size limit.')
                    requested = min(CHUNK, remaining)
                    try:
                        chunk = response.read(requested)
                    except IncompleteRead as error:
                        # Interrupted partial bytes still spent the approved
                        # transport allowance, even though none may publish.
                        if isinstance(error.partial, bytes) and len(error.partial) <= requested:
                            self.ctx.consume_bytes(len(error.partial), kind=kind)
                        raise GameDataError('metadata_download_interrupted', 'The game download was interrupted. Your previous data is retained.', 502) from error
                    if not isinstance(chunk, bytes) or len(chunk) > requested:
                        raise GameDataError('publisher_response_invalid', 'The game server returned invalid download data.')
                    if not chunk:
                        break
                    self.ctx.consume_bytes(len(chunk), kind=kind)
                    self.ctx.check()
                    count += len(chunk)
                    for digest in hashes.values():
                        digest.update(chunk)
                    try:
                        sink(chunk)
                    except OSError as error:
                        raise GameDataError('game_cache_write_failed', 'The game download could not be saved. Your previous data is retained.', 507) from error
                self.ctx.check()
                if target is not None and count != target:
                    raise GameDataError('metadata_download_interrupted', 'The game download was interrupted. Retry to keep preparing it.')
                if expected_size is not None and count != expected_size:
                    raise GameDataError('publisher_size_changed', 'The original game file size differs.')
        except GameDataError:
            raise
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError, IncompleteRead) as error:
            raise GameDataError('metadata_download_interrupted', 'The game download could not finish. Your previous data is retained.', 502) from error
        actual = {name: digest.hexdigest() for name, digest in hashes.items()}
        if any(actual[name] != value for name, value in expected.items()):
            raise GameDataError('publisher_checksum_mismatch', 'The original game download failed its checksum.')
        return TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), count, actual['sha256'], expected, resolved_range, response_etag)

    def fetch_bytes(self, url, *, limit, kind='metadata', expected_size=None, digests=None, original_range=None,
                    headers=None, method='GET', body=None):
        chunks = []
        receipt = self._transfer(url, chunks.append, limit=limit, kind=kind, expected_size=expected_size,
            digests=digests, original_range=original_range, headers=headers, method=method, body=body)
        return b''.join(chunks), receipt

    def download_to(self, url, destination, *, limit, kind='asset', expected_size=None, digests=None,
                    original_range=None, headers=None):
        raw_root = Path(self.ctx.cache_directory).absolute()
        # Inspect the configured root before resolve can conceal a junction.
        for probe in (raw_root, *raw_root.parents):
            if probe.exists() or probe.is_symlink():
                attributes = probe.lstat()
                if probe.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                    raise GameDataError('unsafe_game_cache', 'The game download cache must use ordinary private files.')
        root = raw_root.resolve()
        destination = Path(destination)
        if not destination.is_absolute():
            destination = root / destination
        probe = destination
        while probe != probe.parent:
            if probe.exists() or probe.is_symlink():
                attributes = probe.lstat()
                if probe.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                    raise GameDataError('unsafe_game_cache', 'The game download cache must use ordinary private files.')
            if probe == root:
                break
            probe = probe.parent
        destination = destination.resolve()
        if root not in destination.parents:
            raise GameDataError('unsafe_game_cache', 'The game download destination leaves its private cache.')
        pending = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.part')
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with pending.open('xb') as stream:
                receipt = self._transfer(url, stream.write, limit=limit, kind=kind, expected_size=expected_size,
                    digests=digests, original_range=original_range, headers=headers, method='GET', body=None)
                stream.flush()
                os.fsync(stream.fileno())
            self.ctx.check()
            os.replace(pending, destination)
            return receipt
        except OSError as error:
            raise GameDataError('game_cache_write_failed', 'The game download could not be saved. Your previous data is retained.', 507) from error
        finally:
            if pending.exists():
                pending.unlink()
