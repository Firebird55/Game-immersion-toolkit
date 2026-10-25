"""Isolated private export process; stdout carries progress, never game content."""
import argparse
import json
import time
from pathlib import Path

from .mobile_library import export_library, prepare_source, encoded, export_workers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--game', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog-only', action='store_true')
    parser.add_argument('--account-signature')
    parser.add_argument('--source-locale')
    parser.add_argument('--translation-locale')
    parser.add_argument('--automatic-install', type=Path)
    args = parser.parse_args()
    last = [0.0]

    def progress(value):
        now = time.monotonic()
        if now - last[0] >= .15 or value.get('state') in {'complete', 'error'}:
            print(json.dumps(value), flush=True)
            last[0] = now

    service = None
    from .export_lock import ExportLock
    from .game_paths import settings_path
    queue = ExportLock(settings_path().parent / 'mobile-export.lock')
    try:
        from .mobile_export_layout import work_folder
        while not queue.acquire():
            progress({'state': 'preparing', 'message': 'Waiting for the current mobile export to finish'})
            time.sleep(.5)
        source = None
        if args.automatic_install:
            from .game_assets import asset_adapter
            from .language_worker import build
            from .automatic_mobile_export import atomic_json
            from .mobile_library import digest, file_digest
            adapter, _ = asset_adapter(args.game)
            stamp = adapter.fingerprint(args.automatic_install)
            directory = work_folder(args.output) / 'source'
            directory.mkdir(parents=True, exist_ok=True)
            source = directory / 'textmap.json'
            marker = directory / 'verified.json'
            identity = digest([stamp, adapter.LANGUAGE_INDEX_VERSION, args.source_locale, args.translation_locale])
            try:
                saved = json.loads(marker.read_text())
                valid = source.is_file() and saved == {'identity': identity, 'sha256': file_digest(source)}
            except (OSError, ValueError):
                valid = False
            if not valid:
                temporary = directory / 'textmap.pending'
                build(args.game, args.automatic_install, directory, args.source_locale, [args.translation_locale], temporary)
                if adapter.fingerprint(args.automatic_install) != stamp:
                    raise ValueError('Game changed during preparation.')
                temporary.replace(source)
                atomic_json(marker, {'identity': identity, 'sha256': file_digest(source)})
        records, voice, check, service = prepare_source(args.root, args.game, work_folder(args.output) / 'decoded',
            expected_account_signature=args.account_signature, expected_source_locale=args.source_locale,
            source_path=source, translation_locale=args.translation_locale)
        progress({'state': 'exporting', 'estimatedCatalogBytes': sum(len(encoded(r)) + 1 for r in records),
                  'total': len(records), 'message': 'Converting verified dialogue and voices'})
        export_library(args.game, records, args.output, voice=voice, check=check,
                       include_audio=not args.catalog_only, progress=progress, workers=export_workers())
        return 0
    except Exception:
        progress({'state': 'error', 'message': 'Export failed. Check game data, voice tools and available disk space, then resume.'})
        return 1
    finally:
        queue.close()
        if service:
            service.close()


if __name__ == '__main__':
    raise SystemExit(main())
