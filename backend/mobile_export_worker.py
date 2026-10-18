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
    args = parser.parse_args()
    last = [0.0]

    def progress(value):
        now = time.monotonic()
        if now - last[0] >= .15 or value.get('state') in {'complete', 'error'}:
            print(json.dumps(value), flush=True)
            last[0] = now

    service = None
    try:
        from .mobile_export_layout import work_folder
        records, voice, check, service = prepare_source(args.root, args.game, work_folder(args.output) / 'decoded',
            expected_account_signature=args.account_signature, expected_source_locale=args.source_locale)
        progress({'state': 'exporting', 'estimatedCatalogBytes': sum(len(encoded(r)) + 1 for r in records),
                  'total': len(records), 'message': 'Converting verified dialogue and voices'})
        export_library(args.game, records, args.output, voice=voice, check=check,
                       include_audio=not args.catalog_only, progress=progress, workers=export_workers())
        return 0
    except Exception:
        progress({'state': 'error', 'message': 'Export failed. Check game data, voice tools and available disk space, then resume.'})
        return 1
    finally:
        if service:
            service.close()


if __name__ == '__main__':
    raise SystemExit(main())
