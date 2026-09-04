import json
import struct
from types import SimpleNamespace

import pytest

from backend.agent_library import AgentLibraryUpdater, build_library, stable_asset_id
from backend.capture import CaptureService
from backend.voice_activity import VoiceActivity
from backend.voice_assets import VoiceEntry


def bank_fixture(tmp_path, monkeypatch):
    import backend.agent_library as module
    game = tmp_path/'ZenlessZoneZero_Data'
    folder=game/'Persistent/Audio/Windows/Full/Cn'
    folder.mkdir(parents=True)
    package=folder/'SoundBank_Cn_0.pck'
    def write(voice=b'RIFFvoice', pad=b''):
        chunk=lambda k,v:k+struct.pack('<I',len(v))+v
        package.write_bytes(chunk(b'JUNK',pad)+chunk(b'DIDX',struct.pack('<III',123,0,len(voice)))+chunk(b'DATA',voice))
    write()
    monkeypatch.setattr(module,'package_table',lambda path,section:{1:VoiceEntry(path,0,path.stat().st_size,1)})
    return game, package, write


def test_content_identity_survives_repacked_game_files(tmp_path,monkeypatch):
    game,package,write=bank_fixture(tmp_path,monkeypatch)
    first=build_library(game,{'agents':{'Future Agent':{}},'clips':{}})
    write(pad=b'new package padding')
    repacked=build_library(game,first)
    assert list(first['clips'])==list(repacked['clips'])==['123']
    assert first['clips']['123']['offset'] != repacked['clips']['123']['offset']
    write(voice=b'RIFFa completely different voice')
    changed=build_library(game,repacked)
    assert list(changed['clips']) != ['123']
    assert next(iter(changed['clips'])).isdecimal()
    assert changed['agents']==first['agents']


def test_missing_packages_do_not_replace_existing_library(tmp_path):
    with pytest.raises(ValueError,match='not available'):
        build_library(tmp_path,{'clips':{'123':{}}})


def test_renumbered_media_retains_saved_identity():
    assert stable_asset_id(999,'same-content',{}, {'same-content':'123'})=='123'


def test_learned_future_agent_survives_restart_and_library_refresh(tmp_path):
    from backend.agent_recognition import AgentRecognizer
    recognizer=AgentRecognizer(tmp_path,None,lambda line:None)
    recognizer.remember_agent('Future Agent')
    recognizer.replace_library({'agents':{},'clips':{}})
    assert recognizer.identify_agent(['Future Agent'])=='Future Agent'
    recognizer.close()
    reopened=AgentRecognizer(tmp_path,None,lambda line:None)
    assert reopened.identify_agent(['X Future Agent LB'])=='Future Agent'
    reopened.close()


def test_updater_commits_only_completed_index_and_preserves_saved_entries(tmp_path,monkeypatch):
    import backend.agent_library as module
    game,package,write=bank_fixture(tmp_path,monkeypatch)
    folder=tmp_path/'agent-voices'
    folder.mkdir()
    entries=folder/'entries.db'
    entries.write_bytes(b'precious saved entries')
    library=build_library(game,{'agents':{},'clips':{}})
    (folder/'library.json').write_text(json.dumps(library))
    recognizer=SimpleNamespace(folder=folder,library=library,_future=None,updating=False)
    recognizer.replace_library=lambda value:setattr(recognizer,'library',value)
    updater=AgentLibraryUpdater(recognizer)
    processes=[]
    def process(*args,**kwargs):
        processes.append(args)
        return SimpleNamespace(poll=lambda:0,returncode=0)
    monkeypatch.setattr(module.subprocess,'Popen',process)
    updater.check_once()
    assert updater.state=='ready' and not recognizer.updating
    assert entries.read_bytes()==b'precious saved entries'
    updater.check_once()
    assert len(processes)==1  # no rebuild at each startup/poll when unchanged
    write(pad=b'patch')
    before=(folder/'library.json').read_bytes()
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:SimpleNamespace(poll=lambda:1,returncode=1))
    with pytest.raises(RuntimeError,match='retrying'):
        updater.check_once()
    assert (folder/'library.json').read_bytes()==before
    assert entries.read_bytes()==b'precious saved entries'


def test_update_loop_retries_without_intervention(tmp_path,monkeypatch):
    r=SimpleNamespace(folder=tmp_path)
    updater=AgentLibraryUpdater(r,interval=.001)
    calls=[]
    def check():
        calls.append(1)
        if len(calls)==1:
            raise ValueError('files still updating')
        updater._stop.set()
    monkeypatch.setattr(updater,'check_once',check)
    updater._run()
    assert len(calls)==2


def test_unknown_agent_name_can_be_learned_without_metadata():
    assert CaptureService._nameplate_candidate(['X','Future Agent','LB'])=='Future Agent'
    assert CaptureService._nameplate_candidate(['FUTURE AGENT','Future Agent'])=='Future Agent'
    assert CaptureService._nameplate_candidate(['Future Agent','Other Agent']) is None
    assert CaptureService._nameplate_candidate(['Lv. 60','Equipment','Select','UID: 123']) is None
    assert CaptureService._nameplate_candidate(['Soldier 0 - Anby']) == 'Soldier 0 - Anby'
    assert CaptureService._is_agent_screen(['Character Details','Select','Return','Lv. 60','Lv. 60','Lv. 60'])


def test_instant_selection_voice_uses_pre_roll_and_flushes_on_switch(tmp_path,monkeypatch):
    import backend.agent_recognition as module
    now=[100.]
    monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    r=module.AgentRecognizer(tmp_path,None,lambda line:None)
    snapshots=[]
    monkeypatch.setattr(r,'_submit_snapshot',lambda *args:snapshots.append(args))
    r.observe('Nicole',True)
    assert snapshots==[]  # do not start a costly music-only lookup immediately
    now[0]=101.5
    r.observe('Nicole',True)
    assert snapshots[0]==('Nicole',98.,101.5,98.)
    now[0]=102.
    r.observe('Anby',True)
    assert snapshots[-1]==('Nicole',98.,102.,98.)
    r.close()


def test_voice_activity_ignores_late_results_from_wrong_game_screen():
    activity=VoiceActivity()
    assert activity.record('agents','listening') is None
    agent=activity.record('agents','agents')
    assert activity.record('history','agents') is None
    story=activity.record('history','matched')
    assert story['occurred_at']>agent['occurred_at']
    assert story['kind']=='history'


def test_queued_agent_activity_follows_tab_during_character_changes():
    import asyncio
    from backend.api import Runtime
    runtime=Runtime.__new__(Runtime)
    runtime.voice_activity=VoiceActivity()
    runtime.agents=SimpleNamespace(_context=('Remielle',0,0))
    phase=['agents']
    runtime.capture=SimpleNamespace(snapshot=lambda:SimpleNamespace(phase=phase[0]))
    events=[]
    async def broadcast(event):
        events.append(event)
    runtime.hub=SimpleNamespace(broadcast=broadcast)
    asyncio.run(runtime.emit_activity('agents','Grace'))
    assert events[0]['activity']['kind']=='agents'
    phase[0]='matched'
    asyncio.run(runtime.emit_activity('agents','Grace'))
    assert len(events)==1  # must not steal focus from resumed story dialogue
