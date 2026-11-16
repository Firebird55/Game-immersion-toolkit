"""Read public, data-only NTE archive parameters and prove their applicability.

No game parameters are bundled. A named source entry is only a candidate until
it opens an actual archive index with its complete declared checksum.
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
import struct

from Crypto.Cipher import AES

from .preparation_errors import PreparationFailure
from .publisher_http import download
from .game_tools import _atomic_file

REPOSITORY = 'luk-gg/UnrealExporter'
SOURCE_PATH = 'UnrealExporter/aes.txt'
FALLBACK_REVISION = '8ed1e81ca6c9e08c71e664b4e1d5004c5a18e136'
LIMIT = 256 * 1024
MAGIC = b'\xe1\x12\x6f\x5a'
LOCALIZATION_REPOSITORY = 'FabianFG/CUE4Parse'
LOCALIZATION_PATH = 'CUE4Parse/GameTypes/NTE/Encryption/NevernessToEvernessLocresEncryption.cs'
LOCALIZATION_FALLBACK = '4d2301a8eb129f593f1c76ff82612400801f1a94'


def check(condition):
    if not condition:
        raise PreparationFailure('game_metadata_unavailable',
            'Compatible NTE archive format metadata could not be verified. '
            'Refresh game data and retry; the previous completed index is retained.')


@dataclass(frozen=True)
class Catalog:
    revision: str
    digest: str
    parameters: dict = field(repr=False)
    fallback: bool = False

    def verified_key(self, read, size, region=None):
        """Read bounded index bytes from a local or publisher range source."""
        check(type(size) is int and 64 <= size <= 1024**4)
        tail_size = min(512, size)
        footer = read(size - tail_size, tail_size)
        check(len(footer) == tail_size)
        marker = footer.rfind(MAGIC)
        check(17 <= marker <= len(footer) - 44)
        version, stored_offset, length = struct.unpack_from('<IQQ', footer, marker + 4)
        # The NTE v12 publisher stores its index offset one byte ahead.
        offset = stored_offset - 1
        check(version == 12 and footer[marker - 1] in (0, 1))
        if not footer[marker - 1]:
            return None  # A plaintext archive cannot establish a matching key.
        stored_length = (length + 15) // 16 * 16
        check(0 < length <= 64 * 1024**2 and 0 <= offset <= size - stored_length)
        data = read(offset, stored_length)
        check(len(data) == stored_length)
        expected = footer[marker + 24:marker + 44]
        check(region is None or region in ('nte-global', 'nte-cn'))
        values = set(self.parameters.values() if region is None else
                     (self.parameters.get(region),))
        check(1 <= len(values) <= 2 and all(isinstance(v, str) and
              re.fullmatch(r'0x[0-9a-fA-F]{64}', v) for v in values))
        found = []
        for value in values:
            plain = AES.new(bytes.fromhex(value[2:]), AES.MODE_ECB).decrypt(data)[:length]
            if hashlib.sha1(plain).digest() == expected:
                found.append(value)
        check(len(found) == 1)
        return found[0]


def _source(repository, source_path, fallback_revision, *, fetch=None, revision=None, digest=None, cache=None):
    fetch = fetch or download
    historical = revision is not None or digest is not None
    if historical:
        check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision) and
              isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest))
    fallback = False
    if not historical:
        try:
            url = f'https://api.github.com/repos/{repository}/commits?path={source_path}&per_page=1'
            rows = json.loads(fetch(url, LIMIT))
            check(isinstance(rows, list) and len(rows) == 1)
            revision = rows[0]['sha']
            check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
        except (OSError, ValueError, KeyError, TypeError, IndexError, PreparationFailure):
            # An API outage can use the independently checked immutable reference.
            # Its values still have to prove themselves against the chosen archive.
            revision, fallback = fallback_revision, True
    try:
        path = cache / f'{revision}-{digest}.txt' if historical and cache is not None else None
        raw = path.read_bytes() if path is not None and path.is_file() and path.stat().st_size <= LIMIT else b''
        if not raw or hashlib.sha256(raw).hexdigest() != digest:
            raw = fetch(f'https://raw.githubusercontent.com/{repository}/{revision}/{source_path}', LIMIT)
        check(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT)
        actual_digest = hashlib.sha256(raw).hexdigest()
        check(digest is None or actual_digest == digest)
    except (OSError, ValueError, TypeError) as error:
        raise PreparationFailure('game_metadata_unavailable',
            'The NTE format source is unavailable or incompatible. '
            'Retry preparation; existing prepared data is retained.') from error
    return raw, revision, actual_digest, fallback


def _cache_source(cache, revision, digest, raw):
    path = cache / f'{revision}-{digest}.txt'
    def identical():
        try:
            return path.is_file() and path.stat().st_size == len(raw) and path.read_bytes() == raw
        except OSError:
            return False
    if identical():
        return
    try:
        _atomic_file(path, raw)
    except PermissionError:
        # Concurrent preparation can publish the same verified immutable source
        # while another Windows reader denies replacement of that exact file.
        if not identical():
            raise


def load(*, fetch=None, revision=None, digest=None, cache=None):
    raw, revision, actual_digest, fallback = _source(REPOSITORY, SOURCE_PATH, FALLBACK_REVISION,
        fetch=fetch, revision=revision, digest=digest, cache=cache)
    try:
        text = raw.decode('utf-8-sig')
        pairs = re.findall(r'^Neverness to Everness \((chinese|global)\)[ \t]+(0x[0-9a-fA-F]{64})[ \t]*$',
                           text.replace('\r\n', '\n'), re.M)
        parameters = {}
        for label, value in pairs:
            region = {'global': 'nte-global', 'chinese': 'nte-cn'}[label]
            check(region not in parameters)
            parameters[region] = value.lower()
        check(parameters)
        if cache is not None:
            _cache_source(cache, revision, actual_digest, raw)
    except (OSError, ValueError, TypeError) as error:
        raise PreparationFailure('game_metadata_unavailable',
            'The NTE archive format source is unavailable or incompatible. '
            'Retry preparation; existing prepared data is retained.') from error
    return Catalog(revision, actual_digest, parameters, fallback)


@dataclass(frozen=True)
class LocalizationCatalog:
    revision: str
    digest: str
    parameter: str = field(repr=False)
    fallback: bool = False


def load_localization(*, fetch=None, revision=None, digest=None, cache=None):
    """Read one data-only candidate; the locres split marker proves applicability."""
    raw, revision, actual_digest, fallback = _source(
        LOCALIZATION_REPOSITORY, LOCALIZATION_PATH, LOCALIZATION_FALLBACK,
        fetch=fetch, revision=revision, digest=digest, cache=cache)
    parameters = re.findall(rb'0x[0-9a-fA-F]{64}', raw)
    check(len(parameters) == 1)
    if cache is not None:
        _cache_source(cache, revision, actual_digest, raw)
    return LocalizationCatalog(revision, actual_digest, parameters[0].decode('ascii').lower(), fallback)


def for_install(install, catalog):
    root = install / 'Client/WindowsNoEditor/HT/Content'
    archives = sorted(root.rglob('*.pak'), key=lambda path: path.stat().st_size)
    check(archives)
    for path in archives:
        with path.open('rb') as stream:
            def read(offset, size):
                stream.seek(offset)
                return stream.read(size)
            if value := catalog.verified_key(read, path.stat().st_size):
                return value
    check(False)
