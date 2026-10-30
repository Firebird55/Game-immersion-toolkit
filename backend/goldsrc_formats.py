"""Bounded read-only GoldSrc PAK/BSP, titles and sentence-definition readers.

Sentence definitions name samples and playback parameters, never transcripts.
Only official mount names supplied by the game adapter are considered.
"""
from pathlib import Path
import re
import struct

from .source_formats import invalid, keyvalues, safe_name


def decode_text(data, locale='en'):
    if len(data) > 16 * 1024 * 1024:
        raise invalid('GoldSrc text exceeds its size limit.')
    try:
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            return data.decode('utf-16')
        try:
            return data.decode('utf-8-sig')
        except UnicodeError:
            return data.decode({'zh-Hans': 'gb18030', 'zh-Hant': 'big5', 'ko': 'cp949'}.get(locale, 'cp1252'))
    except UnicodeError:
        raise invalid('Unsupported GoldSrc text encoding.') from None


class PakArchive:
    def __init__(self, path):
        self.path = Path(path)
        size = self.path.stat().st_size
        with self.path.open('rb') as stream:
            header = stream.read(12)
            if len(header) != 12:
                raise invalid('Truncated GoldSrc PAK header.')
            magic, offset, length = struct.unpack('<4sII', header)
            if magic != b'PACK' or offset < 12 or length % 64 or length > 64 * 100000 or offset + length > size:
                raise invalid('Unsupported GoldSrc PAK directory.')
            stream.seek(offset)
            table = stream.read(length)
        self.entries = {}
        for raw, start, count in struct.iter_unpack('<56sII', table):
            try:
                name = safe_name(raw.split(b'\0', 1)[0].decode('ascii'))
            except UnicodeError:
                raise invalid('Unsupported GoldSrc PAK filename.') from None
            if name in self.entries or start < 12 or start + count > offset:
                raise invalid('Duplicate or out-of-bounds GoldSrc PAK member.')
            self.entries[name] = (start, count)

    def read(self, name, maximum=64 * 1024 * 1024):
        start, count = self.entries[safe_name(name)]
        if count > maximum:
            raise invalid('GoldSrc member exceeds its size limit.')
        with self.path.open('rb') as stream:
            stream.seek(start)
            data = stream.read(count)
        if len(data) != count:
            raise invalid('Truncated GoldSrc PAK member.')
        return data


class GoldSrcFiles:
    def __init__(self, install, mount):
        self.install = Path(install).resolve()
        self.mount = safe_name(mount)
        self.root = self.install / self.mount
        if not self.root.resolve().is_relative_to(self.install):
            raise invalid('GoldSrc mount escaped the install folder.')
        self.archives, self.entries = [], {}
        # GoldSrc searches higher numbered PAKs first. Loose official files
        # take precedence. Never inspect addons, downloads, saves or configs.
        for path in sorted(self.root.glob('pak[0-9].pak'), reverse=True):
            if not path.resolve().is_relative_to(self.root.resolve()):
                raise invalid('GoldSrc archive escaped its mount.')
            archive = PakArchive(path)
            self.archives.append(archive)
            for name in archive.entries:
                self.entries.setdefault(name, archive)

    def loose(self, member):
        path = self.root / safe_name(member)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise invalid('GoldSrc member escaped its mount.')
        return path if path.is_file() else None

    def has(self, member):
        return self.loose(member) is not None or safe_name(member) in self.entries

    def names(self, directory, suffix):
        directory = safe_name(directory)
        result = {name for name in self.entries if name.startswith(directory + '/') and name.endswith(suffix)}
        for path in (self.root / directory).rglob('*' + suffix):
            name = path.relative_to(self.root).as_posix().casefold()
            if self.loose(name) is not None:
                result.add(name)
            if len(result) > 100000:
                raise invalid('GoldSrc resource inventory exceeds its limit.')
        return sorted(result)

    def read(self, member, maximum=64 * 1024 * 1024):
        member = safe_name(member)
        if path := self.loose(member):
            if path.stat().st_size > maximum:
                raise invalid('GoldSrc resource exceeds its size limit.')
            return path.read_bytes()
        if member in self.entries:
            return self.entries[member].read(member, maximum)
        raise FileNotFoundError('The selected GoldSrc resource is not installed.')

    def map_entities(self, member, locale='en'):
        member = safe_name(member)
        if path := self.loose(member):
            with path.open('rb') as stream:
                header = stream.read(124)
                offset, length = entity_bounds(header, path.stat().st_size)
                stream.seek(offset)
                data = stream.read(length)
        else:
            # PAK-contained maps are bounded separately; modern Steam maps
            # are loose and only their entity lump is read.
            raw = self.read(member, 128 * 1024 * 1024)
            offset, length = entity_bounds(raw[:124], len(raw))
            data = raw[offset:offset + length]
        if len(data) != length:
            raise invalid('Truncated GoldSrc map entity lump.')
        return entities(data, locale)


def entity_bounds(header, total):
    if len(header) != 124 or struct.unpack_from('<I', header)[0] != 30:
        raise invalid('Unsupported GoldSrc map version.')
    offset, length = struct.unpack_from('<II', header, 4)
    if offset < 124 or not 0 < length <= 16 * 1024 * 1024 or offset + length > total:
        raise invalid('GoldSrc map entities exceed their file bounds.')
    return offset, length


def entities(data, locale='en'):
    text = decode_text(data, locale).rstrip('\0').strip()
    cursor, result = 0, []
    pattern = re.compile(r'\s*\{((?:[^{}"]|"(?:[^"\\]|\\.)*")*)\}', re.S)
    while cursor < len(text):
        match = pattern.match(text, cursor)
        if match is None or len(result) >= 100000:
            raise invalid('Malformed GoldSrc map entities.')
        pairs = keyvalues(match[1].encode('utf-8'))
        entity = {}
        for key, value in pairs:
            key = key.casefold()
            if not isinstance(value, str):
                raise invalid('Invalid GoldSrc map entity field.')
            # GoldSrc invokes KeyValue in file order. Repeated scalar fields
            # replace earlier values; multi_manager also has repeated targets.
            entity[key] = value
        result.append(entity)
        cursor = match.end()
    return result


def titles(data, locale='en'):
    """Retain authored line breaks and display positions; no UI-token guessing."""
    lines = decode_text(data, locale).splitlines()
    result, cursor, position = {}, 0, None
    while cursor < len(lines):
        line = lines[cursor].strip(); cursor += 1
        if not line or line.startswith('//'):
            continue
        if line.startswith('$'):
            if line.startswith('$position'):
                try:
                    values = line.split('//', 1)[0].split()
                    position = tuple(float(x) for x in values[1:])
                    if len(position) != 2 or any(not -1 <= x <= 1 for x in position):
                        raise ValueError()
                except ValueError:
                    raise invalid('Unsupported GoldSrc title position.') from None
            continue
        if not re.fullmatch(r'[A-Za-z0-9_]+', line):
            raise invalid('Unsupported GoldSrc title identity.')
        while cursor < len(lines) and (not lines[cursor].strip() or lines[cursor].strip().startswith('//')):
            cursor += 1
        if cursor >= len(lines) or lines[cursor].strip() != '{':
            raise invalid('GoldSrc title is missing its text block.')
        cursor += 1
        body = []
        while cursor < len(lines) and lines[cursor].strip() != '}':
            body.append(lines[cursor]); cursor += 1
        if cursor >= len(lines) or len(result) > 100000:
            raise invalid('Unclosed GoldSrc title block.')
        cursor += 1
        name = line.casefold()
        entry = {'text': '\n'.join(body).strip(), 'position': position}
        if name in result and result[name] != entry:
            raise invalid('Conflicting GoldSrc title identity.')
        result[name] = entry
    return result


def sentences(data):
    """Inventory only. Playback words, punctuation and controls are not prose."""
    result = []
    for line in decode_text(data).splitlines():
        line = line.split('//', 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)\s+(.+)', line)
        if match is None or len(result) > 100000:
            raise invalid('Unsupported GoldSrc sentence definition.')
        name, sequence = match.groups()
        name = name.casefold()
        # Native tables contain repeated sentence names. Preserve each
        # definition for the inventory; none establishes a unique text bind.
        result.append((name, sequence))
    return result


def single_sample(sequence):
    # A direct single sample has no pitch/trimming/time controls, punctuation,
    # pauses or fragment assembly. Everything else remains an inventory item.
    if re.fullmatch(r'[A-Za-z0-9_]+/[A-Za-z0-9_]+(?:\.wav)?', sequence):
        return safe_name('sound/' + sequence + ('' if sequence.casefold().endswith('.wav') else '.wav'))
    return None
