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
    assert not build_sound_id_audio_map(graph,locale_code='unsupported')
    (banks/f'dialogue.sbnk.1.x64.{code}').unlink()
    assert assets.build_records(tmp_path,locale,{locale,'ar'},graph)[0]['audio'] is None


def test_unknown_timeline_guid_and_unvoiced_alias_never_borrow_a_performance(tmp_path,monkeypatch):
    root=tmp_path/'natives/stm/message/mes_main/conv';root.mkdir(parents=True);(root/'voice.msg.23').touch()
    monkeypatch.setattr(assets.reader,'read_msg',lambda *args:[{'name':'Unknown','sound_id':0,'guid':'unmapped','texts':{'en':'A caption.'}}])
    assert assets.build_records(tmp_path,'en',{'en'}, {})[0]['audio'] is None


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
