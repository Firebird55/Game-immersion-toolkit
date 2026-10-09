"""Per-PC game locations. Game assets are read in place, never redistributed."""
from __future__ import annotations

import json
import os
from pathlib import Path

GAMES = ("zzz", "pragmata", "hito", "cyberpunk", "wuwa", "witcher3")


def settings_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Proxy Transcript/game-paths.json"


def validate_install(game: str, path: Path) -> Path:
    if game not in GAMES:
        raise ValueError("Unsupported game")
    root = path.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Choose the installed game folder, not an archive or executable")
    if game == "zzz" and root.name == "ZenlessZoneZero_Data":
        root = root.parent
    valid = {
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
    values = load_paths()
    values[game] = str(root)
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(target)
    return root


def discover_install(game: str) -> Path | None:
    configured = configured_install(game)
    if configured:
        return configured
    names = {"cyberpunk": "Cyberpunk 2077", "wuwa": "Wuthering Waves", "witcher3": "The Witcher 3"}
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
        candidates.extend(path / "steamapps/common" / names[game] for path in libraries)
    except (ImportError, OSError):
        pass
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.extend(Path(f"{letter}:/") / suffix / names[game] for suffix in
                          ("SteamLibrary/steamapps/common", "Program Files (x86)/Steam/steamapps/common"))
    for path in candidates:
        try:
            return validate_install(game, path)
        except (OSError, ValueError):
            continue
    return None
