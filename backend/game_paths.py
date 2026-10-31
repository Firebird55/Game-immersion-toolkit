"""Per-PC game locations. Game assets are read in place, never redistributed."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from .steam_games import STEAM_GAMES

GAMES = ("zzz", "pragmata", "cyberpunk", "wuwa", "witcher3", "nte", "beyond", "heavyrain", "starrail", "genshin", "endfield", "riseofthetombraider", "shadowofthetombraider")
GAMES += tuple(STEAM_GAMES)
GAME_NAMES = {"starrail": "Honkai: Star Rail", "genshin": "Genshin Impact", "endfield": "Arknights: Endfield", "zzz": "Zenless Zone Zero", "pragmata": "PRAGMATA", "hito": "Hito's World",
              "cyberpunk": "Cyberpunk 2077", "wuwa": "Wuthering Waves", "witcher3": "The Witcher 3",
              "nte": "Neverness to Everness", "beyond": "BEYOND: Two Souls", "heavyrain": "HEAVY RAIN"}
GAME_NAMES.update(riseofthetombraider="Rise of the Tomb Raider", shadowofthetombraider="Shadow of the Tomb Raider")
GAME_NAMES.update({game: spec.title for game, spec in STEAM_GAMES.items()})
_path_lock = threading.RLock()


def settings_path() -> Path:
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        return layout.settings_root / 'game-paths.json'
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Proxy Transcript/game-paths.json"


def validate_install(game: str, path: Path) -> Path:
    if game not in GAMES:
        raise ValueError("Unsupported game")
    root = path.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Choose the installed game folder, not an archive or executable")
    if game in STEAM_GAMES:
        spec = STEAM_GAMES[game]
        if (root / spec.executable).is_file() and all((root / name).exists() for name in spec.markers):
            return root
        raise ValueError(f"Choose the {spec.title} installation folder containing {spec.executable} and its game data.")
    if game in {'starrail', 'genshin', 'endfield'}:
        folders = {'starrail': ('StarRail_Data',), 'genshin': ('GenshinImpact_Data', 'YuanShen_Data'),
                   'endfield': ('Endfield_Data',)}[game]
        nested = {'starrail': 'games/Star Rail Games', 'genshin': 'games/Genshin Impact game', 'endfield': '.'}[game]
        for candidate in (root, root.parent, root / nested):
            if any((candidate / name).is_dir() for name in folders):
                root = candidate
                break
    if game == "zzz" and root.name == "ZenlessZoneZero_Data":
        root = root.parent
    if game == "wuwa" and root.name == "Client":
        root = root.parent
    if game == "heavyrain" and root.name == "Resources":
        root = root.parent
    if game == "honkai3" and root.name == "BH3_Data":
        root = root.parent
    if game == "nte":
        # Accept the launcher root or the nested Client/WindowsNoEditor/HT
        # folder. Never mistake the launcher alone for a downloaded client.
        for parent in [root, *list(root.parents)[:3]]:
            if (parent / "Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe").is_file():
                root = parent
                break
    valid = {
        "riseofthetombraider": lambda: (root / "ROTTR.exe").is_file() and (root / "bigfile.000.tiger").is_file(),
        "shadowofthetombraider": lambda: (root / "SOTTR.exe").is_file() and (root / "bigfile.000.tiger").is_file(),
        "starrail": lambda: (root / 'StarRail.exe').is_file() and (root / 'StarRail_Data/StreamingAssets').is_dir(),
        "genshin": lambda: any((root / exe).is_file() and (root / data / 'StreamingAssets').is_dir()
            for exe, data in [('GenshinImpact.exe', 'GenshinImpact_Data'), ('YuanShen.exe', 'YuanShen_Data')]),
        "endfield": lambda: (root / 'Endfield.exe').is_file() and (root / 'Endfield_Data/StreamingAssets/VFS').is_dir(),
        "heavyrain": lambda: (root / "HeavyRain.exe").is_file() and (root / "Resources/BigFile_WIN.idx").is_file()
        and (root / "Resources/GameData/GameData_WIN.idx").is_file(),
        "beyond": lambda: (root / "BeyondTwoSouls_Steam.exe").is_file() and (root / "BigFile_PC.idx").is_file(),
        "nte": lambda: (root / "Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe").is_file()
        and any((root / "Client/WindowsNoEditor/HT/Content/Paks").glob("*.pak")),
        "honkai3": lambda: (root / "BH3.exe").is_file() and (root / "BH3_Data/StreamingAssets").is_dir(),
        "witcher3": lambda: any((root / folder / "witcher3.exe").is_file() for folder in ("bin/x64", "bin/x64_dx12"))
        and any((root / "content").glob("*/en.w3strings")),
        "wuwa": lambda: (root / "Client/Binaries/Win64/Client-Win64-Shipping.exe").is_file()
        and any((root / "Client/Content/Paks").glob("pakchunk*.pak")),
        "cyberpunk": lambda: (root / "bin/x64/Cyberpunk2077.exe").is_file()
        and (root / "archive/pc/content/lang_en_text.archive").is_file(),
        "zzz": lambda: (root / "ZenlessZoneZero_Data").is_dir()
        and ((root / "ZenlessZoneZero_Data/StreamingAssets").is_dir()
             or (root / "ZenlessZoneZero_Data/Persistent").is_dir()),
        "hito": lambda: (root / "resources/app.asar").is_file(),
        "pragmata": lambda: (root / "PRAGMATA.exe").is_file()
        and any(root.glob("re_chunk_*.pak*")),
    }[game]()
    if not valid:
        raise ValueError("Required game files were not found in this folder; see INSTALL.md")
    return root


def load_paths() -> dict[str, str]:
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8-sig"))
        return {key: path for key, path in value.items() if key in GAMES and isinstance(path, str)}
    except (OSError, ValueError, AttributeError):
        return {}


def configured_install(game: str) -> Path | None:
    path = load_paths().get(game)
    if path:
        try:
            return validate_install(game, Path(path))
        except (OSError, ValueError):
            pass  # Removed drives/updated installs must not disable automatic discovery.
    return None


def save_install(game: str, path: Path) -> Path:
    root = validate_install(game, path)
    with _path_lock:
        values = load_paths()
        values[game] = str(root)
        _write_paths(values)
    return root


def clear_install(game: str) -> None:
    if game not in GAMES:
        raise ValueError("Unsupported game")
    with _path_lock:
        values = load_paths()
        values.pop(game, None)
        _write_paths(values)


def _write_paths(values: dict[str, str]) -> None:
    target = settings_path()
    # Retiring an adapter must not erase its old local location when another
    # game's selection changes. Archived entries are never enumerated by setup.
    try:
        old = json.loads(target.read_text(encoding="utf-8-sig"))
        for key in ('hito', 'honkai3'):
            if isinstance(old.get(key), str):
                values[key] = old[key]
    except (OSError, ValueError, AttributeError):
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(target)


def discover_install(game: str) -> Path | None:
    if game not in GAMES:
        raise ValueError("Unsupported game")
    configured = configured_install(game)
    if configured:
        return configured
    names = [STEAM_GAMES[game].directory] if game in STEAM_GAMES else [GAME_NAMES[game]]
    if game == "starrail":
        names = ["HonkaiStarRail/games/Star Rail Games", "Star Rail Games", "Honkai Star Rail"]
    elif game == "genshin":
        names = ["GenshinImpact/games/Genshin Impact game", "Genshin Impact game", "Genshin Impact"]
    elif game == "endfield":
        names = ["Arknights Endfield", "Endfield", "Endfield Game"]
    elif game == "beyond":
        names = ["BEYOND Two Souls"]
    elif game == "heavyrain":
        names = ["HEAVY RAIN"]
    elif game == "zzz":
        names = ["Zenless Zone Zero/games/ZenlessZoneZero Game", "Zenless Zone Zero", "ZenlessZoneZero Game"]
    elif game == "honkai3":
        names = ["HonkaiImpact3rd", "Honkai Impact 3rd", "Honkai Impact 3rd Games"]
    candidates = []
    # Respect Steam's registered libraries as well as conventional drive roots.
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
        import re
        libraries = [steam]
        config = steam / "steamapps/libraryfolders.vdf"
        if config.is_file():
            libraries.extend(Path(value.replace("\\\\", "\\")) for value in
                             re.findall(r'"path"\s+"([^"]+)"', config.read_text(encoding="utf-8")))
        if game in STEAM_GAMES:
            for library in libraries:
                try:
                    manifest = library / f'steamapps/appmanifest_{STEAM_GAMES[game].app_id}.acf'
                    match = re.search(r'"installdir"\s+"([^"\\/]+)"', manifest.read_text(encoding='utf-8-sig'))
                    if match and match[1] not in {'.', '..'} and ':' not in match[1]:
                        candidates.append(library / 'steamapps/common' / match[1])
                except OSError:
                    continue
        candidates.extend(path / "steamapps/common" / name for path in libraries for name in names)
    except (ImportError, OSError):
        pass
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.extend(Path(f"{letter}:/") / suffix / name for name in names for suffix in
                          ("SteamLibrary/steamapps/common", "Program Files (x86)/Steam/steamapps/common", "Epic", "Epic Games", "Program Files/Epic Games", "Program Files/HoYoPlay/games"))
    for path in candidates:
        try:
            return validate_install(game, path)
        except (OSError, ValueError):
            continue
    return None
