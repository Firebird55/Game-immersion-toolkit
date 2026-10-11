"""Export your own indexed game for the browser phone panel; outputs remain private."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.mobile_library import export_library, prepare_source
from backend.game_paths import GAMES

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", choices=GAMES, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--max-lines", type=int, help="Explicit subset for private device verification")
    args = parser.parse_args()
    output = args.output or ROOT / "output/mobile-libraries" / args.game
    rows, voice, check, service = prepare_source(ROOT, args.game, output / "decoded")
    if args.max_lines is not None:
        if args.max_lines < 1:
            parser.error("max-lines must be positive")
        rows = rows[:args.max_lines]
    try:
        last = [-1]
        def progress(value):
            percent = value.get("progress", 0)
            if percent != last[0]:
                print(f"{percent}% {value['message']}", flush=True)
                last[0] = percent
        result = export_library(args.game, rows, output, voice=voice, check=check,
                                include_audio=not args.catalog_only,
                                progress=progress)
        print(result["folder"])
    finally:
        if service:
            service.close()

if __name__ == "__main__":
    main()
