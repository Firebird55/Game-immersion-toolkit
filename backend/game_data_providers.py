"""Register maintained, packaged publishers; never load downloaded provider code.

An absent or unsupported reader stays unavailable in the shared game's status.
An available metadata stage still has to pass the service's plan/source checks;
registration alone establishes neither full preparation nor audio readiness.
"""
from importlib import import_module
import logging


PROVIDER_MODULES = {
    'zzz': '.zzz_game_data',
    'genshin': '.genshin_game_data',
    'starrail': '.starrail_game_data',
    'endfield': '.endfield_game_data',
    'wuwa': '.wuwa_game_data',
    'nte': '.nte_game_data',
    'reverse1999': '.reverse1999_game_data',
    'infinitynikki': '.infinitynikki_game_data',
}


def create_game_data_providers(*, platform, native=None):
    if platform not in {'android', 'windows', 'linux', 'macos'}:
        raise ValueError('A supported native host platform is required')
    providers = {}
    for game, name in PROVIDER_MODULES.items():
        try:
            module = import_module(name, __package__)
        except ImportError as error:
            if not isinstance(error, ModuleNotFoundError) or error.name != __package__ + name:
                # Do not break the other games or expose private exception
                # strings/paths through a public status response.
                logging.getLogger(__name__).warning('Original-data reader unavailable for %s: runtime import missing', game)
            continue
        provider = module.create_provider(platform=platform, native=native)
        if provider is None:
            continue
        if any(not callable(getattr(provider, method, None)) for method in ('plan', 'download', 'restore')):
            raise TypeError('The packaged game-data provider has an invalid contract')
        providers[game] = provider
    return providers
