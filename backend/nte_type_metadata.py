"""Version-selected public type data, pinned immutably with each NTE snapshot."""
from dataclasses import dataclass, field
import hashlib
import json
import re

from . import nte_archive_metadata as metadata
from .game_tools import _atomic_file
from .publisher_http import download
from .nte_publisher_pak import Reader

REPOSITORY = '555me/NTE-usmap'
FALLBACK = '1b92d5267092dac6bcfec605bcaf6ae05b664746'
LIMIT = 8 * 1024**2


def validate(data):
    """Bound the expansion declared to the isolated managed type-data parser."""
    metadata.check(isinstance(data, bytes) and 12 <= len(data) <= LIMIT)
    reader = Reader(data)
    metadata.check(reader.number('H') == 0x30c4)
    version = reader.number('B')
    metadata.check(version <= 5)
    flag = reader.number('I') if version >= 1 else 0
    metadata.check(flag in (0, 1))
    if flag:
        if version >= 5:
            reader.read(10)  # Engine major/minor/patch and changelist.
            reader.string(8192)
        reader.read(8)  # UE4/UE5 package versions.
        reader.read(reader.count(4096) * 20)  # GUID plus version per custom entry.
        reader.read(4)  # Net changelist.
    method, packed, expanded = reader.number('B'), reader.number('I'), reader.number('I')
    metadata.check(method in (0, 1, 2, 3) and packed == len(data) - reader.position and
                   0 < expanded <= 64 * 1024**2 and (method != 0 or packed == expanded))


@dataclass(frozen=True)
class Schema:
    reference: dict
    data: bytes = field(repr=False)


def _version(value):
    metadata.check(isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+', value))
    return tuple(map(int, value.split('.')))


def load(version, cache, *, reference=None, fetch=None):
    try:
        return _load(version, cache, reference=reference, fetch=fetch)
    except (ValueError, TypeError, KeyError, UnicodeError):
        metadata.check(False)


def _load(version, cache, *, reference=None, fetch=None):
    """Never follow a community-supplied URL or replace historical metadata."""
    fetch = fetch or download
    selected = _version(version)
    historical = reference is not None
    if historical:
        metadata.check(isinstance(reference, dict) and set(reference) == {'revision', 'index_sha256', 'path', 'sha256'})
    raw, revision, index_digest, _ = metadata._source(REPOSITORY, 'index.json', FALLBACK,
        revision=reference['revision'] if historical else None,
        digest=reference['index_sha256'] if historical else None, cache=cache, fetch=fetch)
    index = json.loads(raw)
    metadata.check(index.get('game') == 'HT-NTE_UE5_6' and isinstance(index.get('mapping'), list)
                   and 0 < len(index['mapping']) <= 128)
    candidates = []
    for row in index['mapping']:
        metadata.check(isinstance(row, dict) and isinstance(row.get('url'), str) and isinstance(row.get('versionInfo'), str))
        match = re.fullmatch(r'https://github\.com/555me/NTE-usmap/raw/refs/heads/main/(mapping/HT-[0-9.-]+\.usmap)', row['url'])
        versions = re.fullmatch(r'(\d+\.\d+)-(\d+\.\d+\.\d+)', row['versionInfo'])
        metadata.check(match and versions)
        baseline = _version(versions[2])
        metadata.check(versions[1] == '.'.join(map(str, baseline[:2])))
        if baseline <= selected:
            candidates.append((baseline, match[1]))
    metadata.check(candidates)
    latest = max(v for v, _ in candidates)
    paths = {path for v, path in candidates if v == latest}
    metadata.check(len(paths) == 1)
    path = paths.pop()
    if historical:
        metadata.check(reference['path'] == path and re.fullmatch('[0-9a-f]{64}', reference['sha256']))
    cached = cache / (reference['sha256'] + '.usmap') if historical else None
    data = cached.read_bytes() if cached is not None and cached.is_file() and cached.stat().st_size <= LIMIT else b''
    if not data or hashlib.sha256(data).hexdigest() != reference['sha256']:
        data = fetch(f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{path}', LIMIT)
    validate(data)
    digest = hashlib.sha256(data).hexdigest()
    metadata.check(not historical or digest == reference['sha256'])
    _atomic_file(cache / f'{revision}-{index_digest}.txt', raw)
    _atomic_file(cache / (digest + '.usmap'), data)
    return Schema({'revision': revision, 'index_sha256': index_digest, 'path': path, 'sha256': digest}, data)
