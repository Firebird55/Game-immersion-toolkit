"""Bounded Source VSIF v2 / binary VCD v4 dialogue timelines.

The layout is documented by Valve's Source SDK SceneImageFile.h and
CChoreoEvent/CChoreoScene serialization. This reader is independently written.
"""
from collections import defaultdict
import lzma
import math
import struct

from .source_formats import invalid


class Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise invalid('Truncated Source choreography.')
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def unpack(self, fmt):
        result = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))
        if any(isinstance(value, float) and not math.isfinite(value) for value in result):
            raise invalid('Non-finite Source choreography timing.')
        return result[0] if len(result) == 1 else result


def decompress_scene(data):
    if data[:4] != b'LZMA':
        return data
    if len(data) < 17:
        raise invalid('Truncated Source LZMA header.')
    size, packed, properties, dictionary = struct.unpack_from('<IIBI', data, 4)
    if not 0 < size <= 16 * 1024 * 1024 or packed != len(data) - 17 or properties >= 225 or dictionary > 64 * 1024 * 1024:
        raise invalid('Source compressed scene exceeds its bounds.')
    lc, remainder = properties % 9, properties // 9
    lp, pb = remainder % 5, remainder // 5
    try:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[
            {'id': lzma.FILTER_LZMA1, 'dict_size': max(4096, dictionary), 'lc': lc, 'lp': lp, 'pb': pb}])
        result = decoder.decompress(data[17:], max_length=size)
    except lzma.LZMAError:
        raise invalid('Invalid Source LZMA stream.') from None
    # Valve's raw streams may omit the EOS marker; the authored output length
    # is authoritative, while the output limit prevents decompression bombs.
    if len(result) != size or decoder.unused_data:
        raise invalid('Source scene decompressed to an unexpected size.')
    return result


def binary_scene(data, strings):
    cursor = Cursor(decompress_scene(data))
    if cursor.take(5) != b'bvcd\x04':
        raise invalid('Unsupported Source binary choreography version.')
    cursor.take(4)  # CRC of original source VCD, not the compiled byte stream.

    def string():
        index = cursor.unpack('h')
        if not 0 <= index < len(strings):
            raise invalid('Source scene string index exceeds its table.')
        return strings[index]

    def curve():
        for _ in range(cursor.unpack('B')):
            cursor.unpack('fB')

    def event():
        kind = cursor.unpack('B')
        if kind > 16:
            raise invalid('Unsupported Source choreography event.')
        name = string()
        start, end = cursor.unpack('ff')
        parameters = [string() for _ in range(3)]
        curve()
        flags = cursor.unpack('B')
        cursor.unpack('f')
        for _ in range(2):
            for _ in range(cursor.unpack('B')):
                string(); cursor.take(1)
        for _ in range(2):
            for _ in range(cursor.unpack('B')):
                string(); cursor.take(2)
        if kind == 6:
            cursor.unpack('f')
        relative = cursor.unpack('B')
        if relative not in (0, 1):
            raise invalid('Invalid Source relative event tag.')
        if relative:
            string(); string()
        for _ in range(cursor.unpack('B')):
            string()
            flex_flags = cursor.unpack('B')
            cursor.unpack('ff')
            samples = cursor.unpack('h')
            if samples < 0:
                raise invalid('Invalid Source flex sample count.')
            cursor.take(samples * 7)
            if flex_flags & 2:
                cursor.take(cursor.unpack('H') * 7)
        if kind == 12:
            cursor.take(1)
        result = {'kind': kind, 'name': name, 'start': start, 'end': end,
                  'sound': parameters[0], 'active': bool(flags & 8), 'relative': bool(relative)}
        if kind == 5:
            result['caption_type'] = cursor.unpack('B')
            result['caption'] = string()
            result['caption_flags'] = cursor.unpack('B')
            if result['caption_type'] > 2 or not -3600 <= start <= 3600 or not -3600 <= end <= 3600:
                raise invalid('Unsupported Source speech timing or caption type.')
        return result

    groups = [[event() for _ in range(cursor.unpack('B'))]]
    for _ in range(cursor.unpack('B')):
        string()
        actor_groups = []
        for _ in range(cursor.unpack('B')):
            string()
            events = [event() for _ in range(cursor.unpack('B'))]
            if cursor.unpack('B') == 1:
                actor_groups.append(events)
        if cursor.unpack('B') == 1:
            groups.extend(actor_groups)
    curve()
    cursor.take(1)
    if cursor.pos != len(cursor.data):
        raise invalid('Unexpected trailing Source choreography data.')
    return groups


def scene_image(data):
    if not 20 <= len(data) <= 256 * 1024 * 1024:
        raise invalid('Invalid Source scene image size.')
    magic, version, count, string_count, entries = struct.unpack_from('<4s4I', data)
    if magic != b'VSIF' or version != 2 or count > 100000 or string_count > 32768 or 20 + string_count * 4 > entries or entries + count * 16 > len(data):
        raise invalid('Unsupported Source scene image layout.')
    strings = []
    for number in range(string_count):
        offset = struct.unpack_from('<I', data, 20 + 4 * number)[0]
        end = data.find(b'\0', offset, min(offset + 4096, entries))
        if offset < 20 + string_count * 4 or end < 0:
            raise invalid('Source scene string exceeds its pool.')
        try:
            strings.append(data[offset:end].decode('utf-8'))
        except UnicodeError:
            raise invalid('Unsupported Source choreography string encoding.') from None
    result = {}
    for number in range(count):
        identity, offset, size, summary = struct.unpack_from('<4I', data, entries + number * 16)
        if identity in result or offset < entries + count * 16 or size < 10 or offset + size > len(data) or summary + 8 > len(data):
            raise invalid('Source scene entry exceeds its image.')
        _duration, sounds = struct.unpack_from('<II', data, summary)
        if sounds > 100000 or summary + 8 + sounds * 4 > len(data):
            raise invalid('Source scene summary exceeds its image.')
        result[identity] = binary_scene(data[offset:offset + size], strings)
    return result


def caption_sequences(scenes):
    """Caption→unique ordered sound/timing tuples, mirroring channel grouping.

    Conflicting scene performances stay ambiguous. Disabled, inactive and
    relative-tag events cannot accidentally become a guessed composition.
    """
    candidates = defaultdict(set)
    for groups in scenes.values():
        for events in groups:
            grouped = defaultdict(list)
            for event in events:
                if event['kind'] != 5 or not event['active'] or event['caption_type'] == 2:
                    continue
                token = (event['caption'] or event['sound']).casefold()
                grouped[token].append(event)
            for token, values in grouped.items():
                ordered = sorted(values, key=lambda value: value['start'])
                start = ordered[0]['start']
                if any(value['relative'] or value['end'] < value['start'] for value in values):
                    candidates[token].add(())
                    continue
                candidates[token].add(tuple((value['sound'].casefold(), round((value['start'] - start) * 1000))
                                            for value in ordered))
    return {token: next(iter(values)) if len(values) == 1 else () for token, values in candidates.items()}
