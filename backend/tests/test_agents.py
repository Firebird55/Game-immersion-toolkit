from datetime import datetime, timezone
import numpy as np

from backend.agent_fingerprint import landmarks, waveform_score
from backend.agent_store import AgentVoiceStore
from backend.capture import CaptureService


def test_agent_ui_not_character_names():
    assert CaptureService._is_agent_screen(['Dialyn','Base','Skills','Equipment'])
    assert CaptureService._is_agent_screen(['LV. 40','Training Plan'])
    assert not CaptureService._is_agent_screen(['Yidhari?', 'Promeia...', 'Skills are important.'])
    assert not CaptureService._is_agent_screen(['Base', 'Nicole'])


def test_agent_navigation_accepts_both_input_prompt_styles():
    # Synthetic OCR variants: separate labels, joined tabs, and input glyphs.
    assert CaptureService._is_agent_screen(['Q Base', 'E Skills', 'Equipment'])
    assert CaptureService._is_agent_screen(['LB Base Skills Equipment RB'])
    assert CaptureService._is_agent_screen(['L1 Base', 'R1 Skills', 'B Back'])
    assert CaptureService._is_agent_screen(['◀ Base', 'Skills ▶'])
    assert not CaptureService._is_agent_screen(['Our base needs equipment.', 'Skills are important.'])


def test_agent_identity_is_exact_and_unambiguous():
    from backend.agent_recognition import AgentRecognizer
    recognizer = AgentRecognizer.__new__(AgentRecognizer)
    recognizer.library = {'agents': {'Dialyn': {}, 'Yidhari': {}}}
    assert recognizer.identify_agent(['☆ Dialyn', 'Base']) == 'Dialyn'
    assert recognizer.identify_agent(['X Dialyn LB']) == 'Dialyn'
    assert recognizer.identify_agent(['Dialyn', 'Yidhari']) is None
    assert recognizer.identify_agent(['Dialyn is here.']) is None


def test_supplied_dialyn_keyboard_and_controller_ocr():
    # Recognized from the user's two reference screenshots, 4 September 2026.
    common = ['Special', 'Training Plan', 'S Lv. 401', 'Lv. 40 X', 'Dialyn']
    keyboard = common + ['Base', 'Skills', 'Equipment', 'DIALYN']
    controller = common + ['LS', 'RB', 'RS', 'X', 'LB', 'Y', 'Character Details', 'A', 'Select', 'B', 'Return']
    assert CaptureService._is_agent_screen(keyboard)
    assert CaptureService._is_agent_screen(controller)
    assert CaptureService._is_agent_screen(['Y Character Details','A Select','B Return','Lv. 40','Lv. 30','Lv. 20'])
    assert not CaptureService._is_agent_screen(['Training Plan', 'Talk'])


def test_agent_replays_upsert_and_reorder_across_restarts(tmp_path):
    path = tmp_path / 'agents.db'
    store = AgentVoiceStore(path)
    first = store.record('Dialyn', '123', '你好。', '2026-09-04T12:00:00+00:00')
    store.record('Yidhari', '456', '再见。', '2026-09-04T12:01:00+00:00')
    replay = store.record('Dialyn', '123', 'different ASR must not overwrite', '2026-09-04T12:02:00+00:00')
    assert replay['key'] == first['key']
    assert replay['heard_count'] == 2 and replay['chinese'] == '你好。'
    assert replay['first_heard'] == first['first_heard']
    reopened = AgentVoiceStore(path)
    assert reopened.count() == 2
    assert reopened.list()[0]['key'] == first['key']
    assert reopened.list(limit=1,offset=1)[0]['agent'] == 'Yidhari'


def test_agent_library_is_not_pruned_at_fifty(tmp_path):
    store = AgentVoiceStore(tmp_path/'agents.db')
    for i in range(65):
        store.record('Anby', str(i), '你好。')
    assert store.count() == 65
    assert len(store.list()) == 65


def test_waveform_matching_handles_gain_noise_and_offset():
    rng = np.random.default_rng(7)
    reference = rng.normal(0,.1,16000).astype(np.float32)
    observed = rng.normal(0,.04,40000).astype(np.float32)
    observed[7000:23000] += reference*.6
    score, offset = waveform_score(reference,observed)
    assert score > .7 and offset == 7000
    assert waveform_score(reference,rng.normal(0,.1,40000).astype(np.float32))[0] < .1


def test_fingerprints_ignore_silence_and_are_gain_invariant():
    assert landmarks(np.zeros(16000,dtype=np.float32)) == []
    rng = np.random.default_rng(8)
    reference = rng.normal(0,.1,16000).astype(np.float32)
    assert landmarks(reference) == landmarks(reference*.6)


def test_bank_media_bounds_and_offsets(tmp_path):
    import struct
    import pytest
    from backend.agent_bank import bank_media, package_table
    from backend.voice_assets import VoiceEntry
    path = tmp_path/'bank.pck'
    chunk = lambda kind,data: kind+struct.pack('<I',len(data))+data
    bank = chunk(b'DIDX',struct.pack('<III',123,2,4))+chunk(b'DATA',b'xxRIFF')
    path.write_bytes(b'prefix'+bank)
    found=bank_media(VoiceEntry(path,6,len(bank),1))
    assert found[123].read() == b'RIFF'
    path.write_bytes(chunk(b'DIDX',struct.pack('<III',123,2,99))+chunk(b'DATA',b'xxvoice'))
    with pytest.raises(ValueError,match='exceeds'):
        bank_media(VoiceEntry(path,0,path.stat().st_size,1))
    with pytest.raises(ValueError):
        package_table(path,1)


def test_asr_uses_isolated_process_and_reports_failures(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    import backend.agent_recognition as module
    folder=tmp_path/'model'
    folder.mkdir()
    (folder/'model.int8.onnx').touch()
    recognizer=module.AgentRecognizer.__new__(module.AgentRecognizer)
    recognizer.folder=tmp_path
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        assert args[1:3] == ['-m','backend.agent_transcribe']
        return SimpleNamespace(returncode=0,stdout=json.dumps({'text':'你好。'}))
    monkeypatch.setattr(module.subprocess,'run',run)
    assert recognizer._transcribe(np.zeros(8000,dtype=np.float32)) == '你好。'
    assert calls[0][1]['timeout'] == 60
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError,match='capture is still running'):
        recognizer._transcribe(np.zeros(8000,dtype=np.float32))


def test_browser_replay_is_excluded_from_future_matching(monkeypatch):
    from backend.agent_recognition import AgentRecognizer
    import backend.agent_recognition as module
    recognizer=AgentRecognizer.__new__(AgentRecognizer)
    recognizer._consumed_until=0.
    monkeypatch.setattr(module.time,'monotonic',lambda:100.)
    recognizer.suppress_playback(4.)
    assert recognizer._replay_until == 104.
    assert recognizer._consumed_until == 104.


def test_recognition_pipeline_deduplicates_same_audio_occurrence(tmp_path,monkeypatch):
    import json,sqlite3
    import backend.agent_recognition as module
    (tmp_path/'library.json').write_text(json.dumps({'agents':{'Dialyn':{}},'clips':{'123':{}}}))
    (tmp_path/'pcm').mkdir()
    rng=np.random.default_rng(32)
    reference=rng.normal(0,.1,24000).astype(np.float32)
    np.save(tmp_path/'pcm/123.npy',reference)
    with sqlite3.connect(tmp_path/'fingerprints.db') as db:
        db.execute('CREATE TABLE clips (asset_id TEXT)')
        db.execute("INSERT INTO clips VALUES ('123')")
        db.execute('CREATE TABLE hashes (hash INTEGER,asset_id TEXT,frame INTEGER)')
        db.executemany("INSERT INTO hashes VALUES (?,'123',?)",landmarks(reference))
    published=[]
    recognizer=module.AgentRecognizer(tmp_path,None,published.append)
    monkeypatch.setattr(module.time,'monotonic',lambda:1000.)
    recognizer._context=('Dialyn',900.,1000.)
    monkeypatch.setattr(recognizer,'_original_audio',lambda asset:(reference,8000,tmp_path/'voice.wav'))
    monkeypatch.setattr(recognizer,'_transcribe',lambda *args:'你好。')
    # Only the first 1.8 seconds are heard; playback still uses the full asset.
    observed=np.r_[np.zeros(2048,dtype=np.float32),reference[:14400]]
    recognizer._recognize('Dialyn',950.,observed,8000)
    assert len(published)==1
    recognizer._recognize('Dialyn',950.,observed,8000)
    assert len(published)==1  # overlapping scan of the same occurrence
    recognizer._recognize('Dialyn',960.,observed,8000)
    assert len(published)==2 and recognizer.store.count()==1
    assert recognizer.store.list()[0]['heard_count']==2
    recognizer._context=(None,1000.,1000.)
    recognizer._recognize('Dialyn',970.,observed,8000)
    assert len(published)==2  # left the agent screen
    recognizer._recognize('Dialyn',980.,observed,8000,context_since=979.)
    assert len(published)==3  # valid captured audio finishes after a screen change
    recognizer.close()
