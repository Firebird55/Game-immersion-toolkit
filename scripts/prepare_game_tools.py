"""Prepare tools for selected local games; never download game archives or voices."""
import argparse
from pathlib import Path

from backend.game_paths import GAMES, GAME_NAMES, configured_install, load_paths
from backend.game_tools import prepare_tools


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--configured", action="store_true")
    choice.add_argument("--game", choices=GAMES)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    games = [args.game] if args.game else [game for game in load_paths() if configured_install(game)]
    failed = False
    for game in games:
        try:
            prepare_tools(root, game, lambda message: print(f"[{GAME_NAMES[game]}] {message}", flush=True))
        except Exception as error:
            print(f"[{GAME_NAMES[game]}] Preparation failed: {error}. Retry from Setup in the app.", flush=True)
            failed = True
    if not games:
        print("Choose a game in the app's Setup screen when you are ready.")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
