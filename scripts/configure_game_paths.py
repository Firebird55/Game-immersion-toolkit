"""Used by the installer and the optional game-folder picker."""
import argparse
from pathlib import Path

from backend.game_paths import GAMES, GAME_NAMES, load_paths, save_install, validate_install


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", choices=GAMES)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate without changing preferences")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--catalog", action="store_true", help="List supported game identifiers and names")
    args = parser.parse_args()
    if args.catalog:
        import json
        print(json.dumps([{'id': game, 'name': GAME_NAMES[game]} for game in GAMES]))
        return
    if args.list:
        import json
        print(json.dumps(load_paths()))
        return
    if not args.game or not args.path:
        parser.error("Provide --game and --path, or --list")
    try:
        (validate_install if args.check else save_install)(args.game, args.path)
    except (OSError, ValueError) as error:
        print(str(error))
        raise SystemExit(1)
    print("Game folder verified" if args.check else "Game folder saved for this PC")


if __name__ == "__main__":
    main()
