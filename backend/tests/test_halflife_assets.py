"""Synthetic GoldSrc fixtures; no proprietary game data or transcripts."""
import hashlib
import io
import json
from pathlib import Path
import struct
import wave

import pytest

from backend import halflife_assets as hl
from backend import goldsrc_formats as gold
from backend.local_game import LocalDialogue, LocalGameTextIndex
from backend.preparation_errors import PreparationFailure


def wav():
    out = io.BytesIO()
    with wave.open(out, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(1)
        stream.setframerate(11025)
        stream.writeframes(bytes(range(256)) * 8)
    return out.getvalue()


def bsp(items, version=30):
    data = ('\n'.join('{\n' + '\n'.join(json.dumps(key) + ' ' + json.dumps(value) for key, value in item.items())
                      + '\n}' for item in items) + '\0').encode()
    return struct.pack('<III', version, 124, len(data)) + bytes(112) + data


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def package(root, files):
    body, directory = b'', b''
    for name, data in files.items():
        directory += struct.pack('<56sII', name.encode(), 12 + len(body), len(data))
        body += data
    return write(root, 'valve/pak0.pak', struct.pack('<4sII', b'PACK', 12 + len(body), len(directory)) + body + directory)


def install(root):
    write(root, 'hl.exe', b'synthetic')
    write(root, 'valve/liblist.gam', b'game "Synthetic Half-Life test"')
    write(root, 'valve/titles.txt', b'$position .1 .8\nCARD\n{\nSynthetic screen card\nSecond row\n}\n'
          b'SOUND\n{\nSynthetic attached sound\n}\nUNUSED\n{\nUnknown unused title\n}\n')
    write(root, 'valve/maps/c0a0.bsp', bsp([
        {'classname': 'env_message', 'message': 'CARD'},
        {'classname': 'env_message', 'message': 'SOUND', 'messagesound': 'scientist/line.wav'},
        {'classname': 'game_text', 'message': 'Synthetic inline screen message'},
        {'classname': 'scripted_sentence', 'sentence': 'FAKE_LINE'},
        {'classname': 'ambient_generic', 'message': 'scientist/line.wav'},
        {'classname': 'speaker', 'preset': '3'}]))
    write(root, 'valve/sound/sentences.txt', b'FAKE_LINE scientist/line\nASSEMBLED vox/one(p110) two three\n')
    write(root, 'valve/sound/scientist/line.wav', wav())
    return root


def test_original_identity_does_not_accept_source_or_other_goldsrc_mod(tmp_path):
    assert hl.discover_install([tmp_path]) is None
    write(tmp_path, 'hl2.exe', b'x')
    write(tmp_path, 'hl1/gameinfo.txt', b'x')
    assert hl.discover_install([tmp_path]) is None
    assert hl.discover_install([install(tmp_path)]) == tmp_path


def test_soundless_bindings_only_and_no_filenames_as_transcripts(tmp_path):
    result = hl.index_language(install(tmp_path), tmp_path / 'cache', 'en', [])
    rows = {row['text_id']: LocalDialogue(**row) for row in result['records']}
    assert rows['halflife:title:card'].voice_status == 'unvoiced'
    assert rows['halflife:title:sound'].voice_status == 'unknown'
    assert rows['halflife:title:unused'].voice_status == 'unknown'
    assert rows['halflife:map:maps/c0a0.bsp:2'].voice_status == 'unvoiced'
    assert all(not row.audio for row in rows.values())
    assert not result['capture_capabilities']['voiced']
    assert result['capture_capabilities']['unvoiced']
    assert 'not ready' in result['message']
    assert result['narrative_inventory']['sentence_definitions'] == 2
    assert result['narrative_inventory']['single_sample_sentences'] == 1
    assert result['narrative_inventory']['assembled_or_parameterized_sentences'] == 1
    assert result['narrative_inventory']['speech_entries_with_verified_authored_text'] == 0
    assert all('scientist/line' not in row.source_text for row in rows.values())


def test_unvoiced_toggle_uses_full_message_and_authored_line_anchors(tmp_path):
    result = hl.index_language(install(tmp_path), tmp_path / 'cache', 'en', [])
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'textmap.json').write_text(json.dumps(result), encoding='utf-8')
    index = LocalGameTextIndex('halflife', cache)
    assert index.match_lines(['Synthetic screen card'], exact_only=True) is None
    index.capture_unvoiced = True
    assert index.match_lines(['Synthetic screen card'], exact_only=True).voice_status == 'unvoiced'
    assert index.match_lines(['Unknown unused title'], exact_only=True) is None
    assert index.match_lines(['Synthetic attached sound'], exact_only=True) is None
    assert index.audio_count == 0
    assert index.state == 'unvoiced_only', 'An unsupported speech reader is not a missing voice pack'
    from backend.multilingual_index import MultilingualTextIndex
    multilingual = MultilingualTextIndex('halflife', cache)
    multilingual.path = cache / 'textmap.json'
    assert multilingual.load() and multilingual.state == 'unvoiced_only'
    assert multilingual.status()['capture_capabilities']['voiced'] is False
    from backend.installation import _voice_state
    assert _voice_state('halflife', tmp_path, {'index_state': 'needs_language_setup'}) == 'unvoiced_only'
    assert _voice_state('halflife', None, {}) == 'not_checked'


@pytest.mark.parametrize('locale,text,encoding', [
    ('en', 'Synthetic screen card', 'utf-8'), ('fr', 'Message créé', 'cp1252'),
    ('de', 'Erfundene Grüße', 'utf-8'), ('it', 'Testo sintetico', 'utf-8'),
    ('es-ES', 'Mensaje de prueba', 'utf-8'), ('zh-Hans', '虚构测试消息', 'utf-16'),
    ('zh-Hant', '虛構測試訊息', 'utf-16'), ('ko', '가상 시험 메시지', 'utf-16')])
def test_all_official_language_mounts_and_encoding_without_english_fallback(tmp_path, locale, text, encoding):
    install(tmp_path)
    write(tmp_path, hl.mount(locale) + '/titles.txt', ('CARD\n{\n' + text + '\n}\n').encode(encoding))
    write(tmp_path, hl.mount(locale) + '/sound/scientist/line.wav', wav())
    result = hl.index_language(tmp_path, tmp_path / 'cache', locale, ['en'])
    row = next(row for row in result['records'] if row['text_id'] == 'halflife:title:card')
    assert row['source_text'] == text
    assert row['source_locale'] == locale
    assert row['voice_status'] == 'unvoiced'
    assert hl.probe_voice_pack(tmp_path, locale) == 'present'
    if locale != 'en':
        assert row['texts']['en'] == 'Synthetic screen card Second row'
        assert not any(item['text_id'].startswith('halflife:map:') for item in result['records'])
        assert result['narrative_inventory']['inline_messages_without_selected_locale'] == 1


@pytest.mark.parametrize('locale', [value for value in hl.SUPPORTED_LOCALES if value != 'en'])
def test_absent_locale_is_actionable_and_never_borrows_english(tmp_path, locale):
    install(tmp_path)
    assert hl.probe_voice_pack(tmp_path, locale) == 'missing'
    with pytest.raises(PreparationFailure, match='Steam game Properties') as caught:
        hl.index_language(tmp_path, tmp_path / 'cache', locale, [])
    assert caught.value.code == 'halflife_language_pack_missing'


def test_missing_recording_does_not_turn_unknown_sound_message_into_silence(tmp_path):
    install(tmp_path)
    (tmp_path / 'valve/sound/scientist/line.wav').unlink()
    result = hl.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert result['voice_pack_state'] == 'incomplete'
    assert result['narrative_inventory']['single_sample_sentences_without_selected_recording'] == 1
    assert next(row for row in result['records'] if row['text_id'].endswith(':sound'))['voice_status'] == 'unknown'


def test_title_used_with_and_without_sound_is_unknown(tmp_path):
    install(tmp_path)
    write(tmp_path, 'valve/maps/c1a0.bsp', bsp([{'classname': 'env_message', 'message': 'CARD', 'messagesound': 'missing.wav'}]))
    result = hl.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert next(row for row in result['records'] if row['text_id'].endswith(':card'))['voice_status'] == 'unknown'


def test_pak_mounts_read_only_and_loose_override(tmp_path):
    package(tmp_path, {'titles.txt': b'FIRST\n{\nSynthetic archive text\n}\n', 'sound/scientist/line.wav': wav()})
    files = gold.GoldSrcFiles(tmp_path, 'valve')
    assert len(files.names('sound', '.wav')) == 1
    assert gold.titles(files.read('titles.txt'))['first']['text'] == 'Synthetic archive text'
    write(tmp_path, 'valve/titles.txt', b'OVERRIDE\n{\nSynthetic loose text\n}\n')
    assert 'override' in gold.titles(files.read('titles.txt'))


@pytest.mark.parametrize('name', ['../outside.wav', '/absolute.wav', 'C:/drive.wav', 'sound\\escape.wav'])
def test_pak_member_traversal_rejected(tmp_path, name):
    path = package(tmp_path, {name: b'x'})
    with pytest.raises(PreparationFailure):
        gold.PakArchive(path)


def test_pak_bounds_rejected(tmp_path):
    path = write(tmp_path, 'valve/pak0.pak', struct.pack('<4sII', b'PACK', 99, 64))
    with pytest.raises(PreparationFailure):
        gold.PakArchive(path)


@pytest.mark.parametrize('data', [b'', struct.pack('<I', 29) + bytes(120), struct.pack('<III', 30, 120, 10) + bytes(112),
                                 struct.pack('<III', 30, 124, 999) + bytes(112)])
def test_bsp_entity_bounds_are_checked(data):
    with pytest.raises(PreparationFailure):
        gold.entity_bounds(data, 200)


def test_entity_quotes_duplicate_scalar_and_authored_position():
    parsed = gold.entities(b'{"classname" "game_text" "message" "first" "message" "text { braces }"}')
    assert parsed[0]['message'] == 'text { braces }'
    assert gold.titles(b'$position .1 .8\nA\n{\nRow one\nRow two\n}\n')['a'] == {
        'text': 'Row one\nRow two', 'position': (.1, .8)}


@pytest.mark.parametrize('data', [b'A\n{\nUnclosed', b'A\nMissing brace', b'$position NaN 0\n', b'A\n{\nOne\n}\nA\n{\nTwo\n}'])
def test_malformed_titles_fail_closed(data):
    with pytest.raises(PreparationFailure):
        gold.titles(data)


def test_sentence_control_codes_stay_inventory_and_duplicates_preserved():
    definitions = gold.sentences(b'FAKE scientist/sample\nFAKE vox/(p110) one two\n')
    assert len(definitions) == 2
    assert gold.single_sample(definitions[0][1]) == 'sound/scientist/sample.wav'
    assert gold.single_sample(definitions[1][1]) is None
    assert gold.single_sample('scientist/sample(e50)') is None


def test_extract_preserves_exact_original_audio_and_rejects_changed_or_cross_locale_samples(tmp_path):
    install(tmp_path)
    audio = {'locale': 'en', 'member': 'sound/scientist/line.wav', 'sha256': hashlib.sha256(wav()).hexdigest()}
    assert hl.extract_voice(tmp_path, audio, None, None) == wav()
    with pytest.raises(FileNotFoundError):
        hl.extract_voice(tmp_path, {**audio, 'locale': 'fr'}, None, None)
    with pytest.raises(PreparationFailure):
        hl.extract_voice(tmp_path, {**audio, 'sha256': '0' * 64}, None, None)
    with pytest.raises(PreparationFailure):
        hl.extract_voice(tmp_path, {**audio, 'member': '../outside.wav'}, None, None)


def test_fingerprint_updates_for_locale_files_but_not_private_config(tmp_path):
    install(tmp_path)
    before = hl.fingerprint(tmp_path)
    write(tmp_path, 'valve/config.cfg', b'private user settings')
    assert hl.fingerprint(tmp_path) == before
    write(tmp_path, 'valve_french/titles.txt', b'CARD\n{\nSynthetic French test\n}\n')
    assert hl.fingerprint(tmp_path) != before


def test_changed_files_retains_previous_snapshot(tmp_path, monkeypatch):
    install(tmp_path)
    stamps = iter(['before', 'after'])
    monkeypatch.setattr(hl, 'fingerprint', lambda _: next(stamps))
    with pytest.raises(PreparationFailure) as caught:
        hl.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert caught.value.game_files_changed and caught.value.previous_snapshot_retained
