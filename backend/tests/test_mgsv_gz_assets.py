"""Synthetic GZS/SAB/SANI fixtures; no game text, recordings or binaries."""
from pathlib import Path
import json
import struct

import pytest

from backend import fox_dialogue as fox, mgsv_gz_archive as gz, mgsv_gz_assets as assets
from backend.local_game import LocalDialogue
from backend.preparation_errors import PreparationFailure
from backend.tests.test_mgsv_tpp_assets import bnk, fpk as win_fpk, fsm, sbp, stp, subp, wem


def fpk(files):
    data = bytearray(win_fpk(files))
    data[7:10] = b'ste'
    return bytes(data)


def gzs(root, files, key=None):
    data, table = bytearray(), []
    for identity, raw in files.items():
        data += bytes(-len(data) % 16)
        at = len(data)
        if key is not None:
            payload = bytearray(raw)
            state = (key | ((key ^ 0xffffcdec) << 16)) & 0xffffffff
            for pos in range(0, len(payload) - 3, 4):
                struct.pack_into('<I', payload, pos, struct.unpack_from('<I', payload, pos)[0] ^ state)
                state = (state * 69069 + key * 207207) & 0xffffffff
            raw = struct.pack('<II', 0xa0f8efe6, key) + payload
        table.append((identity, at // 16, len(raw)))
        data += bytes(value ^ (((at + index) * 6339797 >> 16) & 255) for index, value in enumerate(raw))
    data += bytes(-len(data) % 16)
    directory = len(data) // 16
    data += b''.join(struct.pack('<QII', *row) for row in table)
    data += struct.pack('<5I', len(files), 0x71610000, directory, 0, 20)
    (root / 'data_02.g0s').write_bytes(data)


def sab(media_name='RECORDING_A', subtitle='synthetic_caption'):
    label = bytes(18) + subtitle.encode() + b'\0'
    pair = struct.pack('<I4sI', 1, b'st\0\0', 12) + label
    return b'SAL3' + struct.pack('<IQII', 1, fox.strcode48(media_name), 24, 0) + pair


def lang(rows):
    keys, values, indices = bytearray(), bytearray(), bytearray()
    for key, text in rows:
        indices += struct.pack('<II', len(keys), len(values))
        keys += key.encode() + b'\0'
        values += b'\x01\0' + text.encode() + b'\0'
    key_at, value_at = 32 + len(indices), 32 + len(indices) + len(keys)
    return b'LANG\x02\0\0\0LE\0\0' + struct.pack('<5I', len(rows), 32, key_at, value_at, 0) + indices + keys + values


def fox2(entities):
    data, strings = bytearray(), {}
    for class_name, fields in entities:
        entity = bytearray(64)
        struct.pack_into('<H', entity, 0, 64)
        entity[6:10] = b'ent\0'
        size = 64 + len(fields) * 48
        struct.pack_into('<QHHIII', entity, 28, fox.strcode48(class_name), len(fields), 0, 64, size, size)
        for name, kind, value in fields:
            prop = bytearray(48)
            struct.pack_into('<QBBHHH', prop, 0, fox.strcode48(name), kind, 0, 1, 32, 48)
            identity = fox.strcode48(value) if isinstance(value, str) else value
            struct.pack_into('<Q', prop, 32, identity)
            entity += prop
            if isinstance(value, str):
                strings[identity] = value
        data += entity
    text = b''.join(struct.pack('<QI', key, len(value)) + value.encode() for key, value in strings.items()) + bytes(8)
    return struct.pack('<5I12x', 0x786f62f2, 0x35, len(entities), 32 + len(data), 32) + data + text


def sani(rows):
    events = bytearray()
    for frame, label in rows:
        events += b'\x11\xc0\x79\x23\x01\x0a\0\x07' + struct.pack('<III', frame, 0xffffffff, 0)
        events += b''.join(struct.pack('<IHH', fox.strcode32(name), index, kind) for name, index, kind in
                          [('msgId', 1, 11), ('enableTextColorChange', 0, 10), ('key', 0, 11)])
        events += struct.pack('<6H', 3, 3, 2, 1, 6, 0)
        events += struct.pack('<7Q', fox.strcode48(''), fox.strcode48(label), 1, 2, 3, 4, 5)
    offsets = b''.join(struct.pack('<I', 8 + len(rows) * 4 + i * 112) for i in range(len(rows)))
    body = struct.pack('<IIIII', 2, 0, 0, fox.strcode32('Normal'), len(rows)) + offsets + events
    return b'DEMO' + struct.pack('<I', 16 + len(body)) + bytes(8) + body + b'END ' + struct.pack('<I', 16) + bytes(8)


def rdf(label):
    header = bytes((0, 4)) + bytes(9) + b'\x01' + bytes(4)
    part = struct.pack('<III4x', 100, 200, gz.fnv32(label))
    return struct.pack('<HHIII', 1, 1, 48, fox.strcode32('synthetic_radio'), 16) + header + part + bytes(4)


def fixture(root, locale='en', include_audio=True):
    (root / 'MgsGroundZeroes.exe').touch()
    (root / 'data_00.g0s').write_bytes(b'ASF video is not a GZS archive')
    tables = {}
    texts = {'en': ['Synthetic original caption.'], 'ja': ['合成された字幕です。']}
    for text_locale in texts:
        name = f'/Assets/tpp/ui/Subtitles/subp/{assets.VOICE_NAMES[locale]}Voice/{assets.TEXT_NAMES[text_locale]}Text/common.subp'
        tables[name] = b'\x01L' + subp(text_locale, {'synthetic_caption': texts[text_locale],
                                                   'missing_caption': ['Missing recording.']})[2:]
    files = {gz.path_hash(assets._pack_path(locale)): fpk(tables),
             gz.path_hash('/Assets/tpp/radio/synthetic.rdf'): rdf('synthetic_caption')}
    if include_audio:
        files[gz.path_hash('/Assets/tpp/sound/asset/synthetic.sbp')] = sbp({
            'sab': sab(), 'stp': stp({123: wem('RECORDING_A')}, version=0)})
    gzs(root, files, key=1234567)
    return files


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_official_voice_editions_bind_sab_and_original_media(tmp_path, locale):
    fixture(tmp_path, locale)
    result = assets.index_language(tmp_path, tmp_path, locale, list(assets.TEXT_LOCALES))
    assert result['narrative_inventory']['voice_counts'] == {'voiced': 1, 'unavailable': 1}
    row = next(row for row in result['records'] if row['audio'])
    assert row['dialogue_kind'] == 'radio'
    assert set(row['texts']) == {'en', 'ja'}
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('RECORDING_A')
    assert assets.extract_voices(tmp_path, [row['audio']], Path(), tmp_path) == [wem('RECORDING_A')]
    assert assets.discover_install([tmp_path]) == tmp_path
    assert [p.name for p in assets.archive_sources(tmp_path)] == ['data_02.g0s']
    assert all(LocalDialogue(**row).voice_status != 'unvoiced' for row in result['records'])
    for bad in ({'media_label': 'OTHER'}, {'subtitle_label': 'missing_caption'}, {'archive': '../escape.g0s'},
                {'locale_name': 'ja' if locale == 'en' else 'en'}):
        with pytest.raises(PreparationFailure):
            assets.extract_voice(tmp_path, {**row['audio'], **bad}, Path(), tmp_path)


def test_absent_japanese_audio_retains_supported_missing_pack_state(tmp_path):
    fixture(tmp_path)
    assert assets.probe_voice_pack(tmp_path, 'en') == 'present'
    assert assets.probe_voice_pack(tmp_path, 'ja') == 'missing'
    with pytest.raises(PreparationFailure, match='Steam Properties'):
        assets.index_language(tmp_path, tmp_path, 'ja', ['en'])


def test_audio_without_sab_relation_is_unavailable_not_silent(tmp_path):
    files = fixture(tmp_path)
    files[gz.path_hash('/Assets/tpp/sound/asset/synthetic.sbp')] = sbp({'stp': stp({123: wem('synthetic_caption')}, version=0)})
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert {row['voice_status'] for row in result['records']} == {'unavailable'}


def test_interrogation_voice_event_does_not_imply_silence_or_invent_media(tmp_path):
    files = fixture(tmp_path, include_audio=False)
    files[gz.path_hash('/Assets/tpp/interrogation.json')] = json.dumps({
        'interrogationResultTable': [['marker', 'synthetic_caption', 'synthetic_actor', 'generic_voice_event']]
    }).encode()
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row = next(row for row in result['records'] if row['dialogue_kind'] == 'interrogation')
    assert row['voice_status'] == 'unavailable' and not row['audio']
    assert result['narrative_inventory']['authored_interrogation_results'] == 1


def test_conflicting_subtitle_variants_are_preserved_without_ambiguous_audio(tmp_path):
    files = fixture(tmp_path)
    files[gz.path_hash('/Assets/tpp/pack/conflicting.fpk')] = fpk({
        '/Assets/tpp/ui/Subtitles/subp/EngVoice/EngText/e20010.subp':
            b'\x01L' + subp('en', {'synthetic_caption': ['A distinct official synthetic variant.']})[2:]})
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    rows = [row for row in result['records'] if ':conflict:' in row['text_id']]
    assert {row['source_text'] for row in rows} == {'Synthetic original caption.', 'A distinct official synthetic variant.'}
    assert all(row['voice_status'] == 'unavailable' and not row['audio'] for row in rows)


def test_changed_archive_fails_before_replacing_previous_snapshot(tmp_path, monkeypatch):
    fixture(tmp_path)
    stamps = iter(('before', 'after'))
    monkeypatch.setattr(assets, 'fingerprint', lambda _root: next(stamps))
    with pytest.raises(PreparationFailure, match='previous snapshot was retained'):
        assets.index_language(tmp_path, tmp_path, 'en', [])


@pytest.mark.parametrize('locale', assets.TEXT_LOCALES)
def test_all_official_text_encodings_remain_available(tmp_path, locale):
    files = fixture(tmp_path)
    sample = {'ja': '合成された字幕。', 'ru': 'Синтетические субтитры.', 'pt-BR': 'Legenda sintética.'}.get(locale, 'Légende synthétique.')
    name = f'/Assets/tpp/ui/Subtitles/subp/EngVoice/{assets.TEXT_NAMES[locale]}Text/e20010.subp'
    files[gz.path_hash('/Assets/tpp/pack/translation.fpk')] = fpk({name: b'\x01L' + subp(locale, {'translation_only': [sample]})[2:]})
    gzs(tmp_path, files)
    parsed = assets._tables(gz.GzArchive(tmp_path), 'en', set(assets.TEXT_LOCALES), assets.Counter())[0]
    assert parsed[locale][fox.strcode32('translation_only')]['text'] == sample


def add_scene(files, locale='en'):
    movie = '/Assets/tpp/demo/demo_stream/p11_020000_variant.fsm'
    subtitle = '/Assets/tpp/demo/fox_project/p11_010000/evf/p11_010000_subtitle.sani'
    metadata = fox2([('DemoData', [('demoId', 11, 'p11_020000_variant'), ('demoStreamPath', 12, movie),
        ('audioPath', 12, '/Assets/tpp/sound/external/demo/p11_010000.mas'), ('subtitleBinaryFile', 20, subtitle)])])
    files[gz.path_hash('/Assets/tpp/pack/scene.fpk')] = fpk({
        '/Assets/tpp/demo/scene.fox2': metadata,
        subtitle + '#' + ('eng' if locale == 'en' else 'jpn'): sani([(90, 'scene_last'), (30, 'scene_first')]),
        f'/Assets/tpp/ui/Subtitles/subp/{assets.VOICE_NAMES[locale]}Voice/{assets.TEXT_NAMES[locale]}Text/e20010.subp':
            b'\x01L' + subp(locale, {'scene_first': ['Synthetic first scene caption.'],
                                   'scene_last': ['Synthetic final scene caption.']})[2:]})
    files[gz.path_hash(movie)] = fsm(wem('complete_original_scene_mix'))
    return metadata


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_cinematic_uses_typed_movie_subtitle_relation_and_authored_events(tmp_path, locale):
    files = fixture(tmp_path, locale)
    metadata = add_scene(files, locale)
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, locale, [])
    scenes = [row for row in result['records'] if row['dialogue_kind'] == 'cinematic_full_track']
    assert [row['source_text'] for row in scenes] == ['Synthetic first scene caption.', 'Synthetic final scene caption.']
    row = scenes[0]
    assert row['ocr_texts'][locale] == ['Synthetic first scene caption.']
    assert row['audio']['playback_scope'] == 'full_track'
    assert scenes[0]['audio'] == scenes[1]['audio']
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('complete_original_scene_mix')
    assert 'subtitle' not in fox.demo_bindings(fox.View.bytes(metadata))[0]
    assert fox.demo_bindings(fox.View.bytes(metadata), include_subtitles=True)[0]['subtitle'].endswith('.sani')
    bad = {**row['audio'], 'subtitle_events': {**row['audio']['subtitle_events'], 'events': []}}
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, bad, Path(), tmp_path)
    corrupt = bytearray(sani([(30, 'scene_first')]))
    struct.pack_into('<I', corrupt, 36, 0xfffffff0)
    with pytest.raises(PreparationFailure):
        gz.subtitle_events(fox.View.bytes(corrupt))


def add_panels(files, typed=True):
    members = {
        '/Assets/tpp/lang/ui/gz/gz_backstory.lng#eng': lang([('backstory_info_00_00', 'Synthetic readable prose.'), ('backstory_name_00_00', 'Heading')]),
        '/Assets/tpp/lang/ui/gz/gz_quiz.lng#eng': lang([('choice_1_1', 'Synthetic selectable answer.'), ('question_1', 'Synthetic question.'), ('choice_99_1', 'Unproven choice.')]),
        '/Assets/tpp/lang/ui/gz/gz_menu.lng#eng': lang([('collision', 'First official variant.'), ('collision', 'Second official variant.')])}
    if typed:
        members.update({
            '/Assets/tpp/ui/GraphAsset/gz/title_prestory.uigb': b'UIGB',
            '/Assets/tpp/ui/GraphAsset/gz/mgs_quiz.uigb': b'UIGB',
            '/Assets/tpp/ui/GraphAsset/gz/uig_title_prestory_gz.fox2': fox2([
                ('LangData', [('langFile', 20, '/Assets/tpp/lang/ui/gz/gz_backstory.lng')]),
                ('TppUICommonBootData', [('uiFile', 20, '/Assets/tpp/ui/GraphAsset/gz/title_prestory.uigb'), ('pauseFlag', 4, 1)])]),
            '/Assets/tpp/ui/GraphAsset/gz/uig_mgs_quiz.fox2': fox2([
                ('TppUICommonBootData', [('uiFile', 20, '/Assets/tpp/ui/GraphAsset/gz/mgs_quiz.uigb'), ('pauseFlag', 4, 0)])])})
        files[gz.path_hash('/Assets/tpp/level/mission/extra/e20060/e20060_sequence.lua')] = (
            b'ui:SetupMgsQuizItemTable({ quizId=1, answerId=2, questionRadioId="synthetic_question_radio", correctRadioId="synthetic_correct_radio" })')
    files[gz.path_hash('/Assets/tpp/pack/panels.fpk')] = fpk(members)


@pytest.mark.parametrize('typed', [False, True])
def test_only_confirmed_readable_and_choice_routes_enable_silent_capture(tmp_path, typed):
    files = fixture(tmp_path)
    add_panels(files, typed)
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    silent = [row for row in result['records'] if row['voice_status'] == 'unvoiced']
    assert {row['source_text'] for row in silent} == ({'Synthetic readable prose.', 'Synthetic selectable answer.'} if typed else set())
    assert all(not row['audio'] for row in silent)
    unknown = [row['source_text'] for row in result['records'] if row['voice_status'] == 'unknown']
    assert all(text in unknown for text in ['Heading', 'Synthetic question.', 'Unproven choice.',
                                          'First official variant.', 'Second official variant.'])


@pytest.mark.parametrize(('locale', 'name'), [('en', 'tp_pw_01_02'), ('ja', 'tp_arch_cd_01_02')])
def test_cassette_requires_its_exact_original_path_and_subtitle_id(tmp_path, locale, name):
    files = fixture(tmp_path, locale)
    files[gz.path_hash('/Assets/tpp/pack/tapes.fpk')] = fpk({
        f'/Assets/tpp/ui/Subtitles/subp/{assets.VOICE_NAMES[locale]}Voice/{assets.TEXT_NAMES[locale]}Text/tape.subp':
            b'\x01L' + subp(locale, {name: ['First tape page.', 'Second tape page.']})[2:]})
    files[gz.path_hash('/Assets/tpp/sound/external/tape/' + name + '.wem')] = wem('complete_tape')
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, locale, [])
    row = next(row for row in result['records'] if row['dialogue_kind'] == 'cassette_tape_full_track')
    assert len(row['ocr_texts'][locale]) == 2
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('complete_tape')


def test_standalone_labeled_media_still_requires_original_sab_relation(tmp_path):
    files = fixture(tmp_path, include_audio=False)
    files[gz.path_hash('/Assets/tpp/sound/asset/synthetic.sbp')] = sbp({'sab': sab()})
    files[gz.path_hash('/Assets/tpp/sound/external/synthetic.wem')] = wem('RECORDING_A')
    gzs(tmp_path, files)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row = next(row for row in result['records'] if row['audio'])
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == wem('RECORDING_A')
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, {**row['audio'], 'subtitle_label': 'wrong'}, Path(), tmp_path)


def test_gzs_cipher_random_access_platform_and_bounds(tmp_path):
    payload = bytes(range(251)) * 5
    identity = gz.path_hash('/Assets/tpp/synthetic.fpk')
    gzs(tmp_path, {identity: payload}, key=0x12345678)
    archive = gz.GzArchive(tmp_path)
    view = archive.view(archive.entries[identity])
    for start, count in [(0, len(payload)), (3, 71), (1001, 53), (1252, 3)]:
        assert view.read(start, count) == payload[start:start + count]
    archive.close()
    raw = bytearray((tmp_path / 'data_02.g0s').read_bytes())
    struct.pack_into('<I', raw, len(raw) - 12, 0xffffffff)
    (tmp_path / 'data_02.g0s').write_bytes(raw)
    with pytest.raises(PreparationFailure):
        gz.GzArchive(tmp_path)
    broken = bytearray(fpk({'/Assets/tpp/file.lua': b'data'}))
    broken[7:10] = b'ps3'
    with pytest.raises(PreparationFailure):
        list(fox.fpk_entries(fox.View.bytes(broken)))


def test_malformed_label_localization_event_and_ui_fail_closed():
    label = bytearray(sab())
    struct.pack_into('<I', label, 16, 0xffffffff)
    with pytest.raises(PreparationFailure):
        list(gz.sab_labels(fox.View.bytes(label)))
    localized = bytearray(lang([('key', 'Synthetic value.')]))
    struct.pack_into('<I', localized, 24, 0xffffffff)
    with pytest.raises(PreparationFailure):
        gz.read_lang(localized)
    events = bytearray(sani([(30, 'synthetic_caption')]))
    events[40 + 12 + 20] ^= 1
    with pytest.raises(PreparationFailure):
        gz.subtitle_events(fox.View.bytes(events))
    ui = bytearray(fox2([('LangData', [('langFile', 20, '/Assets/tpp/example.lng')])]))
    ui[32 + 64 + 8] = 11
    with pytest.raises(PreparationFailure):
        gz.ui_boot_bindings(fox.View.bytes(ui))
