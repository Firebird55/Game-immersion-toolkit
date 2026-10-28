"""Copyright-free Fox binary fixtures exercise the actual archive/media path."""
from pathlib import Path
import hashlib
import struct
import zlib

import pytest

from backend import fox_dialogue as fox, mgsv_tpp_assets as assets
from backend.local_game import LocalDialogue
from backend.preparation_errors import PreparationFailure


def chunk(kind, payload, align=True):
    return kind + struct.pack('<I', len(payload)) + payload + (b'\0' if align and len(payload) % 2 else b'')


def wem(label='test_line_001'):
    fmt = chunk(b'fmt ', struct.pack('<HHIIHH', 1, 1, 8000, 16000, 2, 16))
    labels = chunk(b'LIST', b'adtl' + chunk(b'labl', struct.pack('<I', 1) + label.encode() + b'\0'))
    body = b'WAVE' + fmt + labels + chunk(b'data', b'\0\1' * 20)
    return b'RIFF' + struct.pack('<I', len(body)) + body


def subp(locale, rows, *, version=0x13):
    enc = {'ru': 'iso8859-5', 'ja': 'utf-8', 'pt-BR': 'utf-8'}.get(locale, 'latin1')
    result = bytearray(bytes((version, assets.TEXT_LOCALES.index(locale))) + struct.pack('<H', len(rows)) + bytes(8 * len(rows)))
    for index, (label, pages) in enumerate(rows.items()):
        struct.pack_into('<II', result, 4 + index * 8, fox.strcode32(label), len(result))
        raw = '$'.join(pages).encode(enc) + b'\0'
        result += struct.pack('<HBBHHHH', 0x4c01, len(pages), 0, len(raw), len(raw), 7, 0x300)
        result += b''.join(struct.pack('<HH', i * 30, (i + 1) * 30) for i in range(len(pages))) + raw
    return bytes(result)


def fpk(files):
    result = bytearray(48 + len(files) * 48)
    result[:10] = b'foxfpk\0win'
    struct.pack_into('<III', result, 32, 2, len(files), 0)
    for index, (name, data) in enumerate(files.items()):
        name_at = len(result)
        result += name.encode() + b'\0'
        at = len(result)
        result += data
        struct.pack_into('<4Q', result, 48 + index * 48, at, len(data), name_at, len(name))
        result[80 + index * 48:96 + index * 48] = hashlib.md5(name.encode()).digest()
    struct.pack_into('<I', result, 10, len(result))
    return bytes(result)


def stp(files, version=1):
    stride = 12 if version else 8
    result = bytearray(b'STPL' + struct.pack('<HBB', len(files), version, 0) + bytes(len(files) * stride))
    result += bytes(-len(result) % 16)
    for index, (identity, payload) in enumerate(files.items()):
        at = len(result)
        struct.pack_into('<II', result, 8 + index * stride, identity, at)
        if version:
            struct.pack_into('<I', result, 16 + index * stride, at)
        result += payload + bytes(-len(payload) % 16)
    return bytes(result)


def bnk(files):
    payload, indices = bytearray(), bytearray()
    for identity, data in files.items():
        indices += struct.pack('<III', identity, len(payload), len(data))
        payload += data
    return chunk(b'BKHD', struct.pack('<IIII', 128, 1, 0, 0), False) + chunk(b'DIDX', indices, False) + chunk(b'DATA', payload, False)


def sbp(files):
    result = bytearray(b'SBPL' + struct.pack('<BHB', len(files), 8 + 12 * len(files), 0) + bytes(12 * len(files)))
    for index, (kind, data) in enumerate(files.items()):
        struct.pack_into('<4sII', result, 8 + index * 12, kind.encode().ljust(4, b'\0'), len(result), len(data))
        result += data
    return bytes(result)


def qar(root, files, name='master/data1.dat', compressed=False, key=None):
    result = bytearray(1024)
    struct.pack_into('<8I', result, 0, 0x52415153, fox.XOR[0], len(files) ^ fox.XOR[1], fox.XOR[2], 0, 1024 ^ fox.XOR[0], 1 ^ fox.XOR[0], fox.XOR[1])
    for index, (name_hash, plain) in enumerate(files.items()):
        result += bytes(-len(result) % 1024)
        at = len(result)
        payload = zlib.compress(plain) if compressed else plain
        if key is not None:
            payload = struct.pack('<II', 0xa0f8efe6, key) + fox.crypt2(payload, key)
        stored, size = len(payload), len(plain) if compressed else len(payload)
        section = (at >> 10) << 40
        struct.pack_into('<II', result, 32 + 8 * index,
                         (section & 0xffffffff) ^ fox.XOR[(index + index * 8 // 5) % 4],
                         (section >> 32) ^ fox.XOR[(index + (index * 8 + 4) // 5) % 4])
        result += struct.pack('<8I', (name_hash & 0xffffffff) ^ fox.XOR[0], (name_hash >> 32) ^ fox.XOR[0],
                              stored ^ fox.XOR[1], size ^ fox.XOR[2], fox.XOR[3], fox.XOR[0], fox.XOR[0], fox.XOR[1])
        result += fox.crypt1(payload, name_hash)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result)


def install(root, locale='en', *, missing=False):
    (root / 'mgsvtpp.exe').touch()
    rows = {'test_line_001': ['Synthetic first page.', 'Synthetic second page.'], 'test_missing_002': ['Missing original recording.']}
    texts = {'en': rows, 'ja': {'test_line_001': ['合成の第一頁。', '合成の第二頁。'], 'test_missing_002': ['録音がありません。']}}
    files = {fox.path_hash(assets._subtitle_path(locale, text, 'common')): subp(text, values) for text, values in texts.items()}
    if not missing:
        files[fox.path_hash('/Assets/tpp/sound/asset/test.sbp')] = sbp({'stp': stp({1234: wem()})})
    qar(root, files)
    return files


def test_legacy_hash_vectors_and_label_join():
    assert fox.path_hash('/Assets/tpp/ui/Subtitles/subp/EngVoice/EngText/common.subp') == 8629369076258937622
    assert fox.path_hash('fpk', extension=False) & 0x1fff == 2629
    assert fox.wem_labels(fox.View.bytes(wem())) == ['test_line_001']


@pytest.mark.parametrize('locale', ['en', 'ja'])
def test_official_editions_use_the_same_native_archive_contract(tmp_path, locale):
    install(tmp_path, locale)
    result = assets.index_language(tmp_path, tmp_path / 'cache', locale, ['ja' if locale == 'en' else 'en'])
    voiced = [row for row in result['records'] if row['audio']]
    assert len(voiced) == 1
    row = voiced[0]
    assert len(row['ocr_texts'][locale]) == 2
    assert row['source_text'] == ' '.join(row['ocr_texts'][locale])
    assert row['audio_locale'] == locale
    assert all(LocalDialogue(**item).voice_status != 'unvoiced' for item in result['records'])
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem()
    assert result['narrative_inventory']['voice_counts'] == {'voiced': 1, 'unavailable': 1}
    for corrupted in ({'locale_name': 'ja' if locale == 'en' else 'en'}, {'subtitle_label': 'wrong'}, {'archive': '../escape.dat'}):
        with pytest.raises(PreparationFailure):
            assets.extract_voice(tmp_path, {**row['audio'], **corrupted}, Path(), tmp_path)


def test_japanese_text_does_not_masquerade_as_japanese_audio(tmp_path):
    install(tmp_path, 'en')
    assert assets.probe_voice_pack(tmp_path, 'en') == 'present'
    assert assets.probe_voice_pack(tmp_path, 'ja') == 'missing'
    with pytest.raises(PreparationFailure, match='Steam Properties'):
        assets.index_language(tmp_path, tmp_path, 'ja', ['en'])


def test_missing_recordings_are_unavailable_never_silent(tmp_path):
    install(tmp_path, missing=True)
    result = assets.index_language(tmp_path, tmp_path, 'en', ['ja'])
    assert {row['voice_status'] for row in result['records']} == {'unavailable'}


def test_conflicting_authored_text_preserves_every_variant_without_guessing_audio(tmp_path):
    files = install(tmp_path)
    files[fox.path_hash('/Assets/tpp/pack/conflicting.fpk')] = fpk({
        assets._subtitle_path('en', 'en', 's10010'): subp('en', {'test_line_001': ['Another authored variant.']})})
    qar(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', ['ja'])
    variants = [row for row in result['records'] if ':conflict:' in row['text_id']]
    assert {row['source_text'] for row in variants} == {
        'Synthetic first page. Synthetic second page.', 'Another authored variant.'}
    assert len({row['text_id'] for row in variants}) == 2
    assert all(row['audio'] is None and row['voice_status'] == 'unavailable' for row in variants)
    assert all(set(row['texts']) == {'en'} for row in variants)
    assert result['narrative_inventory']['source_conflicting_subtitle_ids'] == 1


@pytest.mark.parametrize('compressed,key', [(False, None), (True, None), (False, 19), (True, 19)])
def test_archive_bounded_decompression_and_random_access(tmp_path, compressed, key):
    payload = b'Copyright-free synthetic archive data.\0' * 120
    identity = fox.path_hash('/Assets/tpp/test.fpk')
    qar(tmp_path, {identity: payload}, compressed=compressed, key=key)
    archive = fox.FoxArchive(tmp_path)
    view = archive.view(archive.entries[identity])
    assert view.read() == payload
    assert view.read(13, 1107) == payload[13:1120]
    with pytest.raises(PreparationFailure):
        view.read(len(payload) - 1, 2)


def test_fpk_nested_names_and_embedded_bank_media():
    nested = fpk({'/Assets/tpp/test.subp': subp('ru', {'test_line_001': ['Тестовая строка.']})})
    name, offset, view = next(fox.fpk_entries(fox.View.bytes(nested)))
    assert name == '/Assets/tpp/test.subp'
    assert fox.read_subp(view.read())[fox.strcode32('test_line_001')]['pages'] == ['Тестовая строка.']
    bank = bnk({2: wem(), 7: wem('second_label')})
    entries = list(fox.bnk_entries(fox.View.bytes(bank)))
    assert [entry[0] for entry in entries] == [2, 7]
    assert fox.wem_labels(entries[1][2]) == ['second_label']


@pytest.mark.parametrize('locale', assets.TEXT_LOCALES)
def test_all_official_text_encodings_and_header_variants(locale):
    text = {'ja': '字幕の例。', 'ru': 'Пример.', 'pt-BR': 'Coração.'}.get(locale, 'Exemple synthétique.')
    for version in (0x12, 0x13, 0x1b):
        parsed = fox.read_subp(subp(locale, {'caption': [text]}, version=version))
        assert parsed[fox.strcode32('caption')]['pages'] == [text]


def test_prefetch_and_non_riff_media_never_become_original_audio(tmp_path):
    files = install(tmp_path)
    files[fox.path_hash('/Assets/tpp/sound/asset/prefetch.sbp')] = sbp({'bnk': bnk({12: wem()[:50], 13: b'raw-source-format'})})
    qar(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert result['narrative_inventory']['embedded_prefetch_fragments'] == 1
    assert result['narrative_inventory']['embedded_non_riff_media'] == 1
    assert result['narrative_inventory']['voice_counts']['voiced'] == 1


def test_malformed_subtitle_offsets_and_archive_sizes_fail_closed(tmp_path):
    broken = bytearray(subp('en', {'test_line_001': ['A synthetic line.']}))
    struct.pack_into('<I', broken, 8, 0xfffffff0)
    with pytest.raises(PreparationFailure):
        fox.read_subp(broken)
    install(tmp_path)
    path = tmp_path / 'master/data1.dat'
    path.write_bytes(path.read_bytes()[:1100])
    with pytest.raises(PreparationFailure):
        fox.FoxArchive(tmp_path)


def test_ground_zeroes_stream_table_version_is_reusable():
    identity, _offset, view = next(fox.stp_entries(fox.View.bytes(stp({123: wem()}, version=0))))
    assert identity == 123
    assert view.read() == wem()


def fsm(payload):
    first, second = payload[:59], payload[59:]
    return (b'SYS ' + struct.pack('<I', 16) + bytes(8)
            + b'SND ' + struct.pack('<IdIIII', len(first) + 32, 0.0, len(payload), 2, 0, 0) + first
            + b'SND ' + struct.pack('<Id', len(second) + 16, 1.0) + second
            + b'END ' + struct.pack('<Id', 16, 2.0))


def fox_scene(movie, audio_name):
    fields = [('demoId', 11, Path(movie).stem), ('demoStreamPath', 12, movie),
              ('audioPath', 12, f'/Assets/tpp/sound/external/demo/{audio_name}.mas')]
    entity = bytearray(64)
    struct.pack_into('<H', entity, 0, 64)
    entity[6:10] = b'ent\0'
    struct.pack_into('<QHHIII', entity, 28, fox.strcode48('DemoData'), len(fields), 0, 64, 208, 208)
    strings = bytearray()
    for name, kind, value in fields:
        prop = bytearray(48)
        struct.pack_into('<QBBHHH', prop, 0, fox.strcode48(name), kind, 0, 1, 32, 48)
        struct.pack_into('<Q', prop, 32, fox.strcode48(value))
        entity += prop
        strings += struct.pack('<QI', fox.strcode48(value), len(value)) + value.encode()
    return struct.pack('<5I12x', 0x786f62f2, 0x35, 1, 32 + len(entity), 32) + entity + strings + bytes(8)


def test_authored_scene_alias_binds_and_revalidates_exact_metadata(tmp_path):
    files = install(tmp_path)
    name, movie = 'p51_020000', '/Assets/tpp/demo/demo_stream/p51_020000_000_final.fsm'
    files[fox.path_hash(assets._subtitle_path('en', 'en', 's10010'))] = subp('en', {
        name: ['Synthetic renamed movie.'], Path(movie).stem: ['A different subtitle with a coincidentally matching movie name.']})
    files[fox.path_hash(movie)] = fsm(wem('original_scene_mix'))
    scene = fox_scene(movie, name)
    files[fox.path_hash('/Assets/tpp/pack/scene.fpkd')] = fpk({'/Assets/tpp/demo/scene.fox2': scene})
    files[fox.path_hash('/Assets/tpp/pack/scene.fpk')] = fpk({
        '/Assets/tpp/demo/p51_020000_000_final.sand': b'synthetic scene metadata'})
    qar(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row = next(row for row in result['records'] if row['dialogue_kind'] == 'cinematic')
    assert row['audio']['performance_name'] == 'p51_020000_000_final'
    assert row['audio']['scene_binding']['subtitle_name'] == name
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('original_scene_mix')
    assert result['narrative_inventory']['bound_authored_scene_relations'] == 1
    assert sum(row['dialogue_kind'] == 'cinematic' and row['audio'] is not None for row in result['records']) == 1
    coincidental = next(row for row in result['records'] if row['source_text'].startswith('A different subtitle'))
    assert coincidental['voice_status'] == 'unavailable'
    changed = {**row['audio'], 'scene_binding': {**row['audio']['scene_binding'], 'subtitle_name': 'wrong'}}
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, changed, Path(), tmp_path)
    changed = {**row['audio'], 'scene_binding': {**row['audio']['scene_binding'], 'entity': 4}}
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, changed, Path(), tmp_path)
    broken = bytearray(scene)
    struct.pack_into('<I', broken, 32 + 48, 0xfffffff0)
    with pytest.raises(PreparationFailure):
        fox.demo_bindings(fox.View.bytes(broken))
    broken = bytearray(scene)
    struct.pack_into('<H', broken, 32 + 64 + 14, 16)
    with pytest.raises(PreparationFailure):
        fox.demo_bindings(fox.View.bytes(broken))


def test_scene_string_lookup_must_match_its_authored_hash():
    movie = '/Assets/tpp/demo/demo_stream/p51_020000_final.fsm'
    scene = fox_scene(movie, 'p51_020000')
    corrupted = scene.replace(movie.encode(), movie.replace('020000', '999999').encode())
    assert fox.demo_bindings(fox.View.bytes(corrupted)) == []


def test_cassette_and_cinematic_performances_require_shared_exact_ids(tmp_path):
    files = install(tmp_path)
    scenes = {'p21_010000': ['Synthetic scene page one.', 'Synthetic scene page two.'],
              'tp_c_00000_01': ['Synthetic cassette transcript.']}
    files[fox.path_hash(assets._subtitle_path('en', 'en', 's10010'))] = subp('en', scenes)
    scene_path = '/Assets/tpp/demo/demo_stream/p21_010000.fsm'
    files[fox.path_hash(scene_path)] = fsm(wem('unrelated_mix_label'))
    files[fox.path_hash('/Assets/tpp/pack/synthetic.fpk')] = fpk({'/Assets/tpp/demo/p21_010000_000_final.sand': b'synthetic scene metadata'})
    files[fox.path_hash('/Assets/tpp/sound/external/tape/tp_c_00000_01.wem')] = wem('unrelated_tape_label')
    qar(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    for kind, label in [('cinematic', 'unrelated_mix_label'), ('cassette_tape', 'unrelated_tape_label')]:
        row = next(x for x in result['records'] if x['audio'] and x['dialogue_kind'] == kind)
        assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem(label)
        with pytest.raises(PreparationFailure):
            assets.extract_voice(tmp_path, {**row['audio'], 'performance_name': 'unrelated_name'}, Path(), tmp_path)
    view = fox.fsm_audio(fox.View.bytes(fsm(wem())))
    assert view.read(35, 50) == wem()[35:85]


def test_authored_label_case_normalization_preserves_original_label(tmp_path):
    files = install(tmp_path)
    files[fox.path_hash('/Assets/tpp/sound/asset/test.sbp')] = sbp({'stp': stp({1234: wem('TEST_LINE_001')})})
    qar(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row = next(x for x in result['records'] if x['audio'])
    assert row['audio']['subtitle_label'] == 'TEST_LINE_001'
    assert row['audio']['subtitle_id'] == fox.strcode32('test_line_001')
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('TEST_LINE_001')


def test_big_endian_lng2_and_legacy_japanese_subtitles():
    text = 'Synthetic localization.'
    raw = text.encode() + b'\0'
    values, keys = 24, 24 + 2 + len(raw)
    data = b'LANG' + struct.pack('>I', 3) + b'BE\0\0' + struct.pack('>III', 1, values, keys)
    data += b'\x01\0' + raw + struct.pack('>II', 123, 0)
    assert fox.read_lang(data) == {123: text}
    legacy = b'\x01L' + subp('ja', {'caption': ['合成字幕。']})[2:]
    assert fox.read_subp(legacy, 'utf-8')[fox.strcode32('caption')]['pages'] == ['合成字幕。']
    with pytest.raises(PreparationFailure):
        fox.read_subp(legacy)


def test_movie_truncation_and_missing_compressed_trailer_fail_closed(tmp_path):
    with pytest.raises(PreparationFailure):
        fox.fsm_audio(fox.View.bytes(fsm(wem())[:-16]))
    identity = fox.path_hash('/Assets/tpp/test.fpk')
    qar(tmp_path, {identity: b'Synthetic data ' * 100}, compressed=True)
    path = tmp_path / 'master/data1.dat'
    raw = bytearray(path.read_bytes())
    stored = struct.unpack_from('<I', raw, 1024 + 8)[0] ^ fox.XOR[1]
    struct.pack_into('<I', raw, 1024 + 8, (stored - 3) ^ fox.XOR[1])
    path.write_bytes(raw[:-3])
    archive = fox.FoxArchive(tmp_path)
    with pytest.raises(PreparationFailure):
        archive.view(archive.entries[identity]).read()
