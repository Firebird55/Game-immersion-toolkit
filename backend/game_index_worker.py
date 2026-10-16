"""Build a candidate game index outside the live OCR interpreter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .game_assets import LOCAL_GAMES, asset_adapter
from .local_game import LocalDialogue


def build(game: str, install: Path, directory: Path, output: Path) -> None:
    adapter, _ = asset_adapter(game)
    payload = adapter.index_install(install, directory, lambda _message: None)
    if not payload.get('records'):
        raise ValueError('Extracted dialogue index is empty')
    for record in payload['records']:
        LocalDialogue(**record)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', choices=LOCAL_GAMES, required=True)
    parser.add_argument('--install', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.game, args.install, args.directory, args.output)


if __name__ == '__main__':
    main()
