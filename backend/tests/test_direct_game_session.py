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


def test_real_sqlite_prefix_upgrade_cannot_reuse_older_saved_original_reference(tmp_path):
    from backend.models import TextMatch
    session = PreparedCaptureSession(tmp_path / 'profile')
    _, payload = fixture_library(tmp_path / 'source')
    row = payload['records'][0]
    descriptor = {'game': 'zzz', 'ready': True, 'request': {'content_mode': 'text-audio'}}
    partial = TextMatch(text_id='authored:partial', english='What is reinforcing the seal supposed to mean?',
        chinese='加固封印究竟是什么意思？', source_ocr='What is reinforcing the seal supposed to mean?',
        source_locale='zh-Hans', source_text='加固封印究竟是什么意思？', voice_status='voiced', score=100, kind='exact')
    first, _ = session.history.add_or_upgrade_recent(partial, session.session_id)
    session.recordings.register(first.id, descriptor, row, line_stamp=session._recording_stamp(first))
    assert session._recording_line(first.id) is not None
    complete = partial.model_copy(update={'text_id': 'authored:complete',
        'english': partial.english + ' Was that supposed to be a warning about the forest?',
        'source_text': partial.source_text + '这难道是关于森林的警告吗？',
        'chinese': partial.chinese + '这难道是关于森林的警告吗？',
        'source_ocr': partial.source_ocr + ' Was that supposed to be a warning about the forest?',
        'audio_omitted_by_request': True, 'source_voice_binding': {'authored': 'new-occurrence'},
        'text_capture_verified': True})
    replaced, upgraded = session.history.add_or_upgrade_recent(complete, session.session_id)
    assert upgraded and replaced.id == first.id and session.history.count() == 1
    assert session._recording_line(first.id) is None
    assert not session._line(replaced).get('original_audio_expected')
    session.original_source_for = lambda _: pytest.fail('Upgraded text borrowed older recording')
    session._queue_original(first.id)
    session.preserve_game_recordings('zzz', session.original_source_for, cancelled=lambda: False)
    assert not session.recording_jobs and session.audio_path(first.id) is None
    assert session.history.get(first.id).is_requested_text_only


def test_transcript_stamp_keeps_favorites_but_rejects_changed_text_binding(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    try:
        download(service); finish(service); identity = capture(session); wait_audio(session, identity)
        original = session.history.get(identity)
        session.history.set_favorite(identity, True)
        assert session._recording_line(identity) is not None
        assert session.audio_path(identity).read_bytes() == raw
        changed = original.model_copy(update={'source_text': 'A different occurrence'})
        assert not session.recordings.matches(identity, session._recording_stamp(changed))
    finally: service.close(); session.stop()
