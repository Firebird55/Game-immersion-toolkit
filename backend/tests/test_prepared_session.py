"""Portable libraries must keep production identities and old recordings intact."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import wave
import zipfile

import pytest

from backend.prepared_library import PreparedLibraryStore, write_prepared_library
from backend.prepared_session import PreparedCaptureSession


def fixture_library(root, *, text='Follow the river beyond the bridge.', identity='owned:line', player=None, game='zzz'):
    root.mkdir(parents=True, exist_ok=True)
    clip = root / 'tone.wav'
    with wave.open(str(clip), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        stream.writeframes(struct.pack('<h', 1000) * 1600)
    row = dict(text_id=identity, english=text, chinese='沿河走过桥。', source_locale='en',
        source_text=text, texts={'en': text, 'zh-Hans': '沿河走过桥。'}, audio_locale='en',
        audio={'source': 'owned-authored-fixture'}, voice_status='voiced',
        dialogue_kind='conversation', player_voice=player)
    payload = dict(format=2, game=game, source_locale='en', records=[row])
    return write_prepared_library(payload, root / 'private.zip', {identity: clip}), payload


def test_shared_confirmation_rejects_late_frames_and_keeps_audio_after_restart_update(tmp_path):
    archive, payload = fixture_library(tmp_path / 'input')
    session = PreparedCaptureSession(tmp_path / 'application')
    session.import_library(archive)
    generation = session.start()
    text = payload['records'][0]['source_text']
    assert session.observe(generation, 1, [text], now=10) == []
    assert session.observe(generation, 1, [text], now=10.1) == []  # Replayed frame is not confirmation.
    emitted = session.observe(generation, 2, [text], now=10.2)
    assert len(emitted) == 1 and emitted[0]['text_id'] == 'owned:line'
    assert emitted[0]['audio_source'] == 'original'
    original = session.audio_path(emitted[0]['id']).read_bytes()
    session.history.set_favorite(emitted[0]['id'], True)
    session.stop()
    assert session.observe(generation, 3, [text], now=10.3) == []
    other, _ = fixture_library(tmp_path / 'new', text='A different complete sentence.', identity='owned:new')
    session.import_library(other)
    restarted = PreparedCaptureSession(tmp_path / 'application')
    assert not restarted.running and restarted.history.count() == 1
    assert restarted.history.get(emitted[0]['id']).favorite
    assert restarted.audio_path(emitted[0]['id']).read_bytes() == original


def test_failed_and_cancelled_import_retain_complete_library_and_history(tmp_path):
    archive, _ = fixture_library(tmp_path / 'input')
    store = PreparedLibraryStore(tmp_path / 'store')
    store.import_archive(archive)
    old = store.pointer.read_bytes()
    with pytest.raises(InterruptedError):
        store.import_archive(archive, cancelled=lambda: True)
    assert store.pointer.read_bytes() == old
    corrupt = tmp_path / 'corrupt.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, 'w') as target:
        for name in source.namelist():
            target.writestr(name, b'changed' if name == 'textmap.json' else source.read(name))
    with pytest.raises(ValueError):
        store.import_archive(corrupt)
    assert store.pointer.read_bytes() == old
    assert store.current().is_dir()


def test_original_archive_references_and_path_escapes_are_not_mobile_code_or_audio(tmp_path):
    archive, payload = fixture_library(tmp_path / 'input')
    with zipfile.ZipFile(archive) as source:
        raw = source.read('textmap.json')
    assert b'owned-authored-fixture' not in raw and b'prepared_clip' in raw
    unsafe = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(unsafe, 'w') as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
        target.writestr('../outside.py', 'raise RuntimeError()')
    with pytest.raises(ValueError, match='Unsafe'):
        PreparedLibraryStore(tmp_path / 'store').import_archive(unsafe)
    assert not (tmp_path / 'outside.py').exists()


def test_explicit_missing_and_unvoiced_capture_keep_their_status_and_settings_scope(tmp_path):
    archive, payload = fixture_library(tmp_path / 'input')
    missing = copy.deepcopy(payload['records'][0])
    missing.update(text_id='owned:missing', audio=None, voice_status='unavailable', text_capture_verified=True)
    missing['source_text'] = missing['english'] = missing['texts']['en'] = 'The unavailable sentence remains written.'
    payload['records'].append(missing)
    archive = write_prepared_library(payload, tmp_path / 'mixed.zip', {})
    session = PreparedCaptureSession(tmp_path / 'application');session.import_library(archive)
    text = missing['source_text'];generation = session.start()
    assert not session.observe(generation, 1, [text], now=1)
    assert not session.observe(generation, 2, [text], now=1.1)
    session.update_settings({'capture_missing_audio': True})
    assert not session.observe(generation, 3, [text], now=1.2)
    generation = session.start()
    assert not session.observe(generation, 1, [text], now=2)
    emitted = session.observe(generation, 2, [text], now=2.1)
    assert len(emitted) == 1 and emitted[0]['voice_status'] == 'unavailable' and not emitted[0]['has_audio']


def test_wrong_player_branch_and_gaps_do_not_complete_confirmation(tmp_path):
    archive, payload = fixture_library(tmp_path / 'input', player='female', game='genshin')
    session = PreparedCaptureSession(tmp_path / 'application');session.import_library(archive)
    session.update_settings({'genshin_player_voice': 'male'})
    generation = session.start();text = payload['records'][0]['source_text']
    assert not session.observe(generation, 1, [text], now=1)
    session.index.player_voice = 'female'
    assert not session.observe(generation, 2, [text], now=2)
    assert not session.observe(generation, 3, [text], now=6)
    assert len(session.observe(generation, 4, [text], now=6.1)) == 1
