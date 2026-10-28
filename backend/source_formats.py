"""Bounded Valve VPK, KeyValues and compiled-caption format readers.

Caption layout/hash documented in Valve's source-sdk-2013/public/captioncompiler.h.
No game files are extracted to paths supplied by archive members.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import struct
import zlib

from .preparation_errors import PreparationFailure


def invalid(message='The installed Valve game uses an unsupported or damaged data format.'):
    return PreparationFailure('unsupported_game_format', message + ' Verify game files in Steam and update the toolkit.')


def safe_name(name):
    if not isinstance(name, str):
        raise invalid('Unsafe Valve archive member name.')
    path = PurePosixPath(name)
    if (not name or name.startswith('/') or '\\' in name
            or any(part in {'', '.', '..'} or ':' in part for part in name.split('/'))
            or '\0' in name or path.is_absolute()):
        raise invalid('Unsafe Valve archive member name.')
    return name.casefold()


@dataclass(frozen=True)
class VpkEntry:
    crc: int
    preload: bytes
    archive: int
    offset: int
    length: int


class VpkArchive:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.name.endswith('_dir.vpk'):
            raise invalid('A Valve archive requires its directory VPK.')
        size = self.path.stat().st_size
        with self.path.open('rb') as stream:
            header = stream.read(12)
            if len(header) != 12:
                raise invalid('Truncated Valve archive header.')
            magic, version, tree_size = struct.unpack('<3I', header)
            if magic != 0x55AA1234 or version not in (1, 2) or not 1 <= tree_size <= 128 * 1024 * 1024:
                raise invalid()
            self.data_start = (12 if version == 1 else 28) + tree_size
            self.data_size = size - self.data_start
            if version == 2:
                tail = stream.read(16)
                if len(tail) != 16:
                    raise invalid()
                self.data_size, archive_md5, other_md5, signature = struct.unpack('<4I', tail)
                if self.data_start + self.data_size + archive_md5 + other_md5 + signature != size:
                    raise invalid('Valve archive sections exceed their file bounds.')
            if self.data_start > size:
                raise invalid('Truncated Valve archive directory.')
            tree = stream.read(tree_size)
        cursor = 0

        def string():
            nonlocal cursor
            end = tree.find(b'\0', cursor, min(len(tree), cursor + 4096))
            if end < 0:
                raise invalid('Unterminated Valve archive path.')
            try:
                value = tree[cursor:end].decode('utf-8')
            except UnicodeError:
                raise invalid('Invalid Valve archive path encoding.') from None
            cursor = end + 1
            return value

        self.entries = {}
        while extension := string():
            while directory := string():
                while stem := string():
                    if cursor + 18 > len(tree) or len(self.entries) >= 1000000:
                        raise invalid('Valve archive directory exceeds its bounds.')
                    crc, preload_size, archive, offset, length, terminator = struct.unpack_from('<IHHIIH', tree, cursor)
                    cursor += 18
                    if terminator != 0xFFFF or cursor + preload_size > len(tree):
                        raise invalid('Invalid Valve archive member.')
                    name = safe_name(('' if directory == ' ' else directory + '/') + stem + ('' if extension == ' ' else '.' + extension))
                    if name in self.entries or archive == 0x7FFF and offset + length > self.data_size:
                        raise invalid('Duplicate or out-of-bounds Valve archive member.')
                    self.entries[name] = VpkEntry(crc, tree[cursor:cursor+preload_size], archive, offset, length)
                    cursor += preload_size
        if cursor != len(tree):
            raise invalid('Unexpected Valve archive directory data.')

    def read(self, name, maximum=64 * 1024 * 1024):
        entry = self.entries.get(safe_name(name))
        if entry is None:
            raise FileNotFoundError('The requested Valve archive member is not installed.')
        if len(entry.preload) + entry.length > maximum:
            raise invalid('Valve archive member exceeds its size limit.')
        path = self.path if entry.archive == 0x7FFF else self.path.with_name(self.path.name[:-8] + f'_{entry.archive:03d}.vpk')
        offset = entry.offset + (self.data_start if entry.archive == 0x7FFF else 0)
        if entry.length:
            if not path.resolve().is_relative_to(self.path.parent.resolve()) or offset + entry.length > path.stat().st_size:
                raise invalid('Valve archive data exceeds its file bounds.')
            with path.open('rb') as stream:
                stream.seek(offset)
                data = entry.preload + stream.read(entry.length)
        else:
            data = entry.preload
        if len(data) != len(entry.preload) + entry.length or zlib.crc32(data) != entry.crc:
            raise invalid('Valve archive member checksum failed.')
        return data


def keyvalues(data, *, maximum=32 * 1024 * 1024):
    """Return ordered pairs, preserving repeated wave/options keys."""
    if len(data) > maximum:
        raise invalid('Valve text resource exceeds its size limit.')
    try:
        text = data.decode('utf-16') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else data.decode('utf-8-sig')
    except UnicodeError:
        raise invalid('Unsupported Valve text encoding.') from None
    tokens, cursor = [], 0
    token = re.compile(r'\s+|//[^\r\n]*|/\*.*?\*/|"((?:[^"\\]|\\.)*)"|([{}])|([^\s{}"]+)', re.S)
    while cursor < len(text):
        match = token.match(text, cursor)
        if not match or len(tokens) >= 2000000:
            raise invalid('Malformed Valve KeyValues text.')
        cursor = match.end()
        if match[1] is not None:
            value = re.sub(r'\\([nrt"\\])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), match[1])
            tokens.append((value, True))
        elif match[2] or match[3]:
            tokens.append((match[2] or match[3], False))
    cursor = 0

    def group(depth=0):
        nonlocal cursor
        if depth > 32:
            raise invalid('Valve KeyValues nesting exceeds its limit.')
        result = []
        while cursor < len(tokens):
            key, quoted = tokens[cursor]; cursor += 1
            if key == '}' and not quoted:
                if not depth:
                    raise invalid('Unexpected Valve KeyValues closing brace.')
                return result
            if (key == '{' and not quoted) or cursor >= len(tokens):
                raise invalid('Valve KeyValues key has no value.')
            value, quoted = tokens[cursor]; cursor += 1
            if value == '{' and not quoted:
                value = group(depth+1)
            elif value == '}' and not quoted:
                raise invalid('Valve KeyValues key has no value.')
            enabled = True
            if cursor < len(tokens) and not tokens[cursor][1] and tokens[cursor][0].startswith('['):
                condition = re.fullmatch(r'\[(!)?\$(WIN32|WINDOWS|PC|X360|PS3|LINUX|OSX|POSIX)\]', tokens[cursor][0], re.I)
                if not condition:
                    raise invalid('Unsupported Valve platform condition.')
                enabled = condition[2].upper() in {'WIN32', 'WINDOWS', 'PC'}
                if condition[1]:
                    enabled = not enabled
                cursor += 1
            if enabled:
                result.append((key, value))
        if depth:
            raise invalid('Unclosed Valve KeyValues object.')
        return result
    return group()


def compiled_captions(data):
    """Read Valve VCCD v1 UTF-16 caption blocks keyed by lowercase-token CRC32."""
    if len(data) < 24 or len(data) > 256 * 1024 * 1024:
        raise invalid('Invalid Valve caption resource size.')
    magic, version, blocks, block_size, count, start = struct.unpack_from('<4s5I', data)
    if (magic != b'VCCD' or version != 1 or not 2 <= block_size <= 1024 * 1024
            or count > 1000000 or 24 + count * 12 > start or start + blocks * block_size > len(data)):
        raise invalid('Unsupported Valve compiled caption layout.')
    result = {}
    for number in range(count):
        token, block, offset, size = struct.unpack_from('<IIHH', data, 24 + number * 12)
        if block >= blocks or size < 2 or size % 2 or offset % 2 or offset + size > block_size:
            raise invalid('Valve caption exceeds its authored block.')
        raw = data[start + block * block_size + offset:start + block * block_size + offset + size]
        if raw[-2:] != b'\0\0':
            raise invalid('Unterminated Valve compiled caption.')
        try:
            text = raw[:-2].decode('utf-16-le')
        except UnicodeError:
            raise invalid('Invalid Valve caption encoding.') from None
        if token in result and result[token] != text:
            raise invalid('Ambiguous Valve caption token hash.')
        result[token] = text
    return result
