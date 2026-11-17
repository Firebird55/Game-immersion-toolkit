"""DEBUG fixture admission and real game-data HTTP lifecycle, without ZIP import."""
import hashlib
import time

import pytest

from backend.android_host import AndroidHost
from backend.android_authored_game_data import TEXT, tone
from backend.tests.test_android_game_data import action, game, install
from backend.tests.test_android_host import request
from backend.tests.test_direct_game_session import wait_audio


class DebugNative:
    def assertAuthoredGameData(self):
        pass


@pytest.fixture
def frontend(tmp_path):
    path = tmp_path / 'frontend'
    path.mkdir()
    (path / 'index.html').write_text('<head></head>')
    return path


@pytest.mark.parametrize('root,native', [
    ('toolkit', DebugNative()), ('authored-game-data-ui', None),
    ('authored-game-data-ui', object()),
])
def test_fixture_requires_native_debug_guard_and_separate_root(tmp_path, frontend, root, native):
    with pytest.raises((ValueError, AttributeError)):
        AndroidHost(tmp_path / root, frontend, native, authored_game_data=True)


def test_native_guard_denial_never_starts_fixture(tmp_path, frontend):
    class ReleaseNative:
        def assertAuthoredGameData(self):
            raise ValueError('Not a DEBUG build')
    with pytest.raises(ValueError, match='Not a DEBUG'):
        AndroidHost(tmp_path / 'authored-game-data-ui', frontend, ReleaseNative(), authored_game_data=True)


def test_default_host_does_not_admit_authored_source(tmp_path, frontend):
    host = AndroidHost(tmp_path / 'toolkit', frontend, game_data_providers={})
    try:
        assert host.platform()['authored_game_data_fixture'] is False
        assert host.game_data.providers == {}
    finally:
        host.close()


def test_fixture_text_mode_does_not_generate_or_resolve_audio(tmp_path, frontend, monkeypatch):
    def forbidden():
        raise AssertionError('Text-only preparation touched optional audio')
    monkeypatch.setattr('backend.android_authored_game_data.tone', forbidden)
    host = AndroidHost(tmp_path / 'authored-game-data-ui', frontend, DebugNative(), authored_game_data=True)
    try:
        install(host, mode='text')
        assert host.session.libraries.current() is None
        assert host.session.direct_descriptor is not None
        scope = host.session.start()
        host.session.observe(scope, 1, [TEXT], now=1)
        line = host.session.observe(scope, 2, [TEXT], now=1.1)[0]
        assert line['voice_status'] == 'voiced'
        assert line['audio_omitted_by_request'] and not line['has_audio']
    finally:
        host.close()


def test_direct_fixture_download_restart_delete_preserves_original(tmp_path, frontend):
    root = tmp_path / 'authored-game-data-ui'
    raw = tone()
    host = AndroidHost(root, frontend, DebugNative(), authored_game_data=True)
    try:
        assert host.platform()['authored_game_data_fixture'] is True
        assert game(host)['installed_bytes'] == 0
        install(host)
        assert host.session.libraries.current() is None
        scope = host.session.start()
        host.session.observe(scope, 1, [TEXT], now=1)
        line = host.session.observe(scope, 2, [TEXT], now=1.1)[0]
        identity = line['id']
        assert hashlib.sha256(wait_audio(host.session, identity).read_bytes()).digest() == hashlib.sha256(raw).digest()
        host.session.history.set_favorite(identity, True)
    finally:
        host.close()
    host = AndroidHost(root, frontend, DebugNative(), authored_game_data=True)
    try:
        until = time.monotonic() + 3
        while host.session.index is None and time.monotonic() < until:
            host.snapshot()
            time.sleep(.01)
        assert host.session.index.ready
        assert host.session.history.get(identity).favorite
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
        status, result = action(host, 'DELETE', '/zzz/data', {'revision': game(host)['revision']})
        assert status == 200 and result['freed_bytes'] > 0
        assert result['game']['retained_bytes'] == len(raw)
        assert request(host, 'GET', f'/api/lines/{identity}/audio')[1] == raw
    finally:
        host.close()
