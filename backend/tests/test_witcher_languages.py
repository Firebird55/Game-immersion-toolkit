import json
from pathlib import Path
import pytest
from backend import witcher_assets as assets
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_witcher import strings_file, speech_file, wave

@pytest.mark.parametrize('locale',assets.SUPPORTED_LOCALES)
def test_selected_locale_and_matching_speech_are_bound_by_official_id(tmp_path,locale):
    folder=tmp_path/'game/content/content0';folder.mkdir(parents=True)
    target='fr' if locale!='fr' else 'de'
    source='Official source dialogue.'
    translation='Official target dialogue.'
    strings_file(folder/(assets.TEXT_LOCALES[locale]+'.w3strings'),[(77,source+'<br>~ '+translation)])
    strings_file(folder/(assets.TEXT_LOCALES[target]+'.w3strings'),[(77,translation)])
    speech_file(folder/(assets.TEXT_LOCALES[locale]+'pc.w3speech'),[77])
    payload=assets.index_language(tmp_path/'game',tmp_path/'cache',locale,[target])
    row=payload['records'][0]
    assert row['source_text']==source and row['texts']=={locale:source,target:translation}
    assert row['audio_locale']==locale
    assert assets.extract_voice(tmp_path/'game',row['audio'],Path('unused'),tmp_path)==wave()
    (tmp_path/'textmap.json').write_text(json.dumps(payload),encoding='utf8')
    index=MultilingualTextIndex('witcher3',tmp_path)
    assert index.match_lines([source,translation]).audio_locale==locale


def test_missing_voice_and_translation_do_not_borrow_other_language(tmp_path):
    folder=tmp_path/'content/content0';folder.mkdir(parents=True)
    strings_file(folder/'fr.w3strings',[(77,'Restez avec moi.')])
    speech_file(folder/'cnpc.w3speech',[77])
    row=assets.index_language(tmp_path,tmp_path/'cache','fr',['nl'])
    assert row['missing_translation_locales']==['nl']
    assert row['records'][0]['audio'] is None


def test_dlc_reused_ids_and_ambiguous_performances_stay_separate(tmp_path):
    for group,text in [('content/content0','Base dialogue.'),('dlc/expansion/content','Expansion dialogue.')]:
        folder=tmp_path/group
        strings_file(folder/'fr.w3strings',[(77,text)])
        speech_file(folder/'frpc.w3speech',[77])
    rows=assets.index_language(tmp_path,tmp_path/'cache','fr',[])['records']
    assert len(rows)==2 and len({r['text_id'] for r in rows})==2
    assert all(r['audio'] for r in rows)
    speech_file(tmp_path/'content/content0/frpc.w3speech',[77,77])
    rows=assets.index_language(tmp_path,tmp_path/'cache','fr',[])['records']
    assert next(r for r in rows if r['source_text']=='Base dialogue.')['audio'] is None


def test_wrong_speech_locale_rejected(tmp_path):
    folder=tmp_path/'content/content0';folder.mkdir(parents=True)
    speech_file(folder/'enpc.w3speech',[77])
    with pytest.raises(ValueError,match='locale'):
        assets.extract_voice(tmp_path,{'archive':'content/content0/enpc.w3speech','locale':'fr','offset':0,'size':48},Path('unused'),tmp_path)
