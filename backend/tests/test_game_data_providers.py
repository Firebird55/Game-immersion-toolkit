"""Host isolation matters when a native reader is absent from one platform."""
from types import SimpleNamespace

import pytest

from backend import game_data_providers as registry


def test_missing_game_or_native_dependency_does_not_break_other_packaged_readers(monkeypatch, caplog):
    calls = []
    provider = SimpleNamespace(plan=lambda *a: None, download=lambda *a: None, restore=lambda *a: None)
    native = object()
    def load(name, package):
        calls.append((name, package))
        if name == '.endfield_game_data':
            def factory(**kwargs):
                assert kwargs == {'platform': 'android', 'native': native}
                return provider
            return SimpleNamespace(create_provider=factory)
        if name == '.zzz_game_data':
            raise ImportError('private-runtime-location-never-display')
        raise ModuleNotFoundError(name=package + name)
    monkeypatch.setattr(registry, 'import_module', load)
    assert registry.create_game_data_providers(platform='android', native=native) == {'endfield': provider}
    assert len(calls) == 8
    assert 'private-runtime-location-never-display' not in caplog.text


def test_invalid_host_or_broken_packaged_contract_cannot_become_ready(monkeypatch):
    with pytest.raises(ValueError): registry.create_game_data_providers(platform='untrusted-source-url')
    monkeypatch.setattr(registry, 'import_module', lambda *args: SimpleNamespace(create_provider=lambda **kw: object()))
    with pytest.raises(TypeError): registry.create_game_data_providers(platform='windows')
