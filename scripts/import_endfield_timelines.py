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


def localized_playable(playables, identity, film, dub):
    # Both suffixes occur on playables referenced by the Korean config slot.
    suffixes = ('ko', 'kr') if dub == 'ko' else (dub,)
    matches = [track for suffix in suffixes
               for track in playables.get((identity, film.lower() + '_others_au_' + suffix), ())]
    return matches[0] if len(matches) == 1 else None


def track_clips(objects, root, *, conditions=None, gender=None, durations=None):
    captions, speech = [], []
    pending = [(p, None) for p in reversed(root['m_Tracks'])]
    visited = set()
    while pending:
        pointer, parent = pending.pop()
        if pointer['m_FileID']:
            continue
        identity = pointer['m_PathID']
        track = objects.get(identity, {})
        if identity in visited or (parent is not None and track.get('m_Parent') != parent):
            return None
        visited.add(identity)
        if track.get('m_Muted'):
            continue
        condition = track.get('enableOnCondition', {})
        if condition.get('m_PathID'):
            selection = (conditions or {}).get((condition['m_FileID'], condition['m_PathID']))
            if selection not in ('female', 'male'):
                return None
            if selection != gender:
                continue
        pending.extend((p, pointer) for p in reversed(track.get('m_Children', ())))
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
            end = start + duration
            if (durations and event in durations and asset.get('_stopEventAtClipEnd') == 0
                    and asset.get('_exitAudioEvent', {}).get('_id') == 0):
                end = max(end, start + durations[event])
            interval = round(start, 5), round(end, 5)
            if text:
                captions.append((text, *interval))
            if event.lower().startswith('au_vo_'):
                speech.append((event, *interval))
    return captions, speech


def narrative_conditions(directory):
    import UnityPy
    verified = {}
    for path in directory.glob('*.unity'):
        for obj in UnityPy.load(str(path)).objects:
            if obj.type.name != 'MonoBehaviour':
                continue
            data = obj.read_typetree()
            references = data.get('references', {}).get('RefIds', ())
            if len(references) != 1 or data.get('conditions') != [{'rid': references[0]['rid']}]:
                continue
            condition = references[0]
            if condition['type'].get('class') != 'CheckNarrativeGender':
                continue
            gender = {1: 'male', 2: 'female'}.get(condition['data'].get('narrativeGender'))
            if gender and data['m_Name'] == 'NarrativeGender' + gender.capitalize() + 'Condition':
                if obj.path_id in verified:
                    raise ValueError('Ambiguous narrative gender condition')
                verified[obj.path_id] = gender
    return verified


def localized_tracks(directory, *, packages=None, conditions=None):
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
                playables[identity, obj['m_Name'].lower()].append((objects, obj))
    for film, refs in configs.items():
        for number, dub in enumerate(DUBS):
            if number not in refs:
                continue
            track = localized_playable(playables, refs[number]['m_PathID'], film, dub)
            if track is None:
                continue
            objects, root = track
            conditional = any(o.get('enableOnCondition', {}).get('m_PathID') for o in objects.values())
            variants = (('f_' + film, 'female'), ('m_' + film, 'male')) if conditional else ((film, None),)
            for performance, gender in variants:
                known = (conditions or {})
                bindings = {}
                for obj in objects.values():
                    pointer = obj.get('enableOnCondition', {})
                    identity = pointer.get('m_PathID')
                    if pointer.get('m_FileID', 0) > 0 and identity in known:
                        bindings[pointer['m_FileID'], identity] = known[identity]
                durations = {}
                if packages and performance in packages[dub][1]:
                    _, _, event, frames, rate = packages[dub][1][performance]
                    durations[event] = frames / rate
                clips = track_clips(objects, root, conditions=bindings, gender=gender, durations=durations)
                if clips is not None:
                    yield performance, dub, *clips


def unity_clocks(directory, *, packages=None, conditions=None):
    cues = defaultdict(dict)
    for film, dub, captions, speech in localized_tracks(directory, packages=packages, conditions=conditions):
        for text, start, end in captions:
            matches = [(event, origin) for event, origin, stop in speech if origin <= start < end <= stop]
            if len(matches) != 1:
                continue
            unique = (sum(a < end and start < b for _, a, b in speech) == 1
                      and sum(other == text for other, _, _ in captions) == 1
                      and sum(a < end and start < b for _, a, b in captions) == 1)
            event, origin = matches[0]
            cues[film, text][dub] = start, end, event, origin, unique
    return [{'film': film, 'caption': text, 'locales': clocks} for (film, text), clocks in cues.items()]


def import_clocks(clocks, packages, pcm):
    verified = {dub: set(map(tuple, pcm[dub][0])) for dub in DUBS}
    accepted = set.union(*verified.values())
    films, cues = {}, {}
    for row in clocks:
        key = film, caption = row['film'], row['caption']
        if key not in accepted:
            continue
        if key in cues:
            raise ValueError('Duplicate film caption')
        times = []
        voices = films.setdefault(film, [None] * len(DUBS))
        for number, dub in enumerate(DUBS):
            if key not in verified[dub]:
                times.extend((None, None))
                continue
            start, end, event, origin, unique = row['locales'][dub]
            if not unique or not 0 <= origin <= start < end or not event.lower().startswith('au_vo_'):
                raise ValueError('Ambiguous or invalid localized film clock')
            media, digest, bank_event, frames, rate = packages[dub][1][film]
            if bank_event != event:
                raise ValueError('Film speech event differs from the verified recording')
            if frames <= 0 or rate <= 0:
                raise ValueError('Invalid decoded recording length')
            start_ms = round((start - origin) * 1000)
            # A subtitle can remain visible after the last sample of its sole
            # speech event. Preserve all recorded speech up to that boundary.
            end_ms = min(round((end - origin) * 1000), frames * 1000 // rate)
            if start_ms >= end_ms:
                raise ValueError('Film cue has no interval inside the recording')
            voices[number] = media, digest
            times.extend((start_ms, end_ms))
        cues[key] = tuple(times)
    if set(cues) != accepted or not cues:
        raise ValueError('Incomplete timeline evidence')
    films = {film: tuple(voices) for film, voices in films.items()}
    packs = {name: tuple(tuple(pack) for pack in packages[dub][0]) for dub, name in DUBS.items()}
    return packs, films, cues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundles', type=Path, help='Directory of unpacked Unity serialized FMV assets')
    source.add_argument('--clocks', type=Path, help='Previously exported localized Unity clocks')
    parser.add_argument('--conditions', type=Path, help='Audited external narrative-condition objects')
    for name in ('packages', 'pcm', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    packages = json.loads(args.packages.read_bytes())
    conditions = narrative_conditions(args.conditions) if args.conditions else {}
    clocks = (unity_clocks(args.bundles, packages=packages, conditions=conditions)
              if args.bundles else json.loads(args.clocks.read_bytes()))
    values = import_clocks(clocks, packages, json.loads(args.pcm.read_bytes()))
    events = {film: tuple(packages[dub][1][film][2] if voice else None
                          for dub, voice in zip(DUBS, voices, strict=True))
              for film, voices in values[1].items()}
    with args.output.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('"""Derived publisher package and cinematic bindings. Generated by scripts/import_endfield_timelines.py."""\n')
        for name, mapping in zip(('PACKAGES', 'FILMS', 'CUES', 'EVENTS'), (*values, events), strict=True):
            stream.write('\n' + name + ' = {\n')
            for key, value in sorted(mapping.items()):
                stream.write(f'    {key!r}: {value!r},\n')
            stream.write('}\n')


if __name__ == '__main__':
    main()
