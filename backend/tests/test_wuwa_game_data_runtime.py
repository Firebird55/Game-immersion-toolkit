"""Explicit host capability selection precedes all original source traffic."""
from types import SimpleNamespace

import pytest

from backend import publisher_crypto
from backend import wuwa_game_data as wuwa
from backend.game_data_protocol import GameDataError, GameDataRequest


@pytest.mark.parametrize('platform', ['windows', 'linux', 'macos', 'android'])
def test_explicit_platform_selects_only_its_maintained_crypto_capability(monkeypatch, platform):
    received, accessor_calls = [], []
    marker, result = object(), object()
    def accessor():
        accessor_calls.append(True)
        return marker
    def create(**kwargs):
        received.append(kwargs)
        return result
    monkeypatch.setattr(publisher_crypto, 'create_publisher_crypto', create)
    # An explicitly passed host must not be replaced by the process OS.
    monkeypatch.setattr(wuwa.sys, 'platform', 'unrelated-test-host')
    adapter = wuwa.create_provider(platform, SimpleNamespace(publisherCrypto=accessor))
    assert adapter._crypto() is result
    assert received == ([{'platform': 'android', 'native': marker}] if platform == 'android' else [{'platform': platform}])
    assert accessor_calls == ([True] if platform == 'android' else [])


@pytest.mark.parametrize('host,expected', [('win32','windows'), ('linux','linux'), ('darwin','macos')])
def test_only_legacy_desktop_alias_uses_current_process_platform(monkeypatch, host, expected):
    received = []
    monkeypatch.setattr(wuwa.sys, 'platform', host)
    monkeypatch.setattr(publisher_crypto, 'create_publisher_crypto', lambda **kwargs: received.append(kwargs))
    wuwa.create_provider('desktop')._crypto()
    assert received == [{'platform': expected}]


@pytest.mark.parametrize('kind', ['absent', 'missing-accessor', 'wrong-object', 'loader-failure'])
def test_unavailable_android_capability_is_typed_before_metadata_or_assets(tmp_path, monkeypatch, kind):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('No publisher request without a verified runtime')
    monkeypatch.setattr(wuwa, 'PublisherTransport', forbidden)
    def failed(): raise OSError('Authored native load failure')
    native = {'absent': None, 'missing-accessor': object(),
              'wrong-object': SimpleNamespace(publisherCrypto=lambda: object()),
              'loader-failure': SimpleNamespace(publisherCrypto=failed)}[kind]
    ctx = SimpleNamespace(stage_handle=None, cache_directory=tmp_path, check=lambda: None)
    with pytest.raises(GameDataError) as error:
        wuwa.create_provider('android', native).plan(GameDataRequest('global','ja'), ctx)
    assert error.value.code == 'game_runtime_unavailable'
    assert not calls and not list(tmp_path.iterdir())
