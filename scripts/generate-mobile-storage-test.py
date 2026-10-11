"""Generate a private 2+ GiB synthetic library to exercise iPhone file providers."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.mobile_library import write_pack, digest, encoded, file_digest, FORMAT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/mobile-storage-test")
    args = parser.parse_args()
    root = args.output; root.mkdir(parents=True, exist_ok=True)
    match = re.search(r'export const TONE=("[A-Za-z0-9+/=]+");', (ROOT / "tests/mobile-media-fixtures.mjs").read_text())
    tone = base64.b64decode(json.loads(match[1]))
    rows, packs = [], []
    for pack_number in range(5):
        entries, clips = [], {}
        for number in range(10):
            index = pack_number * 10 + number
            clip = root / (f"generated-{index}.mp3")
            with clip.open("wb") as stream:
                stream.write(tone)
                if index:
                    stream.truncate(45 * 1024 * 1024)
                    stream.seek(45 * 1024 * 1024 - 1); stream.write(bytes([index]))
            sha = file_digest(clip)
            clips[sha] = {"size": clip.stat().st_size, "sha256": sha}
            entries.append(("audio/" + sha + ".mp3", clip))
            rows.append({"id": digest(["storage", index]), "textId": f"storage:{index}",
                         "english": f"Storage test line {index}", "chinese": f"存储测试第{index}句。",
                         "sourceVoice": digest(["tone", index]), "audio": sha, "channels": ["dialogue"]})
        identity = digest(clips); name = f"zzz.voices-{identity[:16]}.zip"
        write_pack(root / name, {"format": FORMAT, "kind": "voices", "game": "zzz", "id": identity, "clips": clips}, entries)
        packs.append({"id": identity, "name": name, "clips": list(clips)})
        for _, path in entries:
            path.unlink()
        print(f"Completed synthetic pack {pack_number+1}/5", flush=True)
    catalog = b"".join(encoded(row)+b"\n" for row in rows)
    manifest = {"format": FORMAT, "kind": "catalog", "game": "zzz", "title": "Synthetic storage verification",
                "revision": digest(rows), "languages": ["zh-Hans", "en"],
                "coverage": {"dialogue": len(rows), "mappedVoices": len(rows), "exportedVoices": len(rows), "partial": True},
                "catalog": [{"name": "catalog/00000.ndjson", "size": len(catalog), "sha256": hashlib.sha256(catalog).hexdigest()}], "packs": packs}
    write_pack(root / "zzz.catalog.zip", manifest, [("catalog/00000.ndjson", catalog)])
    print(f"Synthetic ZIP bytes: {sum(p.stat().st_size for p in root.glob('*.zip'))}; copy to Files for the storage test.")

if __name__ == "__main__":
    main()
