"""Persona MSG1/FLW0 script metadata; no redistributed game dialogue."""
from __future__ import annotations

import struct

from .persona_cri import invalid


def tokens(data, charset):
    text, functions, dynamic, position = [], [], False, 0
    while position < len(data):
        byte = data[position]
        position += 1
        if byte == 0:
            break
        if byte >= 0xf0:
            count = (byte & 15) - 1
            if count < 0 or position + 1 + count * 2 > len(data):
                raise invalid('Invalid Persona message function.')
            function = data[position]
            position += 1
            args = tuple(((data[position + i] - 1) & 255) | (((data[position + i + 1] - 1) & 255) << 8)
                         for i in range(0, count * 2, 2))
            position += count * 2
            group, identity = function >> 5, function & 31
            functions.append((group, identity, args))
            # Runtime substitutions cannot be reconstructed from authored text.
            if group == 4 and identity in (1, 2, 3, 4, 5, 7, 8, 9, 11, 12, 13):
                dynamic = True
                text.append(' ')
        elif byte == 10:
            text.append('\n')
        else:
            index = byte
            if byte >= 128:
                if position >= len(data):
                    raise invalid('Truncated Persona glyph.')
                index = (byte & 127) * 128 + data[position] - 0x60
                position += 1
            if index >= len(charset) or index < 0 or not charset[index]:
                raise invalid('Unknown Persona font glyph; refresh character metadata.')
            text.append(charset[index])
    return ''.join(text), functions, dynamic


def message_section(data):
    if len(data) < 32:
        raise invalid('Truncated Persona script.')
    if data[8:12] in (b'MSG1', b'1GSM'):
        return data
    if data[8:12] not in (b'FLW0', b'0WLF'):
        raise invalid('Unsupported Persona script header.')
    endian = '>' if data[8:12] == b'FLW0' else '<'
    size, count = struct.unpack_from(endian + 'I', data, 4)[0], struct.unpack_from(endian + 'I', data, 16)[0]
    if size != len(data) or not 1 <= count <= 32 or 32 + count * 16 > size:
        raise invalid('Invalid Persona flow sections.')
    found = []
    for at in range(32, 32 + count * 16, 16):
        kind, width, number, start = struct.unpack_from(endian + '4I', data, at)
        if start + width * number > size:
            raise invalid('Persona flow section exceeds bounds.')
        if kind == 3 and number:
            found.append(data[start:start + width * number])
    if len(found) > 1:
        raise invalid('Duplicate Persona message section.')
    return found[0] if found else None


def read_messages(data, charset):
    data = message_section(data)
    if data is None:
        return []
    endian = '<' if data[8:12] == b'MSG1' else '>'

    def unpack(fmt, at):
        if at < 0 or at + struct.calcsize(endian + fmt) > len(data):
            raise invalid('Persona message pointer exceeds bounds.')
        return struct.unpack_from(endian + fmt, data, at)

    size, count = unpack('I', 4)[0], unpack('I', 24)[0]
    if size != len(data) or count > 100000 or 48 + count * 8 > size:
        raise invalid('Invalid Persona message directory.')
    names_at, name_count = unpack('II', 32 + count * 8)
    if name_count > 10000:
        raise invalid('Too many Persona speakers.')
    names = []
    for index in range(name_count):
        start = 32 + unpack('I', 32 + names_at + index * 4)[0]
        end = data.find(b'\0', start, min(start + 4096, len(data)))
        if end < start:
            raise invalid('Invalid Persona speaker string.')
        names.append(tokens(data[start:end], charset)[0])
    rows = []
    for ordinal in range(count):
        kind, offset = unpack('II', 32 + ordinal * 8)
        start = 32 + offset
        if kind not in (0, 1) or start + 28 > size:
            raise invalid('Unsupported Persona message type.')
        # Two shipped labels contain non-ASCII bytes; identity is binary and
        # must not be interpreted using the dialogue character encoding.
        label = data[start:start + 24].split(b'\0', 1)[0].hex()
        if kind == 0:
            number, speaker = unpack('HH', start + 24)
            pointer = start + 28
        else:
            reserved, number = unpack('HH', start + 24)
            if reserved:
                raise invalid('Invalid Persona choice header.')
            speaker, pointer = 0xffff, start + 32
        if number > 10000:
            raise invalid('Too many Persona message pages.')
        if not number:
            continue
        offsets = [32 + unpack('I', pointer + index * 4)[0] for index in range(number)]
        length = unpack('I', pointer + number * 4)[0]
        body = pointer + number * 4 + 4
        end = body + length
        if end > len(data) or offsets[0] != body or offsets != sorted(set(offsets)) or offsets[-1] >= end:
            raise invalid('Invalid Persona page pointers.')
        pages = []
        for index, page_start in enumerate(offsets):
            page_end = offsets[index + 1] if index + 1 < number else end
            text, functions, dynamic = tokens(data[page_start:page_end], charset)
            voices = [args for group, command, args in functions if group == 3 and command == 1]
            if any(len(args) != 6 for args in voices):
                raise invalid('Unsupported Persona voice command.')
            pages.append({'text': text, 'voices': voices, 'dynamic': dynamic, 'functions': functions})
        rows.append({'id': label, 'ordinal': ordinal, 'kind': kind,
                     'speaker': names[speaker] if speaker < len(names) else None, 'pages': pages})
    return rows


def package_members(data):
    """Atlus named PAK/PAC containers, including the older aligned layout."""
    if len(data) < 4:
        raise invalid('Truncated Persona package.')
    new = data[0] == 0 or data[3] == 0 and data[4:5] not in (b'\0', b'\3')
    result = []
    if new:
        endian = '>' if data[0] == 0 else '<'
        count = struct.unpack_from(endian + 'I', data)[0]
        if not 1 <= count <= 10000:
            raise invalid('Invalid Persona package count.')
        at, name_width, alignment = 4, 32, 1
    else:
        endian, count, at, name_width, alignment = '<', 10000, 0, 252, 64
    for _ in range(count):
        if not new and (at == len(data) or len(data) - at < 256 and not any(data[at:])):
            break
        if at + name_width + 4 > len(data):
            raise invalid('Truncated Persona package directory.')
        raw_name = data[at:at + name_width].split(b'\0', 1)[0]
        if not new and not raw_name and len(data) - at <= 256 and not any(data[at:]):
            break
        try:
            name = raw_name.decode('ascii').rstrip(' ').lower()
        except UnicodeDecodeError as error:
            raise invalid('Invalid Persona package name.') from error
        from .persona_cri import safe_name
        safe_name(name)
        length = struct.unpack_from(endian + 'I', data, at + name_width)[0]
        start = at + name_width + 4
        if not length or start + length > len(data):
            raise invalid('Persona package member exceeds bounds.')
        result.append((name, data[start:start + length]))
        at = (start + length + alignment - 1) // alignment * alignment
    if at > len(data) or new and at != len(data):
        raise invalid('Invalid Persona package extent.')
    return result
