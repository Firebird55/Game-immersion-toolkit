"""Prepare one requested official game language outside the capture process."""
import argparse
import json
import inspect
import traceback
from pathlib import Path

from .game_assets import asset_adapter
from .local_game import LocalDialogue


def build(game, install, directory, locale, targets, output, progress=None):
    adapter, _ = asset_adapter(game)
    options = {'progress': progress} if progress and 'progress' in inspect.signature(adapter.index_language).parameters else {}
    payload = adapter.index_language(install, directory, locale, targets, **options)
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
    def report(message):
        path = args.output.with_name('progress.json')
        pending = path.with_suffix('.pending')
        pending.write_text(json.dumps({'message': str(message)[:500]}), encoding='utf-8')
        pending.replace(path)
    try:
        build(args.game, args.install, args.directory, args.locale, json.loads(args.targets), args.output, report)
    except Exception as error:
        from .preparation_errors import public_failure
        args.output.with_name('failure.json').write_text(json.dumps(public_failure(error)), encoding='utf-8')
        args.output.with_name('failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise SystemExit(1)
