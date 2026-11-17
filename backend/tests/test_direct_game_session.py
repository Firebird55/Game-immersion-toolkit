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
    def resolve(self, row, destination, *, cancelled, _raw=None):
        assert self.has(row); self.entered.set(); self.calls += 1
        if self.release: assert self.release.wait(4)
        path = destination.with_suffix('.wav'); path.write_bytes(self.raw if _raw is None else _raw)
        return path


class BoundVoice:
    """Keep original bytes source-specific while sharing authored race controls."""
    def __init__(self, control, raw): self.control, self.raw = control, raw
    def has(self, row): return self.control.has(row)
    def resolve(self, row, destination, *, cancelled):
        return self.control.resolve(row, destination, cancelled=cancelled, _raw=self.raw)


class LocalProvider(Provider):
    def __init__(self, voice): super().__init__(); self.voice = voice
    def download(self, plan, ctx):
        result = super().download(plan, ctx)
        handle = result.restore_handle
        if ctx.request.content_mode == 'text-audio':
            ctx.consume_bytes(len(self.voice.raw), kind='audio')
            (ctx.directory / 'original.wav').write_bytes(self.voice.raw)
            handle = {**handle, 'audio_sha256': hashlib.sha256(self.voice.raw).hexdigest()}
        return SnapshotSource(result.snapshot_path, handle, PROOF,
            BoundVoice(self.voice, self.voice.raw) if ctx.request.content_mode == 'text-audio' else None)
    def restore(self, handle, ctx):
        result = super().restore(handle, ctx)
        if ctx.request.content_mode == 'text-audio':
            # A fresh provider can recover actual original bytes from only its
            # private managed directory and immutable receipt, without RAM/PC.
            raw = (ctx.directory / 'original.wav').read_bytes()
            assert hashlib.sha256(raw).hexdigest() == handle['audio_sha256']
        return SnapshotSource(result.snapshot_path, handle, PROOF,
            BoundVoice(self.voice, raw) if ctx.request.content_mode == 'text-audio' else None)


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
        'text_capture_verified': True})
    replaced, upgraded = session.history.add_or_upgrade_recent(complete, session.session_id)
    assert upgraded and replaced.id == first.id and session.history.count() == 1
    assert session._recording_line(first.id) is None
    assert not session._line(replaced).get('original_audio_expected')
    session.original_source_for = lambda _: pytest.fail('Upgraded text borrowed older recording')
    session._queue_original(first.id)
    session.preserve_game_recordings('zzz', session.original_source_for, cancelled=lambda: False)
    assert not session.recording_jobs and session.audio_path(first.id) is None
    assert session.history.get(first.id).text_id == 'authored:complete'
    assert not session.history.get(first.id).has_audio


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


def test_same_caption_explicit_audio_addition_keeps_old_text_and_gets_new_original(tmp_path):
    import json
    service, session, owner, voice, raw = rig(tmp_path)
    try:
        planned = service.plan('zzz', {**REQUEST, 'content_mode': 'text'})['game']
        service.download('zzz', {'plan_id': planned['plan_id'], 'revision': planned['revision']})
        finish(service); old_id = capture(session); session.history.set_favorite(old_id, True)
        old = session.history.get(old_id)
        assert old.is_requested_text_only and old.publisher_generation == 'authored-one'
        download(service); finish(service); new_id = capture(session)
        current = session.history.get(new_id); path = wait_audio(session, new_id)
        assert new_id != old_id and current.text_id == old.text_id
        assert current.publisher_generation == old.publisher_generation
        assert current.publisher_request_sha256 != old.publisher_request_sha256
        assert current.publisher_request_sha256 == hashlib.sha256(json.dumps(REQUEST, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        assert current.publisher_occurrence_sha256 != old.publisher_occurrence_sha256
        assert path.read_bytes() == raw and session.history.count() == 2
        assert session.history.get(old_id).favorite and not session.history.get(old_id).has_audio
        for field in ('publisher_generation', 'publisher_request_sha256', 'publisher_occurrence_sha256'):
            assert not session.recordings.matches(new_id,
                session._recording_stamp(current.model_copy(update={field: 'b' * 64})))
    finally: service.close(); session.stop()


def test_same_id_new_publisher_generation_uses_new_recording_and_keeps_favorite(tmp_path):
    service, session, owner, voice, raw = rig(tmp_path)
    try:
        download(service); finish(service); old_id = capture(session); old_path = wait_audio(session, old_id)
        session.history.set_favorite(old_id, True)
        newer = raw[:-2] + b'\x34\x12'
        voice.raw = newer; service.providers['zzz'].revision = 'authored-two'
        download(service); finish(service); new_id = capture(session); new_path = wait_audio(session, new_id)
        old, current = session.history.get(old_id), session.history.get(new_id)
        assert new_id != old_id and old.text_id == current.text_id
        assert old.publisher_generation == 'authored-one' and current.publisher_generation == 'authored-two'
        assert old.publisher_request_sha256 == current.publisher_request_sha256
        assert old_path.read_bytes() == raw and new_path.read_bytes() == newer
        assert old_path != new_path and old.favorite and session.history.count() == 2
    finally: service.close(); session.stop()


def test_late_old_decoder_never_publishes_into_same_caption_new_generation(tmp_path, monkeypatch):
    import itertools
    service, session, owner, voice, raw = rig(tmp_path)
    voice.release = threading.Event()
    completed, writes, counter = {}, [], itertools.count(1)
    resolve, update = voice.resolve, session.history.update_audio
    def traced(*args, **kwargs):
        number = next(counter)
        try: return resolve(*args, **kwargs)
        finally: completed[threading.get_ident()] = number
    def published(identity, *args):
        writes.append((identity, completed.get(threading.get_ident())))
        return update(identity, *args)
    monkeypatch.setattr(voice, 'resolve', traced)
    monkeypatch.setattr(session.history, 'update_audio', published)
    try:
        download(service); finish(service)
        old_id = capture(session); old_generation = session.generation
        assert voice.entered.wait(2)
        newer = raw[:-2] + b'\x78\x56'
        voice.raw = newer; service.providers['zzz'].revision = 'authored-two'
        download(service); finish(service); new_id = capture(session)
        assert new_id != old_id
        assert session.observe(old_generation, 3, [TEXT], now=2) == []
        voice.release.set(); new_path = wait_audio(session, new_id)
        until = time.monotonic() + 3
        while session.recording_jobs and time.monotonic() < until: time.sleep(.01)
        # Starting the new source may separately retry saved historical audio.
        # That fresh authorization is allowed; the original delayed decode #1
        # must never publish, including into the new same-ID caption.
        assert writes and not any(number == 1 for _, number in writes)
        if session.history.get(old_id).has_audio:
            assert session.audio_path(old_id).read_bytes() == raw
        assert new_path.read_bytes() == newer
        assert session.history.get(new_id).publisher_generation == 'authored-two'
    finally: voice.release.set(); service.close(); session.stop()


def test_actual_direct_same_id_player_switch_gets_its_own_original_occurrence(tmp_path):
    import json
    from backend.game_data_protocol import GameDataPlan
    fixture_library(tmp_path / 'authored'); female = (tmp_path / 'authored/tone.wav').read_bytes()
    originals = {'female': female, 'male': female[:-2] + b'\x12\x34'}
    class ActorVoice:
        def __init__(self, members): self.members = members
        def has(self, row):
            return row.get('audio', {}).get('file_id') == 'authored:' + row.get('player_voice', '') and row.get('player_voice') in self.members
        def resolve(self, row, destination, *, cancelled):
            assert self.has(row) and not cancelled()
            path = destination.with_suffix('.wav'); path.write_bytes(self.members[row['player_voice']]); return path
    class ActorProvider(Provider):
        def plan(self, request, ctx):
            ctx.consume_bytes(128, kind='metadata')
            return GameDataPlan('authored-actors-one', 32768, 65536, runtime_available=True)
        def download(self, plan, ctx):
            source = super().download(plan, ctx)
            payload = json.loads(source.snapshot_path.read_text())
            payload['records'] = [{**payload['records'][0], 'text_id': 'authored:same-id', 'player_voice': player,
                'audio': {'publisher': 'authored', 'file_id': 'authored:' + player}} for player in originals]
            source.snapshot_path.write_text(json.dumps(payload))
            for player, raw in originals.items():
                ctx.consume_bytes(len(raw), kind='audio'); (ctx.directory / (player + '.wav')).write_bytes(raw)
            handle = {'files': {player: hashlib.sha256(raw).hexdigest() for player, raw in originals.items()}}
            return SnapshotSource(source.snapshot_path, handle, PROOF, ActorVoice(originals))
        def restore(self, handle, ctx):
            with pytest.raises(GameDataError): ctx.consume_bytes(0, kind='audio')
            members = {player: (ctx.directory / (player + '.wav')).read_bytes() for player in handle['files']}
            assert all(hashlib.sha256(raw).hexdigest() == handle['files'][player] for player, raw in members.items())
            return SnapshotSource(ctx.directory / 'textmap.json', handle, PROOF, ActorVoice(members))
    session = PreparedCaptureSession(tmp_path / 'profile')
    def activate(ctx, source):
        session.activate_source(ctx.directory, ctx.index, ctx.source_descriptor, source.voice_source,
            lambda descriptor: service.original_voice_source(descriptor, expected_owner=ctx.owner))
    service = GameDataService(session.root / 'game-data', {'zzz': ActorProvider()}, on_activate=activate)
    try:
        download(service); finish(service)
        session.update_settings({'zzz_proxy_voice': 'female'})
        first = capture(session); first_path = wait_audio(session, first); session.history.set_favorite(first, True)
        session.update_settings({'zzz_proxy_voice': 'male'})
        second = capture(session); second_path = wait_audio(session, second)
        old, current = session.history.get(first), session.history.get(second)
        assert old.text_id == current.text_id == 'authored:same-id' and first != second
        assert old.publisher_generation == current.publisher_generation
        assert old.publisher_request_sha256 == current.publisher_request_sha256
        assert old.publisher_occurrence_sha256 != current.publisher_occurrence_sha256
        assert first_path.read_bytes() == originals['female'] and second_path.read_bytes() == originals['male']
        assert old.favorite and session.history.count() == 2
    finally: service.close(); session.stop()
