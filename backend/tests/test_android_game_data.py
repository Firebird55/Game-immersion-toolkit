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


def test_offline_activation_uses_installed_revision_and_same_source_keeps_receiver_generation(account_host):
    host = account_host; register(host, 'first')
    provider = LocalProvider(LocalVoice(b'never used')); host.game_data.providers['zzz'] = provider
    install(host, mode='text')
    generation = host.session.start()
    provider.revision = 'authored-two'
    assert action(host, 'POST', '/zzz/plan', {**REQUEST, 'content_mode': 'text'})[0] == 200
    row = game(host)
    assert row['revision'] == 'authored-two' and row['installed_revision'] == 'authored-one'
    assert row['can_activate']
    assert action(host, 'POST', '/zzz/activate', {'revision': row['revision']})[0] == 409
    assert action(host, 'POST', '/zzz/activate', {'revision': row['installed_revision']})[0] == 200
    assert host.session.running and host.session.generation == generation
    assert provider.downloads == 1 and provider.voice.calls == 0


def test_newer_explicit_selection_fences_delayed_old_restore(account_host):
    host = account_host; register(host, 'first')
    provider = LocalProvider(LocalVoice(b'never used')); host.game_data.providers['zzz'] = provider
    install(host, mode='text')
    entered, release = threading.Event(), threading.Event(); restore = provider.restore
    calls = [0]
    def delayed(*args):
        calls[0] += 1
        if calls[0] == 1:
            entered.set(); assert release.wait(3)
        return restore(*args)
    provider.restore = delayed; result = []
    worker = threading.Thread(target=lambda: result.append(action(host, 'POST', '/zzz/activate', {'revision': 'authored-one'})))
    worker.start(); assert entered.wait(2)
    try:
        assert action(host, 'POST', '/zzz/activate', {'revision': 'authored-one'})[0] == 200
        generation = host.session.generation
    finally: release.set(); worker.join(3)
    assert not worker.is_alive() and result[0][0] == 409
    assert host.session.generation == generation


def test_late_update_finishes_cache_without_stealing_selected_source_across_restart(tmp_path):
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    provider = LocalProvider(LocalVoice(b'never used'))
    root = tmp_path / 'application'
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        install(host, mode='text')
        original = host.session.direct_descriptor.copy()
        provider.revision = 'authored-two'; provider.gate = threading.Event(); provider.started.clear()
        status, value = action(host, 'POST', '/zzz/plan', {**REQUEST, 'content_mode': 'text'})
        assert status == 200
        row = value['game']
        assert action(host, 'POST', '/zzz/download', {'plan_id': row['plan_id'], 'revision': row['revision']})[0] == 202
        assert provider.started.wait(2)
        assert action(host, 'POST', '/zzz/activate', {'revision': 'authored-one'})[0] == 200
        provider.gate.set(); assert finished(host)['job']['status'] == 'complete'
        assert game(host)['installed_revision'] == 'authored-two'
        assert host.session.direct_descriptor == original
    finally:
        if provider.gate: provider.gate.set()
        host.close()
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        until = time.monotonic() + 3
        while host.session.direct_descriptor is None and time.monotonic() < until:
            host.snapshot(); time.sleep(.01)
        assert host.session.direct_descriptor == original
        assert action(host, 'POST', '/zzz/activate', {'revision': 'authored-two'})[0] == 200
        assert host.session.direct_descriptor['revision'] == 'authored-two'
        assert provider.downloads == 2
    finally: host.close()


def test_fresh_host_resumes_interrupted_original_from_managed_bytes_without_capture_or_download(tmp_path):
    fixture_library(tmp_path / 'authored')
    raw = (tmp_path / 'authored/tone.wav').read_bytes()
    voice = LocalVoice(raw); voice.release = threading.Event(); provider = LocalProvider(voice)
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    root = tmp_path / 'application'
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    install(host)
    generation = host.session.start()
    host.session.observe(generation, 1, [TEXT], now=1)
    identity = host.session.observe(generation, 2, [TEXT], now=1.1)[0]['id']
    assert voice.entered.wait(2)
    previous = host.session
    host.close(); voice.release.set()
    until = time.monotonic() + 3
    while previous.recording_jobs and time.monotonic() < until: time.sleep(.01)
    assert not previous.history.get(identity).has_audio
    # No reference to the previous provider's original bytes is required.
    fresh = LocalProvider(LocalVoice(b''))
    host = AndroidHost(root, frontend, game_data_providers={'zzz': fresh})
    try:
        until = time.monotonic() + 3
        while not host.session.history.get(identity).has_audio and time.monotonic() < until:
            host.snapshot(); time.sleep(.01)
        assert host.session.history.get(identity).has_audio
        assert not host.session.running and host.receiver_owner is None
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
        assert fresh.voice.calls == 1 and fresh.downloads == 0
    finally: host.close()


def test_delete_preservation_blocks_new_capture_and_snapshot_decode_until_safe_commit(tmp_path):
    fixture_library(tmp_path / 'authored')
    raw = (tmp_path / 'authored/tone.wav').read_bytes()
    voice = LocalVoice(raw); voice.release = threading.Event(); provider = LocalProvider(voice)
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    host = AndroidHost(tmp_path / 'application', frontend, game_data_providers={'zzz': provider})
    result = []; worker = None
    try:
        install(host)
        generation = host.session.start()
        host.session.observe(generation, 1, [TEXT], now=1)
        identity = host.session.observe(generation, 2, [TEXT], now=1.1)[0]['id']
        assert voice.entered.wait(2); host.session.stop(); voice.release.set()
        until = time.monotonic() + 3
        while host.session.recording_jobs and time.monotonic() < until: time.sleep(.01)
        assert not host.session.history.get(identity).has_audio
        voice.entered.clear(); voice.release = threading.Event()
        revision = game(host)['revision']
        worker = threading.Thread(target=lambda: result.append(action(host, 'DELETE', '/zzz/data', {'revision': revision})))
        worker.start(); assert voice.entered.wait(2)
        status, value = request(host, 'POST', '/api/capture/start', headers=headers(host))
        assert status == 409 and value['code'] == 'game_data_busy'
        for _ in range(3): host.snapshot()
        assert host.session.source_transition and not host.session.recording_jobs
        voice.release.set(); worker.join(3)
        assert not worker.is_alive() and result[0][0] == 200
        assert host.session.index is None and not host.session.source_transition
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
    finally:
        voice.release.set()
        if worker: worker.join(3)
        host.close()


def test_unexpected_native_decoder_failure_is_bounded_until_explicit_retry(tmp_path):
    fixture_library(tmp_path / 'authored'); raw = (tmp_path / 'authored/tone.wav').read_bytes()
    voice = LocalVoice(raw); provider = LocalProvider(voice)
    def fail(*_, **__):
        voice.calls += 1
        raise RuntimeError('Authored native bridge failure; never expose provider diagnostics')
    voice.resolve = fail
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    host = AndroidHost(tmp_path / 'application', frontend, game_data_providers={'zzz': provider})
    try:
        install(host)
        generation = host.session.start()
        host.session.observe(generation, 1, [TEXT], now=1)
        identity = host.session.observe(generation, 2, [TEXT], now=1.1)[0]['id']
        until = time.monotonic() + 3
        while identity not in host.session.recording_errors and time.monotonic() < until: time.sleep(.01)
        for _ in range(5):
            line = host.snapshot()['lines'][0]
            assert line['original_audio_expected'] and not line['audio_pending'] and not line['has_audio']
            assert 'provider diagnostics' not in json.dumps(line)
        assert voice.calls == 1
    finally: host.close()


def test_old_context_stamp_and_actual_wav_reopen_without_rehashing_saved_pointer(tmp_path):
    from backend.models import TextMatch
    fixture_library(tmp_path / 'authored'); raw = (tmp_path / 'authored/tone.wav').read_bytes()
    provider = LocalProvider(LocalVoice(raw))
    frontend = tmp_path / 'reader'; frontend.mkdir(); (frontend / 'index.html').write_text('<head></head>')
    root = tmp_path / 'application'
    host = AndroidHost(root, frontend, game_data_providers={'zzz': provider})
    try:
        install(host)
        # Recreate the genuine old stamp format: optional publisher fields did
        # not exist in either JSON context or the complete TranscriptLine DTO.
        old = host.session.history.add(TextMatch(text_id='authored:old', game='zzz',
            english=TEXT, chinese='沿河走过桥。', source_text=TEXT, source_ocr=TEXT,
            source_locale='en', source_language='en', audio_locale='en', score=100, kind='exact', voice_status='voiced'),
            host.session.session_id)
        old_dto = old.model_dump(mode='json', exclude={'favorite', 'has_audio', 'voiced', 'audio_source', 'audio_pending',
            'publisher_generation', 'publisher_request_sha256', 'publisher_occurrence_sha256'})
        old_stamp = hashlib.sha256(json.dumps(old_dto, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        row = host.session.index._records[0]
        host.session.recordings.register(old.id, host.session.direct_descriptor, row, line_stamp=old_stamp)
        path = host.session.recordings.materialize(old.id, host.session.original_source_for)
        host.session.history.update_audio(old.id, 'official-retained/' + path.name, True)
        host.session.history.set_favorite(old.id, True)
        pointer = host.session.recordings.root / 'lines' / (str(old.id) + '.json')
        original_pointer = pointer.read_bytes()
    finally: host.close()
    host = AndroidHost(root, frontend, game_data_providers={'zzz': LocalProvider(LocalVoice(b''))})
    try:
        line = host.session.history.get(old.id)
        assert line.favorite
        for name in ('publisher_generation', 'publisher_request_sha256', 'publisher_occurrence_sha256'):
            assert getattr(line, name, None) is None
        assert host.session._recording_stamp(line) == old_stamp
        assert request(host, 'GET', f'/api/lines/{old.id}/audio')[1] == raw
        assert pointer.read_bytes() == original_pointer  # No blind rehash/adoption.
        # Unknown older pointer formats never become trusted by reopening.
        pointer.write_text(json.dumps({'reference': json.loads(original_pointer)['reference']}))
        assert request(host, 'GET', f'/api/lines/{old.id}/audio')[0] == 404
    finally: host.close()
