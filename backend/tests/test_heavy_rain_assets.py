"""Synthetic older Quantic PC resources; no game text, files or recordings."""
import struct
import json
import zlib

import pytest

from backend import quantic_assets as q
from backend import quantic_legacy as legacy, heavy_rain_assets as assets


def ints(*values):
    return struct.pack('>' + 'I' * len(values), *values)


def string(value):
    data = value.encode('ascii')
    return ints(len(data)) + data


def compact_localization(*, declared=True, pointer=0, source='HOL', source_voice=42, flags=1):
    deps = ints(4091, 42) + b'\1' + bytes(8) if declared else b''
    body = b'COM_CONT' + ints(3, int(declared)) + deps
    body += b'LOADCONT' + ints(2) + b'LOCALIZ_' + ints(5) + b'\1' + ints(2)
    for code, text, voice in [(source, 'Een synthetische zin.', source_voice), ('SCH', '合成测试句子。', 0)]:
        encoded = text.encode('utf-16-be')
        rows = ints(101, 0, len(encoded) // 2, flags, pointer, 4091 if voice else 0, voice)
        body += b'\2' + string(code) + ints(1) + rows + ints(len(encoded)) + encoded
    return body


def entry(tmp_path, data):
    index = tmp_path / 'Synthetic_WIN.idx'
    index.with_suffix('.dat').write_bytes(data)
    return q.Entry(index, 29, 1, 0, len(data), 0, 0)


def segmented(parts):
    packed, rows = bytearray(), []
    for part in parts:
        compressor = zlib.compressobj(wbits=-15)
        data = compressor.compress(part) + compressor.flush()
        if len(packed) % 2:
            packed.append(0)
        rows.append(struct.pack('>HHI', len(data), len(part), len(packed) | 1))
        packed.extend(data)
    base = (16 + len(parts) * 8 + 15) // 16 * 16
    return b'segs' + struct.pack('>HHII', 1, len(parts), sum(map(len, parts)), len(packed)) + b''.join(rows) + bytes(base - 16 - len(rows) * 8) + packed


def container():
    refs = ints(1016, 17, 4091, 42) + b'\5' + ints(4092, 42)
    bodies = [compact_localization(), b'typed voice metadata', b'typed offset metadata']
    stream = b''.join(ints(len(body) + 4) + bytes(4) + b'\1' + bytes(5) + body for body in bodies)
    return b'DC_INFO ' + ints(2, len(refs) + 4, 3) + refs + b'DC_DATA ' + ints(7, len(stream)) + stream


def partition(*, single=False, silent=False):
    payload = b'NULL' + ints(16000) if silent else b'\xff\xfa\x92\xc0' + bytes(12)
    block = ints(0) + struct.pack('>2f', 0, .5) + ints(0)
    block += ints(4) + b'000000000000' if single else ints(8, 16 + len(payload)) + b'00000000'
    block += payload
    footer = b'PARTOFFS' + ints(2, 16, 4092, 42, 1, 0)
    footer += b'STREAMAB' + ints(1, 0)
    footer += b'HEADER__' + ints(4, 16, 1, 2) + struct.pack('>2f', 100, 400)
    data = b'PARTITIO' + ints(2, 2048 + len(block) - 16) + bytes(2032) + block + footer
    offsets = b'TBOFFSET' + ints(4, 1, 0, len(block), len(block))
    return data, offsets, payload


def test_raw_deflate_ranges_are_bounded_and_cross_chunk_boundaries(tmp_path):
    reader = legacy.Metadata(entry(tmp_path, segmented([b'a' * 100, b'b' * 120])))
    assert reader.read(95, 10) == b'aaaaabbbbb'
    assert reader.read(220, 0) == b''
    with pytest.raises(ValueError, match='bounds'):
        reader.read(219, 2)
    with pytest.raises(ValueError, match='bounds'):
        reader.read(0, q.METADATA_LIMIT + 1)


def test_unused_scene_chunk_is_not_inflated(tmp_path):
    data = bytearray(segmented([b'first', b'unrelated']))
    base = 32
    second = struct.unpack_from('>I', data, 28)[0] & ~1
    data[base + second] ^= 255
    reader = legacy.Metadata(entry(tmp_path, data))
    assert reader.read(0, 5) == b'first'
    with pytest.raises(ValueError):
        reader.read(5, 9)


def test_typed_components_keep_the_authored_language_without_guessing(tmp_path):
    reader = legacy.Metadata(entry(tmp_path, b'QZIP\0' + container()))
    refs, _ = legacy.references(reader)
    assert refs == [(1016, 17, None), (4091, 42, 5), (4092, 42, None)]
    components = list(legacy.components(reader, {1016, 4092}))
    assert [(kind, identity) for kind, identity, _, _ in components] == [(1016, 17), (4092, 42)]
    tables = legacy.localization(components[0][3])
    assert tables['HOL']['texts'][101] == 'Een synthetische zin.'
    assert tables['HOL']['bindings'][101] == (4091, 42)
    assert tables['SCH']['texts'][101] == '合成测试句子。'
    assert tables['SCH']['bindings'][101] is None


def test_older_dependency_table_does_not_invent_a_voice_language(tmp_path):
    data = b'DC_INFO ' + ints(1, 12, 1, 4091, 42)
    reader = legacy.Metadata(entry(tmp_path, b'QZIP\0' + data))
    assert legacy.references(reader)[0] == [(4091, 42, None)]


def test_undeclared_localization_pointer_cannot_select_original_audio():
    assert legacy.localization(compact_localization(declared=False))['HOL']['bindings'][101] is None
    with pytest.raises(ValueError, match='pointer'):
        legacy.localization(compact_localization(pointer=1))
    with pytest.raises(ValueError):
        legacy.localization(compact_localization()[:-1])


def write_archive(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    content, rows = bytearray(), []
    for kind, identity, data in entries:
        rows.append(struct.pack('>7I', kind, 1, identity, len(content), len(data), 0, 0))
        content.extend(data)
    path.write_bytes(q.MAGIC + ints(13, 0) + b'ZEP' * 24 + ints(len(rows)) + b''.join(rows))
    path.with_suffix('.dat').write_bytes(content)


def installation(root, locale='nl', *, language=None):
    code = assets.TEXT_LOCALES[locale]
    language = assets.LANGUAGE_IDS[code] if language is None else language
    raw, offsets, _ = partition()
    refs = ints(1016, 17, 4091, 42) + bytes([language]) + ints(4092, 42)
    bodies = [compact_localization(source=code), b'typed voice metadata', offsets]
    stream = b''.join(ints(len(body) + 4) + bytes(4) + b'\1' + bytes(5) + body for body in bodies)
    meta = b'QZIP\0DC_INFO ' + ints(2, len(refs) + 4, 3) + refs + b'DC_DATA ' + ints(7, len(stream)) + stream
    write_archive(root / assets.SCENE_INDEXES[1], [(29, 19, meta)])
    write_archive(root / assets.VOICE_INDEXES[0], [(4091, 42, raw)])
    return raw


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_each_selected_voice_language_keeps_official_source_and_target_distinct(tmp_path, locale):
    installation(tmp_path, locale)
    result = assets.index_language(tmp_path, tmp_path / 'cache', locale, ['zh-hans', 'ar'])
    assert len(result['records']) == 1
    row = result['records'][0]
    assert row['source_locale'] == row['audio_locale'] == row['audio']['locale'] == locale
    assert row['source_text'] == 'Een synthetische zin.'
    assert row['texts']['zh-Hans'] == '合成测试句子。'
    assert row['audio']['start_ms'] == 100 and row['audio']['end_ms'] == 400
    assert row['audio']['language_id'] == assets.LANGUAGE_IDS[assets.TEXT_LOCALES[locale]]
    assert result['missing_translation_locales'] == ['ar']
    assert 'ar' not in row['texts'] and set(row['texts']) == {locale, 'zh-Hans'}


def test_original_voice_language_and_conflicting_banks_are_not_guessed(tmp_path):
    installation(tmp_path, language=0)
    missing = assets.index_language(tmp_path, tmp_path / 'cache', 'nl', ['zh-hans'])
    assert missing['records'][0]['voice_status'] == 'unavailable'
    assert missing['records'][0]['audio'] is None
    raw = installation(tmp_path)
    write_archive(tmp_path / assets.VOICE_INDEXES[1], [(4091, 42, raw[:-1])])
    with pytest.raises(ValueError, match='Conflicting'):
        assets.index_language(tmp_path, tmp_path / 'cache', 'nl', ['zh-hans'])


def test_unknown_patch_and_unsafe_voice_references_fail_explicitly(tmp_path):
    installation(tmp_path)
    write_archive(tmp_path / 'Resources/UnverifiedPatch.idx', [])
    with pytest.raises(ValueError, match='patch priority'):
        assets.index_language(tmp_path, tmp_path / 'cache', 'nl', ['zh-hans'])
    with pytest.raises(ValueError, match='reference'):
        assets.extract_voice(tmp_path, {'locale': 'nl', 'identity': 42, 'index': '../voice.idx'}, None, tmp_path)


def test_authored_pages_are_anchors_for_one_complete_paragraph(tmp_path):
    assert assets.pages('{S}Eerste pagina.{B}Tweede pagina.') == ['Eerste pagina.', 'Tweede pagina.']


@pytest.mark.parametrize('single,silent', [(False, False), (True, False), (False, True), (True, True)])
def test_original_audio_uses_authored_sizes_and_millisecond_timings(single, silent):
    data, offsets, payload = partition(single=single, silent=silent)
    identity, times, _ = legacy.partition(data)
    assert identity == 42 and times == [(.1, .4)]
    assert legacy.partition_blocks(data, offsets) == [None if silent else payload]


@pytest.mark.parametrize('change', ['truncated', 'offset', 'frame', 'timing', 'duration'])
def test_invalid_original_audio_is_rejected(change):
    data, offsets, _ = partition()
    if change == 'truncated':
        data = data[:-1]
    elif change == 'offset':
        offsets = offsets[:16] + ints(100000) + offsets[20:]
    elif change == 'frame':
        data = data[:2048] + ints(1) + data[2052:]
    elif change == 'timing':
        data = data[:-8] + struct.pack('>2f', float('nan'), 400)
    else:
        data = data[:-8] + struct.pack('>2f', 500, 100)
    with pytest.raises(ValueError):
        legacy.partition_blocks(data, offsets)


@pytest.mark.parametrize('origin_ms', [-.022675842, -.068027526])
def test_shipped_sample_offset_before_zero_is_an_authored_timing_origin(origin_ms):
    data, _, _ = partition()
    data = data[:-8] + struct.pack('>2f', origin_ms, 400)
    assert legacy.partition(data)[1] == [(0, .4)]
    with pytest.raises(ValueError, match='times'):
        legacy.partition(data[:-8] + struct.pack('>2f', -1, 400))


def test_runtime_page_needs_a_long_exact_unique_bound_paragraph(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    first = 'We vertrekken morgen samen vroeg. Neem de blauwe koffer mee naar het station.'
    second = 'We vertrekken morgen samen vroeg. Laat de groene koffer hier in de slaapkamer.'
    rows = []
    for identity, text in enumerate([first, second]):
        rows.append({'text_id': f'heavyrain:synthetic:{identity}', 'source_locale': 'nl', 'audio_locale': 'nl',
            'source_text': text, 'texts': {'nl': text, 'zh-Hans': f'第{identity}个合成段落。请把蓝色行李箱带到车站去。'},
            'audio': {'identity': identity}})
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'heavyrain', 'source_locale': 'nl', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('heavyrain', tmp_path); index.target_locale = 'zh-Hans'
    hit = index.match_text('Neem de blauwe koffer mee naar het station.')
    assert hit.text_id == rows[0]['text_id'] and hit.source_text == first
    assert hit.translation_text == rows[0]['texts']['zh-Hans']
    assert not index.match_text('We vertrekken morgen samen vroeg.')
    assert not index.match_text('koffer mee')
    assert not index.match_lines(['Neem de blauwe koffers mee naar het station.'], exact_only=True)
    assert not index.match_text('Neem de blauwe koffer mee naar het station.', channel='tip')


def test_document_text_above_subtitles_cannot_capture_its_spoken_paragraph():
    from backend.capture import CaptureService
    from backend.models import CaptureRegion
    def row(text, y):
        return {'text': text, 'bounding_rect': {'x1': 100, 'x2': 800, 'x3': 800, 'x4': 100,
            'y1': y, 'y2': y, 'y3': y + 20, 'y4': y + 20}}
    document = row('Een volledig leesbare brief in de spelwereld.', 30)
    caption = row('De gesproken ondertitel blijft onderaan staan.', 160)
    response = CaptureService._local_subtitle_rows({'lines': [document, caption]}, (1000, 280),
        CaptureRegion(left=0, top=.70, width=1, height=.28), 'heavyrain')
    assert response['lines'] == [caption]
