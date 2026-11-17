"""Reuse complete originals only under their exact authored package/member owner.

Only the ordinary validated extractor writes this cache. An unqualified older
snapshot cache is not evidence for a new owner and is never promoted here.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .game_tools import _atomic_file

MAX_BYTES = 512 * 1024**2
MAGIC = b'WUS1'


def _identity(depot, reference):
    # Older internal callers may not yet carry a complete publisher reference.
    # They cannot use this cache; their original extraction path still applies.
    if (not isinstance(depot, str) or len(depot) > 4096 or
            not depot.startswith('Client/Content/Aki/WwiseAudio_Generated/') or
            not depot.endswith('.wem') or '\\' in depot or ':' in depot or
            any(part in ('', '.', '..') for part in depot.split('/')) or
            not isinstance(reference, (tuple, list)) or len(reference) != 2):
        return None
    info, position = reference
    if (not isinstance(info, (tuple, list)) or len(info) != 3 or
            type(position) is not int or position < 0):
        return None
    url, size, digest = info
    if (not isinstance(url, str) or len(url) > 4096 or type(size) is not int or size <= 0 or
            not isinstance(digest, str) or not re.fullmatch(r'(?:[0-9a-f]{32}|[0-9a-f]{40})', digest)):
        return None
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != parsed.hostname or
            not parsed.hostname or parsed.query or parsed.fragment):
        return None
    return hashlib.sha256(json.dumps([url, size, digest, position, depot],
        separators=(',', ':'), ensure_ascii=True).encode()).digest()


def _path(tools, identity):
    return Path(tools) / 'wuwa-publisher' / 'owned-sources' / identity.hex()


def _wem(data):
    return (isinstance(data, bytes) and 12 <= len(data) <= MAX_BYTES and
            data[:4] == b'RIFF' and data[8:12] == b'WAVE' and
            int.from_bytes(data[4:8], 'little') + 8 == len(data))


def cached(tools, depot, reference):
    identity = _identity(depot, reference)
    if identity is None:
        return None
    path = _path(tools, identity)
    if not path.is_file() or path.is_symlink() or not 80 <= path.stat().st_size <= MAX_BYTES + 68:
        return None
    value = path.read_bytes()
    data = value[68:]
    if (value[:36] == MAGIC + identity and _wem(data) and
            hashlib.sha256(data).digest() == value[36:68]):
        return data
    return None


def remember(tools, depot, reference, data):
    """Call after ordinary original extraction and full local WEM validation."""
    identity = _identity(depot, reference)
    if identity is None:
        return
    if not _wem(data):
        raise ValueError('The complete original Wuthering recording is invalid.')
    _atomic_file(_path(tools, identity), MAGIC + identity + hashlib.sha256(data).digest() + data)
