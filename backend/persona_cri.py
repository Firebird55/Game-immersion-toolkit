"""Bounded, read-only CRI UTF/CPK archive primitives for Persona 5 Royal."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import struct

from .preparation_errors import PreparationFailure


def invalid(message='Unsupported or incomplete Persona 5 Royal archive.'):
    return PreparationFailure('persona5_format', message + ' Verify game files, update the toolkit, and prepare again.')


def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\0' in value:
        raise invalid('Invalid Persona archive path.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or value != path.as_posix():
        raise invalid('Invalid Persona archive path.')
    return value


def utf(data):
    """Decode typed CRI @UTF tables, including nested data columns."""
    if len(data) < 32 or data[:4] != b'@UTF':
        raise invalid('Invalid CRI table header.')
    size, rows_at, strings_at, blobs_at, _name, columns, stride, count = struct.unpack_from('>IIIIIHHI', data, 4)
    if rows_at >> 16 not in (0, 1):
        raise invalid('Unsupported CRI table version.')
    rows_at &= 0xffff
    end, rows_at, strings_at, blobs_at = size + 8, rows_at + 8, strings_at + 8, blobs_at + 8
    if not 32 <= rows_at <= strings_at <= blobs_at <= end <= len(data) or count > 1_000_000 or columns > 256 or rows_at + stride * count > strings_at:
        raise invalid('CRI table exceeds its container.')

    def string(offset):
        at = strings_at + offset
        stop = data.find(b'\0', at, blobs_at)
        if at < strings_at or stop < at or stop - at > 4096:
            raise invalid('Invalid CRI string.')
        try:
            return data[at:stop].decode('utf-8')
        except UnicodeDecodeError as error:
            raise invalid('Invalid CRI string encoding.') from error

    formats = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'Q', 7: 'q', 8: 'f', 9: 'd', 10: 'I', 11: 'II'}

    def value(kind, at, limit):
        if kind not in formats:
            raise invalid('Unsupported CRI column type.')
        fmt = '>' + formats[kind]
        length = struct.calcsize(fmt)
        if at < 0 or at + length > limit:
            raise invalid('CRI column exceeds its table.')
        values = struct.unpack_from(fmt, data, at)
        result = values[0]
        if kind == 10:
            result = string(result)
        elif kind == 11:
            offset, length_blob = values
            if blobs_at + offset + length_blob > end:
                raise invalid('CRI data exceeds its table.')
            result = data[blobs_at + offset:blobs_at + offset + length_blob]
        return result, at + length

    specs, cursor = [], 32
    for _ in range(columns):
        if cursor + 5 > rows_at:
            raise invalid()
        flag = data[cursor]
        name = string(struct.unpack_from('>I', data, cursor + 1)[0])
        cursor += 5
        storage, kind = flag & 0xf0, flag & 15
        if kind not in formats:
            raise invalid('Unsupported CRI column type.')
        constant = '' if kind == 10 else b'' if kind == 11 else 0
        if storage == 0x30:
            constant, cursor = value(kind, cursor, rows_at)
        elif storage not in (0x10, 0x50):
            raise invalid('Unsupported CRI column storage.')
        specs.append((name, storage, kind, constant))
    result = []
    for row in range(count):
        cursor, limit = rows_at + row * stride, rows_at + (row + 1) * stride
        record = {}
        for name, storage, kind, constant in specs:
            if name in record:
                raise invalid('Duplicate CRI column.')
            if storage == 0x50:
                constant, cursor = value(kind, cursor, limit)
            record[name] = constant
        if cursor != limit:
            raise invalid('Invalid CRI row stride.')
        result.append(record)
    return result


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    size: int
    extracted: int


class Cpk:
    def __init__(self, path):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        header = self._table(0, b'CPK ')
        if len(header) != 1:
            raise invalid()
        header = header[0]
        toc = header.get('TocOffset')
        content = header.get('ContentOffset')
        if type(toc) is not int or type(content) is not int:
            raise invalid('Persona archive has no named file table.')
        self.entries = {}
        for row in self._table(toc, b'TOC '):
            directory = row.get('DirName') or ''
            name = safe_name((directory + '/' if directory else '') + row['FileName'])
            offset, length, extracted = row['FileOffset'], row['FileSize'], row['ExtractSize']
            if any(type(value) is not int or value < 0 for value in (offset, length, extracted)):
                raise invalid()
            offset += min(toc, content)
            if offset + length > self.size or name.casefold() in self.entries:
                raise invalid('Persona archive file exceeds bounds or is duplicated.')
            self.entries[name.casefold()] = Entry(name, offset, length, extracted)

    def read_at(self, offset, size, limit=128 * 1024 * 1024):
        if offset < 0 or size < 0 or size > limit or offset + size > self.size:
            raise invalid('Persona archive read exceeds bounds.')
        with self.path.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(size)
        if len(data) != size:
            raise invalid('Persona archive was truncated during reading.')
        return data

    def _table(self, offset, magic):
        header = self.read_at(offset, 16)
        if header[:4] != magic:
            raise invalid('Invalid Persona CRI packet.')
        size = struct.unpack_from('<Q', header, 8)[0]
        data = self.read_at(offset + 16, size, 64 * 1024 * 1024)
        if not data.startswith(b'@UTF'):
            key, decoded = 0x655f, bytearray(data)
            for i in range(len(decoded)):
                decoded[i] ^= key & 255
                key = key * 0x4115 & 0xffffffff
            data = bytes(decoded)
        return utf(data)

    def read(self, name, limit=128 * 1024 * 1024):
        safe_name(name)
        entry = self.entries.get(name.casefold())
        if entry is None:
            raise invalid('Persona archive member is missing.')
        if entry.extracted > limit:
            raise invalid('Persona archive member is too large.')
        data = self.read_at(entry.offset, entry.size, limit)
        if data.startswith(b'CRILAYLA'):
            data = crilayla(data, limit)
        if len(data) != entry.extracted:
            raise invalid('Persona archive expanded size disagrees with its table.')
        return data


def crilayla(data, limit=128 * 1024 * 1024):
    if len(data) < 16 or data[:8] != b'CRILAYLA':
        raise invalid('Invalid CRI compression header.')
    size, header_offset = struct.unpack_from('<II', data, 8)
    if size + 256 > limit or 16 + header_offset + 256 != len(data):
        raise invalid('Invalid CRI compression bounds.')
    result = bytearray(size + 256)
    result[:256] = data[16 + header_offset:]
    at, bits, available, target = 16 + header_offset - 1, 0, 0, len(result) - 1

    def read_bits(count):
        nonlocal at, bits, available
        while available < count:
            if at < 16:
                raise invalid('Truncated CRI compressed stream.')
            bits = (bits << 8) | data[at]
            available += 8
            at -= 1
        available -= count
        value = (bits >> available) & ((1 << count) - 1)
        bits &= (1 << available) - 1
        return value

    while target >= 256:
        if not read_bits(1):
            result[target] = read_bits(8)
            target -= 1
            continue
        distance, length = read_bits(13) + 3, 3
        for width in (2, 3, 5, 8):
            extra = read_bits(width)
            length += extra
            if extra < (1 << width) - 1:
                break
        else:
            while True:
                extra = read_bits(8)
                length += extra
                if extra != 255:
                    break
        if target + distance >= len(result) or target - length + 1 < 256:
            raise invalid('Invalid CRI compression back-reference.')
        for _ in range(length):
            result[target] = result[target + distance]
            target -= 1
    return bytes(result)


def awb_entries(header, container_size):
    """AFS2 offsets are unaligned ends; each payload starts at aligned offset."""
    if len(header) < 16 or header[:4] != b'AFS2':
        raise invalid('Invalid Persona voice wavebank.')
    version, width, id_width, _reserved = header[4:8]
    count, alignment, key = struct.unpack_from('<IHH', header, 8)
    if version not in (1, 2) or width not in (2, 4, 8) or id_width not in (2, 4) or not 1 <= alignment <= 65536 or count > 100000 or key:
        raise invalid('Unsupported Persona wavebank layout.')
    needed = 16 + count * id_width + (count + 1) * width
    if needed > len(header):
        raise invalid('Truncated Persona wavebank directory.')
    ids = [int.from_bytes(header[16 + i * id_width:16 + (i + 1) * id_width], 'little') for i in range(count)]
    offset_at = 16 + count * id_width
    offsets = [int.from_bytes(header[offset_at + i * width:offset_at + (i + 1) * width], 'little') for i in range(count + 1)]
    if len(set(ids)) != count or offsets != sorted(offsets) or offsets[0] < needed or offsets[-1] > container_size:
        raise invalid('Invalid Persona wavebank offsets.')
    result = {}
    for index, identity in enumerate(ids):
        start = (offsets[index] + alignment - 1) // alignment * alignment
        end = offsets[index + 1]
        if start >= end:
            raise invalid('Empty Persona voice payload.')
        result[identity] = (start, end - start)
    return result


def read_acb(data):
    rows = utf(data)
    if len(rows) != 1:
        raise invalid('Invalid Persona cue bank.')
    root = rows[0]
    tables = {key: utf(value) for key, value in root.items() if isinstance(value, bytes) and value.startswith(b'@UTF')}

    def table(name, index):
        values = tables.get(name, [])
        if type(index) is not int or not 0 <= index < len(values):
            raise invalid('Persona audio cue pointer exceeds bounds.')
        return values[index]

    def resolve(kind, index, depth=0):
        if depth > 4:
            return None
        if kind == 1:
            wave = table('WaveformTable', index)
            if wave.get('Streaming') not in (0, 1) or wave.get('EncodeType') not in (0, 2) or wave.get('StreamAwbPortNo', 0) != 0:
                return None
            return {'wave': index, 'id': wave['StreamAwbId' if wave['Streaming'] else 'MemoryAwbId'],
                    'streamed': bool(wave['Streaming']), 'samples': wave['NumSamples'],
                    'rate': wave['SamplingRate'], 'channels': wave['NumChannels']}
        if kind == 2:
            synth = table('SynthTable', index)
            refs = synth.get('ReferenceItems', b'')
            if len(refs) != 4 or synth.get('NumActionTracks', 0) or synth.get('Type') != 0:
                return None
            return resolve(*struct.unpack('>HH', refs), depth + 1)
        if kind == 3:
            sequence = table('SequenceTable', index)
            tracks = sequence.get('TrackIndex', b'')
            if sequence.get('NumTracks') != 1 or len(tracks) != 2 or sequence.get('NumActionTracks', 0):
                return None
            track = table('TrackTable', struct.unpack('>H', tracks)[0])
            event = table('TrackEventTable', track['EventIndex']).get('Command', b'')
            # A single note-on (2000) followed by end (0). Other timelines,
            # delayed/repeated notes and random playlists remain unresolved.
            if len(event) != 10 or event[:3] != b'\x07\xd0\x04' or event[7:] != b'\0\0\0':
                return None
            return resolve(*struct.unpack_from('>HH', event, 3), depth + 1)
        return None

    bindings, unresolved = {}, set()
    for cue in tables.get('CueTable', []):
        identity = cue['CueId']
        if identity in bindings or identity in unresolved:
            raise invalid('Duplicate Persona audio cue identity.')
        ref = resolve(cue['ReferenceType'], cue['ReferenceIndex'])
        if ref:
            bindings[identity] = {**ref, 'duration_ms': cue.get('Length')}
        else:
            unresolved.add(identity)
    headers = tables.get('StreamAwbAfs2Header', [])
    return {'bindings': bindings, 'unresolved': unresolved, 'embedded': root.get('AwbFile') or b'',
            'stream_header': headers[0]['Header'] if len(headers) == 1 else None, 'name': root.get('Name')}
