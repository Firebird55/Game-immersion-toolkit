"""Build a local exact-voice manifest from extracted GalScript links.

Run with python -m scripts.index_voice_assets --help. All game files are read-only.
"""
import argparse
import json
import os
import shutil
from pathlib import Path

from backend.voice_assets import index_mandarin, merge_valid_manifest_entries, resolve_links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", type=Path, required=True)
    parser.add_argument("--links", type=Path, required=True)
    parser.add_argument("--prefixes", type=Path, required=True)
    parser.add_argument("--decoder-dir", type=Path, required=True)
    args = parser.parse_args()
    project = Path(os.environ.get("PROXY_TRANSCRIPT_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
    output = project / "data/voice-assets"
    output.mkdir(parents=True, exist_ok=True)
    entries = index_mandarin(args.game_data)
    links = json.loads(args.links.read_text(encoding="utf-8"))
    prefixes = json.loads(args.prefixes.read_text(encoding="utf-8"))["allPrefixes"]
    resolved = resolve_links(links, prefixes, entries)
    stats = {}
    for record in resolved.values():
        package = record["package"]
        if package not in stats:
            stat = Path(package).stat()
            stats[package] = (stat.st_size, stat.st_mtime_ns)
        record["package_size"], record["package_mtime_ns"] = stats[package]
    manifest = output / "manifest.json"
    try:
        previous = json.loads(manifest.read_text(encoding="utf-8")).get("entries", {})
    except (OSError, ValueError):
        previous = {}
    resolved = merge_valid_manifest_entries(previous, resolved)
    if not resolved:
        raise ValueError("No exact voice mappings found; previous manifest left unchanged")
    if not (args.decoder_dir / "vgmstream-cli.exe").is_file():
        raise ValueError("Missing vgmstream decoder")
    shutil.copytree(args.decoder_dir, output / "vgmstream", dirs_exist_ok=True)
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps({"version": 1, "entries": resolved}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(manifest)
    print(f"Indexed {len(resolved)} exact Mandarin lines from {len(entries)} local voice assets.")


if __name__ == "__main__":
    main()
