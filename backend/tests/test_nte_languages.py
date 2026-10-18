import json,struct
from pathlib import Path
import pytest
from backend import nte_assets as assets
from backend.tests.test_new_game_assets import bank
from backend.nte_cinematics import SRT_ROOT

@pytest.mark.parametrize('locale',assets.SUPPORTED_LOCALES)
def test_selected_text_bank_language_and_media_path_agree(tmp_path,locale):
    (tmp_path/'banks').mkdir()
    text={'ns':'Dialogue','key':'Synthetic_1','value':'Official source dialogue.'}
    target={'ns':'Dialogue','key':'Synthetic_1','value':'Traduction officielle.'}
    (tmp_path/'localization.json').write_text(json.dumps({assets.TEXT_LOCALES[locale]:[text],'fr':[target]}))
    language=assets.VOICE_LOCALES[locale];depot=f'HT/Content/WwiseAudio/Media/{language}/123.wem'
    (tmp_path/'media.json').write_text(json.dumps([depot]))
    event='Play_Vo_Synthetic_1'
    path=tmp_path/'banks'/f'{event}.bnk'
    path.write_bytes(bank(version=154,bank_id=assets.wwise_hash(event),language=assets.wwise_hash(language),event=assets.wwise_hash(event)))
    row=assets.build_records(tmp_path,source_locale=locale,target_locales=['fr'])[0]
    assert row['audio']['depot']==depot and row['source_text']==text['value']
    assert row['texts']['fr']==target['value']
    assert row['audio_locale']==('zh-Hans' if locale=='zh-Hant' else locale)
    raw=bytearray(path.read_bytes());struct.pack_into('<I',raw,16,assets.wwise_hash('Unsupported'))
    path.write_bytes(raw)
    assert assets.build_records(tmp_path,source_locale=locale,target_locales=['fr'])[0]['audio'] is None


@pytest.mark.parametrize('tables',[{'en':[]},{'en':[],'ko':[]}])
def test_missing_source_pack_is_explicit(tmp_path,tables):
    (tmp_path/'localization.json').write_text(json.dumps(tables))
    with pytest.raises(ValueError,match='text pack'):
        assets.build_records(tmp_path,source_locale='ko')


def test_traditional_chinese_uses_its_official_locale_and_original_mandarin():
    assert assets.TEXT_LOCALES['zh-Hant']=='zh-Hant'
    assert assets.VOICE_LOCALES['zh-Hant']==assets.VOICE_LOCALES['zh-Hans']=='Chinese'


def test_double_dash_ocr_alias_preserves_authored_words_and_voice_ambiguity(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    text='——这是一段合成测试台词，请在门外等我。'
    assert assets.punctuation_anchors('这是一段普通台词。')==[]
    assert assets.punctuation_anchors(text)==[prefix+text[2:] for prefix in ('一','一一','ー','ーー')]
    assert assets.punctuation_anchors('――合成の日本語字幕です。')[2]=='ー合成の日本語字幕です。'
    row={'text_id':'nte:synthetic:one','source_locale':'zh-Hans','source_text':text,'texts':{'zh-Hans':text},
         'audio_locale':'zh-Hans','audio':{'depot':'original-one'},'ocr_texts':{'zh-Hans':assets.punctuation_anchors(text)}}
    payload={'format':2,'game':'nte','source_locale':'zh-Hans','records':[row]}
    (tmp_path/'textmap.json').write_text(json.dumps(payload),encoding='utf-8')
    index=MultilingualTextIndex('nte',tmp_path)
    hit=index.match_lines(['一'+text[2:]],exact_only=True)
    assert hit.text_id==row['text_id'] and hit.source_text==text
    collision={**row,'text_id':'nte:synthetic:two','source_text':'一'+text[2:],
               'texts':{'zh-Hans':'一'+text[2:]},'audio':{'depot':'different-original'},'ocr_texts':{}}
    payload['records'].append(collision)
    (tmp_path/'textmap.json').write_text(json.dumps(payload),encoding='utf-8')
    assert not MultilingualTextIndex('nte',tmp_path).match_lines(['一'+text[2:]],exact_only=True)


def test_japanese_small_repeated_vowels_preserve_syllables_and_allow_independent_ocr_sizes():
    text='――なぁ、これは合成の字幕だぁよ！'
    anchors=assets.ocr_anchors(text,'ja')
    assert '一なぁ、これは合成の字幕だあよ！' in anchors
    assert 'ーなあ、これは合成の字幕だぁよ！' in anchors
    assert 'ーーなあ、これは合成の字幕だあよ！' in anchors
    assert not assets.ocr_anchors('ティーときゃくは同じ読みではありません。','ja')
    assert not assets.ocr_anchors('なぁという合成の例。','zh-Hant')
    assert len(assets.ocr_anchors('なぁ'*5,'ja'))==0


def test_voice_cannot_cross_locale_or_batch_languages(tmp_path):
    with pytest.raises(ValueError,match='locale'):
        assets.extract_voice(tmp_path,{'locale':'ko','depot':assets.MEDIA_ROOT+'123.wem'},Path('tool'),tmp_path)
    with pytest.raises(ValueError,match='one selected'):
        assets.extract_voices(tmp_path,[{'locale':'en','depot':'HT/Content/WwiseAudio/Media/English/123.wem'},
            {'locale':'ko','depot':'HT/Content/WwiseAudio/Media/Korean/123.wem'}],Path('tool'),tmp_path)
