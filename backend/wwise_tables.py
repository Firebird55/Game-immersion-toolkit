"""Read original Wwise package and bank tables from bounded byte sources."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

MANDARIN = "chinese(prc)"


def wwise_short_id(name: str) -> int:
    value = 2166136261
    for byte in name.lower().encode("utf-8"):
        value = ((value * 16777619) & 0xffffffff) ^ byte
    return value


def voice_hash(path: str) -> int:
    value = 0xCBF29CE484222325
    for byte in path.lower().encode("utf-8"):
        value = ((value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ byte
    return value


@dataclass(frozen=True)
class PackageEntry:
    offset: int
    size: int


@dataclass(frozen=True)
class BankSource:
    media_id: int
    stream_type: int
    memory_size: int


@dataclass(frozen=True)
class VoiceEntry:
    package: Path
    offset: int
    size: int
    file_id: int

    def read(self) -> bytes:
        with self.package.open("rb") as stream:
            stream.seek(self.offset)
            data = stream.read(self.size)
        if len(data) != self.size or data[:4] != b"RIFF":
            raise ValueError("Voice asset missing, changed, or not a RIFF WEM")
        return data


def read_external_table(package: Path) -> list[VoiceEntry]:
    """Read the small PCK table, never the complete audio package."""
    size = package.stat().st_size
    with package.open("rb") as stream:
        def read(offset, length):
            stream.seek(offset)
            return stream.read(length)
        return external_table(package, size, read)


def external_table(package, size, read):
    header = read(0, 28)
    if len(header) < 28 or header[:4] != b"AKPK":
        raise ValueError("Not a Wwise PCK")
    header_size, flag, languages, banks, sounds, externals = struct.unpack_from("<6I", header, 4)
    if flag != 1 or not 16 <= header_size <= min(size, 32 * 1024 * 1024):
        raise ValueError("Unsupported PCK header")
    if languages + banks + sounds + 16 >= header_size:
        return []
    offset = 28 + languages + banks + sounds
    if not 4 <= externals <= 32 * 1024 * 1024 or offset + externals > min(size, header_size + 8):
        raise ValueError("Invalid external table bounds")
    table = read(offset, externals)
    if len(table) != externals:
        raise ValueError("Truncated external table")
    count = struct.unpack_from("<I", table)[0]
    if count == 0:
        return []
    if externals != 4 + count * 24:
        raise ValueError("Unsupported external entry layout")
    entries = []
    for file_id, block, length, position, _language in struct.iter_unpack("<Q4I", table[4:]):
        position *= block or 1
        if not 0 < length <= 64 * 1024 * 1024 or position < header_size or position + length > size:
            raise ValueError("External voice outside package")
        entries.append(VoiceEntry(package, position, length, file_id))
    return entries


def package_tables(path: Path) -> tuple[dict[int, str], dict[tuple[int, int], PackageEntry], dict[tuple[int, int], PackageEntry]]:
    total = path.stat().st_size
    with path.open("rb") as stream:
        def read(offset, length):
            stream.seek(offset)
            return stream.read(length)
        return package_tables_from_reader(total, read)


def package_tables_from_reader(total, read):
    """The same PCK metadata contract over an authenticated publisher reader."""
    header = read(0, 28)
    if len(header) != 28 or header[:4] != b"AKPK":
        raise ValueError("Invalid Honkai audio package")
    size, endian, language_size, bank_size, sound_size, external_size = struct.unpack_from("<6I", header, 4)
    if endian != 1 or size != 20 + language_size + bank_size + sound_size + external_size or not 20 <= size <= min(total - 8, 32 * 1024 * 1024):
        raise ValueError("Unsupported Honkai package table layout")
    raw = read(28, language_size + bank_size + sound_size + external_size)
    if len(raw) != language_size + bank_size + sound_size + external_size or language_size < 4:
        raise ValueError("Truncated Honkai package tables")
    language_raw = raw[:language_size]
    count = struct.unpack_from("<I", language_raw)[0]
    if 4 + count * 8 > language_size:
        raise ValueError("Invalid audio language table")
    languages = {}
    for i in range(count):
        offset, language_id = struct.unpack_from("<II", language_raw, 4 + i * 8)
        if offset < 4 + count * 8 or offset >= language_size or offset % 2:
            raise ValueError("Invalid audio language name")
        end = offset
        while end + 2 <= language_size and language_raw[end:end + 2] != b"\0\0":
            end += 2
        if end + 2 > language_size:
            raise ValueError("Unterminated audio language name")
        languages[language_id] = language_raw[offset:end].decode("utf-16-le").lower()

    def table(start: int, length: int) -> dict:
        data = raw[start:start + length]
        if len(data) < 4:
            raise ValueError("Missing audio table")
        entries = struct.unpack_from("<I", data)[0]
        if length != 4 + entries * 20:
            raise ValueError("Unsupported Honkai audio entries")
        result = {}
        for entry_id, block, length, position, language in struct.iter_unpack("<5I", data[4:]):
            position *= block or 1
            if language not in languages or length <= 0 or position < size + 8 or position + length > total:
                raise ValueError("Honkai audio entry exceeds package bounds")
            key = (entry_id, language)
            if key in result:
                raise ValueError("Duplicate Honkai audio entry")
            result[key] = PackageEntry(position, length)
        return result
    return languages, table(language_size, bank_size), table(language_size + bank_size, sound_size)


def read_entry(path: Path, entry: PackageEntry) -> bytes:
    if not 0 < entry.size <= 64 * 1024 * 1024 or entry.offset < 28 or entry.offset + entry.size > path.stat().st_size:
        raise ValueError("Original voice entry is outside its package")
    with path.open("rb") as stream:
        stream.seek(entry.offset)
        data = stream.read(entry.size)
    if len(data) != entry.size:
        raise ValueError("Original audio package changed while reading")
    return data


def bank_sources(data: bytes, bank_id: int, *, language: str = MANDARIN) -> tuple[dict[int, int], dict[int, PackageEntry]]:
    """Wwise 135: accept one Play action targeting one language-specific sound.

    Reject switches, random containers, silence generators and multiple actions.
    IDs come from serialized event/action/source fields, never audio ordinals.
    """
    return bank_sources_from_reader(len(data), lambda start, size: data[start:start + size], bank_id, language=language)


def bank_metadata_from_reader(total, read, bank_id: int, *, language: str = MANDARIN):
    """Parse the same bank metadata without fetching its embedded DATA payload."""
    header = read(0, 20) if total >= 20 else b''
    if len(header) != 20 or header[:4] != b"BKHD" or struct.unpack_from("<3I", header, 8) != (135, bank_id, wwise_short_id(language)):
        raise ValueError("Unsupported Honkai Chinese voice bank")
    objects, media = {}, {}
    position, didx, data_start, data_size = 0, b"", 0, 0
    while position + 8 <= total:
        chunk = read(position, 8)
        if len(chunk) != 8:
            raise ValueError("Truncated Honkai bank header")
        kind, size = struct.unpack("<4sI", chunk)
        end = position + 8 + size
        if end > total:
            raise ValueError("Truncated Honkai bank")
        body = read(position + 8, size) if kind in (b'HIRC', b'DIDX') and size else b''
        if kind in (b'HIRC', b'DIDX') and len(body) != size:
            raise ValueError("Truncated Honkai bank metadata")
        if kind == b"HIRC":
            if len(body) < 4:
                raise ValueError("Missing Honkai bank objects")
            pos = 4
            for _ in range(struct.unpack_from("<I", body)[0]):
                if pos + 5 > len(body):
                    raise ValueError("Truncated Honkai bank object")
                obj_type, length = struct.unpack_from("<BI", body, pos)
                payload = body[pos + 5:pos + 5 + length]
                if len(payload) != length or length < 4:
                    raise ValueError("Invalid Honkai bank object size")
                oid = struct.unpack_from("<I", payload)[0]
                if oid in objects:
                    raise ValueError("Duplicate Honkai bank object")
                objects[oid] = (obj_type, payload)
                pos += 5 + length
            if pos != len(body):
                raise ValueError("Invalid Honkai hierarchy bounds")
        elif kind == b"DIDX":
            didx = body
        elif kind == b"DATA":
            data_start, data_size = position + 8, size
        position = end
    if position != total or len(didx) % 12:
        raise ValueError("Invalid Honkai bank chunk bounds")
    for media_id, offset, size in struct.iter_unpack("<3I", didx):
        if not data_start or not size or offset + size > data_size:
            raise ValueError("Honkai media exceeds its bank")
        media[media_id] = PackageEntry(data_start + offset, size)
    return objects, media


def bank_sources_from_reader(total, read, bank_id: int, *, language: str = MANDARIN, detailed=False):
    objects, media = bank_metadata_from_reader(total, read, bank_id, language=language)
    events = {}
    for event_id, (obj_type, payload) in objects.items():
        if obj_type != 4 or len(payload) != 9 or payload[4] != 1:
            continue
        action_type, action = objects.get(struct.unpack_from("<I", payload, 5)[0], (0, b""))
        if action_type != 3 or len(action) < 10 or struct.unpack_from("<H", action, 4)[0] != 0x0403:
            continue
        sound_type, sound = objects.get(struct.unpack_from("<I", action, 6)[0], (0, b""))
        if sound_type != 2 or len(sound) < 18 or struct.unpack_from("<I", sound, 4)[0] & 0xf != 1 or not sound[17] & 1:
            continue
        source = BankSource(struct.unpack_from('<I', sound, 9)[0], sound[8], struct.unpack_from('<I', sound, 13)[0])
        events[event_id] = source if detailed else source.media_id
    return events, media
