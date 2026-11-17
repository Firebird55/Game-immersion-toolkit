"""Authored non-story text must not acquire an unrelated voice or false silence."""
import pytest

from backend import starrail_assets as starrail
from backend import hoyo_dialogue
from backend.local_game import LocalDialogue


def test_unknown_original_native_voice_enum_retains_text_without_guessing_a_recording_or_silence():
    assert starrail._voice_links(1, 101, 7, {7: {'VoiceType': 123456, 'VoicePath': 'Unproved'}}, 'en') == [
        {'id': '1', 'hash': 101, 'source': None, 'player_voice': None,
         'voice_status': 'unavailable', 'dialogue_kind': 'dialogue'}]


def test_sentence_retention_distinguishes_silence_missing_media_and_unresolved_multi_voice():
    # The separate MultiVoice table makes a missing primary VoiceID ambiguous.
    sentences = [{'TalkSentenceID': identity, 'TalkSentenceText': {'Hash': 100 + identity},
                  **({'VoiceID': voice} if voice else {})}
                 for identity, voice in [(1, None), (2, 20), (3, 30), (4, 40), (5, None), (6, 60), (7, 70)]]
    voices = [{'VoiceID': 20, 'VoicePath': '', 'VoiceType': 'NoVoice'},
              {'VoiceID': 40, 'VoicePath': 'whole_movie', 'VoiceType': 'Cutscene'},
              {'VoiceID': 60, 'VoicePath': '../wrong'},
              {'VoiceID': 70, 'VoicePath': 'scene', 'IsPlayerInvolved': True}]
    sentences[4]['TextmapTalkSentenceName'] = {'Hash': 900}
    links = {row['id']: row for row in starrail.sentence_links(sentences, voices, 'en',
        [{'TalkSentenceID': 5, 'VoiceIDList': [71, 72]}])}
    assert {key: row.get('voice_status') for key, row in links.items() if row['source'] is None} == {
        '1': 'unknown', '2': 'unvoiced', '3': 'unavailable', '4': 'unavailable',
        '5': 'unavailable', '6': 'unavailable'}
    assert links['4']['dialogue_kind'] == 'cutscene_caption'
    assert links['7_m']['source'] == 'English/voice/scene_m.wem'
    assert links['7_f']['source'] == 'English/voice/scene_f.wem'
    assert (links['7_m']['player_voice'], links['7_f']['player_voice']) == ('male', 'female')


def test_narrative_multi_voice_reactions_are_not_promoted_to_speech_of_the_description():
    def sentence(identity, **fields):
        return {'TalkSentenceID': identity, 'TalkSentenceText': {'Hash': 100 + identity}, **fields}
    named = {'TextmapTalkSentenceName': {'Hash': 900}}
    sentences = [sentence(1), sentence(2), sentence(3, **named), sentence(4, VoiceID=40),
                 sentence(5, VoiceID=50), sentence(6)]
    voices = [{'VoiceID': 10, 'VoicePath': 'fixture_greeting'},
              {'VoiceID': 11, 'VoicePath': 'fixture_greeting'},
              {'VoiceID': 40, 'VoicePath': 'spoken_narrator', 'VoiceType': 'StoryNew'},
              {'VoiceID': 50, 'VoicePath': '', 'VoiceType': 'NoVoice'}]
    multi = [{'TalkSentenceID': identity, 'VoiceIDList': candidates}
             for identity, candidates in [(1, [10]), (2, [10, 11]), (3, [10]), (4, [40]), (5, [50]), (6, [50])]]
    def prepare():
        return {row['id']: row for row in starrail.sentence_links(sentences, voices, 'ja', multi)}
    links = prepare()
    for identity in ['1', '2']:
        assert links[identity]['source'] is None and links[identity]['voice_status'] == 'unknown'
        assert links[identity]['dialogue_kind'] == 'dialogue' and links[identity]['unresolved_multi_voice']
    # A named speaker's singleton remains usable. An explicitly authored
    # narrator voice works without a speaker label; explicit NoVoice survives.
    assert links['3']['source'] == 'Japanese/voice/fixture_greeting.wem'
    assert links['4']['source'] == 'Japanese/voice/spoken_narrator.wem'
    assert links['5']['voice_status'] == 'unvoiced'
    assert links['6']['voice_status'] == 'unvoiced'
    # Normal content updates re-evaluate the actual authoring. A new
    # description does not need a hardcoded ID or an English text heuristic.
    sentences.append(sentence(7))
    multi.append({'TalkSentenceID': 7, 'VoiceIDList': [10]})
    assert prepare()['7']['voice_status'] == 'unknown'
    sentences[0]['VoiceID'] = 40
    multi[0]['VoiceIDList'] = [40]
    assert prepare()['1']['source'] == 'Japanese/voice/spoken_narrator.wem'
    # Missing selected media cannot turn any of these into confirmed silence.
    rows = hoyo_dialogue.records('starrail', list(links.values()),
        {'ja': {str(100 + i): 'Owned fixture text' for i in range(1, 7)}}, 'ja', {})
    assert [LocalDialogue(**row).voice_status for row in rows] == [
        'unknown', 'unknown', 'unavailable', 'unavailable', 'unvoiced', 'unvoiced']


def test_phone_options_and_conditional_text_keep_authored_identities_without_media_labels():
    links = starrail.message_links([
        {'ID': 10, 'ItemType': 'Text', 'MainText': {'Hash': 100}, 'OptionText': {'Hash': 101}},
        {'ID': 11, 'ItemType': 'Video', 'MainText': {'Hash': 102}, 'OptionText': {'Hash': 107}},
        {'ID': 12, 'ItemType': 'Sticker', 'MainText': {'Hash': 103}},
    ], [{'ItemID': 10, 'MainText': {'Hash': 104}}, {'ItemID': 10, 'MainText': {'Hash': 105}},
        {'ItemID': 11, 'MainText': {'Hash': 106}}])
    assert {(row['id'], row['hash']) for row in links} == {
        ('message-10', 100), ('message-10-option', 101),
        ('message-10-override-104', 104), ('message-10-override-105', 105)}
    assert all(row['source'] is None and row['voice_status'] == 'unvoiced' for row in links)


class Catalog:
    def __init__(self):
        self.tables = {
            'TalkSentenceConfig': [{'TalkSentenceID': 1, 'TalkSentenceText': {'Hash': 101}, 'VoiceID': 10}],
            'VoiceConfig': [{'VoiceID': 10, 'VoicePath': 'dialogue'},
                {'VoiceID': 20, 'VoicePath': 'narration', 'IsPlayerInvolved': True}],
            'TalkSentenceMultiVoice': [],
            'TarotBookSentence': [{'ID': 1, 'Sentence': {'Hash': 102}, 'VoiceID': 20}],
            'VoiceAtlas': [
                {'AvatarID': 100, 'VoiceID': 10, 'Voice_M': {'Hash': 103}, 'AudioID': 20},
                {'AvatarID': 100, 'VoiceID': 20, 'Voice_M': {'Hash': 104},
                 'AudioEvent': 'Ev_not_a_media_path', 'IsBattleVoice': True}],
            'MessageItemConfig': [], 'MessageItemTextOverride': [],
            'RestaurantMessageConfig': [], 'IdleLiveMessageContent': [],
            'ActivityHipplenSentence': [], 'ClockParkTalkText': [], 'IdleLiveEventSentence': [],
            'ChimeraTalk': [], 'RogueDialogueOptionDisplay': [],
        }

    def file(self, path):
        return self.tables[path.removeprefix('ExcelOutput/').removesuffix('.json')]


def test_storybook_and_archive_use_explicit_audio_ids_and_keep_events_unavailable():
    links = {row['id']: row for row in starrail.authored_links(Catalog(), 'ko')}
    assert links['narration-1_m']['source'] == 'Korean/voice/narration_m.wem'
    assert links['narration-1_f']['dialogue_kind'] == 'narrated_story'
    # VoiceAtlas.VoiceID is the menu item, while AudioID is the VoiceConfig key.
    assert links['voice-atlas-100-10_m']['source'] == 'Korean/voice/narration_m.wem'
    event = links['voice-atlas-100-20']
    assert event['source'] is None and event['voice_status'] == 'unavailable'
    assert event['dialogue_kind'] == 'battle_voice'


def test_retained_text_survives_the_shared_record_contract_without_false_audio():
    links = starrail.sentence_links([
        {'TalkSentenceID': 1, 'TalkSentenceText': {'Hash': 101}},
        {'TalkSentenceID': 2, 'TalkSentenceText': {'Hash': 102}, 'VoiceID': 20},
        {'TalkSentenceID': 3, 'TalkSentenceText': {'Hash': 103}, 'VoiceID': 30},
    ], [{'VoiceID': 20, 'VoicePath': '', 'VoiceType': 'NoVoice'},
        {'VoiceID': 30, 'VoicePath': 'not_installed'}], 'en')
    rows = hoyo_dialogue.records('starrail', links,
        {'en': {'101': 'Unknown performance.', '102': 'Silent sentence.', '103': 'Missing package.'}}, 'en', {})
    assert [LocalDialogue(**row).voice_status for row in rows] == ['unknown', 'unvoiced', 'unavailable']
    assert all(row['audio'] is None for row in rows)


@pytest.mark.parametrize('replacement', [{}, [{'renamed_field': 1}], ['not a record']])
def test_changed_metadata_schema_fails_instead_of_silently_reducing_coverage(replacement):
    catalog = Catalog()
    catalog.tables['MessageItemConfig'] = replacement
    with pytest.raises(ValueError, match='Unsupported Star Rail MessageItemConfig schema'):
        starrail.authored_links(catalog, 'en')

def test_companion_cutscenes_use_distinct_authored_sentence_recordings():
    sentences = [{'TalkSentenceID': i, 'VoiceID': i, 'TalkSentenceText': {'Hash': 100 + i}} for i in range(1, 5)]
    voices = [{'VoiceID': i, 'VoiceType': 'Cutscene', 'VoicePath': name, 'IsPlayerInvolved': i == 1}
              for i, name in enumerate(('companionX_asta_102', 'companion2_abc_103',
                  'companion2_ABC_103', 'vo_belobog_cutscene_010'), 1)]
    links = {row['id']: row for row in starrail.sentence_links(sentences, voices, 'ja')}
    assert links['1_m']['source'] == 'Japanese/voice/companionX_asta_102_m.wem'
    assert links['1_f']['dialogue_kind'] == 'cutscene_caption'
    assert all(links[i]['source'] is None for i in ('2', '3', '4'))

def test_event_and_readable_records_keep_authored_ids_and_matched_paragraph_translations():
    catalog = Catalog()
    catalog.tables.update({
        'ActivityHipplenSentence': [{'ID': 7, 'SentenceDesc': {'Hash': 11}}],
        'IdleLiveEventSentence': [{'SectionID': 1, 'Index': 0, 'Sentence': {'Hash': 12}}],
        'ChimeraTalk': [{'TalkID': 1, 'TalkContent': {'Hash': 14}, 'EvPath': 'Ev_audio'}],
        'RogueDialogueOptionDisplay': [{'OptionDisplayID': 5, 'OptionTitle': {'Hash': 15},
                                        'OptionDesc': {'Hash': 16}}],
        'LocalbookConfig': [{'BookID': 1,'BookContent': {'Hash': 17}},
                            {'BookID': 2,'BookContent': {'Hash': 18}}],
        'AudioBookData': [{'BookID': 2,'AudioEvent': 'collection'}]})
    found = {r['id']: r for r in starrail._presentation_links(catalog)}
    assert set(found) == {'hipplen-7', 'idle-story-1-0', 'chimera-1', 'rogue-option-5'}
    assert found['chimera-1']['voice_status'] == 'unavailable'
    assert found['rogue-option-5']['hash'] == 15
    tables = {'en': {'17': 'First\\nSecond','18': 'Spoken book'},
              'ja': {'17': 'Only one paragraph'}}
    rows = starrail._readable_records(catalog, tables, 'en')
    assert [(r['source_text'],r['voice_status']) for r in rows] == [
        ('First','unvoiced'),('Second','unvoiced'),('Spoken book','unavailable')]
    assert all('ja' not in r['texts'] for r in rows)
def test_existing_player_record_renders_changed_release_pronoun_in_every_translation():
    from backend.starrail_assets import _player_row
    row = {'text_id': 'starrail:1_m', 'source_locale': 'en', 'texts': {
        'en': 'I think {M#he}{F#she} helped.', 'zh-Hans': '{M#他}{F#她}帮了我。'}}
    result = _player_row(row, 'male')
    assert (result['text_id'], result['source_text'], result['chinese']) == ('starrail:1_m', 'I think he helped.', '他帮了我。')
    row['texts']['en'] = 'I think {M#she}{F#he} helped.'
    assert _player_row(row, 'male')['english'] == 'I think she helped.'
    row['texts'].update(en='The one {F#s}he mentioned.', ja='彼{F#女}は？')
    assert _player_row(row, 'male')['texts'] == {'en': 'The one he mentioned.', 'ja': '彼は？', 'zh-Hans': '他帮了我。'}
    assert _player_row(row, 'female')['texts']['ja'] == '彼女は？'
