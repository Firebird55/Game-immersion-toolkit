"""Bounded, revalidated metadata for public publisher update checks.

Every call contacts the source. Only a matching HTTP 304 can reuse a body;
errors never turn cached metadata into a successful freshness check. Entries
are process-local, so temporary launcher query parameters are not persisted.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import threading
from urllib.error import HTTPError
import urllib.request


MAX_ENTRY = 2 * 1024**2
MAX_BYTES = 8 * 1024**2
MAX_ENTRIES = 64
_cache = OrderedDict()
_lock = threading.Lock()


@dataclass(frozen=True)
class _Entry:
    body: bytes
    etag: str
    modified: str


def _header(headers, name):
    value = headers.get(name, '')
    return value if len(value) <= 1024 and all(32 <= ord(c) <= 126 for c in value) else ''


def _not_modified(response, url, previous, conditional):
    if previous is None or not conditional or response.geturl() != url:
        raise ValueError('Publisher returned an unsolicited metadata validation response.')
    tag = _header(response.headers, 'ETag')
    # If-None-Match uses weak comparison for GET (RFC 9110 section 13.1.2).
    if tag and previous.etag and tag.removeprefix('W/') != previous.etag.removeprefix('W/'):
        raise ValueError('Publisher metadata validation identifies a different response.')
    if not _storable(response.headers):
        with _lock:
            key = hashlib.sha256(url.encode()).digest()
            if _cache.get(key) is previous:
                _cache.pop(key)
    return previous.body


def _storable(headers):
    return ('no-store' not in headers.get('Cache-Control', '').lower()
            and '*' not in {value.strip() for value in headers.get('Vary', '').split(',')})


def download(url: str, limit: int = 64 * 1024**2, *, opener=None) -> bytes:
    key = hashlib.sha256(url.encode()).digest()
    with _lock:
        previous = _cache.get(key)
        if previous is not None:
            _cache.move_to_end(key)
    # A smaller caller limit must not inherit an oversized cached response.
    if previous is not None and len(previous.body) > limit:
        previous = None
    headers = {'User-Agent': 'GameImmersionToolkit/1', 'Accept-Encoding': 'identity'}
    if previous is not None:
        if previous.etag:
            headers['If-None-Match'] = previous.etag
        elif previous.modified:
            headers['If-Modified-Since'] = previous.modified
    conditional = 'If-None-Match' in headers or 'If-Modified-Since' in headers
    request = urllib.request.Request(url, headers=headers)
    try:
        with (opener or urllib.request.urlopen)(request, timeout=90) as response:
            if response.status == 304:
                return _not_modified(response, url, previous, conditional)
            if response.status != 200:
                raise ValueError('Publisher metadata response is incomplete.')
            data = response.read(limit + 1)
            length = response.headers.get('Content-Length')
            if len(data) > limit or length is not None and (not length.isdecimal() or int(length) != len(data)):
                raise ValueError('Publisher metadata is truncated or exceeds its size limit.')
            etag, modified = _header(response.headers, 'ETag'), _header(response.headers, 'Last-Modified')
            cacheable = (response.geturl() == url and len(data) <= MAX_ENTRY and (etag or modified)
                         and _storable(response.headers))
    except HTTPError as error:
        if error.code != 304:
            raise
        try:
            return _not_modified(error, url, previous, conditional)
        finally:
            error.close()
    with _lock:
        _cache.pop(key, None)
        if cacheable:
            _cache[key] = _Entry(data, etag, modified)
        while len(_cache) > MAX_ENTRIES or sum(len(entry.body) for entry in _cache.values()) > MAX_BYTES:
            _cache.popitem(last=False)
    return data
