"""Immutable initial candidates, separate from verified archive-key ownership.

The pinned Git blob is the already retained initial input, not a latest-key feed.
Only complete original package checks may authorize a candidate as an archive key.
"""
import base64
import hashlib
import json
import re

from . import wuthering_metadata as metadata

REPOSITORY = 'yarik0chka/wuwa-keys'
BLOB = 'b1fb189eaf793066c6b242d6e4edd9860b232248'
SHA256 = 'a7c1e540b93e14b829967c2c5cb7e46d57d6a701cb7087e904ebe1c3f67679b5'
SIZE = 88674
URL = f'https://api.github.com/repos/{REPOSITORY}/git/blobs/{BLOB}'
WIRE_LIMIT = 256 * 1024


def provenance():
    return {'policy': 'immutable_initial_seed', 'repository': REPOSITORY,
            'blob': BLOB, 'files': {'keys.json': {'sha256': SHA256, 'bytes': SIZE}}}


def _valid(raw):
    return (isinstance(raw, bytes) and len(raw) == SIZE
            and hashlib.sha256(raw).hexdigest() == SHA256
            and hashlib.sha1(b'blob ' + str(SIZE).encode() + b'\0' + raw).hexdigest() == BLOB)


def parameters(tools, fetch):
    path = metadata._path(tools, 'initial-seed') if tools is not None else None
    raw = metadata._read(path) if path is not None else None
    if not _valid(raw):
        wire = fetch(URL, limit=WIRE_LIMIT)
        if not isinstance(wire, bytes) or len(wire) > WIRE_LIMIT:
            raise ValueError('The immutable Wuthering initial seed exceeds its limit.')
        value = json.loads(wire)
        if (not isinstance(value, dict) or value.get('sha') != BLOB or value.get('size') != SIZE
                or value.get('encoding') != 'base64' or not isinstance(value.get('content'), str)):
            raise ValueError('The immutable Wuthering initial seed has different ownership.')
        raw = base64.b64decode(''.join(value['content'].split()), validate=True)
        if not _valid(raw):
            raise ValueError('The immutable Wuthering initial seed checksum differs.')
        if path is not None and (not metadata._write(path, raw) or metadata._read(path) != raw):
            raise OSError('The immutable Wuthering initial seed could not be retained safely.')
    values = tuple(bytes.fromhex(value) for value in dict.fromkeys(
        re.findall(r'0x([0-9a-fA-F]{64})', json.dumps(json.loads(raw)))))
    if not 0 < len(values) <= 4096:
        raise ValueError('The immutable Wuthering initial seed has no bounded candidates.')
    return values
