"""Read character Wwise banks without loading or modifying the game."""
from __future__ import annotations

import struct
from pathlib import Path

from .voice_assets import VoiceEntry


def package_table(path: Path, section: int) -> dict[int, VoiceEntry]:
    if section not in (2, 3):
        raise ValueError('Expected bank or streamed-sound section')
    total = path.stat().st_size
    with path.open('rb') as stream:
        header = stream.read(28)
        if len(header) != 28 or header[:4] != b'AKPK':
            raise ValueError('Not a PCK')
        header_size, flag, lang, banks, sounds, _external = struct.unpack_from('<6I', header, 4)
        if flag != 1:
            raise ValueError('Unsupported PCK endianness')
        start = 28 if lang + banks + sounds + 16 < header_size else 24
        length = banks if section == 2 else sounds
        offset = start + lang + (banks if section == 3 else 0)
        if not length:
            return {}
        if length < 4 or length > 32_000_000 or offset + length > total:
            raise ValueError('Invalid PCK table')
        stream.seek(offset)
        data = stream.read(length)
    count = struct.unpack_from('<I', data)[0]
    if not count:
        return {}
    width = (length - 4) // count
    if width not in (20, 24) or count * width + 4 != length:
        raise ValueError('Unsupported PCK entries')
    entries = {}
    for index in range(count):
        entry_id, block, size, position, _lang = struct.unpack_from('<IIQII' if width == 24 else '<5I', data, 4 + index * width)
        position *= block or 1
        if position + size > total:
            raise ValueError('PCK entry exceeds package')
        entries[entry_id] = VoiceEntry(path, position, size, entry_id)
    return entries


def bank_media(bank: VoiceEntry) -> dict[int, VoiceEntry]:
    """DIDX offsets point into DATA. Read chunk headers plus the small DIDX only."""
    data_start, data_size, index = 0, 0, b''
    with bank.package.open('rb') as stream:
        position, end = bank.offset, bank.offset + bank.size
        while position + 8 <= end:
            stream.seek(position)
            kind, size = struct.unpack('<4sI', stream.read(8))
            if position + 8 + size > end:
                raise ValueError('Bank chunk exceeds bank')
            if kind == b'DIDX':
                index = stream.read(size)
            elif kind == b'DATA':
                data_start, data_size = position + 8, size
            position += size + 8
    if len(index) % 12:
        raise ValueError('Invalid DIDX')
    entries = {}
    for media_id, offset, size in struct.iter_unpack('<3I', index):
        if not data_start or offset + size > data_size:
            raise ValueError('Media exceeds bank DATA')
        entries[media_id] = VoiceEntry(bank.package, data_start + offset, size, media_id)
    return entries
