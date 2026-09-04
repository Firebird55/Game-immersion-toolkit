"""Refresh installed story, sidequest, event, and comic voice mappings.

The game directory is read-only. Generated links stay in work/ and the atomic
runtime manifest stays in data/voice-assets.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from backend.agent_library import atomic_json


def discover_game_data(root: Path) -> Path | None:
    library = root / "data/agent-voices/library.json"
    if library.exists():
        try:
            candidate = Path(json.loads(library.read_text(encoding="utf-8"))["game_data"])
            if candidate.is_dir():
                return candidate
        except (OSError, ValueError, KeyError):
            pass
    manifest = root / "data/voice-assets/manifest.json"
    if manifest.exists():
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
            package = Path(next(iter(entries.values()))["package"])
            return next(parent for parent in package.parents if parent.name.endswith("_Data"))
        except (OSError, ValueError, KeyError, StopIteration):
            pass
    return None


def inventory(game_data: Path, sources: list[Path]) -> dict:
    files = []
    for layer in ("StreamingAssets", "Persistent"):
        audio = game_data / layer / "Audio/Windows/Full/Cn"
        files.extend(audio.glob("*.pck"))
        for name in ("res_version", "res_version_persist"):
            candidate = game_data / layer / name
            if candidate.exists():
                files.append(candidate)
    files.extend(path for path in sources if path.exists())
    return {
        str(path.resolve()): [path.stat().st_size, path.stat().st_mtime_ns]
        for path in sorted(set(files))
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    tools = root / "work/voice-assets"
    template = tools / "PerformTemplateTb.json"
    prefixes = tools / "VoiceData.json"
    decoder = tools / "vgmstream"
    reader = tools / "galgame-perform.ts"
    state_path = root / "data/voice-assets/full-index-state.json"
    required = [template, prefixes, reader, decoder / "vgmstream-cli.exe"]
    game_data = discover_game_data(root)
    if game_data is None or not all(path.exists() for path in required) or not shutil.which("node"):
        print("Full voice refresh skipped; the last complete local manifest remains active.")
        return

    current = inventory(game_data, required)
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    manifest = root / "data/voice-assets/manifest.json"
    if previous.get("version") == 2 and previous.get("inventory") == current and manifest.exists():
        print("Full local voice manifest is already current.")
        return

    options = {
        "cwd": root,
        "check": True,
        "timeout": 600,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    link_files = []
    for category in ("galgame", "comic"):
        output_name = f"scene-links-{category}.json"
        subprocess.run([
            "node", str(root / "scripts/extract_voice_links.mjs"),
            str(game_data), str(tools), category, output_name,
        ], **options)
        link_files.append(tools / output_name)
    combined_links = []
    seen_links = set()
    for link_file in link_files:
        for link in json.loads(link_file.read_text(encoding="utf-8")):
            key = (link["source"].casefold(), link["text_id"])
            if key not in seen_links:
                seen_links.add(key)
                combined_links.append(link)
    combined_path = tools / "scene-links.json"
    atomic_json(combined_path, combined_links)
    subprocess.run([
        sys.executable, "-m", "scripts.index_voice_assets",
        "--game-data", str(game_data),
        "--links", str(tools / "scene-links.json"),
        "--prefixes", str(prefixes),
        "--decoder-dir", str(decoder),
    ], **options)
    atomic_json(state_path, {"version": 2, "inventory": inventory(game_data, required)})
    total = len(json.loads(manifest.read_text(encoding="utf-8"))["entries"])
    print(f"Full local Mandarin voice manifest ready: {total:,} exact lines.")


if __name__ == "__main__":
    main()
