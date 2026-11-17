"""Real Android HTTP + typed authored provider + shared index, no PC/ZIP flow."""
import hashlib
import json
import threading
import time

import pytest

from backend.android_host import AndroidHost
from backend.game_data_protocol import GameDataError
from backend.tests.test_android_host import request
from backend.tests.test_android_account_http import account_host, register, headers as account_headers
from backend.tests.test_direct_game_session import LocalProvider, LocalVoice, TEXT, wait_audio
from backend.tests.test_game_data import REQUEST
from backend.tests.test_prepared_session import fixture_library


def headers(host):
    return {'X-Toolkit-Account-Generation': str(host.account_generation), 'X-Proxy-Transcript': 'setup'}


def action(host, method, path, value):
    return request(host, method, '/api/game-data' + path, json.dumps(value).encode(), headers=headers(host))


def game(host):
    status, payload = request(host, 'GET', '/api/game-data', headers=headers(host))
    assert status == 200
    return payload['games'][0]


def finished(host):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        row = game(host)
        if row['job'] and row['job']['status'] not in {'queued', 'running'}:
            return row
        time.sleep(.01)
    raise AssertionError('Authored download did not settle')


def install(host, *, mode='text-audio'):
    status, value = action(host, 'POST', '/zzz/plan', {**REQUEST, 'content_mode': mode})
    assert status == 200 and value['game']['download_bytes'] > 0
    row = value['game']
    assert action(host, 'POST', '/zzz/download', {'plan_id': row['plan_id'], 'revision': row['revision']})[0] == 202
    assert finished(host)['state'] == 'ready'


def test_http_direct_download_capture_original_delete_and_restart_preserve_history(tmp_path):
    _, payload = fixture_library(tmp_path / 'authored')
    raw = (tmp_path / 'authored/tone.wav').read_bytes()
    provider = LocalProvider(LocalVoice(raw))
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    root = tmp_path / 'application'
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        status, value = request(host, 'GET', '/api/game-data', headers=headers(host))
        assert status == 200 and len(value['games']) == 8
        assert value['games'][0]['state'] == 'not_downloaded'
        assert all(row['state'] == 'unsupported' for row in value['games'][1:])
        assert not host.session.index and provider.downloads == 0
        assert action(host, 'POST', '/zzz/plan', {key: value for key, value in REQUEST.items() if key != 'content_mode'})[0] == 400
        install(host)
        assert host.session.libraries.current() is None  # No backup ZIP or PC path.
        generation = host.session.start()
        assert host.session.observe(generation, 1, [TEXT], now=1) == []
        identity = host.session.observe(generation, 2, [TEXT], now=1.1)[0]['id']
        audio = wait_audio(host.session, identity)
        assert audio.stem == hashlib.sha256(raw).hexdigest()
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
        assert request(host, 'PATCH', f'/api/lines/{identity}/favorite', b'{"favorite":true}', headers=headers(host))[0] == 200
    finally: host.close()
    # Startup only restores validated local state. It never replans/downloads.
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        until = time.monotonic() + 3
        while host.session.index is None and time.monotonic() < until:
            host.snapshot(); time.sleep(.01)
        assert host.session.index.ready and provider.downloads == 1
        assert host.session.history.get(identity).favorite
        assert request(host, 'GET', f'/api/lines/{identity}/audio', headers={'Range': 'bytes=0-43'}) == (206, raw[:44])
        status, value = action(host, 'DELETE', '/zzz/data', {'revision': game(host)['revision']})
        assert status == 200 and value['freed_bytes'] > 0 and value['game']['retained_bytes'] == len(raw)
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
        assert not host.session.running and host.session.index is None
    finally: host.close()
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        assert host.session.index is None and host.session.history.get(identity).favorite
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
        assert provider.downloads == 1
    finally: host.close()


def test_text_http_download_captures_official_voice_intent_without_any_decoder(account_host, tmp_path):
    host = account_host; register(host, 'first')
    provider = LocalProvider(LocalVoice(b'never used'))
    host.game_data.providers['zzz'] = provider
    install(host, mode='text')
    generation = host.session.start()
    host.session.observe(generation, 1, [TEXT], now=1)
    value = host.session.observe(generation, 2, [TEXT], now=1.1)[0]
    assert value['audio_omitted_by_request'] and value['voice_status'] == 'voiced'
    assert not value['has_audio'] and provider.voice.calls == 0
    assert host.session.recordings.lines('zzz') == []


def test_old_owner_pinned_before_service_entry_cannot_adopt_new_profile(account_host, monkeypatch):
    host = account_host; first = register(host, 'first')
    host.game_data.providers['zzz'] = LocalProvider(LocalVoice(b'never used'))
    original, old = host.game_data.plan, headers(host)
    def after_pin(*args, **kwargs):
        register(host, 'second')
        return original(*args, **kwargs)
    monkeypatch.setattr(host.game_data, 'plan', after_pin)
    status, value = request(host, 'POST', '/api/game-data/zzz/plan', json.dumps(REQUEST).encode(), headers=old)
    assert status == 409 and value['code'] == 'game_data_owner_changed'
    assert not host.game_data.plans and game(host)['installed_bytes'] == 0
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=account_headers(host))[0] == 200
    assert request(host, 'GET', '/api/game-data', headers=old)[0] == 409
    assert game(host)['installed_bytes'] == 0


def test_delayed_plan_cannot_publish_after_a_b_a_and_other_account_stays_responsive(account_host):
    host = account_host; first = register(host, 'first')
    provider = LocalProvider(LocalVoice(b'never used')); host.game_data.providers['zzz'] = provider
    entered, release = threading.Event(), threading.Event(); plan = provider.plan
    def delayed(*args):
        entered.set(); assert release.wait(3)
        return plan(*args)
    provider.plan = delayed; result = []; old = headers(host)
    worker = threading.Thread(target=lambda: result.append(request(host, 'POST', '/api/game-data/zzz/plan',
        json.dumps(REQUEST).encode(), headers=old)))
    worker.start(); assert entered.wait(2)
    try:
        register(host, 'second')
        assert game(host)['installed_bytes'] == 0
        assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=account_headers(host))[0] == 200
    finally: release.set(); worker.join(3)
    assert not worker.is_alive() and result[0][0] == 409
    assert not host.game_data.plans and game(host)['installed_bytes'] == 0
