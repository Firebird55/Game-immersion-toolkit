"""Synthetic, copyright-free Shadow format and locale regressions."""
from pathlib import Path
import struct

import pytest

from backend import shadow_tomb_assets as assets
from backend.local_game import LocalDialogue
from backend.preparation_errors import PreparationFailure

KEY = '010_scene_lara_12345678_1234_1234_1234_123456789abc'


def locals_bin(locale, values):
    payload = bytearray(struct.pack('<II', assets._LANGUAGE_IDS[locale], len(values)) + bytes(len(values) * 8))
    for index, (key, value) in enumerate(values.items()):
        struct.pack_into('<Q', payload, 8 + index * 8, len(payload))
        payload.extend((key + ' ' + value).encode() + b'\0')
    return bytes(payload)


def chunk(name, data):
    return name + struct.pack('<I', len(data)) + data + (b'\0' if len(data) & 1 else b'')


def wem(labels=None):
    labels = [(KEY, 0)] if labels is None else labels
    fmt = chunk(b'fmt ', struct.pack('<HHIIHH', 1, 1, 48000, 96000, 2, 16))
    cue = chunk(b'cue ', struct.pack('<I', len(labels)) + b''.join(
        struct.pack('<II4sIII', index, sample, b'data', 0, 0, 0) for index, (_, sample) in enumerate(labels)))
    lab = chunk(b'LIST', b'adtl' + b''.join(chunk(b'labl', struct.pack('<I', index) + label.encode() + b'\0')
                                         for index, (label, _) in enumerate(labels)))
    data = b'WAVE' + fmt + cue + lab + chunk(b'data', bytes(9600))
    return b'RIFF' + struct.pack('<I', len(data)) + data


def tiger(root, name, identity, sub, entries):
    """Make one real-format v5 archive; payloads remain entirely synthetic."""
    root.mkdir(parents=True, exist_ok=True)
    data = bytearray(struct.pack('<4s5I', b'TAFS', 5, 1, len(entries), identity, sub) + b'pcx64-w'.ljust(32, b'\0'))
    offset = len(data) + 32 * len(entries)
    for name_hash, locale, payload in entries:
        data.extend(struct.pack('<QQIIhBBI', name_hash, locale, len(payload), 32761, 0, identity, sub, offset))
        offset += len(payload)
    for _, _, payload in entries:
        data.extend(payload)
    (root / name).write_bytes(data)


def fixture_game(root, locale='en', values=None, voices=None, targets=()):
    values = values or {KEY: 'Synthetic source sentence.'}
    tiger(root, 'bigfile.000.tiger', 1, 0, [])
    for index, code in enumerate([locale, *targets], 1):
        tiger(root, f'bigfile_{assets.TEXT_LOCALES[code]}_allvo_allplt.000.tiger', 1, index,
              [(assets.LOCALS_HASH, assets.TEXT_MASKS[code], locals_bin(code, values))])
    if voices is not False:
        tiger(root, f'bigfile_alltxt_{assets.TEXT_LOCALES[locale]}_allplt.000.tiger', 1, 50,
              [(100 + index, assets.VOICE_MASKS[locale], payload) for index, payload in enumerate(voices or [wem()])])


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_every_official_voice_locale_uses_its_exact_pack(tmp_path, locale):
    fixture_game(tmp_path, locale)
    result = assets.index_language(tmp_path, tmp_path / 'cache', locale, [])
    row, = result['records']
    assert row['audio_locale'] == locale and row['audio']['locale'] == locale
    assert row['audio']['entry']['locale'] == assets.VOICE_MASKS[locale]
    assert row['voice_status'] == 'voiced'
    LocalDialogue(**row)
    assert assets.extract_voice(tmp_path, row['audio'], Path('unused'), tmp_path) == wem()


def test_translation_and_missing_pack_do_not_substitute_english_or_chinese(tmp_path):
    fixture_game(tmp_path, 'zh-Hant', voices=False, targets=['zh-Hans', 'en'])
    tiger(tmp_path, 'bigfile_alltxt_simplechinese_allplt.000.tiger', 1, 50,
          [(100, assets.VOICE_MASKS['zh-Hans'], wem())])
    result = assets.index_language(tmp_path, tmp_path / 'cache', 'zh-Hant', ['en', 'de'])
    row, = result['records']
    assert row['source_locale'] == row['audio_locale'] == 'zh-Hant'
    assert row['audio'] is None and row['voice_status'] == 'unavailable'
    assert result['missing_translation_locales'] == ['de']
    assert set(row['texts']) == {'zh-Hant', 'en'}
    assert 'install the selected original voice pack' in result['message']


def test_missing_regional_text_and_text_only_source_are_actionable(tmp_path):
    fixture_game(tmp_path)
    with pytest.raises(PreparationFailure) as error:
        assets.index_language(tmp_path, tmp_path, 'ja', [])
    assert error.value.code == 'shadow_text_pack_missing'
    with pytest.raises(ValueError, match='text only'):
        assets.index_language(tmp_path, tmp_path, 'ko', [])


def test_cinematic_uses_paired_authored_samples_and_rejects_incomplete_pairs():
    data = wem([('subtitle-start:' + KEY, 480), ('subtitle-end:' + KEY, 2880)])
    assert assets.wem_bindings(data, len(data)) == [{'label': KEY, 'start_ms': 10, 'end_ms': 60}]
    for labels in [[('subtitle-start:' + KEY, 480)],
                   [('subtitle-start:' + KEY, 480), ('subtitle-start:' + KEY, 960), ('subtitle-end:' + KEY, 2880)],
                   [('subtitle-start:' + KEY, 2880), ('subtitle-end:' + KEY, 480)],
                   [(KEY, 0), ('another_line', 960)]]:
        data = wem(labels)
        assert assets.wem_bindings(data, len(data)) == []


def test_cinematic_binding_and_timing_revalidated_at_extraction(tmp_path):
    data = wem([('subtitle-start:' + KEY, 480), ('subtitle-end:' + KEY, 2880)])
    fixture_game(tmp_path, voices=[data])
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert row['dialogue_kind'] == 'cinematic'
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == data
    with pytest.raises(ValueError, match='binding changed'):
        assets.extract_voice(tmp_path, {**row['audio'], 'end_ms': 99}, Path(), tmp_path)


def test_unique_collectible_guid_join_and_ambiguous_guid_rejection(tmp_path):
    label = 'collect_story_lara_document_12345678-1234-1234-1234-123456789abc'
    text_key = 'document_description_12345678_1234_1234_1234_123456789abc'
    fixture_game(tmp_path, values={text_key: 'Synthetic narrated document.'}, voices=[wem([(label, 0)])])
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row, = result['records']
    assert row['voice_status'] == 'voiced' and row['dialogue_kind'] == 'narrated_collectible'
    assert result['narrative_inventory']['unique_guid_bindings'] == 1
    fixture_game(tmp_path, values={text_key: 'First.', KEY: 'Second.'}, voices=[wem([(label, 0)])])
    assert all(row['audio'] is None for row in assets.index_language(tmp_path, tmp_path, 'en', [])['records'])


def test_duplicate_performances_never_pick_first_and_missing_audio_is_not_silence(tmp_path):
    fixture_game(tmp_path, values={KEY: 'Synthetic.', 'ui_prompt': 'Choose an option.'}, voices=[wem(), wem()])
    rows = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert rows[0]['voice_status'] == 'unavailable'
    assert rows[1]['voice_status'] == 'unknown'
    assert all(row['audio'] is None and row['voice_status'] != 'unvoiced' for row in rows)


def test_unique_isolated_cinematic_line_preferred_to_scene_mix(tmp_path):
    movie = wem([('subtitle-start:' + KEY, 480), ('subtitle-end:' + KEY, 2880)])
    fixture_game(tmp_path, voices=[movie, wem()])
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    row, = result['records']
    assert row['voice_status'] == 'voiced' and 'start_ms' not in row['audio']
    assert result['narrative_inventory']['isolated_over_scene_mix'] == 1
    fixture_game(tmp_path, voices=[movie, wem(), wem()])
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert row['voice_status'] == 'unavailable'


def test_locale_and_physical_reference_cannot_be_forged(tmp_path):
    fixture_game(tmp_path)
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    audio = row['audio']
    with pytest.raises(ValueError, match='crosses'):
        assets.extract_voice(tmp_path, {**audio, 'locale': 'fr'}, Path(), tmp_path)
    for altered in [{**audio['entry'], 'archive': '../outside.tiger'}, {**audio['entry'], 'offset': 0}]:
        with pytest.raises(ValueError):
            assets.extract_voice(tmp_path, {**audio, 'entry': altered}, Path(), tmp_path)


def test_batch_reuses_one_directory_and_rejects_mixed_locales_before_reading(tmp_path, monkeypatch):
    fixture_game(tmp_path)
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    audio = row['audio']
    assert assets.extract_voices(tmp_path, [audio, audio], Path(), tmp_path) == [wem(), wem()]
    french = {**audio, 'locale': 'fr', 'entry': {**audio['entry'], 'locale': assets.VOICE_MASKS['fr']}}
    monkeypatch.setattr(assets, 'TigerSet', lambda *_args, **_kwargs: pytest.fail('Mixed dubs must be rejected before reading'))
    with pytest.raises(ValueError, match='crosses'):
        assets.extract_voices(tmp_path, [audio, french], Path(), tmp_path)


def test_malformed_localization_and_wem_fail_closed():
    valid = locals_bin('en', {KEY: 'Synthetic.'})
    wrong_pointer = bytearray(valid)
    struct.pack_into('<Q', wrong_pointer, 8, 8)
    for data in [b'', valid[:-1], bytes(wrong_pointer)]:
        with pytest.raises(PreparationFailure):
            assets.read_locals(data, 'en')
    with pytest.raises(PreparationFailure, match='language'):
        assets.read_locals(valid, 'fr')
    audio = wem()
    with pytest.raises(PreparationFailure):
        assets.wem_bindings(audio[:-1], len(audio) - 1)
    with pytest.raises(PreparationFailure):
        assets.wem_bindings(audio[:80], len(audio))


def test_patch_replaces_only_its_exact_locale_and_identity(tmp_path):
    fixture_game(tmp_path)
    (tmp_path / 'bigfile.update3.002.000.nfo').write_text('update3 version 4 required 1 bigfile 1 dlcindex 12\n')
    tiger(tmp_path, 'bigfile.update3.002_english_allvo_allplt.000.tiger', 12, 1,
          [(assets.LOCALS_HASH, assets.TEXT_MASKS['en'], locals_bin('en', {KEY: 'Patched sentence.'}))])
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert row['source_text'] == 'Patched sentence.' and row['audio']


def test_files_changed_retains_previous_snapshot(tmp_path, monkeypatch):
    fixture_game(tmp_path)
    calls = iter(['before', 'after'])
    monkeypatch.setattr(assets, 'fingerprint', lambda _: next(calls))
    with pytest.raises(PreparationFailure) as error:
        assets.index_language(tmp_path, tmp_path, 'en', [])
    assert error.value.game_files_changed and error.value.previous_snapshot_retained
