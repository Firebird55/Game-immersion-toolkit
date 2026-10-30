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


def message_row(identity='Message_Synthetic', **values):
    return {**dict.fromkeys(assets.MESSAGE_FIELDS, ''), 'LDHNMACDKLH': identity, **values}


def tip_row(identity='Tips_Synthetic', **values):
    return {**dict.fromkeys(assets.TIP_FIELDS, ''), 'BHLFCEAPFIG': identity, 'FFNNCACHDLN': [], **values}


def test_messages_join_exact_ids_without_lending_audio_to_reply_choices(tmp_path):
    source = 'VO_Message/Synthetic/Message_Synthetic_01'
    links, diagnostics = assets.message_links({'rows': [
        message_row(BKAEOOPMGNC=source, GJNMPOBFICI=source, FNOKFPDDECI='Option01_Synthetic',
                    GGHOAADLHCF='UI/Sprite/emoji.png'),
        message_row('Message_Silent'), message_row('Literal content'),
    ]}, {'Message_Synthetic': 'Message', 'Option01_Synthetic': 'Choice', 'Message_Silent': 'Silent',
         'Literal content': 'Not an identity', 'UI/Sprite/emoji.png': 'Not dialogue'})
    assert [(link['text_id'], link['source'], link['voice_status']) for link in links] == [
        ('Message_Synthetic', source, 'unavailable'), ('Option01_Synthetic', '', 'unknown'), ('Message_Silent', '', 'unvoiced')]
    assert diagnostics == {'rows': 3, 'text_references': 3, 'unresolved_voice_variants': 0}
    package = tmp_path / 'voice.pck'; package.write_bytes(bytes(128))
    hashed = voice_hash('japanese(jp)/ex/' + source + '.wem')
    tables = {'ja': {'Message_Synthetic': '原文のメッセージ。', 'Option01_Synthetic': '返事。', 'Message_Silent': '無音の文。'},
              'en': {'Message_Synthetic': 'Official message.'}}
    rows = {row['text_id']: row for row in assets.build_records(tables, 'ja', {'ja'}, links, [],
        {hashed: VoiceEntry(package, 64, 12, hashed)}, {}, 'japanese(jp)')}
    assert rows['Message_Synthetic']['voice_status'] == 'voiced'
    assert rows['Message_Synthetic']['dialogue_kind'] == 'message'
    assert rows['Message_Synthetic']['texts'] == {'ja': '原文のメッセージ。'}
    assert rows['Option01_Synthetic']['audio'] is None
    assert rows['Option01_Synthetic']['dialogue_kind'] == 'choice'
    assert rows['Message_Silent']['voice_status'] == 'unvoiced'


def test_message_alternates_and_unsupported_sources_never_choose_an_installed_variant():
    links, diagnostics = assets.message_links({'rows': [message_row(
        BKAEOOPMGNC='VO_Message/First/Message_First_01', GJNMPOBFICI='VO_Message/Other/Message_Other_01'),
        message_row('Message_Future', BKAEOOPMGNC='FutureUnknownSource')]},
        {'Message_Synthetic': 'Message', 'Message_Future': 'Future'})
    assert all(link['source'] == '' and link['voice_status'] == 'unavailable' for link in links)
    assert diagnostics['unresolved_voice_variants'] == 2


def test_gameplay_tips_distinguish_original_sentences_reactions_and_silence():
    configs = [
        tip_row(NMMACKNBLKO='VO_Tips/VO_Synthetic/Tips_Synthetic_01', FNHBBPCONOL='Smile_01,Smile_02'),
        tip_row('Tips_Silent'),
        tip_row('Tips_Reaction', FNHBBPCONOL='Smile_01'),
        tip_row('Tips_Alternate', NMMACKNBLKO='Level_First_01', NPDBBLABDAK='Level_Other_01'),
        tip_row('Tips_Event', FFNNCACHDLN=['Play_unknown_event']),
        tip_row('Tips_Future', KDPLFOOHOAA='new_configuration'),
        tip_row('UI/Sprite/icon.png'),
    ]
    links, diagnostics = assets.tip_links({'rows': configs}, {row['BHLFCEAPFIG']: 'Text' for row in configs})
    assert [(link['text_id'], link['source'], link['voice_status']) for link in links] == [
        ('Tips_Synthetic', 'VO_Tips/VO_Synthetic/Tips_Synthetic_01', 'unavailable'),
        ('Tips_Silent', '', 'unvoiced'), ('Tips_Reaction', '', 'unknown'),
        ('Tips_Alternate', '', 'unavailable'), ('Tips_Event', '', 'unknown'), ('Tips_Future', '', 'unknown')]
    assert diagnostics['unresolved_voice_variants'] == 1
    assert all(link['dialogue_kind'] == 'gameplay_tip' and link['channels'] == ['tip', 'gameplay'] for link in links)


@pytest.mark.parametrize('reader, row', [(assets.message_links, message_row()), (assets.tip_links, tip_row())])
def test_supplemental_schema_drift_fails_before_certifying_silent_text(reader, row):
    identity = row.get('LDHNMACDKLH') or row.get('BHLFCEAPFIG')
    for changed in ({**row, 'newVoiceField': ''}, {key: value for key, value in row.items() if key != next(iter(row))}):
        with pytest.raises(assets.PreparationFailure, match='unsupported table format'):
            reader({'rows': [row, changed]}, {identity: 'Text'})
    with pytest.raises(assets.PreparationFailure, match='unsupported table format'):
        reader({'rows': []}, {})


def test_supplemental_downloads_are_pinned_and_do_not_depend_on_the_scene_cache(monkeypatch):
    revision = 'a' * 40; urls = []
    def download(url):
        urls.append(url)
        return json.dumps({'rows': [message_row()] if '/MessageConfig' in url else [tip_row()]}).encode()
    monkeypatch.setattr(assets.game_tools, 'download', download)
    links, diagnostics = assets.supplemental_links(revision, {'Message_Synthetic': 'Message', 'Tips_Synthetic': 'Tip'})
    assert len(links) == 2 and len(diagnostics) == 2
    assert all('/raw/commit/' + revision + '/FileCfg/' in url for url in urls)


def test_unmatched_scene_references_are_coverage_notes_without_discarding_verified_audio(tmp_path, monkeypatch):
    (tmp_path / 'ZenlessZoneZero_Data').mkdir()
    package = tmp_path / 'voice.pck'; package.write_bytes(bytes(128))
    source = 'VO_Galgame/VO_Test/Line'
    identity = voice_hash('english(en)/ex/' + source + '.wem')
    tools = tmp_path / 'tools'; tools.mkdir()
    text, male, female = assets.ONGOING_SCHEMAS[0]
    for name, value in {'OngoingTipsConfigTemplateTb.json': {'rows': [{text: '', male: '', female: ''}]},
                        'VoiceData.json': {'allPrefixes': []}, 'AudioResourceData.json': {}}.items():
        (tools / name).write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr(assets.game_tools, 'download', lambda _: json.dumps({'commit': {'id': 'a' * 40}}).encode())
    monkeypatch.setattr(assets, '_tables', lambda *_: {'en': {'GalGame_Test': 'Official synthetic dialogue.'}})
    monkeypatch.setattr(assets, '_links', lambda *_: ([{'text_id': 'GalGame_Test', 'source': source}], [], tools,
        [{'unresolved_scenes': 3, 'unsupported_dialogue_nodes': {}}]))
    monkeypatch.setattr(assets, 'supplemental_links', lambda *_: ([], {}))
    monkeypatch.setattr(assets, 'localized_inventory', lambda *_: ('english(en)', {identity: VoiceEntry(package, 64, 12, identity)}))
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert result['records'][0]['voice_status'] == 'voiced'
    assert result['records'][0]['audio']['file_id'] == f'{identity:016x}'
    assert 'coverage note: 3 unmatched metadata scene references' in result['message']
    assert 'does not stop preparation' in result['coverage_warnings'][0]
    assert result['coverage']['scene_catalogs'][0]['unresolved_scenes'] == 3
