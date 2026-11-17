"""Real production index/confirmation with authored direct-source originals."""
import hashlib
import threading
import time

import pytest

from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError, SnapshotSource
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_game_data import Provider, PROOF, REQUEST, download, finish
from backend.tests.test_prepared_session import fixture_library


TEXT = 'Follow the river beyond the bridge.'


class LocalVoice:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0
        self.entered, self.release = threading.Event(), None
    def has(self, row): return row.get('audio') == {'publisher': 'authored', 'file_id': 'original-bridge'}
    def resolve(self, row, destination, *, cancelled):
        assert self.has(row); self.entered.set(); self.calls += 1
        if self.release: assert self.release.wait(4)
        path = destination.with_suffix('.wav'); path.write_bytes(self.raw)
        return path


class LocalProvider(Provider):
    def __init__(self, voice): super().__init__(); self.voice = voice
    def download(self, plan, ctx):
        result = super().download(plan, ctx)
        return SnapshotSource(result.snapshot_path, result.restore_handle, PROOF,
            self.voice if ctx.request.content_mode == 'text-audio' else None)
    def restore(self, handle, ctx):
        result = super().restore(handle, ctx)
        return SnapshotSource(result.snapshot_path, handle, PROOF,
            self.voice if ctx.request.content_mode == 'text-audio' else None)


def rig(tmp_path):
    fixture_library(tmp_path / 'authored')
    raw = (tmp_path / 'authored/tone.wav').read_bytes()
    session = PreparedCaptureSession(tmp_path / 'profile')
    owner = ['activation-A:1']; voice = LocalVoice(raw)
    def activate(ctx, source):
        if source:
            session.activate_source(ctx.directory, ctx.index, ctx.source_descriptor, source.voice_source,
                lambda descriptor: service.original_voice_source(descriptor, expected_owner=ctx.owner))
        else:
            session.stop()
            session.preserve_game_recordings(ctx.game,
                lambda descriptor: service.original_voice_source(descriptor, expected_owner=ctx.owner),
                cancelled=ctx.cancelled)
            session.deactivate_source(ctx.game)
    service = GameDataService(session.root / 'game-data', {'zzz': LocalProvider(voice)},
        owner_guard=lambda: owner[0], on_activate=activate, retained_bytes=session.recordings.retained_bytes)
    return service, session, owner, voice, raw


def capture(session):
    generation = session.start()
    assert session.observe(generation, 1, [TEXT], now=1) == []
    lines = session.observe(generation, 2, [TEXT], now=1.1)
    assert len(lines) == 1
    return lines[0]['id']


def wait_audio(session, identity):
    until = time.monotonic() + 3
    while time.monotonic() < until:
        if session.history.get(identity).has_audio:
            return session.audio_path(identity)
        time.sleep(.01)
    raise AssertionError('Authored original was not retained')


def test_direct_source_uses_shared_matcher_retains_original_favorite_after_delete_and_restart(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    try:
        download(service); assert finish(service)['state'] == 'ready'
        identity = capture(session)
        path = wait_audio(session, identity)
        assert path.read_bytes() == raw and path.stem == hashlib.sha256(raw).hexdigest()
        assert 'game-data' not in path.relative_to(session.root).parts
        session.history.set_favorite(identity, True)
        revision = service.snapshot()['games'][0]['revision']
        result = service.delete('zzz', {'revision': revision})
        assert result['freed_bytes'] > 0 and result['game']['retained_bytes'] == len(raw)
        assert session.index is None and not session.running
        restarted = PreparedCaptureSession(session.root)
        assert restarted.history.get(identity).favorite
        assert restarted.audio_path(identity).read_bytes() == raw
        assert voice.calls == 1
    finally: service.close(); session.stop()


def test_decoder_does_not_hold_ocr_lock_and_old_generation_cannot_publish(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    voice.release = threading.Event()
    try:
        download(service); finish(service)
        identity = capture(session); assert voice.entered.wait(2)
        assert session.snapshot()['lines'][0]['audio_pending']
        before = time.monotonic(); session.stop('Background pause')
        assert time.monotonic() - before < .5
        owner[0] = 'activation-B:2'; owner[0] = 'activation-A:3'
        voice.release.set()
        until = time.monotonic() + 3
        while session.recording_jobs and time.monotonic() < until: time.sleep(.01)
        assert not session.recording_jobs and not session.history.get(identity).has_audio
        assert session.recordings.path(identity) is None
        assert session.audio_path(identity) is None
    finally: voice.release.set(); service.close(); session.stop()


def test_failed_preservation_refuses_delete_and_keeps_original_source(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    voice.release = threading.Event()
    try:
        download(service); finish(service); identity = capture(session)
        assert voice.entered.wait(2)
        revision = service.snapshot()['games'][0]['revision']
        with pytest.raises(GameDataError, match='still being prepared'):
            service.delete('zzz', {'revision': revision})
        assert service.snapshot()['games'][0]['installed_bytes'] > 0
        assert session.history.get(identity) is not None
        voice.release.set()
        until = time.monotonic() + 3
        while session.recording_jobs and time.monotonic() < until: time.sleep(.01)
        assert service.delete('zzz', {'revision': revision})['game']['retained_bytes'] == len(raw)
        assert session.audio_path(identity).read_bytes() == raw
    finally: voice.release.set(); service.close(); session.stop()


def test_text_only_source_matches_without_constructing_or_resolving_voice(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    try:
        plan = service.plan('zzz', {**REQUEST, 'content_mode': 'text'})['game']
        service.download('zzz', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        assert finish(service)['state'] == 'ready'
        identity = capture(session)
        line = session.history.get(identity)
        assert line.is_requested_text_only and line.voice_status == 'voiced'
        assert not line.has_audio and not line.voiced
        assert session.audio_path(identity) is None and voice.calls == 0
        assert session.recordings.lines('zzz') == []
    finally: service.close(); session.stop()


def test_explicit_text_switch_still_preserves_previously_downloaded_saved_original_locally(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    voice.release = threading.Event()
    try:
        download(service); finish(service); identity = capture(session)
        assert voice.entered.wait(2)
        session.stop(); voice.release.set()
        until = time.monotonic() + 3
        while session.recording_jobs and time.monotonic() < until: time.sleep(.01)
        assert not session.history.get(identity).has_audio
        plan = service.plan('zzz', {**REQUEST, 'content_mode': 'text'})['game']
        service.download('zzz', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        assert finish(service)['state'] == 'ready'
        assert session.direct_voice is None
        # The old explicit audio download still exists locally. Restoring it
        # has a zero-byte network budget, including zero-byte preflight gates.
        result = service.delete('zzz', {'revision': plan['revision']})
        assert result['game']['retained_bytes'] == len(raw)
        assert session.audio_path(identity).read_bytes() == raw
    finally: voice.release.set(); service.close(); session.stop()
