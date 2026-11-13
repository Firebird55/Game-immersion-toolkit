"""Read a bounded Endfield timeline bundle from the public Windows release."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct

from .endfield_metadata import REVISION
from .game_tools import _atomic_file, download

SOURCES = {
    'VFSUtils.cs': '75b435d07a75f66343312dad387816f2f1a3a94224af370c915ad1b7cff547d0',
    'CryptoHelper.cs': '68d3169d9d0bce93c1a70b858ac0843136fb197a426cb040ab9e5f85f0b0688d',
}
MAX_BUNDLE = 64 * 1024**2
MAX_DIRECTORY = 2 * 1024**2
MAX_SERIALIZED = 64 * 1024**2


def _require(condition, message='Unsupported Endfield timeline bundle'):
    if not condition:
        raise ValueError(message)


def _rol(value, bits, width):
    bits %= width
    return ((value << bits) | (value >> (width - bits))) & ((1 << width) - 1)


def _field(high, low, masks, *, width=32, rotate=-18):
    half = width // 2
    mixed = (((high ^ low ^ masks[0]) & ((1 << half) - 1)) << half) | low
    return _rol(mixed, rotate, width) ^ masks[1]


def _xtime(value):
    return ((value << 1) ^ (0x1b if value & 128 else 0)) & 255


def _round_keys(substitutions, first):
    keys, rcon = [first], 1
    for _ in range(10):
        old = keys[-1]
        word = bytearray(substitutions[old[i]] for i in (13, 14, 15, 12))
        word[0] ^= rcon
        rcon = _xtime(rcon)
        result = bytearray()
        for start in range(0, 16, 4):
            word = bytearray(a ^ b for a, b in zip(word, old[start:start + 4]))
            result.extend(word)
        keys.append(bytes(result))
    return tuple(keys)


@dataclass(frozen=True)
class Format:
    masks: tuple
    substitutions: bytes
    keys: tuple
    iv: bytes


@lru_cache(maxsize=2)
def _parse_format(layout, cipher):
    groups = re.findall(r'case GameType\.ArknightsEndfield:(.*?)break;', layout.decode('utf-8-sig'), re.S)
    masks = tuple(tuple(int(x, 16) for x in re.findall(r'0x[\da-fA-F]+', part)) for part in groups)
    _require(tuple(map(len, masks)) == (4, 0, 7, 1, 1, 1, 5, 1, 1, 1, 2, 0, 5, 1))
    text = cipher.decode('utf-8-sig')

    def table(field, count):
        values = re.findall(r'\b' + field + r'\s*=\s*new byte\[\]\s*\{([^}]+)\}', text)
        _require(len(values) == 1)
        result = bytes(int(byte.strip(), 16) for byte in values[0].split(',') if byte.strip())
        _require(len(result) == count)
        return result

    substitutions = table('VFSAESSBox', 256)
    first = table('VFSAESKey', 16)
    return Format(masks, substitutions, _round_keys(substitutions, first), table('VFSAESIV', 16))


def _format(tools):
    docs = []
    for name, digest in SOURCES.items():
        path = Path(tools) / 'format-metadata/endfield-timeline-v1' / name
        if path.is_file() and path.stat().st_size <= 128 * 1024:
            data = path.read_bytes()
        else:
            data = b''
        if hashlib.sha256(data).hexdigest() != digest:
            base = f'https://raw.githubusercontent.com/EIHRTeam/EndfieldStudio/{REVISION}/AnimeStudio/Crypto/'
            data = download(base + name, limit=128 * 1024)
            _require(hashlib.sha256(data).hexdigest() == digest, 'Endfield timeline metadata checksum mismatch')
            _atomic_file(path, data)
        docs.append(data)
    return _parse_format(*docs)


def _stream_blocks(profile):
    state = profile.iv
    while True:
        state = bytes(a ^ b for a, b in zip(state, profile.keys[0]))
        for index, key in enumerate(profile.keys[1:], 1):
            shifted = bytearray(profile.substitutions[state[4 * ((col + row) % 4) + row]]
                                for col in range(4) for row in range(4))
            if index < 10:
                for pos in range(0, 16, 4):
                    column = shifted[pos:pos + 4]
                    total = column[0] ^ column[1] ^ column[2] ^ column[3]
                    for row in range(4):
                        shifted[pos + row] ^= total ^ _xtime(column[row] ^ column[(row + 1) % 4])
            state = bytes(a ^ b for a, b in zip(shifted, key))
        yield state
        mask = profile.masks[13][0].to_bytes(8, 'little')
        state = bytes(profile.substitutions[_rol((value ^ (31 * i) ^ mask[i % 8]) & 255, 3, 8)]
                      for i, value in enumerate(state))


@lru_cache(maxsize=2)
def _prefix_stream(profile):
    stream = _stream_blocks(profile)
    return b''.join(next(stream) for _ in range(16))


def _unmask(data, profile):
    stream = _prefix_stream(profile)
    if len(data) <= 256:
        return bytes(a ^ b for a, b in zip(data, stream))
    result = bytearray(data)
    count = min(len(data) // 16, 256)
    step = 256 // count
    for group in range(count):
        for i in range(step):
            result[group * 16 + i] ^= stream[group * step + i]
    return result


def _inflate(data, expected, inverse):
    out = bytearray()
    pos = 0

    def length(n):
        nonlocal pos
        if n == 15:
            while True:
                _require(pos < len(data))
                v = data[pos]
                pos += 1
                n += v
                _require(n <= expected)
                if v < 255:
                    break
        return n

    while pos < len(data):
        token = data[pos]
        pos += 1
        if inverse:
            literals = (token & 3) | ((token >> 2) & 12)
            matches = ((token >> 2) & 3) | ((token >> 4) & 12)
        else:
            literals, matches = token >> 4, token & 15
        count = length(literals)
        _require(pos + count <= len(data) and len(out) + count <= expected)
        out.extend(data[pos:pos + count])
        pos += count
        if pos == len(data):
            break
        _require(pos + 2 <= len(data))
        distance = int.from_bytes(data[pos:pos + 2], 'big' if inverse else 'little')
        pos += 2
        count = length(matches) + 4
        _require(0 < distance <= len(out) and len(out) + count <= expected)
        # LZ matches may overlap the bytes being written.
        begin = len(out) - distance
        piece = out[begin:begin + min(count, distance)]
        out.extend((piece * ((count + len(piece) - 1) // len(piece)))[:count])
    _require(len(out) == expected, 'Incomplete Endfield timeline block')
    return out


class _Directory:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def unpack(self, layout):
        length = struct.calcsize(layout)
        _require(self.pos + length <= len(self.data))
        result = struct.unpack_from(layout, self.data, self.pos)
        self.pos += length
        return result

    def count(self, mask, final):
        raw, = self.unpack('<I')
        encoded = int.from_bytes((raw ^ mask).to_bytes(4, 'little'), 'big')
        value = _field(encoded >> 16, encoded & 65535, (0, final))
        _require(0 < value <= 10000)
        return value

    def name(self, mask):
        end = self.data.find(0, self.pos, self.pos + 64)
        _require(end > self.pos)
        name = bytes(a ^ ((i ^ mask) & 255) for i, a in enumerate(self.data[self.pos:end])).decode('ascii')
        self.pos = end + 1
        return name


def decode_bundle(data: bytes, tools: Path) -> tuple[str, bytes]:
    """Return the exact CAB node name and serialized Unity v22 bytes."""
    _require(42 <= len(data) <= MAX_BUNDLE)
    profile = _format(tools)
    masks = profile.masks
    first, check = struct.unpack_from('>II', data)
    k1, keep, k2, k3 = masks[0]
    _require(check == ((4 * (first ^ k1) & keep) ^ _rol(first ^ k2, -14, 32) ^ k3))
    c2, f2, enc, s2, f1, u1, u2, s1, c1 = struct.unpack_from('>HIIIIH4xHIH', data, 8)
    m = masks[2]
    packed, plain = _field(c1, c2, m[0:2]), _field(u1, u2, m[2:4])
    flags = f1 ^ f2 ^ m[6]
    header = 48 if (enc ^ f2) >= 7 else 40
    _require(0 < packed <= MAX_DIRECTORY and 0 < plain <= MAX_DIRECTORY)
    at_end = bool(flags & 128)
    declared = _field(s1, s2, m[4:6], width=64) & 0xffffffff
    info = declared - packed if at_end else header
    _require(header <= info <= len(data) - packed)
    compressed = data[info:info + packed]
    layout = _inflate(_unmask(compressed, profile), plain, False) if flags & 63 else compressed
    _require(len(layout) == plain)
    directory = _Directory(layout)
    blocks = []
    total = 0
    for _ in range(directory.count(masks[3][0], masks[4][0])):
        a, b, c, coded, d = directory.unpack('>5H')
        flags16 = coded ^ masks[5][0]
        high, low = flags16 >> 8, flags16 & 255
        flags16 = _rol(((high ^ low) << 8) | low, 14, 16) ^ c ^ masks[6][0]
        size, stored = _field(a, c, masks[6][1:3]), _field(b, d, masks[6][3:5])
        _require(flags16 in (0, 5) and size > 0 and stored > 0 and (flags16 == 5 or stored == size))
        total += size
        _require(total <= MAX_SERIALIZED)
        blocks.append((flags16, size, stored))
    cab = None
    for _ in range(directory.count(masks[7][0], masks[8][0])):
        _, b, c, d = directory.unpack('>4I')
        name = directory.name(masks[10][0])
        e, = directory.unpack('>I')
        m = masks[12]
        offset = _field(d, c, m[1:3], width=64, rotate=14)
        size = _field(b, e, m[3:5], width=64, rotate=14)
        _require(offset <= total and size <= total - offset)
        if re.fullmatch(r'CAB-[0-9a-fA-F]{32}', name):
            _require(cab is None and size >= 48, 'Ambiguous or incomplete Endfield CAB node')
            cab = (name, offset, size)
    _require(cab is not None and directory.pos == len(layout))
    pos = header if at_end else header + (((packed + 15) & ~15) if flags & 512 else packed)
    limit = info if at_end else len(data)
    _require(pos + sum(stored for _, _, stored in blocks) <= limit)
    output = bytearray()
    for compression, original, stored in blocks:
        part = data[pos:pos + stored]
        pos += stored
        output.extend(_inflate(_unmask(part, profile), original, True) if compression else part)
    name, offset, size = cab
    serialized = bytes(memoryview(output)[offset:offset + size])
    _require(struct.unpack_from('>I', serialized, 8)[0] == 22 and
             struct.unpack_from('>Q', serialized, 24)[0] == size, 'Invalid Endfield serialized Unity file')
    return name, serialized
