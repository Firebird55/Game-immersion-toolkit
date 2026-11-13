import json

from backend.genshin_messages import message_records
from backend.multilingual_index import MultilingualTextIndex


class Catalog:
    def __init__(self):
        self.tables = {
            'Mail': [{'id': 1, 'contentTextMapHash': 10, 'titleTextMapHash': 11, 'senderTextMapHash': 12},
                     {'id': 2, 'contentTextMapHash': 99}, {'id': 3, 'contentTextMapHash': 10},
                     {'id': 3, 'contentTextMapHash': 98}],
            'ServerMessage': [{'id': 2, 'contentTextMapHash': 20, 'showType': 'SERVER_MESSAGE_SHOW_TYPE_MESSAGE'},
                              {'id': 3, 'contentTextMapHash': 20, 'showType': 'UNREVIEWED'}],
            'BubbleTalkData': [],
            'TpsGlassesChatCharacter': [{'characterId': 1, 'actorName': 1264548403},
                                        {'characterId': 4, 'actorName': 405055187}],
            'TpsGlassesChatTopic': [{'t': 1001, 'name': 562223715}, {'t': 1002, 'name': 118984643}, {'t': 600, 'name': 45}],
            'TpsGlassesChatMessage': [
                {'idCode': 100101, 'topicCode': 1001, 'kindCode': 'TEXT', 'bodyCode': 3421014762},
                {'idCode': 100201, 'topicCode': 1002, 'kindCode': 'TEXT', 'bodyCode': 2109670066},
                {'idCode': 5008, 'topicCode': 5, 'kindCode': 'LOCATION', 'bodyCode': 800, 'destination': 1008191327},
                {'idCode': 13004, 'topicCode': 13, 'kindCode': 'LOCATION', 'bodyCode': 801, 'destination': 3590868607},
                {'idCode': 60001, 'topicCode': 600, 'kindCode': 'TEXT', 'bodyCode': 30, 'preview': 31, 'characterId': 1},
                {'idCode': 60002, 'topicCode': 600, 'kindCode': 'IMAGE', 'bodyCode': 35},
                {'idCode': 60004, 'topicCode': 600, 'kindCode': 'LOCATION', 'destination': 36},
                {'idCode': 60003, 'topicCode': 600, 'kindCode': 'NEW_TYPE', 'bodyCode': 30}],
            'TpsGlassesChatOption': [
                {'choiceCode': 1001011, 'topicCode': 1001, 'textCode': 4069531165},
                {'choiceCode': 1002021, 'topicCode': 1002, 'textCode': 1143764869},
                {'choiceCode': 60011, 'topicCode': 600, 'textCode': 40}]}

    def file(self, path, *, optional):
        return self.tables[path.removeprefix('ExcelBinOutput/').removesuffix('ExcelConfigData.json')]


def test_message_fields_follow_retained_identities_after_rename_and_future_additions(tmp_path):
    catalog = Catalog()
    full = {'en': {'10': 'Wrong ordinary text', '20': 'The game is in progress.', '30': 'Full chat message.',
                   '31': 'Preview', '35': 'Image caption', '36': 'Travel to the pier', '40': 'A player choice',
                   '45': 'Thread title', '99': 'Wrong namespace',
                   '1264548403': 'Eye of Graeae'}, 'zh-Hans': {'30': '完整消息', '1264548403': '灰姑娘之眼'}}
    medium = {'en': {'10': 'An original written letter.', '11': 'An original heading.', '12': 'Sender',
                     '20': 'Wrong medium text'}, 'zh-Hans': {'10': '这是一封信。', '12': '寄信人'}}
    existing = [{'source_text': full['en']['20'], 'voice_status': 'voiced'}]
    result = message_records(catalog, full, medium, 'en', existing, [])
    rows = {r['text_id']: r for r in result}
    assert set(rows) == {'genshin:mail:1', 'genshin:mail_title:1', 'genshin:server_message:2',
                         'genshin:chat_message:600:60001', 'genshin:chat_attachment:600:60002',
                         'genshin:chat_choice:600:60011', 'genshin:chat_location:600:60004', 'genshin:chat_topic:600'}
    letter = rows['genshin:mail:1']
    assert letter['texts'] == {'en': 'An original written letter.', 'zh-Hans': '这是一封信。'}
    assert letter['speaker_english'] == 'Sender' and letter['speaker_chinese'] == '寄信人'
    chat = rows['genshin:chat_message:600:60001']
    assert chat['source_text'] == full['en']['30'] and chat['speaker_english'] == 'Eye of Graeae'
    assert all(row['audio'] is None for row in result)
    assert all(row['voice_status'] == ('unvoiced' if row['dialogue_kind'] in ('mail', 'mail_title', 'chat_location', 'chat_topic') else 'unknown')
               for row in result)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'genshin', 'source_locale': 'en', 'records': result}))
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.match_unvoiced_lines([letter['source_text']]) == []
    index.capture_unvoiced = True
    assert index.match_unvoiced_lines([letter['source_text']])[0].text_id == letter['text_id']
    assert index.match_unvoiced_lines([chat['source_text']]) == []


def test_ambiguous_missing_or_conflicting_message_fields_fail_closed():
    catalog = Catalog()
    for row in catalog.tables['TpsGlassesChatMessage']:
        row['duplicate'] = row.get('bodyCode')
    catalog.tables['TpsGlassesChatOption'].pop(0)
    warnings = []
    rows = message_records(catalog, {'en': {'30': 'Text', '40': 'Option'}}, {}, 'en', [], warnings)
    assert rows == [] and any('fields' in warning for warning in warnings)


def test_ambient_bubbles_keep_shared_sound_effects_out_of_speech_and_identify_scene_boards():
    catalog = Catalog()
    catalog.tables['BubbleTalkData'] = [
        {'i': 700003, 'h': 2984426480}, {'i': 700006, 'h': 3998572240}, {'i': 1, 'h': 3754392104},
        {'i': 901, 'h': 10, 'soundEffect': 'Shared_Popup'}, {'i': 902, 'h': 11, 'soundEffect': 'Shared_Popup'},
        {'i': 903, 'h': 12, 'style': 'BUBBLE_TALK_STYLE_MOONINFO_SCENE_TEXT_BOARD'},
        {'i': 904, 'h': 13, 'style': 'BUBBLE_TALK_STYLE_MOONINFO_SCENE_TEXT_BOARD'}]
    full = {'en': {'3754392104': 'Test content', '10': 'Hello!', '11': 'Stop!', '12': 'West Entrance', '13': 'Intruder detected!'}}
    existing = [{'source_text': 'Intruder detected!', 'voice_status': 'unavailable'}]
    rows = {r['text_id']: r for r in message_records(catalog, full, {}, 'en', existing, [])}
    assert set(rows) == {f'genshin:bubble:{identity}' for identity in (901, 902, 903, 904)}
    assert [rows[f'genshin:bubble:{i}']['voice_status'] for i in (901, 902, 903, 904)] == ['unknown', 'unknown', 'unvoiced', 'unknown']
    assert all(r['audio'] is None and 'gameplay' in r['channels'] for r in rows.values())
