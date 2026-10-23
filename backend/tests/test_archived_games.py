from pathlib import Path

import pytest

from backend.game_assets import ARCHIVED_GAMES, LOCAL_GAMES
from backend.game_paths import GAMES, discover_install, validate_install
from backend.games import GAME_PROFILES, ordered_profiles
from backend.lexirise import GAME_TITLES, LexiriseError, LexiriseService
from backend.models import AppSettings, CaptureRegion
from backend.windows import WindowInfo, find_active_game_window


@pytest.mark.parametrize('game', ['honkai3', 'hito'])
def test_archived_game_has_no_active_entry_points(tmp_path, monkeypatch, game):
    assert game in ARCHIVED_GAMES
    for registry in (GAMES, LOCAL_GAMES, GAME_PROFILES, GAME_TITLES):
        assert game not in registry
    assert all(p.id != game for p in ordered_profiles(game))
    with pytest.raises(ValueError, match='Unsupported game'):
        discover_install(game)
    with pytest.raises(ValueError, match='Unsupported game'):
        validate_install(game, tmp_path)
    monkeypatch.setattr('backend.windows.list_visible_windows', lambda: [
        WindowInfo(1, 'Honkai Impact 3rd', 'BH3.exe', (0, 0, 1920, 1080))])
    assert find_active_game_window(AppSettings()) is None
    service = LexiriseService(tmp_path / 'account', api_key='fixture')
    with pytest.raises(LexiriseError, match='supported game'):
        service.configure_game_deck(game)


@pytest.mark.parametrize('game', ['honkai3', 'hito'])
def test_retired_preference_preserves_unrelated_calibration(game):
    region = CaptureRegion(left=.2, top=.5, width=.6, height=.3)
    settings = AppSettings.model_validate({'preferred_game': game, 'region': region,
                                           'stable_frames': 4, 'auto_start': False})
    assert settings.preferred_game == 'auto'
    assert settings.region == region and settings.stable_frames == 4
    assert not settings.auto_start


def test_archived_game_is_absent_from_ui_and_picker():
    root = Path(__file__).resolve().parents[2]
    for name in ('app/companion.tsx', 'app/toolkit-setup.tsx', 'scripts/select-game-folders.ps1', 'public/mobile-capture/index.html'):
        assert 'Honkai Impact 3rd' not in (root / name).read_text(encoding='utf-8')
