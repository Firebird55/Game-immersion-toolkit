"""Desktop original identity, deletion retention and delayed-owner protection."""
import hashlib
import io
import threading
import wave

from backend.desktop_game_data import DesktopGameData
from backend.game_data_protocol import SnapshotSource
from backend.tests.test_game_data import Provider, PROOF, REQUEST, finish
from backend.tests.test_desktop_game_data import desktop, prepare, HEADERS, TEXT


def tone(value):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
        stream.writeframes(value.to_bytes(2, 'little', signed=True) * 80)
    return output.getvalue()


class LocalVoice:
    def __init__(self, raw, gate=None): self.raw, self.gate = raw, gate
    def has(self, row): return row.get('audio') == {'publisher': 'authored', 'file_id': 'original-bridge'}
    def resolve(self, row, destination, *, cancelled):
        assert self.has(row)
        if self.gate:
            self.gate[0].set(); assert self.gate[1].wait(5)
        path = destination.with_suffix('.wav'); path.write_bytes(self.raw)
        return path


class LocalProvider(Provider):
    def __init__(self): super().__init__(); self.raw, self.decode_gate = tone(100), None
    def download(self, plan, ctx):
        result = super().download(plan, ctx)
        if ctx.request.content_mode == 'text': return result
        ctx.consume_bytes(len(self.raw), kind='audio')
        (ctx.directory / 'original.wav').write_bytes(self.raw)
        handle = {**result.restore_handle, 'audio_sha256': hashlib.sha256(self.raw).hexdigest()}
        return SnapshotSource(result.snapshot_path, handle, PROOF, LocalVoice(self.raw, self.decode_gate))
    def restore(self, handle, ctx):
        result = super().restore(handle, ctx)
        if ctx.request.content_mode == 'text': return result
        raw = (ctx.directory / 'original.wav').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == handle['audio_sha256']
        return SnapshotSource(result.snapshot_path, handle, PROOF, LocalVoice(raw, self.decode_gate))


def capture(runtime):
    match = runtime.capture.textmaps.match_lines(['Follow the river beyond the bridge.'], threshold=100)
    line, _ = runtime.transcript.add_or_upgrade_recent(match, 'authored-desktop')
    return line


def decode(runtime, line):
    completed, result = threading.Event(), []
    def callback(identity, name, voiced):
        result.append((identity, name, voiced))
        runtime.transcript.update_audio(identity, name, True)
        completed.set()
    assert runtime.capture.voice_assets.schedule(line.text_id, line.id, callback, line.english)
    assert completed.wait(5)
    assert result[0][2] is True


def test_new_generation_and_text_update_preserve_original_http_playback_after_delete_and_restart(desktop):
    client, host, _, runtime = desktop
    provider = host.service.providers['zzz'] = LocalProvider()
    prepare(client, REQUEST); assert finish(host.service)['state'] == 'ready'
    old = capture(runtime); decode(runtime, old)
    old_raw = provider.raw
    assert client.get(f'/api/lines/{old.id}/audio').content == old_raw
    provider.revision, provider.raw = 'authored-two', tone(200)
    prepare(client, REQUEST); assert finish(host.service)['state'] == 'ready'
    current = capture(runtime); assert current.id != old.id
    decode(runtime, current)
    assert client.get(f'/api/lines/{current.id}/audio').content == provider.raw
    assert client.get(f'/api/lines/{old.id}/audio').content == old_raw
    prepare(client, TEXT); row = finish(host.service)
    assert row['state'] == 'ready' and row['retained_bytes'] == len(old_raw) + len(provider.raw)
    text = capture(runtime); assert text.id not in {old.id, current.id}
    assert not runtime.capture.voice_assets.schedule(text.text_id, text.id, lambda *_: None)
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert client.get(f'/api/lines/{old.id}/audio').content == old_raw
    host.pause()
    fresh = DesktopGameData(runtime, host.root, providers={'zzz': provider})
    runtime.publisher_data = fresh
    try:
        fresh.resume()
        assert fresh.capture_ready('zzz') is False
        assert client.get(f'/api/lines/{old.id}/audio').content == old_raw
        assert client.get(f'/api/lines/{current.id}/audio').content == provider.raw
    finally: fresh.pause()


def test_pending_original_is_retained_before_cache_deletion(desktop):
    client, host, _, runtime = desktop
    provider = host.service.providers['zzz'] = LocalProvider()
    prepare(client, REQUEST); row = finish(host.service)
    line = capture(runtime)
    # Model a referenced line whose original decode has not yet run.
    voices = runtime.capture.voice_assets
    from backend.desktop_original_audio import recording_stamp
    host.recordings().register(line.id, {**voices.descriptor, '_desktop_profile': host.profile_root().name},
        voices._row(line), line_stamp=recording_stamp(line))
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert client.get(f'/api/lines/{line.id}/audio').content == provider.raw


def test_delayed_audio_cannot_publish_after_owner_generation_changes(desktop):
    client, host, _, runtime = desktop
    provider = host.service.providers['zzz'] = LocalProvider()
    provider.decode_gate = (threading.Event(), threading.Event())
    prepare(client, REQUEST); assert finish(host.service)['state'] == 'ready'
    line = capture(runtime); callbacks = []
    voices = runtime.capture.voice_assets
    assert voices.schedule(line.text_id, line.id, lambda *args: callbacks.append(args), line.english)
    assert provider.decode_gate[0].wait(5)
    runtime.accounts.generation += 2
    provider.decode_gate[1].set()
    host.audio_pool.shutdown(wait=True)
    assert callbacks == [] and host.recordings().path(line.id) is None


def test_failed_original_decode_refuses_deletion_and_keeps_selected_source(desktop):
    client, host, _, runtime = desktop
    provider = host.service.providers['zzz'] = LocalProvider()
    prepare(client, REQUEST); row = finish(host.service)
    line = capture(runtime)
    voices, index = runtime.capture.voice_assets, runtime.capture.textmaps
    from backend.desktop_original_audio import recording_stamp
    host.recordings().register(line.id, {**voices.descriptor, '_desktop_profile': host.profile_root().name},
        voices._row(line), line_stamp=recording_stamp(line))
    selected = (host.profile_root() / 'selected.json').read_bytes()
    source_for = host.source_for
    class BrokenVoice:
        def has(self, _row): return True
        def resolve(self, *_args, **_kwargs): raise ValueError('authored unavailable decoder')
    host.source_for = lambda *_args: BrokenVoice()
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 409
    assert runtime.capture.textmaps is index and host.capture_ready('zzz') is True
    assert (host.profile_root() / 'selected.json').read_bytes() == selected
    assert (host.profile_root() / 'zzz/current.json').is_file()
    host.source_for = source_for
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200
    assert client.get(f'/api/lines/{line.id}/audio').content == provider.raw
    assert provider.downloads == 1
