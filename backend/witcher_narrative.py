"""Bounded, read-only narrative metadata from installed REDengine 3 bundles.

Only typed scene/journal fields and ReadableItem definitions classify silence.
Localization and speech absence alone never establish that a line is unvoiced.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import struct
import xml.etree.ElementTree as ET
import zlib

from .preparation_errors import PreparationFailure

MAX_RESOURCE = 32 * 1024 * 1024
_JOURNAL = {
    'CJournalQuestDescriptionEntry': 'journal',
    'CJournalCharacterDescription': 'character_profile',
    'CJournalCreatureDescriptionEntry': 'bestiary',
    'CJournalGlossaryDescription': 'readable',
    'CJournalPlaceDescription': 'readable',
}


def _invalid(message):
    return PreparationFailure('witcher_narrative_format', message +
        ' The installed game may have updated. Update the toolkit and verify the game files before retrying.')


def bundle_sources(install: Path) -> list[Path]:
    return sorted({p for folder in ('content', 'dlc') if (install / folder).is_dir()
                   for p in (install / folder).rglob('*.bundle')}, key=lambda p: p.as_posix().casefold())


def bundle_entries(path: Path):
    """Read legacy v3 (320-byte) and retail v5 (304-byte) TOCs only."""
    size = path.stat().st_size
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32 or header[:8] != b'POTATO70':
            raise _invalid('The Witcher bundle header is unsupported or incomplete.')
        table_size, version = struct.unpack_from('<IH', header, 16)
        stride = {3: 320, 5: 304}.get(version)
        if not stride or table_size % stride or table_size > 256 * 1024 * 1024 or table_size + 32 > size:
            raise _invalid('The Witcher bundle table version or bounds are unsupported.')
        raw = stream.read(table_size)
        if len(raw) != table_size:
            raise _invalid('The Witcher bundle table changed while being read.')
    for offset in range(0, table_size, stride):
        entry = raw[offset:offset + stride]
        if b'\0' not in entry[:256]:
            raise _invalid('A Witcher bundle entry has an invalid path.')
        name = entry[:256].split(b'\0', 1)[0].decode('latin1').replace('\\', '/')
        parts = PurePosixPath(name)
        if not name or parts.is_absolute() or ':' in name or '..' in parts.parts:
            raise _invalid('A Witcher bundle entry has an unsafe path.')
        if version == 5:
            position, unpacked, stored, crc, compression = struct.unpack_from('<QIIII', entry, 272)
        else:
            unpacked, stored, position = struct.unpack_from('<III', entry, 276)
            crc, compression = struct.unpack_from('<II', entry, 312)
        if position < table_size + 32 or position + stored > size:
            raise _invalid('A Witcher bundle entry falls outside its installed archive.')
        yield name, (position, unpacked, stored, crc, compression)


def resource_bytes(stream, entry):
    position, unpacked, stored, crc, compression = entry
    if not 0 < unpacked <= MAX_RESOURCE or not 0 < stored <= MAX_RESOURCE:
        raise _invalid('A Witcher narrative resource exceeds the supported size.')
    stream.seek(position)
    raw = stream.read(stored)
    if len(raw) != stored:
        raise _invalid('A Witcher narrative resource is incomplete.')
    try:
        if compression == 0:
            data = raw
        elif compression == 1:
            decoder = zlib.decompressobj()
            data = decoder.decompress(raw, unpacked + 1)
            if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError('invalid compressed stream')
        elif compression in (4, 5):
            data = _lz4(raw, unpacked)
        else:
            raise _invalid(f'Witcher narrative compression {compression} is not supported by this reader.')
    except (ValueError, zlib.error) as error:
        if isinstance(error, PreparationFailure):
            raise
        raise _invalid('A compressed Witcher narrative resource is corrupt.') from error
    if len(data) != unpacked or crc and zlib.crc32(data) != crc:
        raise _invalid('A Witcher narrative resource failed its size or checksum check.')
    return data


def _lz4(raw, expected):
    """Raw LZ4 blocks used by legacy bundles, with an explicit output bound."""
    out, position = bytearray(), 0
    def length(initial):
        nonlocal position
        result = initial
        if initial == 15:
            while True:
                if position >= len(raw):
                    raise ValueError('incomplete LZ4 length')
                value = raw[position]; position += 1; result += value
                if result > expected:
                    raise ValueError('oversized LZ4 sequence')
                if value != 255:
                    break
        return result
    while position < len(raw):
        token = raw[position]; position += 1
        literal = length(token >> 4)
        if position + literal > len(raw) or len(out) + literal > expected:
            raise ValueError('invalid LZ4 literal')
        out.extend(raw[position:position + literal]); position += literal
        if position == len(raw):
            break
        if position + 2 > len(raw):
            raise ValueError('incomplete LZ4 offset')
        distance = int.from_bytes(raw[position:position + 2], 'little'); position += 2
        count = length(token & 15) + 4
        if not 0 < distance <= len(out) or len(out) + count > expected:
            raise ValueError('invalid LZ4 match')
        for _ in range(count):
            out.append(out[-distance])
    if len(out) != expected:
        raise ValueError('incomplete LZ4 block')
    return bytes(out)


def typed_chunks(data: bytes):
    if len(data) < 160 or data[:4] != b'CR2W' or not 159 <= struct.unpack_from('<I', data, 4)[0] <= 164:
        raise _invalid('The Witcher scene or journal version is unsupported.')
    tables = [struct.unpack_from('<III', data, 40 + i * 12) for i in range(10)]
    for index, stride in ((0, 1), (1, 8), (4, 24)):
        position, count, _ = tables[index]
        if count > 1_000_000 or position < 160 or position + count * stride > len(data):
            raise _invalid('The Witcher scene or journal tables are incomplete.')
    strings, strings_size, _ = tables[0]
    names_offset, name_count, _ = tables[1]
    names = []
    for i in range(name_count):
        offset = struct.unpack_from('<I', data, names_offset + i * 8)[0]
        if offset >= strings_size:
            raise _invalid('The Witcher narrative name table is invalid.')
        end = data.find(b'\0', strings + offset, strings + strings_size)
        if end < 0:
            raise _invalid('The Witcher narrative name is incomplete.')
        names.append(data[strings + offset:end].decode('latin1'))
    position, count, _ = tables[4]
    for i in range(count):
        class_id, _flags, _parent, length, start, _template, _crc = struct.unpack_from('<HHIIIII', data, position + i * 24)
        if class_id >= len(names) or length < 3 or start < 160 or start + length > len(data):
            raise _invalid('The Witcher narrative object is outside its resource.')
        kind = names[class_id]
        if kind not in {*_JOURNAL, 'CStorySceneLine', 'CStorySceneChoiceLine', 'CStorySceneQuestChoiceLine', 'CJournalStoryBookPageDescription'}:
            continue
        if data[start] != 0:
            raise _invalid('The Witcher narrative object layout has changed.')
        cursor, end, fields = start + 1, start + length, {}
        while cursor + 2 <= end:
            name_id = struct.unpack_from('<H', data, cursor)[0]
            if name_id == 0:
                break
            if cursor + 8 > end:
                raise _invalid('The Witcher narrative property is incomplete.')
            name_id, type_id, size = struct.unpack_from('<HHI', data, cursor)
            if max(name_id, type_id) >= len(names) or size < 4 or cursor + 4 + size > end:
                raise _invalid('The Witcher narrative property bounds are invalid.')
            name, value_type = names[name_id], names[type_id]
            value = data[cursor + 8:cursor + 4 + size]
            cursor += 4 + size
            if value_type == 'LocalizedString':
                if len(value) != 4 or name in fields:
                    raise _invalid('The Witcher localized reference layout has changed.')
                fields[name] = struct.unpack('<I', value)[0]
            elif value_type == 'Bool' and name in ('isSilent', 'isBackgroundLine'):
                if value not in (b'\0', b'\1') or name in fields:
                    raise _invalid('The Witcher dialogue voice-state field is invalid.')
                fields[name] = value == b'\1'
        else:
            raise _invalid('The Witcher narrative property list is incomplete.')
        yield kind, fields


def key_hash(value: str) -> int:
    result = 0
    raw = value.encode('utf-16-le')
    for (unit,) in struct.iter_unpack('<H', raw):
        result = (result * 31 + unit) & 0xFFFFFFFF
    return result


def readable_keys(data):
    try:
        text = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
    except UnicodeDecodeError as error:
        raise _invalid('The Witcher item definition encoding is unsupported.') from error
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise _invalid('The Witcher item XML contains unsupported declarations.')
    # Some shipped loot definitions have invalid duplicate attributes but no
    # readable items. They are unrelated to this narrowly scoped reader.
    if 'ReadableItem' not in text:
        return
    try:
        # Honor the byte-order mark; some shipped UTF-8 files declare UTF16.
        root = ET.fromstring(text)
    except (ValueError, ET.ParseError) as error:
        raise _invalid('The Witcher item definitions are incomplete.') from error
    for item in root.iter('item'):
        tags = {value.strip() for node in item.findall('tags') for value in (node.text or '').split(',')}
        key = item.get('localisation_key_name')
        if 'ReadableItem' in tags and key and item.get('name') != 'Gwent Almanac':
            # Exact installed inventoryComponent.GetBookTextByName contract.
            yield key_hash(key + '_text')


def inventory(install, progress=lambda _message: None):
    refs, keys, counts = defaultdict(set), defaultdict(set), Counter()
    paths = bundle_sources(install)
    for number, path in enumerate(paths, 1):
        progress(f'Checking Witcher scene and readable metadata: bundle {number}/{len(paths)}')
        parts = path.relative_to(install).parts
        group = '/'.join(parts[:2]) if parts[0].lower() == 'dlc' else 'base'
        with path.open('rb') as stream:
            for name, entry in bundle_entries(path):
                lower = name.casefold()
                if lower.endswith('.subs'):
                    counts['cinematic_subtitle_files'] += 1
                    continue
                if lower.endswith('.xml') and '/items' in lower:
                    keys[group].update(readable_keys(resource_bytes(stream, entry)))
                if not lower.endswith(('.journal', '.w2scene')):
                    continue
                counts['journal_files' if lower.endswith('.journal') else 'scene_files'] += 1
                for kind, fields in typed_chunks(resource_bytes(stream, entry)):
                    if kind == 'CStorySceneLine':
                        identity = fields.get('dialogLine')
                        presentation = 'npc_chatter' if fields.get('isBackgroundLine') else 'dialogue'
                        state = 'unvoiced' if fields.get('isSilent') else 'unavailable'
                    elif kind in ('CStorySceneChoiceLine', 'CStorySceneQuestChoiceLine'):
                        identity = fields.get('choiceLine' if kind == 'CStorySceneChoiceLine' else 'commentText')
                        presentation, state = 'choice', 'unvoiced'
                    else:
                        identity = fields.get('description')
                        presentation = _JOURNAL.get(kind, 'cinematic')
                        state = 'unvoiced' if kind in _JOURNAL else 'unavailable'
                    if identity:
                        refs[(group, identity)].add((presentation, state))
                        counts[presentation + '_references'] += 1
    return refs, keys, dict(counts)
