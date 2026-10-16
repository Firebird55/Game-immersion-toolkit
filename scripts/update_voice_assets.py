"""Refresh installed story, sidequest, event, and comic voice mappings.

The game directory is read-only. Generated links stay in work/ and the atomic
runtime manifest stays in data/voice-assets.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

from backend.agent_library import atomic_json
from backend.textmaps import localized_variants


ONGOING_TEXT_ID = "PMNJCMFLJIL"
ONGOING_FEMALE_VOICE = "DGFCDOGFFGP"
ONGOING_MALE_VOICE = "EODLJIEIIGJ"


def comic_voice_links(links: list[dict], english: dict[str, str]) -> list[dict]:
    result = []
    for link in links:
        variants = dict(re.findall(r"\{([MF])#([^{}]+)\}", link["source"]))
        if not variants:
            result.append(link)
            continue
        translations = dict(re.findall(r"\{([MF])#([^{}]+)\}", english.get(link["text_id"], "")))
        for gender, source in variants.items():
            if gender in translations:
                result.append({**link, "source": source, "english": translations[gender]})
    return result


def ongoing_voice_links(config: dict, english: dict[str, str]) -> list[dict[str, str]]:
    """Link floating gameplay subtitles to every configured speaker asset.

    ZZZ stores these separately from GalGame/Comic performances. The two voice
    fields are normally female/male protagonist variants, but also contain NPC,
    companion, and agent sources, so no speaker allowlist is used.
    """
    rows = next((value for value in config.values() if isinstance(value, list)), [])
    links: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_id = str(row.get(ONGOING_TEXT_ID, "")).strip()
        if "ongoinglevel" not in text_id.casefold() or text_id not in english:
            continue
        variants = localized_variants(english[text_id])
        male = str(row.get(ONGOING_MALE_VOICE, "")).strip()
        female = str(row.get(ONGOING_FEMALE_VOICE, "")).strip()
        if male:
            links.append({"source": male, "text_id": text_id, "english": variants[0]})
        if female:
            variant = variants[1] if len(variants) > 1 else variants[0]
            links.append({"source": female, "text_id": text_id, "english": variant})
    return links


def merged_english_maps(root: Path) -> dict[str, str]:
    from backend.textmaps import TextMapIndex
    directory = TextMapIndex(root / "data/textmaps").active_directory()
    result: dict[str, str] = {}
    for name in ("en_base.json", "en_overwrite.json"):
        result.update(json.loads((directory / name).read_text(encoding="utf-8-sig")))
    return result


def discover_game_data(root: Path) -> Path | None:
    # Prefer the actual running game. The app may later be copied to a PC
    # where ZZZ is installed on a different drive from Proxy Transcript.
    try:
        from backend.config import SettingsStore
        from backend.windows import installed_zzz_game_data_directory
        import os
        local = Path(os.environ.get("LOCALAPPDATA", root / "data")) / "Proxy Transcript/settings.json"
        live = installed_zzz_game_data_directory(SettingsStore(local, legacy_path=root / "data/settings.json").get())
        if live:
            return live
    except (OSError, ValueError):
        pass

    # The portable app and game may move together to another drive letter.
    def available(path: Path) -> Path | None:
        candidates = [path]
        if path.drive and path.drive.casefold() != root.drive.casefold():
            candidates.insert(0, Path(root.anchor, *path.parts[1:]))
        return next((item for item in candidates if item.is_dir()), None)

    library = root / "data/agent-voices/library.json"
    if library.exists():
        try:
            candidate = Path(json.loads(library.read_text(encoding="utf-8"))["game_data"])
            found = available(candidate)
            if found:
                return found
        except (OSError, ValueError, KeyError):
            pass
    manifest = root / "data/voice-assets/manifest.json"
    if manifest.exists():
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
            package = Path(next(iter(entries.values()))["package"])
            candidate = next(parent for parent in package.parents if parent.name.endswith("_Data"))
            return available(candidate)
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
    code = Path(__file__).resolve().parents[1]
    root = Path(os.environ.get("PROXY_TRANSCRIPT_PROJECT_ROOT", code))
    tools = root / "work/voice-assets"
    template = tools / "PerformTemplateTb.json"
    prefixes = tools / "VoiceData.json"
    decoder = tools / "vgmstream"
    reader = tools / "galgame-perform.ts"
    ongoing_config = tools / "OngoingTipsConfigTemplateTb.json"
    state_path = root / "data/voice-assets/full-index-state.json"
    required = [template, prefixes, reader, ongoing_config, decoder / "vgmstream-cli.exe"]
    game_data = discover_game_data(root)
    if game_data is None or not all(path.exists() for path in required) or not shutil.which("node"):
        print("Full voice refresh skipped; installed game files or indexing tools are unavailable. The last local manifest remains active.")
        return

    from backend.textmaps import TextMapIndex
    maps = TextMapIndex(root / "data/textmaps").active_directory()
    sources = [*required, *(maps / name for name in ("en_base.json", "en_overwrite.json"))]
    current = inventory(game_data, sources)
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    manifest = root / "data/voice-assets/manifest.json"
    if previous.get("version") == 5 and previous.get("inventory") == current and manifest.exists():
        print("Full local voice manifest is already current.")
        return

    options = {
        "cwd": code,
        "check": True,
        "timeout": 600,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    link_files = []
    for category in ("galgame", "comic"):
        output_name = f"scene-links-{category}.json"
        subprocess.run([
            "node", str(code / "scripts/extract_voice_links.mjs"),
            str(game_data), str(tools), category, output_name,
        ], **options)
        link_files.append(tools / output_name)
    combined_links = []
    seen_links = set()
    english = merged_english_maps(root)
    for link_file in link_files:
        links = json.loads(link_file.read_text(encoding="utf-8"))
        if "comic" in link_file.stem:
            links = comic_voice_links(links, english)
        for link in links:
            key = (link["source"].casefold(), link["text_id"], link.get("english"))
            if key not in seen_links:
                seen_links.add(key)
                combined_links.append(link)
    ongoing = ongoing_voice_links(
        json.loads(ongoing_config.read_text(encoding="utf-8")),
        english,
    )
    for link in ongoing:
        key = (link["source"].casefold(), link["text_id"], link["english"])
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
    atomic_json(state_path, {"version": 5, "inventory": inventory(game_data, sources)})
    total = len(json.loads(manifest.read_text(encoding="utf-8"))["entries"])
    print(f"Full local Mandarin voice manifest ready: {total:,} exact lines.")


if __name__ == "__main__":
    main()
