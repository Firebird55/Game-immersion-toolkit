"""Synthetic Detroit schemas and performance chains; no shipped game assets."""
import struct
import wave
import io
from types import SimpleNamespace

import pytest

from backend import detroit_assets as assets, detroit_format as fmt
from backend.local_game import LocalDialogue
from backend.preparation_errors import PreparationFailure


KEY = 'X0001A_SYNTHETIC_PC_TEST_LINE'


def ints(*values):
    return struct.pack('<' + 'I' * len(values), *values)


def string(value, encoding='ascii'):
    value = value.encode(encoding)
    return ints(len(value)) + value


def section(tag, version, body):
    return tag + ints(version, len(body)) + body


def component(tag, version, body, dependencies=()):
    refs = ints(len(dependencies)) + b''.join(ints(kind, identity) + b'\1' for kind, identity in dependencies)
    return section(b'COM_CONT', 6, refs) + section(b'LOADCONT', 2, b'') + section(tag, version, body)


def localization(locales, *, source_text='{S}{*1}Synthetic first.{*2}Synthetic second.', alias=True):
    body, dependencies = ints(len(locales)), []
    for index, code in enumerate(locales):
        rows = [(KEY, source_text, 1), ('X0001A_SCENE_PC_CHOICE_TEST', 'Synthetic option', 2),
                ('GUI_MAGAZINE_TEST_ARTICLE1', 'Synthetic readable article.', 1),
                ('GUI_MENU_TEST', 'Synthetic system menu', 1)]
        body += b'\1' + string(code) + ints(len(rows))
        for key, text, flags in rows:
            body += string(key) + string(text, 'utf-16-le') + ints(flags)
        body += ints(int(alias))
        if alias:
            body += string(KEY) + b'\1\1' + ints(4091, 200 + index)
            dependencies.append((4091, 200 + index))
    return component(b'LOCALIZ_', 6, body, dependencies)


def sound(code, *, times=((.1, .4), (.5, .9)), key=KEY):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
        wav.writeframes(bytes(96000))
    recording = output.getvalue()
    body = string('18446744073709551615') + struct.pack('<f', 1.0) + string(key + '_' + code)
    body += ints(len(recording)) + recording + ints(1, 16, 48000, len(times))
    body += b''.join(struct.pack('<2f', *pair) for pair in times)
    return b'QZIP\0' + section(b'CSNDDATA', 0, body)


def install(tmp_path, codes=('ENG', 'SCH'), *, missing=False, source_text=None, wrong_locale=False, times=None):
    rows = [(1016, 100, localization(codes, **({'source_text': source_text} if source_text else {})))]
    for index, code in enumerate(codes):
        rows.append((4091, 200 + index, component(b'HEADER__', 8, bytes(8), [(1033, 300 + index)])))
        if not missing:
            rows.append((1033, 300 + index, sound('RUS' if wrong_locale else code, **({'times': times} if times else {}))))
    encoded, table = bytearray(), bytearray()
    for kind, identity, data in rows:
        table.extend(struct.pack('>7I', kind, 1, identity, len(encoded), len(data), 0, 0))
        encoded.extend(data)
    (tmp_path / 'BigFile_PC.dat').write_bytes(encoded)
    (tmp_path / assets.INDEX_NAME).write_bytes(fmt.MAGIC + struct.pack('>II', 18, 0) + b'ZEP' * 24
                                              + b'\0' + struct.pack('>I', len(rows)) + table)
    return tmp_path


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_official_locale_binding_timing_and_original_audio(tmp_path, locale):
    root = install(tmp_path, (assets.TEXT_LOCALES[locale], 'SCH'))
    payload = assets.index_language(root, tmp_path, locale, ['zh-Hans'])
    voiced = [row for row in payload['records'] if row['voice_status'] == 'voiced']
    assert len(voiced) == 2
    assert [(row['audio']['start_ms'], row['audio']['end_ms']) for row in voiced] == [(100, 400), (500, 900)]
    assert all(row['chinese'] and row['audio_locale'] == locale for row in voiced)
    assert [row['dialogue_kind'] for row in payload['records'] if row['voice_status'] == 'unvoiced'] == ['choice', 'readable']
    assert not any('GUI_MENU' in row['text_id'] for row in payload['records'])
    for row in payload['records']:
        LocalDialogue(**row)
    assert assets.probe_voice_pack(root, locale) == 'present'
    data = assets.extract_voice(root, voiced[0]['audio'], None, tmp_path)
    with wave.open(io.BytesIO(data)) as wav:
        assert wav.getframerate() == 48000 and wav.getnframes() == 48000


def test_missing_original_sound_remains_unavailable(tmp_path):
    root = install(tmp_path, missing=True)
    payload = assets.index_language(root, tmp_path, 'en', ['zh-Hans'])
    row = next(row for row in payload['records'] if KEY in row['text_id'])
    assert row['voice_status'] == 'unavailable' and row['audio'] is None
    assert assets.probe_voice_pack(root, 'en') == 'incomplete'
    assert any('Install or verify' in warning for warning in payload['coverage_warnings'])


def test_absent_locale_is_actionable_and_stays_supported(tmp_path):
    root = install(tmp_path)
    assert 'ar' in assets.SUPPORTED_LOCALES
    with pytest.raises(PreparationFailure) as caught:
        assets.index_language(root, tmp_path, 'ar', [])
    assert caught.value.code == 'missing_voice_pack'
    assert assets.probe_voice_pack(root, 'ar') == 'unknown'


@pytest.mark.parametrize('text', ['{*1}First.{*1}Second.', 'Complete synthetic performance.'])
def test_ambiguous_cue_uses_complete_original_performance(tmp_path, text):
    root = install(tmp_path, source_text=text)
    payload = assets.index_language(root, tmp_path, 'en', [])
    row = next(row for row in payload['records'] if row['audio'])
    assert 'start_ms' not in row['audio']
    assert row['source_text'] == assets.clean_text(text)
    assert row['ocr_texts']['en'] == assets.ocr_pages(text)


def test_authored_cue_range_and_timecode():
    assert assets.cues('{S}{*1-2}Synthetic range.') == {'1-2': 'Synthetic range.'}
    assert assets.cue_times('1-2', [(.1, .2), (.3, .4)], 1) == (100, 400)
    assert assets.cue_times('TC:10|200', [], 1) == (10, 200)
    assert assets.cue_times('3', [(0, .2)], 1) is None


def test_subtitle_hold_beyond_recording_never_invents_a_cut(tmp_path):
    root = install(tmp_path, times=((0, 1.05), (.5, .9)))
    payload = assets.index_language(root, tmp_path, 'en', [])
    row = next(row for row in payload['records'] if row['audio'])
    assert 'start_ms' not in row['audio'] and row['text_id'].endswith(':complete')


def test_wrong_locale_fails_safely(tmp_path):
    root = install(tmp_path, wrong_locale=True)
    with pytest.raises(PreparationFailure) as caught:
        assets.index_language(root, tmp_path, 'en', [])
    assert caught.value.code == 'unsupported_game_format'
    assert str(root) not in str(caught.value)


def test_rejects_invalid_index_bounds_and_sections(tmp_path):
    root = install(tmp_path)
    index = root / assets.INDEX_NAME
    index.write_bytes(index.read_bytes()[:-1])
    with pytest.raises(ValueError, match='bounds'):
        fmt.read_index(index)
    with pytest.raises(ValueError):
        fmt.sections(section(b'LOCALIZ_', 6, b'x')[:-1])


def test_extract_revalidates_authored_chain_and_path(tmp_path):
    root = install(tmp_path)
    audio = next(row['audio'] for row in assets.index_language(root, tmp_path, 'en', [])['records'] if row['audio'])
    with pytest.raises(ValueError, match='reference'):
        assets.extract_voice(root, {**audio, 'index': '../BigFile_PC.idx'}, None, tmp_path)
    with pytest.raises(ValueError, match='binding'):
        assets.extract_voice(root, {**audio, 'identity': 301}, None, tmp_path)


def test_legacy_japanese_alias_and_localization_format():
    data = localization(('JAP',), alias=False)
    parts = fmt.sections(data)
    old = section(b'COM_CONT', 5, bytes(8)) + section(b'LOADCONT', 2, b'')
    old += section(b'LOCALIZ_', 5, b'\0' + parts[b'LOCALIZ_'][1])
    source = assets.locale_table(fmt.localization(old), 'ja')
    assert source['texts'][KEY].startswith('{S}')


def test_non_speech_text_requires_authored_category():
    source = {'text_flags': {'X0001A_TEST': 1, 'THOUGHTS_TEST': 1}, 'binding_states': {}}
    assert assets.unbound_status('X0001A_TEST', 'An unresolved line', source)[0] == 'unavailable'
    assert assets.unbound_status('THOUGHTS_TEST', 'An authored prompt', source)[0] == 'unvoiced'
    assert assets.unbound_status('THOUGHTS_TEST', '{S}Unexpected speech', source)[0] == 'unavailable'


def test_nonfinite_sound_timing_rejected(tmp_path):
    root = install(tmp_path, times=((0, float('nan')),))
    with pytest.raises(PreparationFailure):
        assets.index_language(root, tmp_path, 'en', [])


def test_metadata_limit_is_checked_before_reading():
    oversized = SimpleNamespace(size=fmt.METADATA_LIMIT + 1,
                                read=lambda: pytest.fail('Oversized metadata must not be allocated'))
    with pytest.raises(ValueError, match='limit'):
        fmt.component_bytes(oversized)
