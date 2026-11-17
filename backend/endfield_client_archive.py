"""Bounded, inert ZIP member reads from the launcher's original split artifacts.

The injected reader must bind every range to its declared artifact identity.
ZIP CRC is a transport/control gate, not a complete artifact hash or publisher
signature. A native member must separately pass its publisher signature gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct
from urllib.parse import urlsplit
import zlib

from .endfield_client_source import check

MAX_DIRECTORY = 8 * 1024**2
MAX_ENTRIES = 32768
MAX_MEMBER = 16 * 1024**2


@dataclass(frozen=True)
class Member:
    name: str
    offset: int
    compressed: int
    size: int
    crc32: int
    method: int
    flags: int


class Archive:
    """Logical concatenation, without downloading or copying whole ZIP parts."""

    def __init__(self, artifacts, read_part):
        check(isinstance(artifacts, list) and 1 <= len(artifacts) <= 256)
        self.artifacts, self.starts, self.total = artifacts, [], 0
        names = []
        for item in artifacts:
            check(isinstance(item, dict) and type(item.get('bytes')) is int and
                  0 < item['bytes'] <= 4 * 1024**3 and
                  isinstance(item.get('md5'), str) and re.fullmatch('[0-9a-f]{32}', item['md5']))
            parsed = urlsplit(item.get('url', ''))
            check(parsed.scheme == 'https' and parsed.hostname and not parsed.query and
                  not parsed.fragment and not parsed.username and not parsed.password)
            names.append(parsed.path)
            self.starts.append(self.total)
            self.total += item['bytes']
        if len(names) > 1:
            match = re.fullmatch(r'(.+\.zip)\.001', names[0])
            check(match and names == [f'{match[1]}.{n:03d}' for n in range(1, len(names) + 1)],
                  'Original split ZIP declarations are incomplete or reordered.')
        self.read_part = read_part
        self.directory = None
        self.directory_offset = None

    def read(self, offset, size):
        check(type(offset) is type(size) is int and 0 <= offset <= self.total and
              0 < size <= MAX_MEMBER + 65536 and size <= self.total - offset)
        result = []
        for number, (begin, item) in enumerate(zip(self.starts, self.artifacts)):
            low, high = max(offset, begin), min(offset + size, begin + item['bytes'])
            if low < high:
                raw = self.read_part(number, low - begin, high - low)
                check(isinstance(raw, bytes) and len(raw) == high - low,
                      'Original archive range length differs.')
                result.append(raw)
        check(sum(map(len, result)) == size)
        return b''.join(result)

    def tail(self):
        size = min(65557, self.total)
        raw = self.read(self.total - size, size)
        candidates = []
        for at in range(max(0, len(raw) - 65557), len(raw) - 21):
            if raw[at:at + 4] == b'PK\x05\x06':
                fields = struct.unpack_from('<4s4H2IH', raw, at)
                if at + 22 + fields[-1] == len(raw):
                    candidates.append((at, fields))
        check(len(candidates) == 1, 'Original ZIP has no unique terminal record.')
        at, row = candidates[0]
        check(row[1] == row[2] == 0 and row[3] == row[4], 'Multi-disk ZIP records are unsupported.')
        count, size, offset = row[4:7]
        limit = self.total - len(raw) + at
        if count == 0xffff or size == 0xffffffff or offset == 0xffffffff:
            check(at >= 20 and raw[at - 20:at - 16] == b'PK\x06\x07')
            _, disk, location, disks = struct.unpack_from('<4sIQI', raw, at - 20)
            check(disk == 0 and disks == 1)
            position = location - (self.total - len(raw))
            check(0 <= position <= at - 20 - 56,
                  'Original ZIP64 terminal record leaves its bounded tail.')
            record = struct.unpack_from('<4sQ2H2I4Q', raw, position)
            check(record[0] == b'PK\x06\x06' and 44 <= record[1] <= 4096 and
                  position + 12 + record[1] == at - 20 and record[4] == record[5] == 0 and
                  record[6] == record[7])
            count, size, offset = record[7:10]
            limit = location
        check(0 < count <= MAX_ENTRIES and 0 < size <= MAX_DIRECTORY and
              0 <= offset < limit and offset + size == limit,
              'Original central directory exceeds its declared bounds.')
        return {'offset': offset, 'bytes': size, 'entries': count}

    def members(self):
        if self.directory is not None:
            return self.directory
        plan = self.tail()
        raw = self.read(plan['offset'], plan['bytes'])
        result, intervals, at = {}, [], 0
        for _ in range(plan['entries']):
            check(at + 46 <= len(raw))
            row = struct.unpack_from('<4s6H3I5H2I', raw, at)
            check(row[0] == b'PK\x01\x02')
            flags, method, crc, compressed, size = row[3], row[4], row[7], row[8], row[9]
            name_size, extra_size, comment_size, disk, offset = row[10], row[11], row[12], row[13], row[16]
            end = at + 46 + name_size + extra_size + comment_size
            check(0 < name_size <= 1024 and end <= len(raw) and not flags & (1 | 0x40 | 0x2000) and
                  method in (0, 8) and disk in (0, 0xffff))
            name = raw[at + 46:at + 46 + name_size].decode('utf-8' if flags & 0x800 else 'ascii', 'strict')
            check(not name.startswith('/') and '\\' not in name and '\0' not in name and
                  ':' not in name and all(part not in {'', '.', '..'} for part in name.rstrip('/').split('/')))
            extra = raw[at + 46 + name_size:at + 46 + name_size + extra_size]
            fields, p = {}, 0
            while p < len(extra):
                check(p + 4 <= len(extra))
                kind, length = struct.unpack_from('<HH', extra, p)
                check(kind not in fields and p + 4 + length <= len(extra))
                fields[kind] = extra[p + 4:p + 4 + length]
                p += 4 + length
            required = [(key, width) for key, value, sentinel, width in
                        [('size', size, 0xffffffff, 8), ('compressed', compressed, 0xffffffff, 8),
                         ('offset', offset, 0xffffffff, 8), ('disk', disk, 0xffff, 4)] if value == sentinel]
            if required:
                values, p = {}, 0
                for key, width in required:
                    check(1 in fields and p + width <= len(fields[1]))
                    values[key] = int.from_bytes(fields[1][p:p + width], 'little')
                    p += width
                check(p == len(fields[1]))
                size, compressed = values.get('size', size), values.get('compressed', compressed)
                offset, disk = values.get('offset', offset), values.get('disk', disk)
            check(disk == 0 and name not in result and compressed >= 0 and size >= 0 and
                  offset + 30 + name_size + compressed <= plan['offset'])
            intervals.append((offset, offset + 30 + name_size + compressed))
            result[name] = Member(name, offset, compressed, size, crc, method, flags)
            at = end
        check(at == len(raw))
        ordered = sorted(intervals)
        check(all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:])),
              'Original ZIP member envelopes overlap.')
        self.directory, self.directory_offset = result, plan['offset']
        return result

    def native_member(self, module):
        check(isinstance(module, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,127}', module))
        # The platform path is part of the publisher's authored member identity;
        # never select a similarly named arbitrary DLL or a different architecture.
        name = f'Endfield_Data/Plugins/x86_64/{module}.dll'
        members = self.members()
        check(name in members, 'Original client does not declare its managed native import.')
        return members[name]

    def member_plan(self, member, *, maximum=MAX_MEMBER):
        """Read only the bounded local envelope before approving its payload."""
        check(self.members().get(member.name) == member and type(maximum) is int and
              0 < maximum <= MAX_MEMBER and 0 < member.size <= maximum and
              0 < member.compressed <= maximum,
              'Original native member exceeds the approved output/input bound.')
        header = self.read(member.offset, 30)
        row = struct.unpack('<4s5H3I2H', header)
        check(row[0] == b'PK\x03\x04' and row[2] == member.flags and row[3] == member.method)
        name_size, extra_size = row[-2:]
        check(0 < name_size <= 1024 and 0 <= extra_size <= 65535)
        prefix = self.read(member.offset + 30, name_size + extra_size)
        name = prefix[:name_size].decode('utf-8' if member.flags & 0x800 else 'ascii', 'strict')
        check(name == member.name)
        if not member.flags & 8:
            check(row[6] == member.crc32 and row[7] in (member.compressed, 0xffffffff) and
                  row[8] in (member.size, 0xffffffff))
        start = member.offset + 30 + len(prefix)
        following = min((row.offset for row in self.directory.values() if row.offset > member.offset),
                        default=self.directory_offset)
        check(start + member.compressed <= following,
              'Original local member payload overlaps another member or directory.')
        return {'offset': start, 'download_bytes': member.compressed, 'decoded_bytes': member.size,
                'required_disk_bytes': 2 * member.size + member.compressed}

    def extract(self, member, *, maximum=MAX_MEMBER):
        plan = self.member_plan(member, maximum=maximum)
        compressed = self.read(plan['offset'], plan['download_bytes'])
        if member.method == 0:
            decoded = compressed
        else:
            stream = zlib.decompressobj(-15)
            decoded = stream.decompress(compressed, member.size + 1)
            check(stream.eof and not stream.unused_data and not stream.unconsumed_tail)
        check(len(decoded) == member.size and zlib.crc32(decoded) == member.crc32,
              'Original complete member size or ZIP CRC differs.')
        return decoded
