"""Original updater inventory URLs and bounded data-only binary readers.

The schema comes from the original PaperHotUpdateMgr and native serializers.
Map meanings that are not yet independently bound remain opaque. This module
neither downloads packages nor classifies missing audio. Callers own official
transport/generation verification; a supplied source SHA-256 binds bytes to that
receipt and is not claimed to be a separately published publisher checksum.
"""
from dataclasses import dataclass, field
import hashlib
import re
import struct
from urllib.parse import urlsplit


MAX_PACKED = 128 * 1024**2
MAX_EXPANDED = 512 * 1024**2
MAGIC = 0x20240418
RESOURCE_HOST = 'x6oversea-client.infoldgames.com'
RESOURCE_HOSTS = (RESOURCE_HOST, 'x6oversea-client-backup.infoldgames.com')


def _require(condition):
    if not condition:
        raise ValueError('Could not validate the current official Infinity Nikki inventory data.')


@dataclass(frozen=True)
class InventorySource:
    role: str
    url: str
    version: str
    fast_patch: str


def build_version_urls(pointer: str) -> tuple[str, ...]:
    """Read the SDK's original semicolon-separated primary/backup pointers.

    Every candidate must be in the evidenced official Global host family and
    describe the identical path/generation. Selecting/fetching a candidate and
    checking its response are separate caller responsibilities.
    """
    _require(isinstance(pointer, str) and 0 < len(pointer) <= 8192)
    urls = tuple(pointer.split(';'))
    _require(1 <= len(urls) <= 8 and len(set(urls)) == len(urls))
    paths = set()
    for url in urls:
        parsed = urlsplit(url)
        _require(parsed.scheme == 'https' and parsed.netloc in RESOURCE_HOSTS and not parsed.query and not parsed.fragment and
                 re.fullmatch(r'/[A-Za-z0-9_-]{8,128}/Rel_[0-9]+(?:\.[0-9]+){1,3}/PaperHotUpdate/Protected/BuildVersion/Windows/BuildVersion_[0-9]+\.[0-9]+\.json', parsed.path))
        paths.add(parsed.path)
    _require(len(paths) == 1)
    return urls


def inventory_sources(build_url: str, build: dict) -> tuple[InventorySource, ...]:
    """Apply original URI templates to the current SDK's evidenced Global URL.

    Only the observed Windows source family is accepted. Platform/region aliases
    must be evidenced separately; Android can read platform-independent source
    data without pretending that a guessed Android manifest exists.
    """
    _require(isinstance(build_url, str) and isinstance(build, dict))
    parsed = urlsplit(build_url)
    _require(parsed.scheme == 'https' and parsed.netloc in RESOURCE_HOSTS and not parsed.query and not parsed.fragment)
    match = re.fullmatch(r'(/[A-Za-z0-9_-]{8,128}/Rel_[0-9]+(?:\.[0-9]+){1,3}/PaperHotUpdate/Protected)/BuildVersion/(Windows)/BuildVersion_([0-9]+)\.([0-9]+)\.json', parsed.path)
    _require(match is not None)
    root, platform, version, patch = match.groups()
    _require(all(isinstance(build.get(key), str) and re.fullmatch('[0-9]{1,12}', build[key])
                 for key in ('DefaultVersion', 'FastPatchVersion')) and
             build['DefaultVersion'] == version and build['FastPatchVersion'] == patch)
    prefix = f'https://{parsed.netloc}{root}/HashFiles/{platform}/{version}/'
    return tuple(InventorySource(role, prefix + name, version, patch) for role, name in (
        ('base-json', f'PaperHashFiles_{version}.json'),
        ('base-binary', f'PaperHashFiles_{version}.bin'),
        ('hotfix-binary', f'PaperHashFiles_{version}.{patch}.bin'),
        ('file-pak-map', f'PaperFilePakHashMap_{version}.bin')))


@dataclass(frozen=True)
class InventoryEnvelope:
    packed_bytes: int
    expanded_bytes: int
    header_bytes: int = 9


def inventory_envelope(prefix: bytes, total: int) -> InventoryEnvelope:
    """Quote the complete compressed metadata and declared temporary decode size."""
    _require(isinstance(prefix, bytes) and 9 <= len(prefix) <= 65536 and
             type(total) is int and len(prefix) <= total <= MAX_PACKED)
    magic, flag, expanded = struct.unpack_from('<IBI', prefix)
    _require(magic == MAGIC and flag == 1 and 0 < expanded <= MAX_EXPANDED and total > 9)
    return InventoryEnvelope(total, expanded)


class _Reader:
    def __init__(self, raw):
        self.raw, self.at = raw, 0

    def take(self, size):
        _require(type(size) is int and 0 <= size <= len(self.raw) - self.at)
        value = self.raw[self.at:self.at + size]
        self.at += size
        return value

    def number(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self, minimum_bytes):
        count = self.number()
        _require(0 <= count <= min(4_000_000, (len(self.raw) - self.at) // minimum_bytes))
        return count

    def string(self):
        count = self.number()
        if not count:
            return ''
        width = 1 if count > 0 else 2
        _require(abs(count) * width <= 8192)
        raw = self.take(abs(count) * width)
        _require(raw[-width:] == bytes(width))
        value = raw[:-width].decode('utf-8' if width == 1 else 'utf-16-le')
        _require('\0' not in value)
        return value

    def mapping(self, binary_key):
        values, seen = [], set()
        for _ in range(self.count(16 if binary_key else 8)):
            key = self.take(12) if binary_key else self.string()
            value = self.string()
            _require(key not in seen)
            seen.add(key)
            values.append((key, value))
        return tuple(values)


@dataclass(frozen=True)
class PakInventoryRecord:
    name: str
    digest_text: str
    mount: str
    binary_map_a: tuple[tuple[bytes, str], ...] = field(repr=False)
    text_map: tuple[tuple[str, str], ...] = field(repr=False)
    binary_map_b: tuple[tuple[bytes, str], ...] = field(repr=False)


def parse_inventory_payload(raw: bytes) -> tuple[PakInventoryRecord, ...]:
    """Read the original native array/three-string/three-map schema to exact EOF.

    Opaque 12-byte keys and string values are preserved, including empty values.
    No removal, file-ID, audio-language or silence meaning is inferred here.
    """
    _require(isinstance(raw, bytes) and 4 <= len(raw) <= MAX_EXPANDED)
    reader, records, names = _Reader(raw), [], set()
    try:
        for _ in range(reader.count(24)):
            name, digest, mount = reader.string(), reader.string(), reader.string()
            _require(re.fullmatch(r'[A-Za-z0-9_.-]+\.pak', name) and
                     re.fullmatch('[0-9a-fA-F]{32}', digest) and name.casefold() not in names)
            names.add(name.casefold())
            records.append(PakInventoryRecord(name, digest, mount, reader.mapping(True),
                                               reader.mapping(False), reader.mapping(True)))
        _require(reader.at == len(raw))
        return tuple(records)
    except (UnicodeError, struct.error) as error:
        raise ValueError('Could not read the current official Infinity Nikki inventory strings or fields.') from error


def decode_inventory(raw: bytes, *, expected_sha256: str, decompress) -> tuple[PakInventoryRecord, ...]:
    """Decode verified metadata using the caller's portable pinned Oodle reader.

    The nine-byte envelope and output bound are established before invoking the
    decoder. No client code, Lua VM, native game library or dynamic extraction
    tool is selected by this function.
    """
    _require(isinstance(raw, bytes) and len(raw) <= MAX_PACKED and isinstance(expected_sha256, str) and
             re.fullmatch('[0-9a-f]{64}', expected_sha256) and
             hashlib.sha256(raw).hexdigest() == expected_sha256 and callable(decompress))
    plan = inventory_envelope(raw[:9], len(raw))
    decoded = decompress(raw[plan.header_bytes:], plan.expanded_bytes)
    _require(isinstance(decoded, bytes) and len(decoded) == plan.expanded_bytes)
    return parse_inventory_payload(decoded)
