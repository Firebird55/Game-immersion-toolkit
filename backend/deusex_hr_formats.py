"""Bounded readers for Human Revolution Director's Cut PC resources.

Format references: Gibbed.CrystalDynamics BIGFILE v2/CDRM/DRM and rrika/dxhr.
These readers are independently implemented; no game resource names or text
lists are downloaded or redistributed.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

MAX_RESOURCE = 256 * 1024 * 1024
LOCALE_BITS = {'en': 1, 'fr': 2, 'de': 4, 'it': 8, 'es-ES': 16}


def align(value):
    return (value + 15) & ~15


def filename_hash(name):
    value = 0xffffffff
    for char in name.encode('ascii'):
        value ^= char << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04c11db7 if value & 0x80000000 else 0)) & 0xffffffff
    return value ^ 0xffffffff


@dataclass(frozen=True)
class Entry:
    identity: int
    size: int
    offset: int
    locale: int


class Archive:
    def __init__(self, root):
        self.root = Path(root)
        with (self.root / 'BIGFILE.000').open('rb') as stream:
            head = stream.read(72)
            if len(head) != 72:
                raise ValueError('Truncated Deus Ex BIGFILE header')
            self.alignment = struct.unpack_from('<I', head)[0]
            count = struct.unpack_from('<I', head, 68)[0]
            if self.alignment not in {0x7ff00000, 0x62300000} or head[4:9] != b'pc-w\0' or not 1 <= count <= 500000:
                raise ValueError('Unsupported Deus Ex BIGFILE header')
            table = stream.read(count * 20)
        if len(table) != count * 20:
            raise ValueError('Truncated Deus Ex BIGFILE directory')
        hashes = struct.unpack_from('<' + str(count) + 'I', table)
        self.entries, self.by_id = [], {}
        for index, (size, offset, locale, compressed) in enumerate(struct.iter_unpack('<4I', table[count * 4:])):
            if compressed or size > 2 * 1024 ** 3:
                raise ValueError('Unsupported Deus Ex BIGFILE entry')
            entry = Entry(hashes[index], size, offset, locale)
            self.entries.append(entry)
            self.by_id.setdefault(entry.identity, []).append(entry)

    def select(self, identity, locale):
        bit = LOCALE_BITS[locale]
        matches = [entry for entry in self.by_id.get(identity, []) if entry.locale & bit]
        if len(matches) > 1:
            raise ValueError('Ambiguous Deus Ex original language resource')
        return matches[0] if matches else None

    def read(self, entry, offset=0, size=None):
        size = entry.size - offset if size is None else size
        if not 0 <= offset <= entry.size or not 0 <= size <= min(MAX_RESOURCE, entry.size-offset):
            raise ValueError('Deus Ex resource range exceeds the supported bound')
        part, position = divmod(entry.offset * 2048 + offset, self.alignment)
        if position + size > self.alignment:
            raise ValueError('Deus Ex resource crosses a BIGFILE segment')
        with (self.root / ('BIGFILE.%03d' % part)).open('rb') as stream:
            stream.seek(position)
            result = stream.read(size)
        if len(result) != size:
            raise ValueError('Deus Ex resource is truncated; verify game files')
        return result


def decompress(data):
    if data[:4] != b'CDRM':
        return data
    if len(data) < 16:
        raise ValueError('Truncated CDRM header')
    version, count, padding = struct.unpack_from('<3I', data, 4)
    if version not in {0, 2} or not 1 <= count <= 100000 or 16 + count * 8 > len(data):
        raise ValueError('Unsupported CDRM header')
    cursor = align(16 + count * 8)
    if version == 2 and cursor != 16 + count * 8 + padding:
        raise ValueError('Invalid CDRM block alignment')
    output = bytearray()
    for info, packed in struct.iter_unpack('<II', data[16:16+count*8]):
        length, kind = info >> 8, info & 255
        if cursor + packed > len(data) or len(output) + align(length) > MAX_RESOURCE:
            raise ValueError('CDRM block exceeds the supported bound')
        block = data[cursor:cursor+packed]
        if kind == 2:
            decoder = zlib.decompressobj()
            block = decoder.decompress(block, length + 1)
            if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError('Invalid CDRM compressed block')
        elif kind != 1:
            raise ValueError('Unsupported CDRM block codec')
        if len(block) != length:
            raise ValueError('Incorrect CDRM block size')
        output.extend(block)
        output.extend(b'\0' * (align(length)-length))
        cursor += align(packed)
    return bytes(output)


@dataclass
class Section:
    identity: int
    kind: int
    subtype: int
    locale: int
    data: bytes
    fixup: bytes


def sections(data):
    data = decompress(data)
    if len(data) < 32:
        raise ValueError('Truncated DRM header')
    version, dep1, dep2, extra, _unknown, flags, count, root = struct.unpack_from('<8I', data)
    if version != 21 or extra or flags & ~1 or not 1 <= count <= 100000 or (root >= count and root != 0xffffffff):
        raise ValueError('Unsupported DRM header')
    cursor = 32 + count * 20 + dep1 + dep2
    if cursor > len(data):
        raise ValueError('Truncated DRM section directory')
    if flags & 1:
        cursor = align(cursor)
    result = []
    for size, kind, unknown, _reserved, info, identity, locale in struct.iter_unpack('<IBBHIII', data[32:32+count*20]):
        if unknown & 1:
            raise ValueError('Unsupported DRM section encoding')
        fixup_size = info >> 8
        if cursor + fixup_size > len(data):
            raise ValueError('Truncated DRM relocation directory')
        fixup = data[cursor:cursor+fixup_size]
        cursor += fixup_size
        if flags & 1:
            cursor = align(cursor)
        if cursor + size > len(data):
            raise ValueError('Truncated DRM section data')
        result.append(Section(identity, kind, (info >> 1) & 127, locale, data[cursor:cursor+size], fixup))
        cursor += size
        if flags & 1:
            cursor = align(cursor)
    return result


def locals_table(data):
    if len(data) < 12:
        raise ValueError('Truncated Deus Ex localization')
    language, count = struct.unpack_from('<II', data)
    if language > 15 or not 1 <= count <= 200000 or 8 + count * 4 > len(data):
        raise ValueError('Unsupported Deus Ex localization')
    result = {}
    for identity, (offset,) in enumerate(struct.iter_unpack('<I', data[8:8+4*count])):
        if not offset:
            continue
        if offset < 8 + 4 * count or offset >= len(data):
            raise ValueError('Invalid Deus Ex localization offset')
        end = data.find(b'\0', offset)
        if end < 0 or end-offset > 100000:
            raise ValueError('Unterminated Deus Ex localization')
        result[identity] = data[offset:end].decode('utf-8')
    return language, result


def section_directory(archive, entry):
    """CDRM's first block contains the DRM directory; skip texture/audio data."""
    prefix = archive.read(entry, 0, min(entry.size, 4096))
    if prefix[:4] == b'CDRM':
        if len(prefix) < 24:
            raise ValueError('Truncated CDRM directory')
        version, count, padding, info, packed = struct.unpack_from('<5I', prefix, 4)
        if version not in {0, 2} or not 1 <= count <= 100000 or packed > 16 * 1024 * 1024:
            raise ValueError('Unsupported CDRM directory')
        offset = align(16 + 8 * count)
        if version == 2 and offset != 16 + 8 * count + padding:
            raise ValueError('Invalid CDRM directory alignment')
        block = archive.read(entry, offset, packed)
        # Decode a single synthetic wrapper through the same bounded decoder.
        wrapper = b'CDRM' + struct.pack('<3I', 2, 1, 8) + struct.pack('<II', info, packed) + b'\0' * 8 + block
        data = decompress(wrapper)
    elif prefix[:4] == b'\x15\0\0\0':
        count = struct.unpack_from('<I', prefix, 24)[0]
        if not 1 <= count <= 100000:
            raise ValueError('Invalid DRM section count')
        data = archive.read(entry, 0, 32 + 20 * count)
    else:
        return []
    if len(data) < 32 or struct.unpack_from('<I', data)[0] != 21:
        raise ValueError('Unsupported DRM directory version')
    count = struct.unpack_from('<I', data, 24)[0]
    if not 1 <= count <= 100000 or 32 + count * 20 > len(data):
        raise ValueError('Truncated DRM directory')
    return [(identity, kind, (info >> 1) & 127, locale) for _size, kind, _unknown, _reserved, info, identity, locale
            in struct.iter_unpack('<IBBHIII', data[32:32+20*count])]


def selected_sections(archive, entry, identities):
    """Read only requested sections, bypassing unrelated textures and meshes."""
    prefix = archive.read(entry, 0, min(32, entry.size))
    blocks, cache = [], {}
    if prefix[:4] == b'CDRM':
        version, count, padding = struct.unpack_from('<3I', prefix, 4)
        if version not in {0, 2} or not 1 <= count <= 100000:
            raise ValueError('Unsupported CDRM block directory')
        descriptors = archive.read(entry, 16, count * 8)
        packed_at, logical_at = align(16 + count * 8), 0
        if version == 2 and packed_at != 16 + count * 8 + padding:
            raise ValueError('Invalid CDRM block directory alignment')
        for info, size in struct.iter_unpack('<II', descriptors):
            length, codec = info >> 8, info & 255
            if codec not in {1, 2} or packed_at + size > entry.size or logical_at + align(length) > MAX_RESOURCE:
                raise ValueError('Invalid CDRM block range')
            blocks.append((logical_at, length, packed_at, size, info))
            logical_at += align(length)
            packed_at += align(size)

    def read(offset, length):
        if not blocks:
            return archive.read(entry, offset, length)
        result, end = bytearray(), offset + length
        for index, (start, actual, packed_at, packed, info) in enumerate(blocks):
            stop = start + align(actual)
            if stop <= offset or start >= end:
                continue
            if index not in cache:
                wrapper = b'CDRM' + struct.pack('<3I', 2, 1, 8) + struct.pack('<II', info, packed) + b'\0' * 8
                cache[index] = decompress(wrapper + archive.read(entry, packed_at, packed))
            result.extend(cache[index][max(offset, start)-start:min(stop, end)-start])
        if len(result) != length:
            raise ValueError('DRM section exceeds its compression blocks')
        return bytes(result)

    header = read(0, 32)
    version, dep1, dep2, extra, _unknown, flags, count, root = struct.unpack('<8I', header)
    if version != 21 or extra or flags & ~1 or not 1 <= count <= 100000 or (root >= count and root != 0xffffffff):
        raise ValueError('Unsupported DRM section directory')
    directory = read(32, count * 20)
    cursor = 32 + count * 20 + dep1 + dep2
    if flags & 1:
        cursor = align(cursor)
    result = []
    for size, kind, unknown, _reserved, info, identity, locale in struct.iter_unpack('<IBBHIII', directory):
        fixup_at, fixup_size = cursor, info >> 8
        cursor += fixup_size
        if flags & 1:
            cursor = align(cursor)
        subtype = (info >> 1) & 127
        if (kind, subtype, identity) in identities:
            if unknown & 1:
                raise ValueError('Unsupported DRM section encoding')
            result.append(Section(identity, kind, subtype, locale, read(cursor, size), read(fixup_at, fixup_size)))
        cursor += size
        if flags & 1:
            cursor = align(cursor)
    return result


def local_references(section):
    """Type-zero relocation records point within their authored DRM section."""
    fixup = section.fixup
    if not fixup:
        return {}
    if len(fixup) < 20:
        raise ValueError('Truncated DRM fixups')
    counts = struct.unpack_from('<5I', fixup)
    if counts[3] or 20 + 8 * (counts[0] + counts[1]) + 4 * (counts[2] + counts[4]) != len(fixup):
        raise ValueError('Unsupported DRM fixups')
    refs = {}
    for origin, target in struct.iter_unpack('<II', fixup[20:20+8*counts[0]]):
        if origin + 4 > len(section.data) or target > len(section.data) or origin in refs:
            raise ValueError('Invalid DRM local pointer')
        refs[origin] = target
    return refs


def stream_binding(section):
    """Follow the sound-node/stream-node pointer graph, never scan for strings."""
    if section.kind != 7 or section.subtype != 13:
        return None
    data, refs = section.data, local_references(section)
    if len(data) < 16 or struct.unpack_from('<I', data)[0] != 5:
        return None
    parameters = refs.get(4)
    child = refs.get(parameters)
    if child is None or child + 16 > len(data) or struct.unpack_from('<I', data, child)[0] != 4:
        return None
    stream = refs.get(child + 4)
    if stream is None or stream + 32 > len(data):
        raise ValueError('Truncated Deus Ex stream node')
    name_at = refs.get(stream)
    if name_at is None:
        raise ValueError('Missing Deus Ex stream path')
    end = data.find(b'\0', name_at)
    if end < 0 or end - name_at > 1024:
        raise ValueError('Invalid Deus Ex stream path')
    name = data[name_at:end].decode('ascii').lower()
    if not name.startswith('vo\\'):
        return None
    if any(part in {'', '.', '..'} for part in name.split('\\')) or ':' in name:
        raise ValueError('Unsafe Deus Ex stream path')
    caption = struct.unpack_from('<H', data, stream + 18)[0]
    return caption, name, filename_hash('pc-w\\audio\\streams\\' + name + '.mul')


def choice_text_ids(section):
    """Choice-transition label/preview fields precede the selected spoken node."""
    if section.kind != 7 or section.subtype != 42:
        return set()
    data, refs = section.data, local_references(section)
    if len(data) < 128:
        raise ValueError('Truncated Deus Ex conversation graph')
    node_count, _pointer, transition_count = struct.unpack_from('<III', data, 112)
    nodes, transitions = refs.get(116), refs.get(124)
    if node_count > 10000 or transition_count > 30000 or nodes is None or transitions is None or nodes + node_count * 44 > len(data) or transitions + transition_count * 20 > len(data):
        raise ValueError('Invalid Deus Ex conversation graph')
    choices = set()
    for index in range(node_count):
        name_at = refs.get(nodes + index * 44 + 4)
        if name_at is None:
            raise ValueError('Missing Deus Ex conversation node type')
        end = data.find(b'\0', name_at)
        if end < name_at or end-name_at > 1024:
            raise ValueError('Invalid Deus Ex conversation node type')
        if data[name_at:end].lower() == b'dtp\\conversation\\sharednodes\\conversation_choice.dtp':
            choices.add(index)
    result = set()
    for index in range(transition_count):
        at = transitions + index * 20
        source, target, kind = struct.unpack_from('<III', data, at)
        if source not in choices:
            continue
        if target >= node_count or kind != 1:
            raise ValueError('Unsupported Deus Ex choice transition')
        fields = refs.get(at+16)
        if fields is None or fields + 8 > len(data):
            raise ValueError('Missing Deus Ex choice label fields')
        result.update(text for text in struct.unpack_from('<HH', data, fields+4) if text)
    return result


def mul_header(data):
    if len(data) < 2048:
        raise ValueError('Truncated Deus Ex MUL header')
    rate, _loop, samples, channels = struct.unpack_from('<4I', data)
    if rate not in {5512, 11025, 22050, 44100, 48000} or not 1 <= channels <= 8 or not samples:
        raise ValueError('Unsupported Deus Ex MUL format')
    return rate, samples, channels


def demux_voice(data):
    """Original mono voice stream; facial animation segments remain separate."""
    if mul_header(data)[2] != 1:
        raise ValueError('Deus Ex multichannel cinematic streams require a separate reader')
    return demux_streams(data)[0]


def demux_streams(data):
    """Preserve each authored MUL channel as its complete original FSB."""
    _rate, _samples, channels = mul_header(data)
    if channels not in {1, 2}:
        raise ValueError('Unsupported Deus Ex voice channel layout')
    cursor, outputs = 2048, [bytearray() for _ in range(channels)]
    while cursor < len(data):
        if cursor + 16 > len(data):
            raise ValueError('Truncated MUL segment')
        kind, size, _unknown, reserved = struct.unpack_from('<4I', data, cursor)
        start, end = cursor + 16, cursor + 16 + size
        if kind not in {0, 1, 2} or reserved or end > len(data):
            raise ValueError('Invalid MUL segment')
        if kind == 0:
            while start < end:
                if start + 16 > end:
                    raise ValueError('Truncated MUL audio block')
                length, channel, flags, unknown = struct.unpack_from('<4I', data, start)
                if channel >= channels or flags != 0x2001 or unknown or start + 16 + length > end:
                    raise ValueError('Unsupported MUL audio block')
                outputs[channel].extend(data[start+16:start+16+length])
                start += 16 + length
        cursor += 16 + align(size)
    for output in outputs:
        if output[:4] != b'FSB4' or len(output) < 48 or struct.unpack_from('<I', output, 4)[0] != 1:
            raise ValueError('Unsupported original Deus Ex FSB voice')
    return [bytes(output) for output in outputs]
