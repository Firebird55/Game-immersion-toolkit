"""Prepare ignored footage frames/catalogs for browser OCR verification, locally only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.mobile_library import prepare_source
from backend.media_tools import ffmpeg_executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "backend/tests/fixtures/game-video-ocr.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output/mobile-replay")
    parser.add_argument("--resolutions", default="1280x720,1920x1080")
    parser.add_argument("--games", default="cyberpunk,witcher3,wuwa,nte,honkai3")
    args = parser.parse_args()
    output = args.output; output.mkdir(parents=True, exist_ok=True)
    clips = json.loads(args.manifest.read_text())["clips"]
    clips = [c for c in clips if c["game"] in args.games.split(",")]
    for game in sorted({c["game"] for c in clips}):
        records, _, check, service = prepare_source(ROOT, game, output / "decoded" / game)
        check.force()
        (output / (game + ".json")).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        if service:
            service.close()
    cases = []
    for index, clip in enumerate(clips):
        for resolution in args.resolutions.split(","):
            width, height = map(int, resolution.split("x"))
            folder = output / f"frames-{index}-{resolution}"; folder.mkdir(exist_ok=True)
            if not (folder / "complete").exists():
                subprocess.run([ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(clip.get("start", 0)), "-i", str(ROOT / clip["path"]),
                    "-t", str(clip["duration"]), "-vf", f"fps=2,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                    str(folder / "%05d.png")], check=True)
                (folder / "complete").touch()
            frames = sorted(p.relative_to(output).as_posix() for p in folder.glob("*.png"))
            cases.append({**clip, "resolution": resolution, "frames": frames})
        print(f"Prepared footage case {index+1}/{len(clips)}", flush=True)
    (output / "manifest.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")


if __name__ == "__main__":
    main()
