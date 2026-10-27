"""Locale contracts, authored bindings, safe playback and capture registration."""
import json
from pathlib import Path
import struct

import pytest

from backend import endfield_assets as endfield, genshin_assets as genshin, starrail_assets as starrail
from backend import hoyo_dialogue as common
from backend.dialogue_catalog import selected_tables
from backend.game_assets import LOCAL_GAMES, asset_adapter
from backend.game_paths import validate_install
from backend.games import GAME_PROFILES
from backend.languages import GAME_LOCALES, audio_locale
from backend.models import AppSettings
from backend.multilingual_index import MultilingualTextIndex
from backend.voice_assets import voice_hash


def external_package(path, source, payload=b'RIFF\x04\0\0\0WAVE'):
    identity = voice_hash(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'AKPK' + struct.pack('<6I', 60, 1, 4, 4, 4, 28) + bytes(12) +
        struct.pack('<IQ4I', 1, identity, 1, len(payload), 68, 0) + payload)
    return payload


@pytest.mark.parametrize('game,reader', [('genshin', genshin), ('starrail', starrail)])
@pytest.mark.parametrize('locale', common.SUPPORTED_LOCALES)
def test_authored_locale_binding_roundtrip_and_changed_package_rejection(tmp_path, game, reader, locale):
    folder = 'GenshinImpact_Data' if game == 'genshin' else 'StarRail_Data'
    audio_root = 'AudioAssets' if game == 'genshin' else 'Audio/AudioPackage/Windows'
    namespace = common.voice_namespace(game, locale)
    source = namespace + ('\\VO_Test\\sample.wem' if game == 'genshin' else '/voice/sample.wem')
    package = tmp_path / folder / 'StreamingAssets' / audio_root / namespace / 'External0.pck'
    payload = external_package(package, source)
    entries = common.inventory(tmp_path, game, locale)
    tables = {locale: {'123': 'Synthetic official study sentence.'}, 'fr': {'123': 'Une phrase de test.'}}
    rows = common.records(game, [{'id': '10', 'hash': 123, 'source': source}], tables, locale, entries)
    row, = rows
    assert row['audio'] and row['audio_locale'] == audio_locale(locale)
    assert row['texts'] == {locale: 'Synthetic official study sentence.', 'fr': 'Une phrase de test.'}
    assert reader.extract_voice(tmp_path, row['audio'], Path('unused'), tmp_path) == payload
    wrong = {**row['audio'], 'locale': 'ja' if locale != 'ja' else 'en'}
    with pytest.raises(ValueError, match='locale'):
        reader.extract_voice(tmp_path, wrong, Path('unused'), tmp_path)
    package.write_bytes(package.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='changed'):
        reader.extract_voice(tmp_path, row['audio'], Path('unused'), tmp_path)


def test_genshin_dialogue_join_keeps_conflicts_and_unbound_responses_out():
    hashes = genshin.dialogue_hashes([
        {'PCIAMAFDDAA': [{'id': 1, 'LKECPJIFFEE': 123}, {'id': 2, 'LKECPJIFFEE': 456}]},
        {'dialogList': [{'id': 2, 'talkContentTextMapHash': 789}]}])
    assert hashes == {'1': '123'}
    voices = [{'a': {'gameTrigger': 'Dialog', 'gameTriggerArgs': 1,
                     'sourceNames': [{'sourceFileName': 'VO_Test\\one.wem'}]},
               'b': {'gameTrigger': 'Fetter', 'gameTriggerArgs': 1,
                     'sourceNames': [{'sourceFileName': 'VO_Test\\wrong.wem'}]}}]
    links = genshin.dialogue_links(voices, hashes, 'ko')
    assert links == [{'id': '1', 'hash': '123', 'source': 'Korean\\VO_Test\\one.wem', 'player_voice': None}]


def test_current_genshin_schema_and_reminders_share_only_the_authored_locale_format():
    voice_maps = [{'a': {'GLDBLKKLJHP': [{'CFIKOCLOKGH': 'VO_Test\\current.wem'}],
                        'NLGBEEIGDJP': 'Dialog', 'BMPENHIILJG': 3510001},
                   'b': {'sourceNames': [{'sourceFileName': 'VO_Test\\reminder.wem'}],
                         'gameTrigger': 'DungeonReminder', 'gameTriggerArgs': 3510001}}]
    reminders = genshin.reminder_hashes([{'id': 3510001, 'HNDLKHJFLNF': 777, 'hasAudio': True}])
    links = genshin.dialogue_links(voice_maps, {'3510001': '123'}, 'zh-Hant', reminders)
    assert {(row['id'], row['hash']) for row in links} == {('3510001', '123'), ('reminder-3510001', '777')}
    assert all(row['source'].startswith('Chinese(PRC)\\') for row in links)


def test_endfield_radio_and_narration_use_their_explicit_text_and_voice_references():
    class Catalog:
        def file(self, path):
            return {
                'TableCfg/DialogTextTable.json': {'dlg_one': {'audioOverride': 'au_dlg_one', 'dialogText': {'id': 1}}},
                'TableCfg/RadioTable.json': {'group': {'radioSingleDataList': [
                    {'id': 'radio_one', 'audioOverride': 'au_radio_one', 'radioText': {'id': -2}, 'actorNameId': 'endminf'}]}},
                'TableCfg/TextTable.json': {'black_one': {'id': 3}},
                'TableCfg/TextVoIdTable.json': {'black_one': 'au_black_one', 'unmapped': 'unmapped'},
            }[path]
    rows = endfield.authored_dialogues(Catalog())
    assert set(rows) == {'dlg_one', 'radio_one', 'black_one'}
    assert rows['radio_one']['dialogText'] == {'id': -2}
    assert rows['black_one'] == {'dialogText': {'id': 3}, 'audioOverride': 'au_black_one',
                                 'dialogue_kind': 'narration', 'channels': ['cinematic', 'dialogue']}


def test_starrail_player_branches_remain_distinct_and_movies_are_not_whole_track_substitutes():
    sentences = [{'TalkSentenceID': 1, 'VoiceID': 7, 'TalkSentenceText': {'Hash': 12}},
                 {'TalkSentenceID': 2, 'VoiceID': 8, 'TalkSentenceText': {'Hash': 13}}]
    voices = [{'VoiceID': 7, 'VoicePath': 'scene', 'IsPlayerInvolved': True},
              {'VoiceID': 8, 'VoicePath': 'movie', 'VoiceType': 'Cutscene'}]
    links = starrail.sentence_links(sentences, voices, 'en')
    voiced = [row for row in links if row['source']]
    assert {row['player_voice'] for row in voiced} == {'male', 'female'}
    assert {row['source'] for row in voiced} == {'English/voice/scene_m.wem', 'English/voice/scene_f.wem'}
    assert {row['id'] for row in voiced} == {'1_m', '1_f'}
    movie, = [row for row in links if row['id'] == '2']
    assert movie['source'] is None and movie['voice_status'] == 'unavailable'


@pytest.mark.parametrize('reader', [genshin, starrail, endfield])
def test_every_declared_translation_resolves_and_only_requested_tables_are_read(reader):
    class Catalog:
        def __init__(self):
            self.reads = []
        def file(self, path, **_kwargs):
            self.reads.append(path)
            return {'123': 'Synthetic official text.'}
    for source in reader.SUPPORTED_LOCALES:
        for target in reader.TEXT_LOCALES:
            catalog = Catalog()
            tables = selected_tables(catalog, reader.TEXT_LOCALES, source, [target],
                medium=reader is genshin, prefix='TableCfg/I18nTextTable_' if reader is endfield else 'TextMap/TextMap')
            assert set(tables) == {source, target}
            assert len(catalog.reads) == len(set(catalog.reads))
            if reader is genshin:
                assert any('Medium' in path for path in catalog.reads)
            if reader is starrail and target in {'ko', 'ru', 'th'}:
                assert any('_0.json' in path for path in catalog.reads)
                assert any('_1.json' in path for path in catalog.reads)


@pytest.mark.parametrize('locale', endfield.SUPPORTED_LOCALES)
def test_endfield_exact_authored_source_path_binds_only_the_selected_language(tmp_path, monkeypatch, locale):
    path = 'v1d1/Narrating/Test/au_dlg_synthetic.wem'
    paths = endfield.audio_paths({'17': {'path': path, 'isPlaceholder': False}})
    source = 'voice/' + endfield.VOICE_LOCALES[locale] + '/' + path.lower()
    identity = f'{voice_hash(source):016x}'
    entry = {'file_id': identity, 'block': 101, 'chunk': 'A' * 32 + '.chk', 'file_hash': '123', 'size': 16}
    row, = endfield.dialogue_records({'dlg_test': {'audioOverride': 'au_dlg_synthetic', 'dialogText': {'id': -123}}},
        paths, {locale: {'-123': 'Synthetic study text.'}, 'fr': {'-123': 'Une phrase de test.'}}, locale, {identity: entry})
    assert row['audio']['locale'] == audio_locale(locale)
    calls = []
    monkeypatch.setattr(endfield, 'reader', lambda *args: calls.append(args) or b'RIFFsynthetic')
    assert endfield.extract_voice(tmp_path, row['audio'], Path('reader.dll'), tmp_path) == b'RIFFsynthetic'
    assert calls[0][-1]['language'] == endfield.VOICE_LOCALES[locale]
    with pytest.raises(ValueError, match='locale'):
        endfield.extract_voice(tmp_path, {**row['audio'], 'locale': 'ja' if locale != 'ja' else 'en'}, Path('reader.dll'), tmp_path)
    unresolved, = endfield.dialogue_records({'dlg_test': {'audioOverride': 'not_authored', 'dialogText': {'id': -123}}},
        paths, {locale: {'-123': 'Synthetic study text.'}}, locale, {identity: entry})
    assert unresolved['audio'] is None and unresolved['voice_status'] == 'unavailable'


def test_endfield_ambiguous_and_placeholder_source_paths_cannot_bind():
    assert endfield.audio_paths({'a': {'path': 'one/test.wem'}, 'b': {'path': 'two/test.wem'},
                                'c': {'path': 'one/placeholder.wem', 'isPlaceholder': True}}) == {}


@pytest.mark.parametrize('game', ['genshin', 'starrail', 'endfield'])
def test_new_game_registration_folder_normalization_and_independent_calibration(tmp_path, game):
    assert game in LOCAL_GAMES and GAME_LOCALES[game] == common.SUPPORTED_LOCALES
    assert asset_adapter(game)[0].SUPPORTED_LOCALES == common.SUPPORTED_LOCALES
    root = tmp_path / game
    exe, data = {'genshin': ('GenshinImpact.exe', 'GenshinImpact_Data'),
                 'starrail': ('StarRail.exe', 'StarRail_Data'), 'endfield': ('Endfield.exe', 'Endfield_Data')}[game]
    (root / data / 'StreamingAssets/VFS').mkdir(parents=True)
    (root / exe).touch()
    assert validate_install(game, root / data) == root.resolve()
    settings = AppSettings()
    assert getattr(settings, game + '_region') == GAME_PROFILES[game].subtitle_region
    assert settings.preferred_game == 'auto'
    assert getattr(settings, game + '_player_voice') == 'unconfigured'


@pytest.mark.parametrize('game', ['genshin', 'starrail', 'endfield'])
def test_new_game_multilingual_capture_matches_either_prepared_subtitle_and_skips_other_text(tmp_path, game):
    row = {'text_id': game + ':synthetic', 'source_locale': 'ja', 'source_text': '合成されたテスト文です。',
           'texts': {'ja': '合成されたテスト文です。', 'en': 'A deliberately synthetic subtitle.'},
           'english': 'A deliberately synthetic subtitle.', 'chinese': '', 'audio_locale': 'ja',
           'audio': {'source': 'synthetic-binding'}, 'channels': ['dialogue']}
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': game, 'source_locale': 'ja', 'records': [row]}), encoding='utf-8')
    index = MultilingualTextIndex(game, tmp_path)
    for text in row['texts'].values():
        assert index.match_lines([text]).text_id == row['text_id']
    assert index.match_lines(['A menu item with unrelated content.']) is None
    # A movie can repeat a brief interjection from a later conversation. Text
    # alone must not attach that later scene's voice to the movie caption.
    row['source_text'] = row['texts']['ja'] = '待って！'
    row['texts']['en'] = "Wait, don't go!"
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': game, 'source_locale': 'ja', 'records': [row]}), encoding='utf-8')
    assert index.load()
    assert index.match_lines(["Wait, don't go!"]) is None
