from pathlib import Path
import pytest
from backend.game_paths import clear_install, configured_install, discover_install, load_paths, save_install, validate_install


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


def make_game(tmp_path, game):
    root = tmp_path / game
    root.mkdir()
    if game == "hito":
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
    elif game == "honkai3":
        (root / "BH3.exe").touch()
        (root / "BH3_Data/StreamingAssets").mkdir(parents=True)
    else:
        (root / "PRAGMATA.exe").touch()
        (root / "re_chunk_000.pak").touch()
    return root


@pytest.mark.parametrize("game", ["zzz", "hito", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte", "honkai3"])
def test_saved_game_locations_are_validated_and_per_pc(tmp_path, game):
    root = make_game(tmp_path, game)
    assert save_install(game, root) == root.resolve()
    assert configured_install(game) == root.resolve()
    assert load_paths()[game] == str(root.resolve())


def test_zzz_data_folder_is_normalized_and_other_games_preserved(tmp_path):
    hito = make_game(tmp_path, "hito")
    zzz = make_game(tmp_path, "zzz")
    save_install("hito", hito)
    save_install("zzz", zzz / "ZenlessZoneZero_Data")
    assert configured_install("zzz") == zzz.resolve()
    assert configured_install("hito") == hito.resolve()


def test_bad_or_missing_install_does_not_overwrite_existing_location(tmp_path):
    root = make_game(tmp_path, "hito")
    save_install("hito", root)
    with pytest.raises(ValueError):
        save_install("hito", tmp_path)
    assert configured_install("hito") == root.resolve()
    (root / "resources/app.asar").unlink()
    assert configured_install("hito") is None


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


def test_hito_configured_archive_is_used_without_running_game(tmp_path, monkeypatch):
    from backend.hito import HitoTextIndex
    root = make_game(tmp_path, "hito")
    save_install("hito", root)
    calls = []
    index = HitoTextIndex(tmp_path / "cache")
    monkeypatch.setattr(index, "_ensure_archive", lambda archive: calls.append(archive))
    index.ensure_game_files(None)
    assert calls == [root / "resources/app.asar"]


def test_use_automatic_detection_removes_only_selected_game(tmp_path):
    save_install("hito", make_game(tmp_path, "hito"))
    save_install("zzz", make_game(tmp_path, "zzz"))
    clear_install("zzz")
    assert "zzz" not in load_paths()
    assert configured_install("hito") is not None


def test_wuthering_client_folder_is_normalized(tmp_path):
    root = make_game(tmp_path, "wuwa")
    assert validate_install("wuwa", root / "Client") == root


@pytest.mark.parametrize("game", ["zzz", "hito", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte", "honkai3"])
def test_auto_discovery_accepts_all_supported_games(monkeypatch, game):
    def absent(*_args):
        raise FileNotFoundError("synthetic absent game")
    monkeypatch.setattr("backend.game_paths.validate_install", absent)
    assert discover_install(game) is None


@pytest.mark.parametrize("subfolder", ["Client", "Client/WindowsNoEditor", "Client/WindowsNoEditor/HT"])
def test_nte_nested_client_folders_are_normalized(tmp_path, subfolder):
    root = make_game(tmp_path, "nte")
    assert validate_install("nte", root / subfolder) == root


def test_honkai_data_folder_is_normalized_and_star_rail_is_rejected(tmp_path):
    root = make_game(tmp_path, "honkai3")
    assert validate_install("honkai3", root / "BH3_Data") == root
    (tmp_path / "StarRail.exe").touch()
    with pytest.raises(ValueError):
        validate_install("honkai3", tmp_path)
