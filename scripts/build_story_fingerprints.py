"""Build a compact acoustic index for unnamed Mandarin story WEM files."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from math import ceil
from pathlib import Path
import shutil
import sqlite3

from backend.agent_fingerprint import landmarks
from backend.story_voice import _decode_entry, story_index_inventory, STORY_PACKAGE
from backend.voice_assets import index_mandarin


MAX_LANDMARKS = 360


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / "data/voice-assets"
    manifest_path = folder / "manifest.json"
    decoder = folder / "vgmstream/vgmstream-cli.exe"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    directly_mapped = {int(item["file_id"], 16) for item in manifest.values()}
    entries = {
        file_id: entry
        for file_id, entry in index_mandarin(args.game_data).items()
        if file_id not in directly_mapped and STORY_PACKAGE.fullmatch(entry.package.stem)
    }
    if not entries:
        raise ValueError("No unmapped Mandarin story voice candidates found")

    current = folder / "story-fingerprints.db"
    pending = folder / "story-fingerprints.pending.db"
    if not pending.exists() and current.exists():
        shutil.copy2(current, pending)
    database = sqlite3.connect(pending)
    database.execute("PRAGMA journal_mode=WAL")
    database.execute(
        "CREATE TABLE IF NOT EXISTS clips ("
        "asset_id TEXT PRIMARY KEY, file_id TEXT NOT NULL, package TEXT NOT NULL, "
        "offset INTEGER NOT NULL, size INTEGER NOT NULL, duration REAL NOT NULL, stamp TEXT NOT NULL)"
    )
    database.execute(
        "CREATE TABLE IF NOT EXISTS hashes (hash INTEGER NOT NULL, asset_id TEXT NOT NULL, frame INTEGER NOT NULL)"
    )
    database.execute("CREATE INDEX IF NOT EXISTS idx_story_hash ON hashes(hash)")
    done = {asset: stamp for asset, stamp in database.execute("SELECT asset_id, stamp FROM clips")}

    def decode(pair):
        file_id, entry = pair
        stat = entry.package.stat()
        asset_id = f"{file_id:016x}"
        stamp = f"{stat.st_size}:{stat.st_mtime_ns}:{entry.offset}:{entry.size}"
        if done.get(asset_id) == stamp:
            return asset_id, entry, None, stamp, 0.0
        try:
            samples = _decode_entry(entry, decoder)
            points = landmarks(samples)
            if len(points) > MAX_LANDMARKS:
                points = points[::ceil(len(points) / MAX_LANDMARKS)][:MAX_LANDMARKS]
            return asset_id, entry, points, stamp, len(samples) / 8000
        except Exception as error:
            print(f"Could not index {asset_id}: {error}", flush=True)
            return asset_id, entry, [], stamp, 0.0

    active: list[tuple[str]] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        for index, result in enumerate(pool.map(decode, entries.items()), 1):
            asset_id, entry, points, stamp, duration = result
            active.append((asset_id,))
            if points is not None:
                database.execute("DELETE FROM hashes WHERE asset_id = ?", (asset_id,))
                database.execute(
                    "INSERT OR REPLACE INTO clips VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (asset_id, f"{entry.file_id:016x}", str(entry.package), entry.offset, entry.size, duration, stamp),
                )
                if points:
                    database.executemany(
                        "INSERT INTO hashes VALUES (?, ?, ?)",
                        [(value, asset_id, frame) for value, frame in points],
                    )
                else:
                    failures += 1
            if index % 100 == 0:
                database.commit()
                print(f"{index}/{len(entries)} story candidates indexed", flush=True)

    database.execute("CREATE TEMP TABLE active_assets (asset_id TEXT PRIMARY KEY)")
    database.executemany("INSERT INTO active_assets VALUES (?)", active)
    database.execute(
        "DELETE FROM hashes WHERE asset_id NOT IN (SELECT asset_id FROM active_assets)"
    )
    database.execute(
        "DELETE FROM clips WHERE asset_id NOT IN (SELECT asset_id FROM active_assets)"
    )
    database.commit()
    database.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    database.execute("PRAGMA journal_mode=DELETE")
    total = database.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    hashes = database.execute("SELECT COUNT(*) FROM hashes").fetchone()[0]
    database.close()
    pending.replace(current)
    state = folder / "story-index-state.json"
    temporary = state.with_suffix(".pending")
    temporary.write_text(
        json.dumps({"version": 1, "inventory": story_index_inventory(args.game_data, manifest_path)}),
        encoding="utf-8",
    )
    temporary.replace(state)
    print(f"Complete: {total} candidates, {hashes} sparse landmarks, {failures} unusable files", flush=True)


if __name__ == "__main__":
    main()
