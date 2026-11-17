"""Real service/capture publication through desktop HTTP, with authored data.

Service-only tests cannot catch account/HTTP barriers or a desktop host that
marks an index ready without binding it to the existing capture service.
"""
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from backend import api
from backend.desktop_game_data import DesktopGameData
from backend.tests.test_game_data import Provider, REQUEST, finish
from backend.storage import TranscriptStore


HEADERS = {'X-Proxy-Transcript': 'setup', 'X-Proxy-Transcript-Account': 'legacy',
    'Origin': 'http://127.0.0.1:3000'}
TEXT = {**REQUEST, 'content_mode': 'text'}


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    accounts = SimpleNamespace(lock=threading.RLock(), generation=0, active='legacy')
    accounts.status = lambda: {'active': accounts.active}
    executor = ThreadPoolExecutor(max_workers=1)
    voices = SimpleNamespace(_executor=executor)
    capture = SimpleNamespace(_scan_epoch=0, game_indexes={}, game_voice_assets={})
    runtime = SimpleNamespace(accounts=accounts, capture=capture, voice_assets=voices,
        game_indexes={}, game_voice_assets={}, textmaps=None, transcript=TranscriptStore(tmp_path / 'history.db'))
    provider = Provider()
    host = runtime.publisher_data = DesktopGameData(runtime, tmp_path / 'publisher', providers={'zzz': provider})
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    yield client, host, provider, runtime
    host.pause()
    executor.shutdown()


def prepare(client, request=TEXT):
    response = client.post('/api/game-data/zzz/plan', json=request, headers=HEADERS)
    assert response.status_code == 200, response.text
    row = response.json()['game']
    response = client.post('/api/game-data/zzz/download',
        json={'plan_id': row['plan_id'], 'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return row


def test_desktop_text_download_binds_real_matcher_offline_activation_and_delete(desktop, tmp_path):
    client, host, provider, runtime = desktop
    retained = tmp_path / 'saved-history.wav'
    retained.write_bytes(b'authored retained recording outside publisher cache')
    plan = prepare(client)
    assert plan['download_bytes'] == 2048 and plan['installed_bytes'] == 0
    row = finish(host.service)
    assert row['state'] == 'ready', row
    assert host.capture_ready('zzz') is True
    index = runtime.capture.textmaps
    match = index.match_lines(['Follow the river beyond the bridge.'], threshold=100)
    assert match.text_id == 'authored:bridge'
    assert match.is_requested_text_only and match.voice_status == 'voiced'
    assert match.translation_locale == 'zh-Hans' and match.translation_text == '沿着河流走过桥。'
    assert match.publisher_generation == 'authored-one'
    assert len(match.publisher_request_sha256) == 64
    assert len(match.publisher_occurrence_sha256) == 64
    assert runtime.capture.voice_assets.has_variant(match.text_id, match.english) is False
    assert api.Runtime.activate_language(runtime, 'zzz', 'en', 'legacy') is False
    assert runtime.capture.textmaps is index  # Legacy background activation cannot replace this source.
    host.active.clear()  # A fresh selection can use only the accepted local descriptor.
    response = client.post('/api/game-data/zzz/activate', json={'revision': row['installed_revision']}, headers=HEADERS)
    assert response.status_code == 200 and host.capture_ready('zzz') is True
    assert provider.downloads == 1
    response = client.request('DELETE', '/api/game-data/zzz/data', json={'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()['freed_bytes'] > 0
    assert host.capture_ready('zzz') is False
    assert retained.read_bytes() == b'authored retained recording outside publisher cache'


def test_stage_and_invalid_audio_snapshot_preserve_working_desktop_text(desktop):
    client, host, provider, runtime = desktop
    prepare(client)
    assert finish(host.service)['state'] == 'ready'
    accepted = runtime.capture.textmaps
    pointer = host.profile_root() / 'zzz/current.json'
    previous = pointer.read_bytes()
    provider.revision, provider.stage = 'authored-two', True
    prepare(client)
    assert finish(host.service)['job']['status'] == 'needs_plan'
    assert runtime.capture.textmaps is accepted and pointer.read_bytes() == previous
    provider.stage, provider.invalid = False, True
    prepare(client, REQUEST)
    failed = finish(host.service)
    assert failed['job']['status'] == 'failed'
    assert 'could not be validated' in failed['message']
    assert runtime.capture.textmaps is accepted and pointer.read_bytes() == previous


def test_http_owner_header_and_setup_origin_precede_any_profile_io(desktop):
    client, host, provider, runtime = desktop
    assert client.post('/api/game-data/zzz/plan', json=TEXT).status_code == 403
    assert client.post('/api/game-data/zzz/plan', json=TEXT,
        headers={**HEADERS, 'Origin': 'https://example.com'}).status_code == 403
    assert client.get('/api/game-data', headers={**HEADERS,
        'X-Proxy-Transcript-Account': 'different'}).status_code == 409
    assert client.get('/api/game-data', headers={**HEADERS,
        'X-Toolkit-Account-Generation': '2'}).status_code == 409
    assert not host.root.exists()
    row = client.post('/api/game-data/zzz/plan', json=TEXT, headers=HEADERS).json()['game']
    runtime.accounts.generation += 2  # Includes A -> B -> A, same account label.
    response = client.post('/api/game-data/zzz/download',
        json={'plan_id': row['plan_id'], 'revision': row['revision']}, headers=HEADERS)
    assert response.status_code == 409 and provider.downloads == 0
    response = client.options('/api/game-data/zzz/data', headers={
        'Origin': HEADERS['Origin'], 'Access-Control-Request-Method': 'DELETE',
        'Access-Control-Request-Headers': 'X-Proxy-Transcript'})
    assert response.status_code == 200


def test_source_errors_do_not_publish_private_diagnostics_and_pause_drains(desktop):
    client, host, provider, runtime = desktop
    provider.plan = lambda *_args: (_ for _ in ()).throw(ValueError('private source path and credential diagnostic'))
    response = client.post('/api/game-data/zzz/plan', json=TEXT, headers=HEADERS)
    assert response.status_code == 409 and 'private source' not in response.text
    old = host.service
    host.pause()
    assert old.closed and old.pool._shutdown
    assert client.get('/api/game-data').status_code == 503
    host.resume()
    assert host.service is not old and not host.service.closed
    assert client.get('/api/game-data').status_code == 200


def test_fresh_desktop_host_restores_exact_accepted_text_while_new_stage_is_pending(desktop, monkeypatch):
    client, host, provider, runtime = desktop
    prepare(client)
    assert finish(host.service)['state'] == 'ready'
    provider.revision, provider.stage = 'authored-two', True
    prepare(client)
    assert finish(host.service)['job']['status'] == 'needs_plan'
    selected = (host.profile_root() / 'selected.json').read_bytes()
    host.pause()
    fresh = DesktopGameData(runtime, host.root, providers={'zzz': provider})
    try:
        from backend import desktop_game_data
        monkeypatch.setattr(desktop_game_data, '_write', lambda *_args: pytest.fail('Offline restore rewrote a selection'))
        fresh.resume()
        assert fresh.restore_error is None and fresh.capture_ready('zzz') is True
        assert runtime.capture.textmaps.publisher_generation == 'authored-one'
        assert provider.downloads == 2
        assert (fresh.profile_root() / 'selected.json').read_bytes() == selected
        fresh.pause()
        fresh.resume()
        assert fresh.capture_ready('zzz') is True and provider.downloads == 2
    finally:
        fresh.pause()
