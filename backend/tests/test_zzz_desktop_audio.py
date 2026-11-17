"""Original ZZZ ownership parsers through the frozen desktop HTTP host.

Source bytes and the codec are authored fixtures; this is host integration,
not an assertion of playback coverage for the publisher's complete corpus.
"""
from backend.desktop_game_data import DesktopGameData
from backend.desktop_original_audio import recording_stamp
from backend.tests.test_desktop_game_data import desktop, prepare, HEADERS, TEXT
from backend.tests.test_desktop_original_audio import decode
from backend.tests.test_game_data import REQUEST, finish
from backend.tests.test_zzz_pc_audio import FixtureProvider


def complete(client, host, *, before=None):
    for _ in range(12):
        prepare(client, REQUEST)
        row = finish(host.service)
        assert row['job']['status'] != 'failed', row
        if row['job']['status'] == 'complete':
            return row
        assert row['job']['status'] == 'needs_plan'
        if before:
            before()
    raise AssertionError('Authored original ZZZ stages did not complete')


def capture(runtime):
    match = runtime.capture.textmaps.match_lines(['An authored complete caption.'], threshold=100)
    assert match.audio_scope == 'context'
    line, _ = runtime.transcript.add_or_upgrade_recent(match, 'authored-zzz-package')
    return line


def test_zzz_original_stages_publish_to_desktop_and_preserve_recordings(desktop, tmp_path, monkeypatch):
    client, host, _, runtime = desktop
    prepare(client, TEXT)
    assert finish(host.service)['state'] == 'ready'
    index = runtime.capture.textmaps
    pointer = host.profile_root() / 'zzz/current.json'
    previous = pointer.read_bytes()
    provider = host.service.providers['zzz'] = FixtureProvider(tmp_path, monkeypatch)

    def retained():
        assert runtime.capture.textmaps is index
        assert pointer.read_bytes() == previous

    row = complete(client, host, before=retained)
    assert row['state'] == 'ready' and host.capture_ready('zzz')
    old = capture(runtime)
    decode(runtime, old)
    first = client.get(f'/api/lines/{old.id}/audio').content
    assert first[:4] == b'RIFF'

    provider.version = 'two'
    row = complete(client, host)
    current = capture(runtime)
    assert current.id != old.id
    voices = runtime.capture.voice_assets
    host.recordings().register(current.id, {**voices.descriptor, '_desktop_profile': host.profile_root().name},
        voices._row(current), line_stamp=recording_stamp(current))
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200, response.text
    second = client.get(f'/api/lines/{current.id}/audio').content
    assert second[:4] == b'RIFF' and second != first
    assert client.get(f'/api/lines/{old.id}/audio').content == first
    assert not host.capture_ready('zzz')

    host.pause()
    fresh = runtime.publisher_data = DesktopGameData(runtime, host.root, providers={'zzz': provider})
    calls = list(provider.calls)
    try:
        fresh.resume()
        assert not fresh.capture_ready('zzz') and provider.calls == calls
        assert client.get(f'/api/lines/{old.id}/audio').content == first
        assert client.get(f'/api/lines/{current.id}/audio').content == second
    finally:
        fresh.pause()
