"""Synthetic Genshin schema, modality and local binding regressions."""
import io
import json
import struct
import tarfile

import pytest

from backend import genshin_assets as game
from backend.dialogue_catalog import DialogueCatalog
from backend.preparation_errors import PreparationFailure
from backend.voice_assets import voice_hash


def test_released_movie_subtitles_use_matching_intervals_and_authored_predecessors():
    from backend.genshin_cinematics import movie_records
    def cue(n, start, end, text):
        return f'{n}\n00:00:{start} --> 00:00:{end}\n{text}'
    english = '\n\n'.join([cue(1, '00,200', '01,000', 'First'), cue(2, '01,000', '02,000', '<i>Yes</i>'),
                            cue(4, '02,000', '03,000', 'Later'), cue(5, '02,800', '04,000', 'Overlap')])
    french = '\n\n'.join([cue(1, '00,200', '01,000', 'Une'), cue(2, '01,100', '02,000', 'Oui')])
    class Catalog:
        def directory_text(self, path, *, suffix):
            code = path.split('/')[1]
            assert suffix == '.srt'
            text = english if code == 'EN' else french
            return [('Movie_' + code + suffix, text), ('MissingMovie_' + code + suffix, text)]
    rows = movie_records(Catalog(), {'Movie'}, ['en', 'fr'], 'en', [])
    assert len(rows) == 4 and all(r['audio'] is None and r['voice_status'] == 'unknown' for r in rows)
    assert rows[0]['texts'] == {'en': 'First', 'fr': 'Une'}
    assert rows[1]['texts'] == {'en': 'Yes'} and rows[1]['previous_text_id'] == rows[0]['text_id']
    assert rows[0]['previous_text_id'] is rows[2]['previous_text_id'] is rows[3]['previous_text_id'] is None
    assert rows[1]['text_id'] == 'genshin:movie:Movie:2:1000-2000'


def test_movie_translations_require_exclusive_overlapping_cues_in_both_tracks():
    from backend.genshin_cinematics import _aligned
    source = {1: (100, 900, 'One'), 2: (1200, 2600, 'Two'), 3: (2700, 3200, 'Three')}
    target = {1: (200, 1000, 'Un'), 2: (1250, 2950, 'Deux'), 3: (3000, 3400, 'Trois')}
    assert _aligned(source, target) == {1: 'Un'}
    assert _aligned(source, {1: (200, 1000, 'Un')}) == {}


def test_confirmed_genshin_predecessor_selects_a_short_recording_without_guessing_audio(tmp_path):
    from backend.endfield_caption_context import EndfieldCaptionContext
    from backend.multilingual_index import MultilingualTextIndex
    edges = {1: [2], 2: [], 3: [4], 4: [], 5: [6, 7], 6: [], 7: [], 8: [9], 9: [], 10: [9], 11: [12], 12: []}
    talk = {'dialogList': [{'id': i, 'talkContentTextMapHash': i + 10, 'nextDialogs': successors}
                           for i, successors in edges.items()]}
    annotations = {}
    game.dialogue_hashes([talk], [{'id': 11, 'talkContentTextMapHash': 21, 'nextDialogs': [7]}], annotations=annotations)
    assert {i: a['previous_dialogue'] for i, a in annotations.items() if 'previous_dialogue' in a} == {'2': '1', '4': '3'}
    texts = ['Take this path and follow me.', 'Yes!', 'Head back to the entrance.', 'Yes!']
    rows = [{'text_id': 'genshin:' + str(i), 'source_locale': 'en', 'audio_locale': 'en', 'source_text': text,
             'texts': {'en': text}, 'english': text, 'audio': {'file_id': i}, 'channels': ['dialogue'],
             'dialogue_kind': 'conversation', 'voice_status': 'voiced'} for i, text in enumerate(texts, 1)]
    game._bind_predecessors(rows, annotations)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'genshin', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('genshin', tmp_path)
    context = EndfieldCaptionContext()
    def scan(text, now):
        hit = index.match_lines([text], exact_only=True)
        return context.observe(index, [text], [hit], channel='dialogue', kind='conversation', scope=1, now=now, stable_frames=2)
    assert scan('Yes!', 0) is None
    scan(texts[0], 1)
    scan(texts[0], 1.1)
    assert scan('Yes!', 1.2).text_id == 'genshin:2'
    assert scan('Yes!', 8) is None
    scan(texts[2], 9)
    scan(texts[2], 9.1)
    assert scan('Yes!', 9.2).text_id == 'genshin:4'
    unavailable = {**rows[1], 'audio': None, 'voice_status': 'unavailable'}
    unavailable.pop('previous_text_id')
    game._bind_predecessors([rows[0], unavailable], annotations)
    assert 'previous_text_id' not in unavailable and unavailable['audio'] is None


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


def test_profile_voice_requires_the_actor_and_one_authored_take():
    profiles = [{'avatarId': 7, 'fetterId': 100, 'voiceFile': '35', 'voiceFileTextTextMapHash': 20}]
    avatars = [{'id': 7, 'iconName': 'UI_AvatarIcon_Fixture'}]
    configs = [('ConfigAvatar_Fixture.json', {'audio': {'voiceSwitch': {'text': 'Switch_Cast'}}})]
    for sources in ({('35', 'switch_other'): {('shared', 'a')}}, {('35', 'switch_cast'): {('shared', 'a'), ('shared', 'b')}},
                    {('35', 'switch_cast'): {('shared', 'a'), ('shared', None)}}):
        row, = game.profile_links(profiles, avatars, configs, sources)
        assert row['source'] is None and row['voice_status'] == 'unavailable'
    sources = {('35', 'switch_cast'): {('shared', 'verified.wem')}}
    avatars[0]['combatConfigHash'] = 9876
    renamed = [('9876.json', configs[0][1])]
    assert game.profile_links(profiles, avatars, renamed, sources)[0]['source'] == 'verified.wem'
    changed = [('9876.json', {'audio': {'voiceSwitch': {'text': 'Switch_Different'}}})]
    assert game.profile_links(profiles, avatars, configs + changed, sources)[0]['source'] is None
    branches = game.profile_links(profiles, avatars, renamed, {('35', 'switch_cast'): {('female', 'a'), ('male', 'b')}})
    source_by_gender = {link['player_voice']: link['source'] for link in branches}
    assert source_by_gender == {'male': 'b', 'female': 'a'}
    texts = {'en': {'20': '#Hi {M#brother}{F#sister}.'}, 'zh-Hans': {'20': '欢迎。'}}
    records = game.profile_records(branches, texts, 'en', {})
    assert [(row['player_voice'], row['source_text'], row['chinese']) for row in records] == [
        ('female', 'Hi sister.', '欢迎。'), ('male', 'Hi brother.', '欢迎。')]


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
                'ExcelBinOutput/FettersExcelConfigData.json': [{'avatarId': 20, 'fetterId': 41, 'type': 2,
                    'voiceFile': '17', 'voiceFileTextTextMapHash': 20}],
                'ExcelBinOutput/AvatarExcelConfigData.json': [{'id': 20, 'iconName': 'UI_AvatarIcon_Fixture'}],
                'ExcelBinOutput/GCGTalkDetailExcelConfigData.json': [],
                'ExcelBinOutput/GCGTutorialTextExcelConfigData.json': []}[path]

        def directory_json(self, path, *, with_names=False):
            if path.endswith('Avatar'):
                assert with_names
                return [('ConfigAvatar_Fixture.json', {'audio': {'voiceSwitch': {'text': 'Switch_Original'}}})]
            fetter = voice(17, 'VO\\sample.wem', 'Fetter')
            fetter['sourceNames'][0]['avatarName'] = 'Switch_original'
            fetter['sourceNames'].append({'sourceFileName': 'VO\\wrong_actor.wem', 'avatarName': 'Switch_other'})
            return ([{'dialogList': [{'id': 1, 'talkContentTextMapHash': 10}]}] if path.endswith('Talk') else
                    [{'a': voice(1, 'VO\\sample.wem'), 'b': voice(3, 'VO\\missing.wem', 'DungeonReminder'), 'c': fetter}])

    monkeypatch.setattr(game, 'DialogueCatalog', Catalog)
    snapshot = game.index_language(tmp_path, tmp_path / 'private-data', 'en', ())
    rows = {row['text_id']: row for row in snapshot['records']}
    assert rows['genshin:1']['source_text'] == 'Dialogue text.'
    assert rows['genshin:1']['voice_status'] == 'voiced'
    assert rows['genshin:2']['voice_status'] == 'unknown'
    assert rows['genshin:reminder-3']['source_text'] == 'Reminder text.'
    assert rows['genshin:reminder-3']['voice_status'] == 'unavailable'
    assert 'tip' in rows['genshin:reminder-3']['channels']
    profile = rows['genshin:fetter-20-41']
    assert (profile['source_text'], profile['voice_status'], profile['audio']['source']) == ('Global optional line.', 'voiced', source)
    assert profile['dialogue_kind'] == 'combat_voice' and 'gameplay' in profile['channels']
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

def test_independent_character_triggers_require_matching_actor_source_condition_and_unique_text():
    def trigger(kind, identity, *takes):
        return {'gameTrigger': kind, 'gameTriggerArgs': identity, 'sourceNames': [
            {'avatarName': actor, 'sourceFileName': path, **({'gender': gender} if gender else {})}
            for actor, path, gender in takes]}
    actor = 'Switch_Cast'
    shared = (actor, 'cast/rain.wem', None)
    variants = [(actor, 'cast/f.wem', 1), (actor, 'cast/m.wem', 2)]
    voices = {kind: trigger(kind, 100 + i, shared) for i, kind in enumerate(sorted(game.CHARACTER_TRIGGERS))}
    voices.update(f=trigger('Fetter', 35, shared), alternate=trigger('Fetter', 36, *variants),
                  neither=trigger('JoinTeam', 22, ('Switch_Other', 'cast/rain.wem', None), (actor, 'cast/f.wem', 2)),
                  both=trigger('JoinTeam', 23, *variants))
    sources, gameplay = {}, {}
    game.dialogue_links([voices], {}, 'en', profile_sources=sources, gameplay_sources=gameplay)
    profiles = [{'avatarId': 3, 'fetterId': i, 'voiceFile': str(i), 'voiceFileTextTextMapHash': i + 20} for i in (35, 36)]
    avatars = [{'id': 3, 'combatConfigHash': 98}]
    configs = [('98.json', {'audio': {'voiceSwitch': {'text': actor}}})]
    links = game.profile_links(profiles, avatars, configs, sources, gameplay)
    entries = {voice_hash(link['source']): {'publisher': 'snapshot', 'package': 'test.pck'} for link in links}
    records = game.profile_records(links, {'en': {'55': 'Rain.', '56': '#{M#Brother}{F#Sister}.'}}, 'en', entries)
    single, female, male = records
    assert single['channels'] == ['dialogue', 'gameplay']
    assert {x['type'] for x in single['audio']['gameplay_triggers']} == game.CHARACTER_TRIGGERS
    assert female['source_text'] == 'Sister.' and male['source_text'] == 'Brother.'
    assert all(row['audio']['gameplay_triggers'] == [{'type': 'JoinTeam', 'id': '23'}] for row in (female, male))
    clash = {**profiles[0], 'fetterId': 37, 'voiceFileTextTextMapHash': 99}
    links = game.profile_links(profiles + [clash], avatars, configs, sources, gameplay)
    assert all('gameplay_triggers' not in link for link in links if link['hash'] in ('55', '99'))
