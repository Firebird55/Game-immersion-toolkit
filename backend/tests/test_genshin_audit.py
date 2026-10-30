"""Synthetic Genshin schema, modality and local binding regressions."""
import io
import struct
import tarfile

import pytest

from backend import genshin_assets as game
from backend.dialogue_catalog import DialogueCatalog
from backend.preparation_errors import PreparationFailure
from backend.voice_assets import voice_hash


def test_global_dialogues_fill_gaps_without_resurrecting_runtime_conflicts():
    warnings = []
    talks = [{'dialogList': [{'id': 1, 'talkContentTextMapHash': 10},
                             {'id': 1, 'talkContentTextMapHash': 11},
                             {'id': 2, 'talkContentTextMapHash': 20}]}]
    fallback = [{'GFLDJMJKIKE': 1, 'talkContentTextMapHash': 10},
                {'GFLDJMJKIKE': 2, 'talkContentTextMapHash': 99},
                {'GFLDJMJKIKE': 3, 'talkContentTextMapHash': 30}]
    assert game.dialogue_hashes(talks, fallback, warnings) == {'2': '20', '3': '30'}
    assert 'Conflicting' in warnings[0]


def test_new_or_malformed_talk_structures_warn_without_guessing_hash_fields():
    warnings = []
    assert game.dialogue_hashes([{'newArray': [{'id': 1, 'newHash': 2}]},
                                  {'dialogList': None}, {'dialogList': [None]}], warnings=warnings) == {}
    assert len(warnings) == 1 and 'unsupported structure' in warnings[0]
    assert game.dialogue_hashes([{'dialogList': [{'id': True, 'talkContentTextMapHash': 2},
                                                {'id': 1, 'talkContentTextMapHash': []}]}]) == {}


def test_storyboard_and_choice_metadata_preserve_modality_without_guessing_silence():
    annotations = {}
    hashes = game.dialogue_hashes([
        {'type': 'STORYBOARD', 'dialogList': [{'id': 1, 'talkContentTextMapHash': 10}]}],
        [{'GFLDJMJKIKE': 2, 'talkContentTextMapHash': 20, 'talkShowType': 'TALK_SHOW_FORCE_SELECT'}],
        annotations=annotations)
    assert annotations['1'] == {'dialogue_kind': 'storyboard', 'channels': ['dialogue', 'cinematic']}
    assert annotations['2']['dialogue_kind'] == 'choice'
    assert {r['voice_status'] for r in game._complete_links([], {'Dialog': hashes}, set(), [])} == {'unknown'}


def voice(identity, path, kind='Dialog'):
    return {'gameTrigger': kind, 'gameTriggerArgs': identity,
            'sourceNames': [{'sourceFileName': path}]}


def test_ambiguous_voices_do_not_create_duplicate_gender_ids_or_use_substring_gender():
    warnings, authored = [], set()
    links = game.dialogue_links([{'a': voice(1, 'VO/female_a.wem'),
                                  'b': voice(1, 'VO/female_b.wem'),
                                  'c': voice(2, 'VO/mailman.wem'),
                                  'd': voice(2, 'VO/female_c.wem')}],
                                 {'1': '10', '2': '20'}, 'en', warnings=warnings, authored=authored)
    assert links == [] and authored == {('Dialog', '1'), ('Dialog', '2')}
    completed = game._complete_links(links, {'Dialog': {'1': '10', '2': '20'}}, authored, [])
    assert {link['voice_status'] for link in completed} == {'unavailable'}
    assert len(warnings) == 1


def test_explicit_player_voice_pair_is_retained_and_unsafe_source_is_unavailable():
    authored, warnings = set(), []
    links = game.dialogue_links([{'a': voice(1, 'VO/sample_boy.wem'),
                                  'b': voice(1, 'VO/sample_girl.wem'),
                                  'c': voice(2, '../outside.wem')}], {'1': '10', '2': '20'},
                                 'ja', warnings=warnings, authored=authored)
    assert {link['id'] for link in links} == {'1:male', '1:female'}
    completed = game._complete_links(links, {'Dialog': {'1': '10', '2': '20'}}, authored, [])
    assert len(completed) == 3 and completed[-1]['voice_status'] == 'unavailable'


def test_new_voice_schema_fails_with_actionable_public_error():
    with pytest.raises(PreparationFailure) as error:
        game.dialogue_links([{'guid': {'newSources': [{'file': 'one.wem'}]}}], {'1': '10'}, 'en')
    assert error.value.code == 'unsupported_game_format'
    assert 'Update the toolkit' in str(error.value)


def test_card_voice_ids_keep_original_array_positions_and_exclude_conflicts():
    warnings = []
    cards = game.card_hashes([
        {'talkVoiceId': [0, 12, 0, 13], 'talkContent': [100, 101, 102, 103]},
        {'talkVoiceId': [13], 'talkContent': [999]},
        {'talkVoiceId': [14], 'talkContent': []}],
        [{'voiceTriggerId': 15, 'commentTextMapHash': 105}], warnings)
    assert cards == {'12': '101', '15': '105'}
    links = game.dialogue_links([{'a': voice(12, 'VO/card.wem', 'Card')}], {}, 'ko', cards=cards)
    assert links[0]['id'] == 'card-12' and links[0]['hash'] == '101'
    assert len(warnings) == 2


def test_missing_voice_does_not_mean_unvoiced_and_explicit_silent_reminder_does():
    reminders = [{'id': 1, 'HNDLKHJFLNF': 10, 'hasAudio': False},
                 {'id': 2, 'HNDLKHJFLNF': 20},
                 {'id': 3, 'HNDLKHJFLNF': 30, 'hasAudio': True}]
    result = game._complete_links([], {'Dialog': {'4': '40'}, 'DungeonReminder': game.reminder_hashes(reminders)},
                                  set(), reminders)
    assert {row['id']: row['voice_status'] for row in result} == {
        '4': 'unknown', 'reminder-1': 'unvoiced', 'reminder-2': 'unknown', 'reminder-3': 'unavailable'}


def test_metadata_version_mismatch_rejects_before_indexing_and_missing_version_warns(tmp_path):
    (tmp_path / 'config.ini').write_text('[General]\ngame_version=7.1.0\n')
    catalog = type('Catalog', (), {'revision_title': 'CNRELWin7.2.0_R1_S2_D3'})()
    with pytest.raises(PreparationFailure, match='does not match'):
        game._metadata_version(tmp_path, catalog, [])
    catalog.revision_title = 'CNRELWin7.1.0_R1_S2_D3'
    game._metadata_version(tmp_path, catalog, [])
    warnings = []
    game._metadata_version(tmp_path, object(), warnings)
    assert len(warnings) == 1


def test_index_uses_distinct_reminder_namespace_and_preserves_unavailable_and_unknown(tmp_path, monkeypatch):
    source = 'English(US)\\VO\\sample.wem'
    payload = b'RIFF\x04\0\0\0WAVE'
    package = tmp_path / 'GenshinImpact_Data/StreamingAssets/AudioAssets/English(US)/External.pck'
    package.parent.mkdir(parents=True)
    package.write_bytes(b'AKPK' + struct.pack('<6I', 60, 1, 4, 4, 4, 28) + bytes(12) +
                        struct.pack('<IQ4I', 1, voice_hash(source), 1, len(payload), 68, 0) + payload)
    (tmp_path / 'config.ini').write_text('[General]\ngame_version=7.1.0\n')

    class Catalog:
        revision = 'a' * 40
        revision_title = 'CNRELWin7.1.0_R1_S2_D3'

        def __init__(self, *_args):
            pass

        def file(self, path, **_kwargs):
            return {
                'TextMap/TextMapEN.json': {'10': 'Dialogue text.', '20': 'Global optional line.'},
                'TextMap/TextMap_MediumEN.json': {'10': 'Reminder text.'},
                'ExcelBinOutput/DialogExcelConfigData.json': [{'GFLDJMJKIKE': 2, 'talkContentTextMapHash': 20}],
                'ExcelBinOutput/ReminderExcelConfigData.json': [{'id': 3, 'HNDLKHJFLNF': 10, 'hasAudio': True}],
                'ExcelBinOutput/GCGTalkDetailExcelConfigData.json': [],
                'ExcelBinOutput/GCGTutorialTextExcelConfigData.json': []}[path]

        def directory_json(self, path):
            return ([{'dialogList': [{'id': 1, 'talkContentTextMapHash': 10}]}] if path.endswith('Talk') else
                    [{'a': voice(1, 'VO\\sample.wem'), 'b': voice(3, 'VO\\missing.wem', 'DungeonReminder')}])

    monkeypatch.setattr(game, 'DialogueCatalog', Catalog)
    snapshot = game.index_language(tmp_path, tmp_path / 'private-data', 'en', ())
    rows = {row['text_id']: row for row in snapshot['records']}
    assert rows['genshin:1']['source_text'] == 'Dialogue text.'
    assert rows['genshin:1']['voice_status'] == 'voiced'
    assert rows['genshin:2']['voice_status'] == 'unknown'
    assert rows['genshin:reminder-3']['source_text'] == 'Reminder text.'
    assert rows['genshin:reminder-3']['voice_status'] == 'unavailable'
    assert 'tip' in rows['genshin:reminder-3']['channels']
    assert snapshot['coverage_warnings']
    assert all(str(tmp_path) not in warning for warning in snapshot['coverage_warnings'])
    assert 'community metadata' in snapshot['message']


def test_readables_align_only_authored_file_ids_and_paragraph_boundaries():
    class Catalog:
        def directory_text(self, path):
            return {
                'Readable/EN': [('Book1_EN.txt', 'First paragraph.\n\nSecond paragraph.'),
                                ('Book2_EN.txt', 'Spoken elsewhere.'), ('Letter_EN.txt', 'Unverified modality.')],
                'Readable/JP': [('Book1_JP.txt', '対応する第一段落。\n\n対応する第二段落。'),
                                ('Book2_JP.txt', '一つ。\n\n二つ。')]}[path]
    warnings = []
    rows = game.readable_records(Catalog(), ('en', 'ja'), 'en',
                                [{'source_text': 'Spoken elsewhere.', 'voice_status': 'voiced'}], warnings)
    assert len(rows) == 4
    assert rows[0]['texts']['ja'] == '対応する第一段落。'
    assert rows[0]['voice_status'] == rows[1]['voice_status'] == 'unvoiced'
    assert rows[2]['voice_status'] == rows[3]['voice_status'] == 'unknown'
    assert 'ja' not in rows[2]['texts']
    assert len(warnings) == 1


def text_catalog(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, value in members:
            item = tarfile.TarInfo(name)
            if isinstance(value, int):
                item.size = value
                archive.addfile(item)
            elif value is None:
                item.type, item.linkname = tarfile.SYMTYPE, '../other'
                archive.addfile(item)
            else:
                data = value.encode('utf-8')
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
    catalog = object.__new__(DialogueCatalog)
    catalog.host, catalog.api, catalog.revision = 'gitlab', 'https://example.invalid', 'a' * 40
    catalog._bytes = lambda *_args: buffer.getvalue()
    return catalog


def test_readable_archive_preserves_relative_identity_and_utf8_without_extraction():
    catalog = text_catalog([('snapshot/Readable/JP/Book1_JP.txt', '日本語の段落。')])
    assert list(catalog.directory_text('Readable/JP')) == [('Book1_JP.txt', '日本語の段落。')]


@pytest.mark.parametrize('members,message', [
    ([('../outside.txt', 'bad')], 'Unsafe'),
    ([('snapshot/Readable/EN/link.txt', None)], 'Unsafe'),
    ([('snapshot/Readable/JP/Book1.txt', 'bad')], 'crosses'),
    ([('snapshot/Readable/EN/Book1.txt', 'one'), ('snapshot/Readable/EN/Book1.txt', 'two')], 'Duplicate'),
    ([('snapshot/Readable/EN/huge.txt', 4 * 1024 * 1024 + 1)], 'size limit'),
])
def test_readable_archive_rejects_unsafe_ambiguous_or_oversized_members(members, message):
    with pytest.raises(ValueError, match=message):
        list(text_catalog(members).directory_text('Readable/EN'))
