"""Synthetic authored schemas protect reading boundaries and honest voice evidence."""
import json
from pathlib import Path

import pytest

from backend import cyberpunk_assets as assets
from backend.preparation_errors import PreparationFailure


def write_resource(path, root):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'Data': {'RootChunk': root}}), encoding='utf-8')


def localized(path, kind, entries):
    write_resource(path, {'$type': 'JsonResource', 'root': {'Data': {'$type': kind, 'entries': entries}}})


def test_reading_joins_authored_journal_keys_without_indexing_menus_or_borrowing_voice(tmp_path, monkeypatch):
    install = tmp_path / 'game'
    for group, metadata in [('content', 'basegame_4_gamedata'), ('ep1', 'ep1_2_gamedata')]:
        folder = install / 'archive/pc' / group
        folder.mkdir(parents=True)
        for name in ('lang_en_text', 'lang_zh-cn_text', 'lang_en_voice', metadata):
            (folder / (name + '.archive')).touch()
    monkeypatch.setattr(assets, 'ensure_wolvenkit', lambda _: Path('synthetic'))

    def extract(_tool, command, *args):
        if command == 'cr2w':
            return
        archive, dest = Path(args[0]), Path(args[args.index('-o') + 1])
        group = archive.parent.name
        namespace = 'base' if group == 'content' else 'ep1'
        if 'gamedata' in archive.name:
            entries = [
                {'$type': 'gameJournalPhoneMessage', 'text': {'value': 'LocKey#17'}},
                {'$type': 'gameJournalPhoneChoiceEntry', 'text': {'value': 'reply_key'}},
                {'$type': 'gameJournalOnscreen', 'description': {'value': 'LocKey#19'}},
                {'$type': 'gameJournalEmail', 'content': {'value': 'LocKey#20'},
                 'videoResource': {'DepotPath': {'$value': '0'}}},
                {'$type': 'gameJournalFile', 'content': {'value': 'LocKey#21'},
                 'videoResource': {'DepotPath': {'$value': 'unresolved_video.bk2'}}},
                {'$type': 'gameJournalPhoneMessage', 'text': {'value': 'LocKey#404'}},
            ]
            write_resource(dest / namespace / 'journal/cooked_journal.journal.json',
                {'$type': 'gameJournalResource', 'entry': {'Data': {'entries': entries}}})
        elif '_voice.' in archive.name:
            localized(dest / 'voiceovermap.json.json', 'locVoiceoverMap', [
                {'stringId': '9007199254740995', 'femaleResPath': {'DepotPath': {'$value': group + '/exact.wem'}}},
                {'stringId': '9007199254740996', 'femaleResPath': {'DepotPath': {'$value': '987654321'}}},
            ])
        else:
            marker = ('Study ' if '_en_' in archive.name else 'Translation ') + group
            localized(dest / 'subtitles/open_world/scenes/synthetic.json.json', 'localizationPersistenceSubtitleEntries', [
                {'stringId': identity, 'femaleVariant': marker + ' ' + identity}
                for identity in ['9007199254740995', '9007199254740996', '9007199254740997']
            ])
            localized(dest / 'onscreens/onscreens.json.json', 'localizationPersistenceOnScreenEntries', [
                {'primaryKey': str(key), 'secondaryKey': 'reply_key' if key == 18 else f'key_{key}',
                 'femaleVariant': marker + ' ' + str(key), 'maleVariant': ''}
                for key in [17, 18, 19, 20, 21, 99]
            ])

    monkeypatch.setattr(assets, 'run_wolvenkit', extract)
    result = assets.index_language(install, tmp_path / 'cache', 'en', ['zh-Hans'])
    reading = [row for row in result['records'] if row['voice_status'] == 'unvoiced']
    assert len(reading) == 8
    assert {row['dialogue_kind'] for row in reading} == {'phone_message', 'phone_response', 'readable', 'email'}
    assert all(row['audio'] is None and len(row['texts']) == 2 for row in reading)
    assert all(('content' in row['source_text']) == ('content' in row['texts']['zh-Hans']) for row in reading)
    assert not any(row['source_text'].endswith((' 21', ' 99')) for row in reading)
    spoken = [row for row in result['records'] if row['audio']]
    assert {row['audio']['depot'] for row in spoken} == {'content/exact.wem', 'ep1/exact.wem'}
    assert all(row['voice_status'] == 'voiced' and row['dialogue_kind'] == 'ambient_dialogue' for row in spoken)
    assert all(row['voice_status'] == 'unavailable' for row in result['records']
               if ':9007199254740996:female' in row['text_id'])
    assert all(row['voice_status'] == 'unknown' for row in result['records']
               if ':9007199254740997:' in row['text_id'])
    assert any('2 authored journal references' in warning for warning in result['coverage_warnings'])
    assert any('Scene-embedded response' in warning for warning in result['coverage_warnings'])


@pytest.mark.parametrize('kind,entries', [('newLocalizationFormat', []), ('locVoiceoverMap', {}),
    ('localizationPersistenceSubtitleEntries', [None])])
def test_unrecognized_localization_schema_has_actionable_format_failure(tmp_path, kind, entries):
    path = tmp_path / 'resource.json.json'
    localized(path, kind, entries)
    with pytest.raises(PreparationFailure) as error:
        assets.json_entries(path)
    assert error.value.code == 'unsupported_game_format'
    assert 'Update the toolkit' in str(error.value)
    assert str(path) not in str(error.value)


def test_journal_schema_change_cannot_silently_claim_no_reading_text(tmp_path):
    path = tmp_path / 'cooked_journal.journal.json'
    write_resource(path, {'$type': 'newJournalResource', 'entry': {}})
    with pytest.raises(PreparationFailure) as error:
        assets.journal_references(path)
    assert error.value.code == 'unsupported_game_format'


def test_journal_changes_invalidate_language_preparation(tmp_path):
    path = tmp_path / assets.JOURNAL_ARCHIVES[0]
    path.parent.mkdir(parents=True)
    path.write_bytes(b'old')
    before = assets.fingerprint(tmp_path)
    path.write_bytes(b'new journal metadata')
    assert assets.fingerprint(tmp_path) != before


def test_zero_resource_hash_is_absence_not_an_unresolved_performance():
    assert assets.resource_path({'femaleResPath': {'DepotPath': {'$value': '0'}}}, 'female') == ''
    assert assets.voice_status(None, '') == 'unknown'
    assert assets.voice_status(None, 'nonzero-unresolved-resource') == 'unavailable'


@pytest.mark.parametrize('batch', [False, True])
def test_exact_hash_extracts_voice_when_tool_path_dictionary_lacks_the_authored_name(tmp_path, monkeypatch, batch):
    archive = tmp_path / 'game/archive/pc/content/lang_en_voice.archive'
    archive.parent.mkdir(parents=True)
    archive.touch()
    depot = 'base/localization/en-us/vo/synthetic.wem'
    audio = {'archive': 'archive/pc/content/lang_en_voice.archive', 'depot': depot, 'locale': 'en'}
    waveform = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'synthetic-original'
    calls = []

    def extract(_tool, command, *args):
        calls.append(args)
        output = Path(args[args.index('-o') + 1])
        output.mkdir(parents=True, exist_ok=True)
        if '--hash' in args or (batch and assets.resource_hash(depot) in args[args.index('-r') + 1]):
            (output / (assets.resource_hash(depot) + '.bin')).write_bytes(waveform)

    monkeypatch.setattr(assets, 'run_wolvenkit', extract)
    if batch:
        assert assets.extract_voices(tmp_path / 'game', [audio], Path('tool'), tmp_path / 'out') == [waveform]
    else:
        assert assets.extract_voice(tmp_path / 'game', audio, Path('tool'), tmp_path / 'out') == waveform
        assert calls[-1][calls[-1].index('--hash') + 1] == assets.resource_hash(depot)


def test_hash_key_obeys_resource_path_contract_and_never_accepts_non_audio_bytes(tmp_path):
    # Standard FNV-1a test vector, independent of the implementation's result.
    assert assets.resource_hash('A') == '12638187200555641996'
    assert assets.resource_hash('BASE/VO/TEST.WEM') == assets.resource_hash('base\\vo\\test.wem')
    (tmp_path / (assets.resource_hash('voice.wem') + '.bin')).write_bytes(b'not-an-original-waveform')
    with pytest.raises(ValueError, match='not a supported original voice'):
        assets.read_extracted_voice(tmp_path, 'voice.wem')
