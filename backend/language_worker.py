"""Prepare one requested official game language outside the capture process."""
import argparse
import json
import inspect
import time
import traceback
from pathlib import Path

from .language_snapshot import write_payload as write_snapshot
from .game_assets import PUBLISHER_GAMES, asset_adapter

def progress_reporter(output):
    """Best-effort telemetry must never interrupt the actual language build."""
    path = output.with_name('progress.json')
    pending = path.with_suffix('.pending')
    last_attempt = float('-inf')

    def report(message):
        nonlocal last_attempt
        now = time.monotonic()
        if now - last_attempt < 1:
            return
        last_attempt = now
        try:
            pending.write_text(json.dumps({'message': str(message)[:500]}), encoding='utf-8')
            pending.replace(path)
        except OSError:
            # Windows readers, virus scanners and sync clients can temporarily
            # hold either file. Keep the last readable status and try next time.
            # Snapshot writes and extraction errors still propagate normally.
            pass
    return report


def build(game, install, directory, locale, targets, output, progress=None):
    adapter, _ = asset_adapter(game)
    options = {'progress': progress} if progress and 'progress' in inspect.signature(adapter.index_language).parameters else {}
    payload = adapter.index_language(install, directory, locale, targets, **options)
    write_payload(game, payload, locale, targets, output)


def write_payload(game, payload, locale, targets, output, *, check=None):
    adapter, _ = asset_adapter(game)
    write_snapshot(game, payload, locale, targets, output,
                   reader_revision=adapter.LANGUAGE_INDEX_VERSION, check=check)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--install', type=Path)
    source.add_argument('--publisher', action='store_true')
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--locale', required=True)
    parser.add_argument('--targets', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.publisher and args.game not in PUBLISHER_GAMES:
        parser.error('Publisher preparation is unavailable for this game.')
    report = progress_reporter(args.output)
    try:
        build(args.game, args.install, args.directory, args.locale, json.loads(args.targets), args.output, report)
    except Exception as error:
        from .preparation_errors import public_failure
        args.output.with_name('failure.json').write_text(json.dumps(public_failure(error)), encoding='utf-8')
        args.output.with_name('failure.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise SystemExit(1)
