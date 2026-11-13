"""Publisher editions selected by the user for installation-free preparation."""
from pathlib import Path

from .game_tools import _atomic_file


REGIONS = {'global': 'Global', 'cn': 'Mainland China'}
REGIONAL_GAMES = {'endfield'}


def selected_region(tools: Path, game: str) -> str:
    if game not in REGIONAL_GAMES:
        raise ValueError('Publisher edition selection is unavailable for this game.')
    try:
        with (tools / 'publisher-region').open('rb') as stream:
            region = stream.read(16).decode('ascii')
    except FileNotFoundError:
        return 'global'
    if region not in REGIONS:
        raise ValueError('Choose a supported publisher edition in Setup.')
    return region


def select_region(tools: Path, game: str, region: str) -> None:
    if game not in REGIONAL_GAMES or region not in REGIONS:
        raise ValueError('Unsupported publisher edition.')
    _atomic_file(tools / 'publisher-region', region.encode('ascii'))
