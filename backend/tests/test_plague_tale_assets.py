"""Synthetic fixtures only: no game text, audio, credentials or native archives."""
import json
import struct

import pytest

from backend import plague_tale_assets as game
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex
from backend.plague_tale_formats import Package, bank_events, read_file, script_bundle, text_table, wwise_hash
from backend.preparation_errors import PreparationFailure


def u(fmt, *values):
    return struct.pack('<' + fmt, *values)


def psc(text):
    data = text.encode('utf-8')
    tail, left = b'', len(data) - 15
    if left >= 0:
        while left >= 255:
            tail += b'\xff'
            left -= 255
        tail += bytes([left])
    packed = bytes([min(len(data), 15) << 4]) + tail + data
    return u('II', len(data), len(packed)) + packed


def package(path, languages, banks=(), media=()):
    """Assign different language IDs in different packages to catch guessing."""
    table = u('I', len(languages))
    strings = b''
    for language, identity in languages.items():
        table += u('II', 4 + len(languages) * 8 + len(strings), identity)
        strings += language.encode('utf-16-le') + b'\0\0'
    table += strings
    sizes = len(table), 4 + len(banks) * 20, 4 + len(media) * 20, 4
    header_size = 20 + sum(sizes)
    payload, sections = bytearray(), []
    for entries in (banks, media):
        directory = u('I', len(entries))
        for identity, language, data in entries:
            directory += u('IIIII', identity, 1, len(data), header_size + 8 + len(payload), languages[language])
            payload.extend(data)
        sections.append(directory)
    path.write_bytes(b'AKPK' + u('6I', header_size, 1, *sizes) + table + b''.join(sections) + u('I', 0) + payload)


def bank(language, events, bank_id=17, multi=False, localized=True):
    objects = []
    for number, (identity, media) in enumerate(events.items()):
        sound_id, action_id = 100 + number, 200 + number
        sound = u('IIBII', sound_id, 0x40001, 2, media, 200) + bytes([int(localized)]) + b'\0' * 24
        action = u('IH', action_id, 0x0403) + u('I', sound_id) + b'\0\0\0\4' + u('I', bank_id)
        event = u('IBI', wwise_hash('play_' + identity), 1, action_id)
        if multi:
            event = u('IBII', wwise_hash('play_' + identity), 2, action_id, action_id)
        objects.extend([(2, sound), (3, action), (4, event)])
    hierarchy = u('I', len(objects)) + b''.join(u('BI', kind, len(data)) + data for kind, data in objects)
    header = u('6I', 132, bank_id, wwise_hash(language), 0, 0, 0)
    return b'BKHD' + u('I', len(header)) + header + b'HIRC' + u('I', len(hierarchy)) + hierarchy


VOICE = 'VO__SPEAKER__CH1__RTC_TEST_001__M__1'
BARK = 'VO__SPEAKER__CH1__PATROL_TEST__M__1'
MISSING = 'VO__SPEAKER__CH1__ORDER_TEST__M__1'
PLACEHOLDER = 'VO__SPEAKER__CH1__ONOM_TEST__M__1'
LORE = 'GAME__CODEX_CATEGORY_1_ITEM_1_DESC'
SCRIPT = '''BOOT.TSC\0
LoadFilePackage VO_STRUCTURE TRUE
LoadFilePackage VO_AMICIA_MEDIA TRUE
LoadFilePackage VO_D1_MEDIA TRUE
AddLootItem CODEX_FLOWER_1 GAME__CODEX_CATEGORY_1_ITEM_1 SOUND__LOOT_NORMAL GAME__CODEX_CATEGORY_1_ITEM_1_DESC LOOT_ALL LOOT_01 UI_1 CODEX_FLOWER 1 CHAPTER HAIR EPIC
AddRecipe UPGRADE_TEST UPGRADE HUD__GAMEMENU_UPGRADES_TEST Test Preview HUD__GAMEMENU_UPGRADES_TEST_DESC HUD__GAMEMENU_UPGRADES_TEST_LOREDESC 1 1 MATERIAL 1 TOOL
AddVOSubtitleSpeaker VO__SPEAKER DEFAULT HUD__SUBTITLE_SPEAKER_TEST
'''


def synthetic_install(root, missing_locale=None, missing_media=False):
    (root / 'TRTEXT').mkdir()
    (root / 'SOUNDBANKS').mkdir()
    (root / 'APlagueTaleInnocence_x64.exe').touch()
    (root / 'All.psc').write_bytes(psc(SCRIPT))
    definitions = []
    for locale, number in game.TEXT_LOCALES.items():
        language = game.VOICE_LOCALES.get(locale, 'english(us)')
        definitions.append(f'AddLangDefine {number} 0 0 LANG "{language}"')
        rows = {VOICE: f'A synthetic cinematic in {locale}.', BARK: f'A synthetic patrol in {locale}.',
                MISSING: f'A missing performance in {locale}.', PLACEHOLDER: PLACEHOLDER,
                LORE: f'Synthetic collectible history in {locale}.',
                'HUD__GAMEMENU_UPGRADES_TEST_LOREDESC': f'Synthetic crafting history in {locale}.',
                'HUD__SUBTITLE_SPEAKER_TEST': 'Synthetic speaker', 'MENU__UNKNOWN': 'Unknown menu wording'}
        lines = ['FreeLanguage', 'ResetEnumTT', *(f'TT {i} "{text}" {identity}' for i, (identity, text) in enumerate(rows.items())), 'EndLoadTT']
        (root / 'TRTEXT' / f'tt{number}.pc').write_bytes(('\r\n'.join(lines) + '\r\n').encode('utf-8'))
    (root / 'LangDef.tsc').write_text('\n'.join(definitions), encoding='utf-8')
    languages = {language: number for number, language in enumerate(game.VOICE_LOCALES.values(), 1)}
    structure, base, overlay = [], [], []
    for n, (locale, language) in enumerate(game.VOICE_LOCALES.items(), 1):
        if locale == missing_locale:
            continue
        events = {VOICE: n * 1000 + 1, BARK: n * 1000 + 2, MISSING: n * 1000 + 3, PLACEHOLDER: n * 1000 + 4}
        structure.append((17, language, bank(language, events)))
        if not missing_media:
            for identity in (events[VOICE], events[BARK], events[PLACEHOLDER]):
                base.append((identity, language, b'RIFF' + u('I', 20) + b'WAVEbase-' + locale.encode()))
            overlay.append((events[VOICE], language, b'RIFF' + u('I', 20) + b'WAVEpatch-' + locale.encode()))
    folder = root / 'SOUNDBANKS'
    package(folder / 'VO_STRUCTURE.PC.PCK', languages, banks=structure)
    package(folder / 'VO_AMICIA_MEDIA.PC.PCK', {key: value + 12 for key, value in languages.items()}, media=base)
    package(folder / 'VO_D1_MEDIA.PC.PCK', {key: 99 - value for key, value in languages.items()}, media=overlay)


@pytest.mark.parametrize('locale', game.SUPPORTED_LOCALES)
def test_all_official_voices_and_text_locales_use_authored_original_bindings(tmp_path, locale):
    synthetic_install(tmp_path)
    result = game.index_language(tmp_path, tmp_path, locale, list(game.TEXT_LOCALES))
    assert result['format'] == 2 and not result['missing_translation_locales']
    assert result['narrative_inventory']['voice_counts'] == {'voiced': 2, 'unavailable': 1, 'unvoiced': 2, 'unknown': 2}
    assert result['narrative_inventory']['voice_identifiers_without_subtitle_prose'] == 1
    for row in result['records']:
        LocalDialogue(**row)
        assert row['source_text'] == row['texts'][locale]
        assert row['audio_locale'] == locale
        assert set(row['texts']) == set(game.TEXT_LOCALES)
    cinematic = next(row for row in result['records'] if row['dialogue_kind'] == 'cinematic')
    assert cinematic['audio']['archive'] == 'VO_D1_MEDIA.PC.PCK'
    assert game.extract_voice(tmp_path, cinematic['audio'], None, None).endswith(b'patch-' + locale.encode())
    assert cinematic['speaker_english'] == 'Synthetic speaker'
    (tmp_path / 'textmap.json').write_text(json.dumps(result), encoding='utf-8')
    index = MultilingualTextIndex(game.GAME, tmp_path)
    assert index.ready and index.audio_count == 2


@pytest.mark.parametrize('locale', game.SUPPORTED_LOCALES)
def test_absent_original_pack_remains_available_as_an_actionable_choice(tmp_path, locale):
    synthetic_install(tmp_path, missing_locale=locale)
    result = game.index_language(tmp_path, tmp_path, locale, [])
    assert game.probe_voice_pack(tmp_path, locale) == 'missing'
    counts = result['narrative_inventory']['voice_counts']
    assert counts.get('voiced', 0) == 0 and counts['unavailable'] == 3 and counts['unvoiced'] == 2
    assert any('verify game files' in warning for warning in result['coverage_warnings'])
    assert locale in game.SUPPORTED_LOCALES


def test_missing_recording_is_never_unvoiced_and_absent_script_cannot_invent_priority(tmp_path):
    synthetic_install(tmp_path, missing_media=True)
    result = game.index_language(tmp_path, tmp_path, 'en', [])
    assert result['narrative_inventory']['voice_counts']['unavailable'] == 3
    (tmp_path / 'All.psc').unlink()
    result = game.index_language(tmp_path, tmp_path, 'en', [])
    assert not any(row['voice_status'] == 'unvoiced' for row in result['records'])


def test_extraction_revalidates_locale_graph_and_patch_precedence(tmp_path):
    synthetic_install(tmp_path)
    row = next(row for row in game.index_language(tmp_path, tmp_path, 'en', [])['records'] if row['audio'])
    for change in ({'archive': '../outside'}, {'archive': 'VO_AMICIA_MEDIA.PC.PCK'}, {'locale': 'de'},
                   {'media': 999}, {'bank': 99}, {'text_id': BARK}, {'event': True}):
        with pytest.raises(PreparationFailure):
            game.extract_voice(tmp_path, {**row['audio'], **change}, None, None)


def test_package_header_is_bounded_and_language_ids_are_package_local(tmp_path):
    path = tmp_path / 'sample.pck'
    package(path, {'german': 81}, media=[(9, 'german', b'synthetic')])
    archive = Package(path)
    entry = archive.entries['media', 9, 'german']
    assert archive.read(entry) == b'synthetic'
    with pytest.raises(PreparationFailure):
        archive.read(entry, limit=2)
    original = path.read_bytes()
    for offset, value in ((4, 0xffffffff), (8, 2), (12, 0), (28, 0xffffffff)):
        damaged = bytearray(original)
        struct.pack_into('<I', damaged, offset, value)
        path.write_bytes(damaged)
        with pytest.raises(PreparationFailure):
            Package(path)
    path.write_bytes(original[:-1])
    with pytest.raises(PreparationFailure):
        Package(path)


def test_unknown_event_topologies_and_unlocalized_sources_are_unavailable():
    language = game.VOICE_LOCALES['fr']
    for kwargs in ({'multi': True}, {'localized': False}):
        events, unresolved = bank_events(bank(language, {VOICE: 10}, **kwargs), language, 17)
        assert events == {} and unresolved == {wwise_hash('play_' + VOICE)}
    for data, language, identity in ((bank('german', {VOICE: 10}), 'english(us)', 17),
                                      (bank('german', {VOICE: 10}), 'german', 18),
                                      (bank('german', {VOICE: 10})[:-1], 'german', 17)):
        with pytest.raises(PreparationFailure):
            bank_events(data, language, identity)


def test_tsc_preserves_unicode_and_case_insensitive_ids_but_rejects_ambiguity():
    data = 'FreeLanguage\nResetEnumTT\nTT 4 "试验 / Grüße / 日本語" VO__Mixed\nEndLoadTT'.encode()
    assert text_table(data) == {'VO__MIXED': '试验 / Grüße / 日本語'}
    for bad in (data.replace(b'TT 4', b'BAD 4'), data.replace(b'EndLoadTT', b''),
                data.replace(b'EndLoadTT', b'TT 5 "Duplicate" VO__MIXED\nEndLoadTT')):
        with pytest.raises(PreparationFailure):
            text_table(bad)


def test_lz4_and_file_reads_enforce_output_bounds(tmp_path):
    text = 'SYNTHETIC.TSC\0\n' + 'long command\n' * 40
    assert script_bundle(psc(text)) == text
    for bad in (psc(text)[:-1], u('II', 0xffffffff, 0), u('II', 4, 3) + b'\0\0\0'):
        with pytest.raises(PreparationFailure):
            script_bundle(bad)
    path = tmp_path / 'oversized'
    path.write_bytes(b'12345')
    with pytest.raises(PreparationFailure):
        read_file(path, 4)


def test_new_pickup_sound_does_not_claim_silence_and_readables_require_authored_fields(tmp_path):
    synthetic_install(tmp_path)
    (tmp_path / 'All.psc').write_bytes(psc(SCRIPT.replace('SOUND__LOOT_NORMAL', 'SOUND__NEW_UNKNOWN')))
    result = game.index_language(tmp_path, tmp_path, 'en', [])
    lore = next(row for row in result['records'] if row['text_id'].endswith(LORE))
    assert lore['voice_status'] == 'unknown'


def test_missing_text_invalid_manifest_and_fingerprint_changes(tmp_path):
    synthetic_install(tmp_path)
    before = game.fingerprint(tmp_path)
    path = tmp_path / 'TRTEXT/tt04.pc'
    path.unlink()
    assert game.fingerprint(tmp_path) != before
    with pytest.raises(PreparationFailure, match='text is missing'):
        game.index_language(tmp_path, tmp_path, 'de', [])
    manifest = tmp_path / 'LangDef.tsc'
    manifest.write_text(manifest.read_text().replace('"german"', '"english(us)"'))
    with pytest.raises(PreparationFailure, match='LangDef'):
        game.index_language(tmp_path, tmp_path, 'de', [])
