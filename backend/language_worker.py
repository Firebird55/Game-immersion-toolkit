"""Prepare one requested official game language outside the capture process."""
import argparse
import json
from pathlib import Path

from .game_assets import asset_adapter
from .local_game import LocalDialogue


def build(game, install, directory, locale, targets, output):
    adapter, _ = asset_adapter(game)
    payload = adapter.index_language(install, directory, locale, targets)
    if payload.get('format') != 2 or payload.get('game') != game or payload.get('source_locale') != locale or not payload.get('records'):
        raise ValueError('Incomplete official language snapshot')
    for record in payload['records']:
        LocalDialogue(**record)
    payload['reader_revision'] = adapter.LANGUAGE_INDEX_VERSION
    payload['targets_requested'] = sorted(targets)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', required=True)
    parser.add_argument('--install', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--locale', required=True)
    parser.add_argument('--targets', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.game, args.install, args.directory, args.locale, json.loads(args.targets), args.output)
