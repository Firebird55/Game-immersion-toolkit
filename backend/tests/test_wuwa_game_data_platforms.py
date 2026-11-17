"""The canonical registry must be able to construct Wuwa on every host."""
import pytest

from backend import game_data_providers as registry
from backend import wuwa_game_data as wuwa


@pytest.mark.parametrize('platform', ['windows', 'linux', 'macos', 'android'])
def test_actual_registry_constructs_wuwa_with_the_explicit_host_platform(monkeypatch, platform):
    # Exercise actual registry import/constructor dispatch without requiring
    # unrelated providers or any publisher data/runtime capability.
    monkeypatch.setattr(registry, 'PROVIDER_MODULES', {'wuwa': '.wuwa_game_data'})
    providers = registry.create_game_data_providers(platform=platform, native=object())
    assert set(providers) == {'wuwa'}
    adapter = providers['wuwa']
    assert isinstance(adapter, wuwa.WutheringGameDataProvider)
    assert adapter.platform == platform
    assert all(callable(getattr(adapter, name)) for name in ('plan', 'download', 'restore'))


def test_legacy_direct_desktop_alias_is_retained():
    assert wuwa.create_provider('desktop').platform == 'desktop'


@pytest.mark.parametrize('platform', ['ios', 'unknown'])
def test_unknown_wuwa_host_stays_an_explicit_constructor_error(platform):
    with pytest.raises(ValueError, match='platform'):
        wuwa.create_provider(platform)
