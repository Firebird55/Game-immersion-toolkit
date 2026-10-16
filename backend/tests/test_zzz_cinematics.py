import struct

import pytest

from backend.nte_assets import wwise_hash
from backend.voice_assets import VoiceEntry
from backend.zzz_cinematics import event_bank_links, resolve_cinematic_links
from backend.tests.test_new_game_assets import bank


def cinematic_package(path, language='chinese(prc)', dynamic=False, multi=False):
    event=wwise_hash('Play_vo_Synthetic_01')
    events=bank(bank_id=77, language=wwise_hash(language), event=event, dynamic=dynamic, multi=multi)
    wem=b'RIFF'+bytes(100)
    header=struct.pack('<3I',135,88,wwise_hash(language))
    media=(b'BKHD'+struct.pack('<I',len(header))+header+
           b'DIDX'+struct.pack('<4I',12,123,0,len(wem))+b'DATA'+struct.pack('<I',len(wem))+wem)
    name=(language+'\0').encode('utf-16-le')
    languages=struct.pack('<3I',1,12,2)+name
    sizes=(len(languages),44,4,4);header_size=20+sum(sizes);start=header_size+8
    entries=struct.pack('<I',2)+struct.pack('<5I',77,1,len(events),start,2)+struct.pack('<5I',88,1,len(media),start+len(events),2)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b'AKPK'+struct.pack('<6I',header_size,1,*sizes)+languages+entries+bytes(8)+events+media)
    return wem


def resolve(tmp_path, banks=(77,88), **options):
    package=tmp_path/'Persistent/Audio/Windows/Full/Cn/SoundBank_Cn_0.pck'
    wem=cinematic_package(package,**options)
    links=[{'text_id':'CS_Synthetic_01','event':'Play_vo_Synthetic_01'}]
    result=resolve_cinematic_links(links,tmp_path,{'eventReferenceBanks':[wwise_hash(links[0]['event']),*banks,0]})
    return result,wem


def test_original_cinematic_voice_can_live_in_another_authored_bank(tmp_path):
    result,wem=resolve(tmp_path)
    item=result['CS_Synthetic_01']
    assert item['matched_by']=='authored_cinematic_event'
    from pathlib import Path
    assert VoiceEntry(Path(item['package']),item['offset'],item['size'],int(item['file_id'],16)).read()==wem


@pytest.mark.parametrize('options',[{'language':'japanese'},{'dynamic':True},{'multi':True},{'banks':(77,)}])
def test_unverified_languages_dynamic_events_and_unreferenced_media_are_rejected(tmp_path,options):
    assert resolve(tmp_path,**options)[0]=={}


def test_incomplete_event_reference_data_cannot_supply_guessed_bank_links():
    with pytest.raises(ValueError,match='Incomplete'):
        event_bank_links({'eventReferenceBanks':[1,2]})
