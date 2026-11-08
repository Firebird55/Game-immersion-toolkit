"""Import audited Unity FMV clocks into a release profile without including game assets.

Inputs are private exports from one publisher release: localized timeline occurrences
(film, caption and per-dub start/end/event/event-start/unique), verified package
headers and film media identities, and the independently decoded PCM coverage.
Only public distribution coordinates, checksums, identifiers and timings are emitted.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path


DUBS = {'cn': 'chinese', 'en': 'english', 'jp': 'japanese', 'ko': 'korean'}


def track_clips(objects, root):
    captions, speech = [], []
    for pointer in root['m_Tracks']:
        if pointer['m_FileID']:
            continue
        track = objects.get(pointer['m_PathID'], {})
        if track.get('m_Muted'):
            continue
        for clip in track.get('m_Clips', ()):
            ref = clip['m_Asset']
            asset = objects.get(ref['m_PathID'], {}) if not ref['m_FileID'] else {}
            text, event = asset.get('_textId'), asset.get('_audioEventKey', '')
            if not text and not event.lower().startswith('au_vo_'):
                continue
            start, duration = clip['m_Start'], clip['m_Duration']
            if (clip.get('m_TimeScale', 1) != 1 or clip.get('m_ClipIn', 0) != 0
                    or not math.isfinite(start + duration) or start < 0 or duration <= 0):
                return None
            interval = round(start, 5), round(start + duration, 5)
            if text:
                captions.append((text, *interval))
            if event.lower().startswith('au_vo_'):
                speech.append((event, *interval))
    return captions, speech


def unity_clocks(directory):
    # UnityPy is needed only by maintainers regenerating a release profile.
    import UnityPy
    configs, playables = {}, defaultdict(list)
    for path in sorted(directory.glob('*.unity')):
        objects = {obj.path_id: obj.read_typetree() for obj in UnityPy.load(str(path)).objects
                   if obj.type.name == 'MonoBehaviour'}
        for identity, obj in objects.items():
            if 'fmvId' in obj:
                cfg = obj['config']
                track_map = cfg['audioLangKey2SubtitleTrack']
                refs = dict(zip(track_map['_keys'], track_map['_values'], strict=True))
                refs.setdefault(0, cfg['defaultPlayable'])
                if obj['fmvId'] in configs:
                    raise ValueError('Ambiguous FMV configuration')
                configs[obj['fmvId']] = refs
            if 'm_Tracks' in obj:
                playables[identity, obj['m_Name'].lower()].append(track_clips(objects, obj))
    cues = defaultdict(dict)
    for film, refs in configs.items():
        for number, dub in enumerate(DUBS):
            if number not in refs:
                continue
            key = refs[number]['m_PathID'], film.lower() + '_others_au_' + dub
            candidates = playables.get(key, [])
            if len(candidates) != 1 or candidates[0] is None:
                continue
            captions, speech = candidates[0]
            for text, start, end in captions:
                matches = [(event, origin) for event, origin, stop in speech if origin <= start < end <= stop]
                if len(matches) != 1:
                    continue
                unique = (sum(other == text for other, _, _ in captions) == 1
                          and sum(a < end and start < b for _, a, b in captions) == 1)
                event, origin = matches[0]
                cues[film, text][dub] = start, end, event, origin, unique
    return [{'film': film, 'caption': text, 'locales': clocks} for (film, text), clocks in cues.items()]


def import_clocks(clocks, packages, pcm):
    accepted = set.intersection(*(set(map(tuple, pcm[dub][0])) for dub in DUBS))
    films, cues, events = {}, {}, {}
    for row in clocks:
        film, caption = row['film'], row['caption']
        if (film, caption) not in accepted:
            continue
        times = []
        voices = []
        for dub in DUBS:
            start, end, event, origin, unique = row['locales'][dub]
            if not unique or not 0 <= origin <= start < end or not event.lower().startswith('au_vo_'):
                raise ValueError('Ambiguous or invalid localized film clock')
            if events.setdefault((film, dub), event) != event:
                raise ValueError('Film requires more than one speech recording')
            voices.append(tuple(packages[dub][1][film]))
            times.extend((round((start - origin) * 1000), round((end - origin) * 1000)))
        films[film] = tuple(voices)
        if (film, caption) in cues:
            raise ValueError('Duplicate film caption')
        cues[film, caption] = tuple(times)
    if set(cues) != accepted or not cues:
        raise ValueError('Incomplete timeline evidence')
    packs = {name: tuple(tuple(pack) for pack in packages[dub][0]) for dub, name in DUBS.items()}
    return packs, films, cues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundles', type=Path, help='Directory of unpacked Unity serialized FMV assets')
    source.add_argument('--clocks', type=Path, help='Previously exported localized Unity clocks')
    for name in ('packages', 'pcm', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    clocks = unity_clocks(args.bundles) if args.bundles else json.loads(args.clocks.read_bytes())
    values = import_clocks(clocks, json.loads(args.packages.read_bytes()), json.loads(args.pcm.read_bytes()))
    with args.output.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('"""Derived publisher package and cinematic bindings. Generated by scripts/import_endfield_timelines.py."""\n')
        for name, mapping in zip(('PACKAGES', 'FILMS', 'CUES'), values):
            stream.write('\n' + name + ' = {\n')
            for key, value in sorted(mapping.items()):
                stream.write(f'    {key!r}: {value!r},\n')
            stream.write('}\n')


if __name__ == '__main__':
    main()
