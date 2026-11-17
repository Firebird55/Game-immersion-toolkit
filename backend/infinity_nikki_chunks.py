"""Original Global BuildPatch JSON ownership and verified fixed-window chunks.

The current publisher manifest and original native path consumer establish this
feature-13/ChunksV3 source family. The source transport/generation receipt stays
external. Manifest SHA-1 fields are authored checksums; the supplied SHA-256 is
only a caller-bound complete-response identity, not a publisher signature.
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
import struct
from urllib.parse import urlsplit
import zlib

from .infinity_nikki_inventory import RESOURCE_HOSTS, inventory_sources


WINDOW = 1024**2
MAX_MANIFEST = 64 * WINDOW
MAX_CHUNKS = 500_000


def _check(value):
    if not value:
        raise ValueError('Could not verify the current official Infinity Nikki chunk ownership or data.')


def manifest_sources(build_url: str, build: dict) -> tuple[str, str]:
    """Use the original updater's base and FastPatch templates, without probes.

    A source can be absent. In particular, an absent optional FastPatch manifest
    does not prove that all patch sources or the normal update format changed.
    """
    source = inventory_sources(build_url, build)[0]
    root = source.url.split('/HashFiles/Windows/')[0]
    prefix = f'{root}/HttpChunkInstall/Windows/{source.version}/'
    return (prefix + 'CloudDir/PaperHttpChunkInstall.manifest',
            prefix + f'CloudFastPatchDir/{source.fast_patch}/PaperHttpChunkInstall.manifest')


def _source(url, version):
    _check(isinstance(url, str) and isinstance(version, str))
    parsed = urlsplit(url)
    _check(parsed.scheme == 'https' and parsed.netloc in RESOURCE_HOSTS and not parsed.query and not parsed.fragment)
    match = re.fullmatch(r'/[A-Za-z0-9_-]{8,128}/Rel_[0-9]+(?:\.[0-9]+){1,3}/PaperHotUpdate/Protected/'
                         r'HttpChunkInstall/Windows/([0-9]{1,12})/(CloudDir|CloudFastPatchDir/[0-9]{1,12})/'
                         r'PaperHttpChunkInstall\.manifest', parsed.path)
    _check(match is not None and match[1] == version)
    return url.rsplit('/', 1)[0]


def _blob(value, size):
    _check(isinstance(value, str) and len(value) == size * 3 and re.fullmatch('[0-9]+', value))
    values = [int(value[i:i + 3]) for i in range(0, len(value), 3)]
    _check(all(n <= 255 for n in values))
    return bytes(values)


def _number(value, size):
    return int.from_bytes(_blob(value, size), 'little')


def _guid(value):
    _check(isinstance(value, str) and re.fullmatch('[0-9A-F]{32}', value))
    return value


def _unique(items):
    result = {}
    for key, value in items:
        _check(key not in result)
        result[key] = value
    return result


@dataclass(frozen=True)
class Chunk:
    guid: str
    rolling_hash: int
    sha1: bytes = field(repr=False)
    group: int
    packed_bytes: int
    url: str
    expanded_bytes: int = WINDOW


@dataclass(frozen=True)
class FilePart:
    guid: str
    offset: int
    size: int


@dataclass(frozen=True)
class ManifestFile:
    name: str
    sha1: bytes = field(repr=False)
    parts: tuple[FilePart, ...] = field(repr=False)

    @property
    def size(self):
        return sum(part.size for part in self.parts)


@dataclass(frozen=True)
class ChunkPlan:
    files: tuple[ManifestFile, ...]
    chunks: tuple[Chunk, ...]
    wire_bytes: int
    retained_file_bytes: int
    temporary_decoded_bytes: int
    shared_carrier_guids: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    version: str
    source_sha256: str
    metadata_bytes: int
    files: tuple[ManifestFile, ...] = field(repr=False)
    chunks: tuple[Chunk, ...] = field(repr=False)

    def plan(self, names):
        """Quote complete verified carrier bytes, including shared resources.

        No audio/text classification or patch priority is guessed from names.
        A caller must show required shared-carrier/bootstrap overhead explicitly.
        """
        _check(isinstance(names, (tuple, list)) and names and all(isinstance(name, str) for name in names) and
               len(set(names)) == len(names))
        by_name = {file.name: file for file in self.files}
        _check(all(isinstance(name, str) and name in by_name for name in names))
        selected = tuple(by_name[name] for name in names)
        wanted = {part.guid for file in selected for part in file.parts}
        chunks = tuple(chunk for chunk in self.chunks if chunk.guid in wanted)
        shared = {part.guid for file in self.files if file.name not in names for part in file.parts if part.guid in wanted}
        return ChunkPlan(selected, chunks, sum(c.packed_bytes for c in chunks), sum(f.size for f in selected),
                         max((c.expanded_bytes for c in chunks), default=0), tuple(sorted(shared)))


def parse_manifest(raw: bytes, *, expected_sha256: str, manifest_url: str, expected_version: str) -> Manifest:
    """Validate typed original metadata and bind every selected file to chunks."""
    _check(isinstance(raw, bytes) and 0 < len(raw) <= MAX_MANIFEST and isinstance(expected_sha256, str) and
           re.fullmatch('[0-9a-f]{64}', expected_sha256) and hashlib.sha256(raw).hexdigest() == expected_sha256)
    root = _source(manifest_url, expected_version)
    try:
        data = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: _check(False))
        _check(isinstance(data, dict) and _number(data['ManifestFileVersion'], 4) == 13 and
               data['bIsFileData'] is False and data['AppNameString'] == 'PaperHttpChunkInstall' and
               data['BuildVersionString'] == expected_version)
        hash_map, sha_map, group_map, size_map = (data[key] for key in
            ('ChunkHashList', 'ChunkShaList', 'DataGroupList', 'ChunkFilesizeList'))
        _check(all(isinstance(value, dict) for value in (hash_map, sha_map, group_map, size_map)) and
               0 < len(hash_map) <= MAX_CHUNKS and hash_map.keys() == sha_map.keys() == group_map.keys() == size_map.keys())
        chunks = []
        for guid in hash_map:
            _guid(guid)
            rolling, group, size = _number(hash_map[guid], 8), _number(group_map[guid], 1), _number(size_map[guid], 8)
            sha = sha_map[guid]
            _check(isinstance(sha, str) and re.fullmatch('[0-9A-Fa-f]{40}', sha) and group < 100 and 62 <= size <= 4 * WINDOW)
            url = f'{root}/ChunksV3/{group:02d}/{rolling:016X}_{guid}.chunk'
            chunks.append(Chunk(guid, rolling, bytes.fromhex(sha), group, size, url))
        rows = data['FileManifestList']
        _check(isinstance(rows, list) and 0 < len(rows) <= 100_000)
        files, names = [], set()
        for row in rows:
            _check(isinstance(row, dict))
            name, parts = row['Filename'], row['FileChunkParts']
            _check(isinstance(name, str) and re.fullmatch('[A-Za-z0-9_.-]{1,1024}', name) and
                   name not in ('.', '..') and name.casefold() not in names and
                   isinstance(parts, list) and 0 <= len(parts) <= 1_000_000)
            names.add(name.casefold())
            parsed = []
            for part in parts:
                _check(isinstance(part, dict))
                guid, offset, size = _guid(part['Guid']), _number(part['Offset'], 4), _number(part['Size'], 4)
                _check(guid in hash_map and 0 < size <= WINDOW and offset <= WINDOW - size)
                parsed.append(FilePart(guid, offset, size))
            files.append(ManifestFile(name, _blob(row['FileHash'], 20), tuple(parsed)))
        return Manifest(expected_version, expected_sha256, len(raw), tuple(files), tuple(chunks))
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, struct.error) as error:
        raise ValueError('Could not read the current official Infinity Nikki chunk manifest fields.') from error


def decode_chunk(raw: bytes, owner: Chunk) -> bytes:
    """Read the evidenced v2 header, bounded zlib and full authored data SHA-1.

    The rolling-hash descriptor must match metadata, but no computed rolling
    checksum is claimed. Full decoded SHA-1 is independently checked against the
    header and manifest. No key or game library is involved in chunk decoding.
    """
    _check(isinstance(owner, Chunk) and isinstance(raw, bytes) and len(raw) == owner.packed_bytes and
           62 <= len(raw) <= 4 * WINDOW and owner.expanded_bytes == WINDOW and len(owner.sha1) == 20)
    magic, version, header, size = struct.unpack_from('<4I', raw)
    guid = ''.join(f'{word:08X}' for word in struct.unpack_from('<4I', raw, 16))
    rolling, stored_as = struct.unpack_from('<QB', raw, 32)
    _check((magic, version, header) == (0xb1fe3aa2, 2, 62) and size == len(raw) - header and
           guid == owner.guid and rolling == owner.rolling_hash and stored_as in (0, 1) and
           raw[41:61] == owner.sha1 and raw[61] == 3)
    if stored_as:
        try:
            decoder = zlib.decompressobj()
            result = decoder.decompress(raw[header:], WINDOW + 1)
        except zlib.error as error:
            raise ValueError('The original Infinity Nikki chunk compression could not be verified.') from error
        _check(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
    else:
        result = raw[header:]
    _check(len(result) == WINDOW and hashlib.sha1(result).digest() == owner.sha1)
    return result


def read_file_range(file: ManifestFile, offset: int, size: int, get_verified_chunk) -> bytes:
    """Read a bounded selected interval from already verified immutable chunks.

    Caller chunk caches must use decode_chunk with this manifest's owner. This
    function's ranges do not imply verification of the whole file's SHA-1.
    """
    _check(isinstance(file, ManifestFile) and type(offset) is int and type(size) is int and
           0 <= size <= 64 * WINDOW and 0 <= offset <= file.size - size and callable(get_verified_chunk))
    result, start = [], 0
    for part in file.parts:
        lo, hi = max(offset, start), min(offset + size, start + part.size)
        if lo < hi:
            raw = get_verified_chunk(part.guid)
            _check(isinstance(raw, bytes) and len(raw) == WINDOW)
            result.append(raw[part.offset + lo - start:part.offset + hi - start])
        start += part.size
        if start >= offset + size:
            break
    value = b''.join(result)
    _check(len(value) == size)
    return value


def read_small_file(file: ManifestFile, get_verified_chunk) -> bytes:
    """Reconstruct one bounded bootstrap member and verify its manifest SHA-1."""
    _check(isinstance(file, ManifestFile) and file.size <= 64 * WINDOW and len(file.sha1) == 20)
    raw = read_file_range(file, 0, file.size, get_verified_chunk)
    _check(hashlib.sha1(raw).digest() == file.sha1)
    return raw
