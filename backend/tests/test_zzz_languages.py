import json
from pathlib import Path

import pytest

from backend import zzz_assets as assets
from backend.multilingual_index import MultilingualTextIndex
from backend.models import is_comic_text_id
from backend.voice_assets import VoiceEntry, voice_hash
from backend.tests.test_zzz_cinematics import cinematic_package
from backend.nte_assets import wwise_hash

NAMESPACES = {'en': 'english(en)', 'zh-Hans': 'chinese(prc)', 'zh-Hant': 'chinese(prc)',
              'ja': 'japanese(jp)', 'ko': 'korean(kr)'}


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_selected_text_uses_the_authored_namespace_and_original_pack(tmp_path, locale):
    root = tmp_path / 'ZenlessZoneZero_Data'
    package = root / 'Persistent/Audio/Windows/Full' / assets.VOICE_FOLDERS[locale] / 'voice.pck'
    package.parent.mkdir(parents=True)
    wem = b'RIFF\x04\0\0\0WAVE'
    package.write_bytes(bytes(64) + wem)
    source = 'VO_Galgame/Ver3_1/VO_Synthetic/GalGame_Synthetic_01'
    identity = voice_hash(NAMESPACES[locale] + '/ex/' + source + '.wem')
    tables = {'en': {'GalGame_Test': 'Official English binding text.'},
              locale: {'GalGame_Test': 'Official study text.'}, 'fr': {'GalGame_Test': 'Traduction officielle.'}}
    rows = assets.build_records(tables, locale, {locale, 'fr'}, [{'text_id': 'GalGame_Test', 'source': source}], [],
        {identity: VoiceEntry(package, 64, len(wem), identity)}, {}, NAMESPACES[locale])
    row, = rows
    assert row['source_text'] == 'Official study text.'
    assert row['audio_locale'] == ('zh-Hans' if locale == 'zh-Hant' else locale)
    assert row['texts'] == {locale: 'Official study text.', 'fr': 'Traduction officielle.'}
    assert ('en' in row['texts']) == (locale == 'en'), 'Binding metadata cannot provision an English translation'
    assert assets.extract_voice(tmp_path, row['audio'], Path('unused'), tmp_path) == wem
    wrong = {**row['audio'], 'locale': 'ja' if locale != 'ja' else 'en'}
    with pytest.raises(ValueError, match='locale'):
        assets.extract_voice(tmp_path, wrong, Path('unused'), tmp_path)


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_cinematic_language_is_read_from_selected_pack_metadata(tmp_path, locale):
    root = tmp_path / 'ZenlessZoneZero_Data'
    path = root / 'Persistent/Audio/Windows/Full' / assets.VOICE_FOLDERS[locale] / 'bank.pck'
    wem = cinematic_package(path, language=NAMESPACES[locale])
    namespace, _ = assets.localized_inventory(root, locale)
    assert namespace == NAMESPACES[locale]
    result = assets.resolve_cinematic_links([{'text_id': 'CS_Synthetic_01', 'event': 'Play_vo_Synthetic_01'}], root,
        {'eventReferenceBanks': [wwise_hash('Play_vo_Synthetic_01'), 77, 88, 0]},
        folder=assets.VOICE_FOLDERS[locale], namespace=namespace)
    item = result['CS_Synthetic_01']
    assert VoiceEntry(Path(item['package']), item['offset'], item['size'], int(item['file_id'], 16)).read() == wem


def test_explicit_comic_gender_bindings_keep_originals_and_historical_visibility(tmp_path):
    root = tmp_path / 'ZenlessZoneZero_Data'
    package = root / 'Persistent/Audio/Windows/Full/Jp/voice.pck'
    package.parent.mkdir(parents=True); package.write_bytes(bytes(128))
    identity = 'Comic_' + 'a' * 32
    sources = {'M': 'VO_Test/Male', 'F': 'VO_Test/Female'}
    inventory = {value: VoiceEntry(package, 64, 12, value) for source in sources.values()
                 for value in [voice_hash('japanese(jp)/ex/' + source + '.wem')]}
    rows = assets.build_records({'en': {identity: '{M#His sentence.}{F#Her sentence.}'},
        'ja': {identity: '同じ字幕です。'}}, 'ja', {'ja'},
        [{'text_id': identity, 'source': '{M#' + sources['M'] + '}{F#' + sources['F'] + '}', 'channels': ['cinematic']}],
        [], inventory, {}, 'japanese(jp)')
    assert {r['text_id'] for r in rows} == {identity + ':M', identity + ':F'}
    assert all(is_comic_text_id(r['text_id']) for r in rows)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'zzz', 'source_locale': 'ja', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('zzz', tmp_path)
    assert index.match_lines(['同じ字幕です。'], channel='cinematic') is None
    for voice, suffix in [('male', ':M'), ('female', ':F')]:
        index.player_voice = voice
        assert index.match_lines(['同じ字幕です。'], channel='cinematic').text_id == identity + suffix
    assert index.is_capture_text(identity, '', 'cinematic'), 'Historical Chinese comic identities remain visible'
    assert not index.is_capture_text(identity, '', 'dialogue')
    rows[0]['source_text'] = rows[0]['texts']['ja'] = '男性の字幕です。'
    rows[1]['source_text'] = rows[1]['texts']['ja'] = '女性の字幕です。'
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'zzz', 'source_locale': 'ja', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('zzz', tmp_path)
    assert index.match_lines(['女性の字幕です。'], channel='cinematic').text_id == identity + ':F'


def test_uninstalled_pack_and_mixed_language_batch_never_borrow(tmp_path):
    assert assets.localized_inventory(tmp_path, 'ko') == (None, {})
    with pytest.raises(ValueError, match='crosses study/audio locales'):
        assets.extract_voices(tmp_path, [{'locale': 'en'}, {'locale': 'ja'}], Path('unused'), tmp_path)


@pytest.mark.parametrize('schema', assets.ONGOING_SCHEMAS)
def test_authored_ongoing_fields_preserve_proxy_roles_across_supported_schemas(schema):
    text, male, female = schema
    links = assets.ongoing_links({'rows': [{text: 'Main_OngoingLevel_Test', male: 'Wise_source', female: 'Belle_source'},
                                          {text: 'Tips_Test', male: '', female: 'NPC_source'}]})
    assert [(r['source'], r['gender'], r['channels']) for r in links] == [
        ('Wise_source', 'M', ['gameplay']), ('Belle_source', 'F', ['gameplay']), ('NPC_source', None, ['tip'])]


def test_unknown_ongoing_schema_cannot_silently_publish_an_incomplete_index():
    with pytest.raises(ValueError, match='Unsupported ZZZ ongoing dialogue schema'):
        assets.ongoing_links({'rows': [{'unknown': 'Main_OngoingLevel_Test'}]})


@pytest.mark.parametrize('schema', assets.ONGOING_SCHEMAS)
def test_authored_silent_ongoing_rows_survive_and_later_schema_drift_fails(schema):
    text, male, female = schema
    rows = [{text: 'Tips_Synthetic', male: '', female: ''}]
    link, = assets.ongoing_links({'rows': rows})
    assert link['source'] == '' and link['voice_status'] == 'unvoiced'
    assert link['dialogue_kind'] == 'ambient'
    with pytest.raises(ValueError, match='Unsupported ZZZ ongoing'):
        assets.ongoing_links({'rows': rows + [{text: 'Tips_NewSchema'}]})


def test_typed_silent_choices_missing_voices_and_unknown_comics_are_distinct():
    comic = 'Comic_' + 'f' * 32
    texts = {identity: 'Synthetic dialogue ' + str(i) for i, identity in enumerate(['Silent', 'Choice', 'Missing', 'Conflict', comic])}
    links = [
        {'text_id': 'Silent', 'source': '', 'voice_status': 'unvoiced', 'dialogue_kind': 'conversation'},
        {'text_id': 'Choice', 'source': '', 'voice_status': 'unknown', 'dialogue_kind': 'choice'},
        {'text_id': 'Missing', 'source': 'GalGame_Synthetic'},
        {'text_id': 'Conflict', 'source': '', 'voice_status': 'unvoiced'},
        {'text_id': 'Conflict', 'source': '', 'voice_status': 'unknown'},
    ]
    rows = {row['text_id']: row for row in assets.build_records({'en': texts}, 'en', {'en'}, links, [], {}, {}, None)}
    assert {key: row['voice_status'] for key, row in rows.items()} == {
        'Silent': 'unvoiced', 'Choice': 'unknown', 'Missing': 'unavailable', 'Conflict': 'unknown', comic: 'unknown'}
    assert rows['Choice']['dialogue_kind'] == 'choice' and rows[comic]['dialogue_kind'] == 'comic'
    assert all(row['audio'] is None for row in rows.values())


def test_unrequested_english_variants_do_not_change_a_neutral_selected_language(tmp_path):
    package = tmp_path / 'voice.pck'; package.write_bytes(bytes(128))
    source = 'VO_Galgame/VO_Test/Line'
    hashed = voice_hash('japanese(jp)/ex/' + source + '.wem')
    rows = assets.build_records({'en': {'GalGame_Test': '{M#His words.}{F#Her words.}'},
        'ja': {'GalGame_Test': '同じ字幕です。'}}, 'ja', {'ja'},
        [{'text_id': 'GalGame_Test', 'source': source}], [], {hashed: VoiceEntry(package, 64, 12, hashed)}, {}, 'japanese(jp)')
    row, = rows
    assert row['text_id'] == 'GalGame_Test' and row['player_voice'] is None
    assert row['texts'] == {'ja': '同じ字幕です。'}
