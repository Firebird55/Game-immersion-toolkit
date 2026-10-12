"""Read-only Witcher 3 localization and original Mandarin speech containers.

IDs are joined across RTSW string tables and CPSW speech tables. Format markers
are public file-format constants, not account credentials or stored AES keys.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from .bilingual import contains_han
from .textmaps import display_text

# RTSW/CPSW language format markers (English, legacy Traditional Chinese, and
# unmasked formats including next-gen Simplified Chinese).
_FORMAT_MAGIC = {0x43975139: 0x79321793, 0x18632176: 0x16875467, 0: 0}


def _read(stream, size):
    value = stream.read(size)
    if len(value) != size:
        raise ValueError("Witcher language file is incomplete")
    return value


def _bit6(stream):
    value, shift = 0, 0
    for index in range(6):
        byte = _read(stream, 1)[0]
        if byte == 128 and index == 0:
            return 0
        bits = 7 if byte > 127 else 6
        mask = 127 if byte > 127 else 63 if index == 0 and byte > 63 else 255
        value |= (byte & mask) << shift
        shift += bits
        if byte < 64 or (index >= 2 and byte < 128):
            if value > 0xFFFFFFFF:
                break
            return value
    raise ValueError("Invalid Witcher language table count")


def _header(stream, signature):
    if _read(stream, 4) != signature:
        raise ValueError("Unsupported Witcher language file format")
    version, first = struct.unpack("<IH", _read(stream, 6))
    if version not in (162, 163, 164):
        raise ValueError("Unsupported Witcher language file version")
    return version, first


def _magic(first, last):
    marker = (first << 16) | last
    if marker not in _FORMAT_MAGIC:
        raise ValueError("Unsupported or incomplete Witcher language encoding")
    return _FORMAT_MAGIC[marker]


def read_strings(path: Path) -> dict[int, str]:
    with path.open("rb") as stream:
        version, first = _header(stream, b"RTSW")
        stream.seek(-2, 2)
        magic = _magic(first, struct.unpack("<H", _read(stream, 2))[0])
        stream.seek(10)
        count = _bit6(stream)
        if count > 2_000_000:
            raise ValueError("Witcher localization table is too large or incomplete")
        entries = [struct.unpack("<III", _read(stream, 12)) for _ in range(count)]
        keys = _bit6(stream)
        if keys > 2_000_000:
            raise ValueError("Witcher localization key table is invalid")
        _read(stream, keys * 8)
        characters = _bit6(stream)
        start = stream.tell()
        size = path.stat().st_size
        unit = 1 if version == 164 else 2
        # Some mod-generated tables declare the older version but retain the
        # UTF-8 buffer layout. Its exact boundary identifies that representation.
        if unit == 2 and start + characters == size - 2:
            unit = 1
        if start + characters * unit > size - 2:
            raise ValueError("Witcher localization string buffer is incomplete")
        result = {}
        for masked_id, offset, length in entries:
            if length > 100_000 or offset + length > characters:
                raise ValueError("Invalid Witcher localized string bounds")
            stream.seek(start + offset * unit)
            stored = _read(stream, length * unit)
            units = list(stored) if unit == 1 else list(struct.unpack(f"<{length}H", stored))
            rolling = (magic >> 8) & 0xFFFF
            for index, character in enumerate(units):
                units[index] = character ^ (((length + 1) * rolling) & (0xFF if unit == 1 else 0xFFFF))
                rolling = ((rolling << 1) | (rolling >> 15)) & 0xFFFF
            text = bytes(units).decode("utf-8") if unit == 1 else struct.pack(f"<{length}H", *units).decode("utf-16-le")
            if "\0" in text:
                raise ValueError("Witcher localized text is incomplete or invalid")
            result[masked_id ^ magic] = text
        return result


def read_speech(path: Path) -> dict[int, dict]:
    with path.open("rb") as stream:
        _version, first = _header(stream, b"CPSW")
        count = _bit6(stream)
        if count > 2_000_000:
            raise ValueError("Witcher speech table is invalid")
        entries = [struct.unpack("<10I", _read(stream, 40)) for _ in range(count)]
        # CPSW keeps the lower language marker immediately after its table,
        # before the speech payload; it is not the last two bytes of the file.
        magic = _magic(first, struct.unpack("<H", _read(stream, 2))[0])
        size = path.stat().st_size
        result = {}
        for values in entries:
            # Audio offsets are 64-bit: next-gen cnpc can exceed four GiB.
            offset = values[2] | (values[3] << 32)
            stored_size = values[4]
            if not offset or stored_size < 12:
                continue
            position = offset + 4
            if position + 12 > size:
                raise ValueError("Witcher original speech entry falls outside its container")
            stream.seek(position)
            header = _read(stream, 12)
            if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                raise ValueError("Witcher original speech data is incomplete or unsupported")
            length = struct.unpack_from("<I", header, 4)[0] + 8
            if length < 44 or length > stored_size or position + length > size:
                raise ValueError("Witcher original speech length is invalid")
            identity = values[0] ^ magic
            result[identity] = {"offset": position, "size": length} if identity not in result else {"ambiguous": True}
        return result


def archive_sources(install: Path) -> list[Path]:
    names = {"en.w3strings", "cn.w3strings", "zh.w3strings", "cnpc.w3speech", "zhpc.w3speech"}
    roots = [install / "content", install / "dlc"]
    return sorted({path for root in roots if root.is_dir() for path in root.rglob("*")
                   if path.is_file() and path.name.lower() in names}, key=lambda p: p.relative_to(install).as_posix())


def fingerprint(install: Path) -> str:
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in archive_sources(install)]
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def primary_text(value: str, chinese: bool) -> str:
    # The linked Dual Subtitles mod retains the base-language text first and
    # appends a translation using ' ~ ' or '<br>~ '. Read that primary text
    # directly, rather than relying on potentially stale backup files.
    parts = re.split(r"(?:<br\s*/?>\s*|\s+)~\s*", value, flags=re.IGNORECASE)
    if len(parts) > 1 and len({contains_han(part) for part in parts if part.strip()}) > 1:
        same_language = [part for part in parts if part.strip() and contains_han(part) == chinese]
        if len(same_language) != 1:
            return ""  # Ambiguous multi-language content is never guessed.
        value = same_language[0]
    return display_text(value)


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    stamp = fingerprint(install)
    english, chinese, voices = {}, {}, {}
    paths = archive_sources(install)
    # Next-gen Mandarin uses cn; zh is the legacy Traditional Chinese text.
    # Do not substitute a different speech language when cn is unavailable.
    for path in paths:
        if path.name.lower() == "en.w3strings":
            progress("Reading installed Witcher English subtitles")
            english.update({key: primary_text(value, False) for key, value in read_strings(path).items()})
        elif path.name.lower() == "cn.w3strings":
            progress("Reading installed Witcher Chinese subtitles")
            chinese.update({key: primary_text(value, True) for key, value in read_strings(path).items()})
        elif path.name.lower() == "cnpc.w3speech":
            progress("Checking exact Witcher Mandarin speech IDs")
            for key, audio in read_speech(path).items():
                previous = voices.get(key)
                reference = {"archive": path.relative_to(install).as_posix(), **audio}
                # Multiple original performances for one ID are unsafe to pick.
                voices[key] = reference if previous is None else {"ambiguous": True}
    records = [{"text_id": f"witcher3:{key}", "english": value, "chinese": chinese[key],
                "audio": voices[key] if key in voices and not voices[key].get("ambiguous") else None}
               for key, value in english.items() if value and chinese.get(key)]
    if not records:
        raise ValueError("No English/Chinese Witcher subtitle pairs found; wait for Steam to finish downloading")
    if fingerprint(install) != stamp:
        raise ValueError("Witcher files changed while indexing; retry after Steam finishes")
    mapped = sum(bool(record["audio"]) for record in records)
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": records,
        "message": f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices" if mapped else
                   "Witcher subtitles indexed; install the official Chinese speech pack in Steam"}


def extract_voice(install: Path, audio: dict, _executable: Path, _destination: Path) -> bytes:
    path = (install / audio["archive"]).resolve()
    if not path.is_relative_to(install.resolve()) or path.name.casefold() != "cnpc.w3speech":
        raise ValueError("Invalid original Witcher Mandarin speech reference")
    offset, size = int(audio["offset"]), int(audio["size"])
    if offset < 0 or size < 44 or size > 100 * 1024 * 1024 or offset + size > path.stat().st_size:
        raise ValueError("Invalid original Witcher speech bounds")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = _read(stream, size)
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Original Witcher speech is unavailable or changed")
    return data


def extract_voices(install: Path, audios: list[dict], _executable: Path, _destination: Path) -> list[bytes]:
    from contextlib import ExitStack
    streams, result = {}, []
    with ExitStack() as stack:
        for audio in audios:
            path = (install / audio['archive']).resolve()
            if not path.is_relative_to(install.resolve()) or path.name.casefold() != 'cnpc.w3speech':
                raise ValueError('Invalid original Witcher Mandarin speech reference')
            offset, size = int(audio['offset']), int(audio['size'])
            if offset < 0 or not 44 <= size <= 100 * 1024 * 1024 or offset + size > path.stat().st_size:
                raise ValueError('Invalid original Witcher speech bounds')
            if path not in streams:
                streams[path] = stack.enter_context(path.open('rb'))
            stream = streams[path]; stream.seek(offset); data = _read(stream, size)
            if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
                raise ValueError('Original Witcher speech is unavailable or changed')
            result.append(data)
    return result
