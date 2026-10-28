from pathlib import Path
import pytest
from backend.game_paths import clear_install, configured_install, discover_install, load_paths, save_install, validate_install
from backend.steam_games import STEAM_GAMES


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


def make_game(tmp_path, game):
    root = tmp_path / game
    root.mkdir()
    if game in STEAM_GAMES:
        spec = STEAM_GAMES[game]
        (root / spec.executable).touch()
        for name in spec.markers:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch() if path.suffix else path.mkdir(exist_ok=True)
    elif game == "hito":
        (root / "resources").mkdir()
        (root / "resources/app.asar").write_bytes(b"local game")
    elif game == "zzz":
        (root / "ZenlessZoneZero_Data/StreamingAssets").mkdir(parents=True)
    elif game == "cyberpunk":
        (root / "bin/x64").mkdir(parents=True)
        (root / "bin/x64/Cyberpunk2077.exe").touch()
        (root / "archive/pc/content").mkdir(parents=True)
        (root / "archive/pc/content/lang_en_text.archive").touch()
    elif game == "wuwa":
        (root / "Client/Binaries/Win64").mkdir(parents=True)
        (root / "Client/Binaries/Win64/Client-Win64-Shipping.exe").touch()
        (root / "Client/Content/Paks").mkdir(parents=True)
        (root / "Client/Content/Paks/pakchunk0.pak").touch()
    elif game == "witcher3":
        (root / "bin/x64_dx12").mkdir(parents=True)
        (root / "bin/x64_dx12/witcher3.exe").touch()
        (root / "content/content0").mkdir(parents=True)
        (root / "content/content0/en.w3strings").touch()
    elif game == "nte":
        (root / "Client/WindowsNoEditor/HT/Binaries/Win64").mkdir(parents=True)
        (root / "Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe").touch()
        (root / "Client/WindowsNoEditor/HT/Content/Paks").mkdir(parents=True)
        (root / "Client/WindowsNoEditor/HT/Content/Paks/pakchunk0.pak").touch()
    elif game == "heavyrain":
        (root / "HeavyRain.exe").touch()
        (root / "Resources/GameData").mkdir(parents=True)
        (root / "Resources/BigFile_WIN.idx").touch()
        (root / "Resources/GameData/GameData_WIN.idx").touch()
    elif game in {"riseofthetombraider", "shadowofthetombraider"}:
        (root / ("ROTTR.exe" if game == "riseofthetombraider" else "SOTTR.exe")).touch()
        (root / "bigfile.000.tiger").touch()
    elif game == "honkai3":
        (root / "BH3.exe").touch()
        (root / "BH3_Data/StreamingAssets").mkdir(parents=True)
    else:
        (root / "PRAGMATA.exe").touch()
        (root / "re_chunk_000.pak").touch()
    return root


@pytest.mark.parametrize("game", ["zzz", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte", "heavyrain", "riseofthetombraider", "shadowofthetombraider", *STEAM_GAMES])
def test_saved_game_locations_are_validated_and_per_pc(tmp_path, game):
    root = make_game(tmp_path, game)
    assert save_install(game, root) == root.resolve()
    assert configured_install(game) == root.resolve()
    assert load_paths()[game] == str(root.resolve())


def test_zzz_data_folder_is_normalized_and_other_games_preserved(tmp_path):
    pragmata = make_game(tmp_path, "pragmata")
    zzz = make_game(tmp_path, "zzz")
    save_install("pragmata", pragmata)
    save_install("zzz", zzz / "ZenlessZoneZero_Data")
    assert configured_install("zzz") == zzz.resolve()
    assert configured_install("pragmata") == pragmata.resolve()


def test_bad_or_missing_install_does_not_overwrite_existing_location(tmp_path):
    root = make_game(tmp_path, "pragmata")
    save_install("pragmata", root)
    with pytest.raises(ValueError):
        save_install("pragmata", tmp_path)
    assert configured_install("pragmata") == root.resolve()
    (root / "PRAGMATA.exe").unlink()
    assert configured_install("pragmata") is None


def test_configured_zzz_is_used_when_game_is_closed(tmp_path, monkeypatch):
    from backend.windows import installed_zzz_game_data_directory
    from backend.models import AppSettings
    root = make_game(tmp_path, "zzz")
    save_install("zzz", root)
    monkeypatch.setattr("backend.windows.game_data_directory", lambda settings: None)
    assert installed_zzz_game_data_directory(AppSettings()) == root / "ZenlessZoneZero_Data"


def test_configured_pragmata_is_used_outside_steam(tmp_path):
    from scripts.index_pragmata_assets import find_install
    root = make_game(tmp_path, "pragmata")
    save_install("pragmata", root)
    assert find_install() == root.resolve()


def test_use_automatic_detection_removes_only_selected_game(tmp_path):
    save_install("pragmata", make_game(tmp_path, "pragmata"))
    save_install("zzz", make_game(tmp_path, "zzz"))
    clear_install("zzz")
    assert "zzz" not in load_paths()
    assert configured_install("pragmata") is not None


def test_wuthering_client_folder_is_normalized(tmp_path):
    root = make_game(tmp_path, "wuwa")
    assert validate_install("wuwa", root / "Client") == root


def test_heavy_rain_resources_folder_requires_the_actual_game_and_story_archive(tmp_path):
    root = make_game(tmp_path, 'heavyrain')
    assert validate_install('heavyrain', root / 'Resources') == root
    (root / 'Resources/GameData/GameData_WIN.idx').unlink()
    with pytest.raises(ValueError, match='Required game files'):
        validate_install('heavyrain', root)


@pytest.mark.parametrize("game", ["zzz", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte"])
def test_auto_discovery_accepts_all_supported_games(monkeypatch, game):
    def absent(*_args):
        raise FileNotFoundError("synthetic absent game")
    monkeypatch.setattr("backend.game_paths.validate_install", absent)
    assert discover_install(game) is None


@pytest.mark.parametrize("subfolder", ["Client", "Client/WindowsNoEditor", "Client/WindowsNoEditor/HT"])
def test_nte_nested_client_folders_are_normalized(tmp_path, subfolder):
    root = make_game(tmp_path, "nte")
    assert validate_install("nte", root / subfolder) == root


def test_archived_honkai_is_rejected_even_with_valid_files(tmp_path):
    root = make_game(tmp_path, "honkai3")
    with pytest.raises(ValueError, match="Unsupported game"):
        validate_install("honkai3", root / "BH3_Data")
    (tmp_path / "StarRail.exe").touch()
    with pytest.raises(ValueError):
        validate_install("honkai3", tmp_path)


def test_saving_an_active_game_preserves_archived_local_locations(tmp_path):
    import json
    from backend.game_paths import settings_path
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'hito': 'retained-local-location'}), encoding='utf-8')
    save_install('zzz', make_game(tmp_path, 'zzz'))
    assert 'hito' not in load_paths()
    assert json.loads(path.read_text())['hito'] == 'retained-local-location'
