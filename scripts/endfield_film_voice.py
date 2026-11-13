"""Fetch a whole released film voice performance by its authored Wwise event."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import endfield_assets, endfield_film_voice, endfield_release
from backend.game_tools import _atomic_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event')
    parser.add_argument('--cache', type=Path, required=True, help='Private publisher cache')
    parser.add_argument('--locale', choices=endfield_assets.SUPPORTED_LOCALES, required=True)
    parser.add_argument('--region', choices=endfield_release.CHANNELS, default='global')
    parser.add_argument('--wem', type=Path, required=True, help='Destination for the original whole-event WEM')
    args = parser.parse_args()
    cache = args.cache.resolve()
    catalog = endfield_release.prepare(cache, args.region)
    identity, data = endfield_film_voice.recording(cache, catalog.stamp, endfield_assets.VOICE_LOCALES[args.locale], args.event)
    if endfield_release.discover(args.region)[0] != catalog.stamp:
        raise ValueError('The release changed during the film request. Retry.')
    _atomic_file(args.wem, data)
    print(json.dumps({'event': args.event, 'locale': args.locale, 'region': args.region, 'version': catalog.revision_title,
                      'revision': catalog.stamp, 'media_id': identity, 'sha256': hashlib.sha256(data).hexdigest()}))


if __name__ == '__main__':
    main()
