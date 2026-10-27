"""Synthetic current-format failures absent from the original voice-only tests."""
import json
import sqlite3
import struct

import pytest

from backend import wuthering_assets as assets
from backend.local_game import LocalDialogue
from backend.preparation_errors import PreparationFailure
from backend.tests.test_wuthering import database, plot_blob


def flat_blob(fields):
    count = max(fields) + 1
    table = 8 + count * 2
    table += -table % 4
    blob = bytearray(table + 4 + count * 4)
    struct.pack_into('<I', blob, 0, table)
    struct.pack_into('<HH', blob, 4, 4 + count * 2, 4 + count * 4)
    struct.pack_into('<i', blob, table, table - 4)
    for slot, value in fields.items():
        position = table + 4 + slot * 4
        struct.pack_into('<H', blob, 8 + slot * 2, 4 + slot * 4)
        if isinstance(value, str):
            struct.pack_into('<I', blob, position, len(blob) - position)
            encoded = value.encode()
            blob.extend(struct.pack('<I', len(encoded)) + encoded + b'\0')
            blob.extend(b'\0' * (-len(blob) % 4))
        else:
            struct.pack_into('<i', blob, position, value)
    return bytes(blob)


def flow_database(root, actions):
    with sqlite3.connect(root / 'db_flowState.db') as db:
        db.execute('CREATE TABLE flowstate (StateKey TEXT, BinData BLOB)')
        db.execute('INSERT INTO flowstate VALUES (?, ?)', ('fixture_state', flat_blob({0: 'fixture_state', 6: json.dumps(actions)})))


def add_text(root, keys):
    for locale in ('en', 'zh-Hans'):
        with sqlite3.connect(root / locale / 'lang_multi_text.db') as db:
            db.executemany('INSERT INTO MultiText VALUES (?, ?)', [(key, 'Authored test text ' + key) for key in keys])


def test_flow_types_keep_missing_audio_distinct_from_silent_choices_and_messages(tmp_path):
    database(tmp_path, [('spoken', 'The fictional gate opens.', '虚构的大门打开了。', plot_blob('spoken', 'vo_spoken'))])
    add_text(tmp_path, ['unknown', 'silent', 'choice', 'message', 'voice_message', 'attachment', 'card', 'disabled'])
    flow_database(tmp_path, [
        {'Name': 'ShowTalk', 'Params': {'TalkItems': [
            {'TidTalk': 'unknown', 'Type': 'Talk', 'Options': [{'TidTalkOption': 'choice'}]},
            {'TidTalk': 'silent', 'Type': 'Talk', 'PlayVoice': False},
            {'TidTalk': 'card', 'Type': 'CenterText'},
        ]}},
        {'Name': 'SetPlotMode', 'Params': {'Mode': 'PhoneMessage'}},
        {'Name': 'ShowTalk', 'Params': {'TalkItems': [
            {'TidTalk': 'message', 'Type': 'Talk'},
            {'TidTalk': 'voice_message', 'Type': 'PhoneMessage', 'MessageType': {'Type': 'Voice'}, 'PlayVoice': True},
            {'TidTalk': 'attachment', 'Type': 'PhoneMessage', 'MessageType': {'Type': 'Attachment'}},
        ]}},
        {'Name': 'ShowTalk', 'Disabled': True, 'Params': {'TalkItems': [{'TidTalk': 'disabled'}]}},
    ])
    rows = {row['text_id']: row for row in assets.build_language_records(tmp_path, [], 'en', ['zh-Hans'])}
    for row in rows.values():
        LocalDialogue(**row)
    assert {key: row['voice_status'] for key, row in rows.items()} == {
        'wuwa:spoken': 'unavailable', 'wuwa:unknown': 'unknown', 'wuwa:silent': 'unvoiced',
        'wuwa:choice': 'unvoiced', 'wuwa:message': 'unvoiced', 'wuwa:voice_message': 'unavailable', 'wuwa:card': 'unknown',
    }
    assert rows['wuwa:message']['dialogue_kind'] == 'message'
    assert rows['wuwa:card']['dialogue_kind'] == 'story_card'
    with_voice = assets.build_language_records(tmp_path, [assets.EXTERNAL_ROOT + 'en_vo_spoken.wem'], 'en', [])
    assert with_voice[0]['voice_status'] == 'voiced'


def test_movie_caption_embedded_voice_and_readable_audio_are_never_certified_silent(tmp_path):
    database(tmp_path, [])
    add_text(tmp_path, ['movie', 'reading', 'unknown_reading', 'shared'])
    flow_database(tmp_path, [{'Name': 'ShowTalk', 'Params': {'TalkItems': [
        {'TidTalk': 'shared', 'Options': [{'TidTalkOption': 'shared'}]},
    ]}}])
    for filename, table, blobs in [
        ('db_cgVedio.db', 'videocaption', [flat_blob({4: 'movie', 11: 0})]),
        ('db_infodisplay.db', 'infodisplay', [flat_blob({4: 'reading', 6: 'authored_event'}), flat_blob({4: 'unknown_reading'})]),
    ]:
        with sqlite3.connect(tmp_path / filename) as db:
            db.execute(f'CREATE TABLE {table} (BinData BLOB)')
            db.executemany(f'INSERT INTO {table} VALUES (?)', [(blob,) for blob in blobs])
    rows = {row['text_id']: row for row in assets.build_language_records(tmp_path, [], 'en', [])}
    assert rows['wuwa:movie']['voice_status'] == rows['wuwa:reading']['voice_status'] == 'unavailable'
    assert rows['wuwa:unknown_reading']['voice_status'] == rows['wuwa:shared']['voice_status'] == 'unknown'
    assert rows['wuwa:movie']['dialogue_kind'] == 'cinematic'


def test_text_shard_replaces_nonempty_placeholder_without_cross_locale_fallback(tmp_path):
    database(tmp_path, [('spoken', 'Placeholder', '占位文本', plot_blob('spoken', 'vo_spoken'))])
    for locale in ('en', 'zh-Hans'):
        with sqlite3.connect(tmp_path / locale / 'lang_multi_text.db') as db:
            db.execute('ALTER TABLE MultiText ADD COLUMN RedirectDbIndex INT DEFAULT 0')
            db.execute('UPDATE MultiText SET RedirectDbIndex = 1')
        with sqlite3.connect(tmp_path / locale / 'lang_multi_text_1sthalf.db') as db:
            db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
            db.execute('INSERT INTO MultiText VALUES (?, ?)', ('spoken', 'Redirected test sentence.' if locale == 'en' else '重定向测试句子。'))
        db.close()
    row, = assets.build_language_records(tmp_path, [], 'en', ['zh-Hans'])
    assert row['english'] == 'Redirected test sentence.' and row['chinese'] == '重定向测试句子。'
    (tmp_path / 'en/lang_multi_text_1sthalf.db').unlink()
    with pytest.raises(PreparationFailure) as missing:
        assets.build_language_records(tmp_path, [], 'en', ['zh-Hans'])
    assert missing.value.code == 'incomplete_game_data'
    with sqlite3.connect(tmp_path / 'en/lang_multi_text.db') as db:
        db.execute('UPDATE MultiText SET RedirectDbIndex = 2')
    with pytest.raises(PreparationFailure) as changed:
        assets.build_language_records(tmp_path, [], 'en', ['zh-Hans'])
    assert changed.value.code == 'unsupported_format'


@pytest.mark.parametrize('blob', [b'', b'\xff' * 12, struct.pack('<I', 4) + b'\0' * 12])
def test_truncated_metadata_fails_with_actionable_format_error(blob):
    with pytest.raises(PreparationFailure) as error:
        assets._string(blob, 0)
    assert error.value.code == 'unsupported_format'


def test_unknown_flow_container_does_not_succeed_as_empty_dialogue(tmp_path):
    flow_database(tmp_path, {'FutureActions': []})
    with pytest.raises(PreparationFailure, match='unsupported container'):
        assets._narrative_refs(tmp_path)


def test_existing_base_cache_still_extracts_required_redirect_shard(tmp_path, monkeypatch):
    root = tmp_path / 'Client/Content/Aki/ConfigDB'
    database(root, [('spoken', 'Placeholder', '占位文本', plot_blob('spoken', 'vo_spoken'))])
    with sqlite3.connect(root / 'en/lang_multi_text.db') as db:
        db.execute('ALTER TABLE MultiText ADD COLUMN RedirectDbIndex INT DEFAULT 1')
    for relative in assets.NARRATIVE_TABLES:
        (root / relative).touch()
    calls = []
    def extract(_install, _reader, _cache, keyword):
        calls.append(keyword)
        with sqlite3.connect(root / 'en/lang_multi_text_1sthalf.db') as db:
            db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
            db.execute('INSERT INTO MultiText VALUES (?, ?)', ('spoken', 'The resolved test sentence.'))
    monkeypatch.setattr(assets, 'run_extractor', extract)
    assets._prepare_text_tables(tmp_path, tmp_path, tmp_path, {'en'}, lambda _: None)
    assert calls == ['ConfigDB/en/lang_multi_text']
    assert assets._text_table(root, 'en')['spoken'] == 'The resolved test sentence.'
