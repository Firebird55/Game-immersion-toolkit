import io
import json
from pathlib import Path
from types import SimpleNamespace
import struct
import zlib

import pytest

from backend import witcher_assets as assets
from backend import witcher_narrative as narrative
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure
from backend.tests.test_witcher import strings_file, speech_file, bit6


def cr2w(chunks):
    names = ['']
    for kind, properties in chunks:
        for name in [kind, *(v for prop in properties for v in prop[:2])]:
            if name not in names:
                names.append(name)
    strings, name_rows = bytearray(), bytearray()
    for name in names:
        name_rows.extend(struct.pack('<II', len(strings), 0))
        strings.extend(name.encode() + b'\0')
    exports, bodies = bytearray(), bytearray()
    exports_at = 160 + len(strings) + len(name_rows)
    body_at = exports_at + len(chunks) * 24
    for kind, properties in chunks:
        body = bytearray(b'\0')
        for name, value_type, value in properties:
            raw = bytes([value]) if value_type == 'Bool' else struct.pack('<I', value)
            body.extend(struct.pack('<HHI', names.index(name), names.index(value_type), len(raw) + 4) + raw)
        body.extend(b'\0\0')
        exports.extend(struct.pack('<HHIIIII', names.index(kind), 0, 0, len(body), body_at + len(bodies), 0, 0))
        bodies.extend(body)
    header = bytearray(160)
    header[:4] = b'CR2W'
    struct.pack_into('<I', header, 4, 164)
    for number, offset, count in [(0, 160, len(strings)), (1, 160 + len(strings), len(names)), (4, exports_at, len(chunks))]:
        struct.pack_into('<III', header, 40 + number * 12, offset, count, 0)
    return bytes(header + strings + name_rows + exports + bodies)


def bundle(path, resources, version=5, compression=0):
    stride = 304 if version == 5 else 320
    header = bytearray(32)
    header[:8] = b'POTATO70'
    struct.pack_into('<IH', header, 16, len(resources) * stride, version)
    table, bodies = bytearray(), bytearray()
    for name, data in resources:
        stored = zlib.compress(data) if compression == 1 else data
        row = bytearray(stride)
        row[:len(name)] = name.encode()
        offset = 32 + len(resources) * stride + len(bodies)
        if version == 5:
            struct.pack_into('<QIIII', row, 272, offset, len(data), len(stored), zlib.crc32(data), compression)
        else:
            struct.pack_into('<III', row, 276, len(data), len(stored), offset)
            struct.pack_into('<II', row, 312, zlib.crc32(data), compression)
        table.extend(row); bodies.extend(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + table + bodies)


def add_keys(path, count, keys):
    raw = path.read_bytes()
    start = 10 + len(bit6(count)) + count * 12
    path.write_bytes(raw[:start] + bit6(len(keys)) + b''.join(struct.pack('<II', key, identity) for key, identity in keys) + raw[start + 1:])


def test_authored_silence_choices_books_and_missing_speech_are_separate(tmp_path):
    folder = tmp_path / 'content/content0'
    strings_file(folder / 'en.w3strings', [(i, f'Synthetic narrative sentence {i}.') for i in range(1, 9)])
    add_keys(folder / 'en.w3strings', 8, [(narrative.key_hash('book_key_text'), 7)])
    speech_file(folder / 'enpc.w3speech', [1])
    scene = cr2w([
        ('CStorySceneLine', [('dialogLine', 'LocalizedString', 1)]),
        ('CStorySceneLine', [('dialogLine', 'LocalizedString', 2)]),
        ('CStorySceneLine', [('dialogLine', 'LocalizedString', 3), ('isSilent', 'Bool', 1)]),
        ('CStorySceneQuestChoiceLine', [('commentText', 'LocalizedString', 4)]),
        ('CJournalCharacterDescription', [('description', 'LocalizedString', 5)]),
        ('CJournalStoryBookPageDescription', [('description', 'LocalizedString', 6)]),
    ])
    xml = b'<redxml><item name="Book" localisation_key_name="book_key"><tags>ReadableItem, Quest</tags></item></redxml>'
    bundle(folder / 'bundles/story.bundle', [('story.w2scene', scene), ('gameplay/items/def_item_books.xml', xml)])
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    states = {r['text_id']: r['voice_status'] for r in result['records']}
    assert list(states.values()) == ['voiced', 'unavailable', 'unvoiced', 'unvoiced', 'unvoiced', 'unavailable', 'unvoiced', 'unknown']
    assert next(r for r in result['records'] if r['text_id'] == 'witcher3:7')['dialogue_kind'] == 'readable'
    (tmp_path / 'textmap.json').write_text(json.dumps(result), encoding='utf8')
    index = MultilingualTextIndex('witcher3', tmp_path)
    assert index.match_lines(['Synthetic narrative sentence 7.'], exact_only=True) is None
    index.capture_unvoiced = True
    assert index.match_lines(['Synthetic narrative sentence 7.'], exact_only=True).voice_status == 'unvoiced'
    assert index.match_lines(['Synthetic narrative sentence 2.'], exact_only=True) is None


@pytest.mark.parametrize('version,compression', [(3, 0), (3, 1), (5, 0), (5, 1)])
def test_legacy_and_new_bundle_layouts_read_only_typed_resources(tmp_path, version, compression):
    data = cr2w([('CStorySceneChoiceLine', [('choiceLine', 'LocalizedString', 71)])])
    path = tmp_path / 'story.bundle'
    bundle(path, [('scene.w2scene', data)], version, compression)
    name, entry = next(narrative.bundle_entries(path))
    with path.open('rb') as stream:
        assert list(narrative.typed_chunks(narrative.resource_bytes(stream, entry))) == [('CStorySceneChoiceLine', {'choiceLine': 71})]
    raw = bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
    with path.open('rb') as stream, pytest.raises(PreparationFailure):
        narrative.resource_bytes(stream, entry)


def test_future_formats_bounds_and_unsafe_paths_fail_with_update_error(tmp_path):
    path = tmp_path / 'test.bundle'
    bundle(path, [('../escape.w2scene', b'not a scene')])
    with pytest.raises(PreparationFailure, match='unsafe path'):
        list(narrative.bundle_entries(path))
    bundle(path, [('scene.w2scene', b'not a scene')])
    raw = bytearray(path.read_bytes()); struct.pack_into('<H', raw, 20, 999); path.write_bytes(raw)
    with pytest.raises(PreparationFailure, match='version') as error:
        list(narrative.bundle_entries(path))
    assert error.value.code == 'witcher_narrative_format'
    data = bytearray(cr2w([('CStorySceneLine', [('dialogLine', 'LocalizedString', 1)])]))
    struct.pack_into('<I', data, 4, 999)
    with pytest.raises(PreparationFailure, match='version'):
        list(narrative.typed_chunks(data))
    struct.pack_into('<I', data, 4, 164)
    struct.pack_into('<I', data, 40, len(data) + 1)
    with pytest.raises(PreparationFailure, match='tables'):
        list(narrative.typed_chunks(data))

    strings_file(tmp_path / 'en.w3strings', [(1, 'A synthetic sentence.')], version=164)
    raw = bytearray((tmp_path / 'en.w3strings').read_bytes()); struct.pack_into('<I', raw, 4, 999)
    (tmp_path / 'en.w3strings').write_bytes(raw)
    with pytest.raises(PreparationFailure) as error:
        assets.read_strings(tmp_path / 'en.w3strings')
    assert error.value.code == 'witcher_language_format'


def test_readable_xml_and_key_collisions_do_not_guess(tmp_path):
    assert list(narrative.readable_keys(b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF16"?><items><item name="Book" localisation_key_name="book"><tags>ReadableItem</tags></item></items>')) == [narrative.key_hash('book_text')]
    with pytest.raises(PreparationFailure):
        list(narrative.readable_keys(b'<!DOCTYPE x [<!ENTITY bad "x">]><x>ReadableItem</x>'))
    path = tmp_path / 'en.w3strings'
    strings_file(path, [(1, 'First book'), (2, 'Second book')])
    add_keys(path, 2, [(123, 1), (123, 2)])
    assert assets.read_string_keys(path) == {123: None}


def test_lz4_blocks_and_bundle_changes_are_bounded(tmp_path):
    assert narrative._lz4(b'\x40abcd\x04\x00\x50efghi', 13) == b'abcdabcdefghi'
    for data, expected in [(b'\x00\x00\x00', 4), (b'\xf0', 15), (b'\x40abcd', 3)]:
        with pytest.raises(ValueError):
            narrative._lz4(data, expected)
    folder = tmp_path / 'content/content0'
    strings_file(folder / 'en.w3strings', [(1, 'A sentence.')])
    stamp = assets.fingerprint(tmp_path)
    bundle(folder / 'bundles/new.bundle', [('scene.w2scene', cr2w([('CStorySceneChoiceLine', [('choiceLine', 'LocalizedString', 1)])]))])
    assert assets.fingerprint(tmp_path) != stamp


def test_bundle_v5_uses_64_bit_offsets_without_allocating_large_files(tmp_path):
    path = tmp_path / 'test.bundle'
    bundle(path, [('story.w2scene', b'example')])
    header = bytearray(path.read_bytes()[:336])
    offset = (1 << 32) + 100
    struct.pack_into('<Q', header, 32 + 272, offset)
    virtual = SimpleNamespace(open=lambda _: io.BytesIO(header), stat=lambda: SimpleNamespace(st_size=offset + 7))
    assert next(narrative.bundle_entries(virtual))[1][0] == offset


def test_conflicting_scene_silence_is_not_inferred_and_readable_breaks_are_preserved(tmp_path):
    folder = tmp_path / 'content/content0'
    strings_file(folder / 'en.w3strings', [(1, 'First paragraph.<br>Second paragraph.')])
    scene = cr2w([
        ('CStorySceneLine', [('dialogLine', 'LocalizedString', 1), ('isSilent', 'Bool', 1)]),
        ('CStorySceneLine', [('dialogLine', 'LocalizedString', 1)]),
    ])
    bundle(folder / 'bundles/story.bundle', [('story.w2scene', scene)])
    row = assets.index_language(tmp_path, tmp_path, 'en', [])['records'][0]
    assert row['voice_status'] == 'unavailable'
    assert row['source_text'] == 'First paragraph. Second paragraph.'
