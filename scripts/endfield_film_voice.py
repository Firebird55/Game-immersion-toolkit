"""Fetch an original Endfield film performance or a verified historical caption."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import endfield_assets, endfield_film_voice, endfield_release, endfield_test_film
from backend.game_tools import _atomic_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('event', nargs='?', help='Authored Wwise event from the selected game release')
    source.add_argument('--test-caption', help='Mandarin Technical Test caption ID, or "list" for its transcript')
    parser.add_argument('--cache', type=Path, required=True, help='Private publisher cache')
    parser.add_argument('--locale', choices=endfield_assets.SUPPORTED_LOCALES, required=True)
    parser.add_argument('--region', choices=endfield_release.CHANNELS, default='global')
    output = parser.add_mutually_exclusive_group()
    output.add_argument('--wem', type=Path, help='Destination for the original whole-event WEM')
    output.add_argument('--mp3', type=Path, help='Destination for one historical film caption')
    args = parser.parse_args()
    cache = args.cache.resolve()
    if args.test_caption:
        if args.locale != 'zh-Hans':
            parser.error('The verified Technical Test source has Mandarin audio and Simplified Chinese captions.')
        if args.test_caption == 'list':
            if args.wem or args.mp3:
                parser.error('Listing the historical transcript does not take an output file.')
            print(json.dumps(endfield_test_film.lines(cache), ensure_ascii=True))
        else:
            if not args.mp3:
                parser.error('--test-caption requires --mp3 for a caption export.')
            record = endfield_test_film.export(cache, args.test_caption, args.mp3)
            print(json.dumps({'caption': args.test_caption, 'locale': args.locale, **record}))
        return
    if not args.wem:
        parser.error('A game voice event requires --wem.')
    catalog = endfield_release.prepare(cache, args.region)
    identity, data = endfield_film_voice.recording(cache, catalog.stamp, endfield_assets.VOICE_LOCALES[args.locale], args.event)
    if endfield_release.discover(args.region)[0] != catalog.stamp:
        raise ValueError('The release changed during the film request. Retry.')
    _atomic_file(args.wem, data)
    print(json.dumps({'event': args.event, 'locale': args.locale, 'region': args.region, 'version': catalog.revision_title,
                      'revision': catalog.stamp, 'media_id': identity, 'sha256': hashlib.sha256(data).hexdigest()}))


if __name__ == '__main__':
    main()
