"""Authored non-story text must not acquire an unrelated voice or false silence."""
import pytest

from backend import starrail_assets as starrail
from backend import hoyo_dialogue
from backend.local_game import LocalDialogue


def test_sentence_retention_distinguishes_silence_missing_media_and_unresolved_multi_voice():
    # The separate MultiVoice table makes a missing primary VoiceID ambiguous.
    sentences = [{'TalkSentenceID': identity, 'TalkSentenceText': {'Hash': 100 + identity},
                  **({'VoiceID': voice} if voice else {})}
                 for identity, voice in [(1, None), (2, 20), (3, 30), (4, 40), (5, None), (6, 60), (7, 70)]]
    voices = [{'VoiceID': 20, 'VoicePath': '', 'VoiceType': 'NoVoice'},
              {'VoiceID': 40, 'VoicePath': 'whole_movie', 'VoiceType': 'Cutscene'},
              {'VoiceID': 60, 'VoicePath': '../wrong'},
              {'VoiceID': 70, 'VoicePath': 'scene', 'IsPlayerInvolved': True}]
    links = {row['id']: row for row in starrail.sentence_links(sentences, voices, 'en',
        [{'TalkSentenceID': 5, 'VoiceIDList': [71, 72]}])}
    assert {key: row.get('voice_status') for key, row in links.items() if row['source'] is None} == {
        '1': 'unknown', '2': 'unvoiced', '3': 'unavailable', '4': 'unavailable',
        '5': 'unavailable', '6': 'unavailable'}
    assert links['4']['dialogue_kind'] == 'cutscene_caption'
    assert links['7_m']['source'] == 'English/voice/scene_m.wem'
    assert links['7_f']['source'] == 'English/voice/scene_f.wem'
    assert (links['7_m']['player_voice'], links['7_f']['player_voice']) == ('male', 'female')


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
