import json
import struct
from pathlib import Path
import pytest
from backend import pragmata_assets as assets
from backend.pragmata_audio import build_sound_id_audio_map,cutscene_audio_for_bank

@pytest.mark.parametrize('locale',assets.SUPPORTED_LOCALES)
def test_selected_msg_and_authored_localized_sound_id_agree(tmp_path,monkeypatch,locale):
    code=assets.VOICE_LOCALES[locale]
    root=tmp_path/'natives/stm';message=root/'message/mes_main/conv/voice.msg.23';message.parent.mkdir(parents=True);message.touch()
    banks=root/'sound/wwise';banks.mkdir(parents=True);(banks/f'dialogue.sbnk.1.x64.{code}').touch()
    monkeypatch.setattr(assets.reader,'read_msg',lambda path,locales:[{'name':'Spoken_1','sound_id':123,'guid':'',
        'texts':{locale:'Source dialogue.','ar':'ترجمة رسمية'}}])
    package={'index':f'natives/stm/sound/wwise/dialogue.spck.1.x64.{code}','streaming':''}
    graph={'source_event_records':[['dialogue',22]],'source_events':{'222':[0]},
        'media_links':{f'natives/stm/sound/wwise/dialogue.sbnk.1.x64.{code}':{f'dialogue.{code}':[222]}},
        'media_packages':{f'dialogue.{code}':package},'bank_events':{'dialogue':{'22':{'trigger_ids':[123]}}}}
    # One exact source does not require parsing a layered event tree.
    monkeypatch.setattr('backend.pragmata_audio.read_bank_play_layers',lambda *_:{})
    rows=assets.build_records(tmp_path,locale,{locale,'ar'},graph)
    assert len(rows)==1 and rows[0]['source_locale']==rows[0]['audio_locale']==locale
    assert rows[0]['audio']['index']==package['index']
    assert rows[0]['audio']['locale']==locale and rows[0]['texts']['ar']=='ترجمة رسمية'
    assert rows[0]['voice_status'] == 'voiced' and rows[0]['dialogue_kind'] == 'conversation'
    assert not build_sound_id_audio_map(graph,locale_code='unsupported')
    (banks/f'dialogue.sbnk.1.x64.{code}').unlink()
    missing = assets.build_records(tmp_path,locale,{locale,'ar'},graph)[0]
    assert missing['audio'] is None and missing['voice_status'] == 'unavailable'


def test_unknown_timeline_guid_and_unvoiced_alias_never_borrow_a_performance(tmp_path,monkeypatch):
    root=tmp_path/'natives/stm/message/mes_main/conv';root.mkdir(parents=True);(root/'voice.msg.23').touch()
    monkeypatch.setattr(assets.reader,'read_msg',lambda *args:[{'name':'Unknown','sound_id':0,'guid':'unmapped','texts':{'en':'A caption.'}}])
    record = assets.build_records(tmp_path,'en',{'en'}, {})[0]
    assert record['audio'] is None and record['voice_status'] == 'unknown'


def test_reserved_msg_languages_are_not_official_translation_targets():
    assert set(assets.TEXT_LOCALES) == set(assets.SUPPORTED_LOCALES) | {'pl', 'ar', 'zh-Hant'}


def test_msg_uses_authored_language_identifiers_instead_of_column_positions(tmp_path, monkeypatch):
    pool = 'Spoken\0中文\0Français\0English\0'.encode('utf-16-le')
    data = bytearray(256 + len(pool))
    struct.pack_into('<I4sQIII', data, 0, 23, b'GMSG', 0, 1, 0, 3)
    struct.pack_into('<5Q', data, 32, 256, 80, 88, 104, 104)
    struct.pack_into('<Q', data, 72, 112)
    struct.pack_into('<3I', data, 88, 13, 2, 1)
    struct.pack_into('<IIQQ3Q', data, 128, 123, 0, 256, 0, 270, 276, 294)
    data[256:] = pool
    path = tmp_path / 'shuffled.msg.23'
    path.write_bytes(data)
    monkeypatch.setattr(assets.reader, 'decrypt', lambda value: value)
    row, = assets.reader.read_msg(path, {'fr': 2, 'zh-Hans': 13, 'en': 1, 'absent': 999})
    assert row['texts'] == {'fr': 'Français', 'zh-Hans': '中文', 'en': 'English'}


def test_missing_or_conflicting_references_do_not_create_partial_official_text(tmp_path, monkeypatch):
    root = tmp_path / 'natives/stm/message'
    (root / 'mes_main/conv').mkdir(parents=True)
    for name in ('one', 'two'):
        (root / f'{name}.msg.23').touch()
    (root / 'mes_main/conv/voice.msg.23').touch()
    def read(path, locales):
        if path.name in ('one.msg.23', 'two.msg.23'):
            return [{'name': 'Shared', 'texts': {'en': 'Name' if path.name.startswith('one') else 'Other name'}}]
        return [
            {'name': 'Missing', 'guid': '', 'texts': {'en': 'Hello <REF Missing>.'}},
            {'name': 'Conflict', 'guid': '', 'texts': {'en': 'Hello <REF Shared>.'}},
            {'name': 'Official', 'guid': '', 'texts': {'en': 'Hello.', 'ar': 'Text <REF Missing>'}},
        ]
    monkeypatch.setattr(assets.reader, 'read_msg', read)
    rows = assets.build_records(tmp_path, 'en', {'en', 'ar'}, {})
    assert [row['source_text'] for row in rows] == ['Hello.']
    assert 'ar' not in rows[0]['texts']


def test_readable_pages_resolve_nested_names_without_promoting_ui_or_inventing_voice(tmp_path, monkeypatch):
    # Archive pages use nested speaker aliases. Generic labels and cyclic or
    # incomplete references must not become captured narrative text.
    root = tmp_path / 'natives/stm/message'
    def row(name, text):
        return {'name': name, 'guid': '', 'sound_id': 123, 'texts': {'en': text},
                'english': text, 'chinese': '示例'}
    tables = {
        'mes_main/ref/ref_charactername.msg.23': [row('LocalizedName', 'Aster')],
        'mes_main/ingame/speakername.msg.23': [row('Speaker', '<REF LocalizedName>')],
        'mes_main/archive/archive_talk.msg.23': [
            row('Archive_Talk_Test', 'Transcript heading'),
            row('Archive_Talk_Test_desc', '<REF Speaker>\n<REF Dialogue>')],
        'mes_main/conv/conv_base.msg.23': [row('Dialogue', 'The door is open.')],
        'mes_main/archive/archive_stage01.msg.23': [
            row('File_St01_001_Head', 'File heading'),
            row('File_St01_001_Desc', 'A written account.'),
            row('File_St01_002_Desc', 'An incomplete <REF Missing>'),
            row('File_St01_003_Desc', '<REF Loop>')],
        'mes_main/ref/ref_common.msg.23': [row('Loop', '<REF Loop>')],
        'mes_main/archive/archive_figure.msg.23': [
            row('Figure_001', 'Bot label'), row('Figure_001_height', '2 m'),
            row('Figure_001_desc', 'This bot maintains the station.')],
        'mes_main/gui/ui2200.msg.23': [row('UI2200_001_Desc', 'Aim with the button.')],
        'mes_main/ingame/item.msg.23': [row('Item_001_Desc', 'An inventory description.')],
    }
    for name in tables:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(assets.reader, 'read_msg', lambda path, *_: tables[path.relative_to(root).as_posix()])
    rows = assets.build_records(tmp_path, 'en', {'en'}, {})
    assert {r['source_text'] for r in rows} == {
        'Aster\nThe door is open.', 'The door is open.', 'A written account.',
        'This bot maintains the station.'}
    assert sum(r['dialogue_kind'] == 'readable' for r in rows) == 3
    assert all(r['voice_status'] == 'unknown' and r['audio'] is None for r in rows)
    legacy = assets.reader.build_index(root, None)
    assert {r['english'] for r in legacy['records']} == {r['source_text'] for r in rows}
    assert all(r['voice_status'] == 'unknown' for r in legacy['records'])


def test_localized_preparation_includes_nonstandard_voice_bank_names_without_media_or_other_dubs(tmp_path, monkeypatch):
    import io
    names = [
        'natives/stm/message/mes_main/conv/conv_earth.msg.23',
        'natives/stm/sound/wwise/ch01000_earth.sbnk.1.x64.zhcn',
        'natives/stm/sound/wwise/ch05000_chp7.sbnk.1.x64.zhcn',
        'natives/stm/sound/wwise/ch05000_chp8.sbnk.1.x64.zhcn',
        'natives/stm/sound/wwise/ch01000_cmn.sbnk.1.x64.zhcn',
        'natives/stm/sound/wwise/ch01000_earth.sbnk.1.x64.en',
        'natives/stm/sound/wwise/ch01000_earth.spck.1.x64.zhcn',
        'natives/stm/streaming/sound/wwise/ch01000_earth.spck.1.x64.zhcn',
    ]
    monkeypatch.setattr(assets.reader.urllib.request, 'urlopen',
                        lambda *_args, **_kwargs: io.BytesIO('\n'.join(names).encode()))
    assets.reader.update_asset_list(tmp_path, 'zhcn')
    selected = (tmp_path / 'Projects/P_PRAGMATA_INDEX.list').read_text().splitlines()
    assert selected == names[:5]


def test_localized_nonverbal_caption_does_not_turn_into_chinese_dialogue(tmp_path, monkeypatch):
    root = tmp_path / 'natives/stm/message/mes_main/event/cutscene'
    root.mkdir(parents=True)
    (root / 'cs0001.msg.23').touch()
    monkeypatch.setattr(assets.reader, 'read_msg', lambda *_: [
        {'name': 'cs0001_0010_Ch00000', 'guid': '', 'english': '[humming]',
         'texts': {'zh-Hans': '（哼歌）'}}])
    assert assets.build_records(tmp_path, 'zh-Hans', {'zh-Hans'}, {}) == []


def test_conflicting_cinematic_intervals_are_unavailable_in_both_indexes(tmp_path, monkeypatch):
    root = tmp_path / 'natives/stm'
    message = root / 'message/mes_main/event/cutscene/cs0001.msg.23'
    message.parent.mkdir(parents=True)
    message.touch()
    timelines = root / 'event/cs/cs0001/flow'
    timelines.mkdir(parents=True)
    for name in ('first', 'second'):
        (timelines / f'{name}.tmlfsm2.42091004').touch()
    banks = root / 'sound/wwise'
    banks.mkdir(parents=True)
    (banks / 'cs0001_dialogue.sbnk.1.x64.zhcn').touch()
    monkeypatch.setattr(assets.reader, 'read_msg', lambda *_: [{
        'name': 'cs0001_0010_Ch00000', 'guid': 'subtitle-guid',
        'english': 'The signal is clear.', 'chinese': '信号清晰。',
        'texts': {'en': 'The signal is clear.', 'zh-Hans': '信号清晰。'}}])
    def segments(path):
        return [{'guid': 'subtitle-guid', 'start_seconds': 1 if path.name.startswith('first') else 2,
                 'end_seconds': 3}]
    def audio(*_):
        return {'bank': 'cs0001_dialogue', 'media_id': 5, 'mapping': 'timeline_guid'}
    for module in (assets, assets.reader):
        monkeypatch.setattr(module, 'read_tmlfsm_dialogue_segments', segments)
        monkeypatch.setattr(module, 'cutscene_audio_for_bank', audio)
    graph = {'banks': {'cs0001_dialogue': {}}}
    localized = assets.build_records(tmp_path, 'zh-Hans', {'zh-Hans', 'en'}, graph)[0]
    legacy = assets.reader.build_index(root / 'message', None, root, graph)['records'][0]
    assert localized['audio'] is None and 'audio' not in legacy
    assert localized['voice_status'] == legacy['voice_status'] == 'unavailable'
