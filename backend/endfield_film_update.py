"""Rebuild localized FMV cues from the active release's config, playable, bank and audio."""
from collections import Counter
from contextlib import ExitStack
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import re
import json
import subprocess
import tempfile
import wave

from . import endfield_director as director, endfield_film_registry as registry, endfield_release as release
from .endfield_unity_timeline import timeline_objects
from .media_tools import vgmstream_executable
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure


FMV = 'assets/beyond/dynamicassets/gamedata/subtitle/fmv/'
CONDITIONS = 'assets/beyond/dynamicassets/gameplay/dialog/condition/narrativegender'
TRACKS = {'chinese': (0, ('cn',)), 'english': (1, ('en',)), 'japanese': (2, ('jp',)),
          'korean': (3, ('ko', 'kr'))}


def _check(condition):
    if not condition:
        raise ValueError('Invalid or ambiguous Endfield cinematic source.')


@lru_cache(maxsize=3)
def _files(tools, stamp):
    base, rows = release.group(tools, stamp, 4)
    manifest, = [row for row in rows if row.name == 'Data/Bundles/Windows/manifest.hgmmap']
    raw = registry.inflate(release._whole(tools, base, manifest, 160 * 1024**2), 384 * 1024**2)
    paths = {}
    for _, path, bundle in registry.bindings(raw, path_prefixes=(FMV, CONDITIONS)):
        if path.endswith(('.playable', '.asset')):
            _check(path not in paths)
            paths[path] = 'Data/Bundles/Windows/' + bundle
    del raw
    found = {}
    for role, block in [('initial', 2), ('main', 11)]:
        names = frozenset(name for name in paths.values() if name.startswith('Data/Bundles/Windows/' + role + '/'))
        if names:
            base, rows = release.group(tools, stamp, block, names)
            for row in rows:
                _check(row.name not in found)
                found[row.name] = (base, row)
    return {path: found[name] for path, name in paths.items() if name in found}


def _asset(tools, source, path):
    from .endfield_timeline_bundle import decode_bundle
    base, file = source
    cab, payload = decode_bundle(release._whole(tools, base, file, 32 * 1024**2), tools)
    objects, containers, externals = timeline_objects(payload)
    roots = [pair['second']['asset'] for container in containers.values() for pair in container['m_Container']
             if pair['first'] == path]
    _check(len(roots) == 1 and roots[0]['m_FileID'] == 0 and roots[0]['m_PathID'] in objects)
    return cab, roots[0]['m_PathID'], objects, externals


def _cab(externals, pointer):
    index = pointer['m_FileID']
    if not 0 < index <= len(externals):
        return None
    path = externals[index - 1]
    match = re.fullmatch(r'archive:/(CAB-[0-9a-f]{32})/\1', path)
    return match[1] if match else None


def _conditions(tools, files):
    found = {}
    for gender in ('male', 'female'):
        path = CONDITIONS + gender + 'condition.asset'
        if path not in files:
            continue
        cab, root, objects, _ = _asset(tools, files[path], path)
        obj = objects[root]
        refs = obj.get('references', {}).get('RefIds', [])
        if (obj.get('m_Name') == 'NarrativeGender' + gender.capitalize() + 'Condition' and len(refs) == 1
                and obj.get('conditions') == [{'rid': refs[0]['rid']}]
                and refs[0]['type'].get('class') == 'CheckNarrativeGender'
                and refs[0]['data'].get('narrativeGender') == {'male': 1, 'female': 2}[gender]):
            found[cab, root] = gender
    return found


def _tracks(tools, files, dub, unchanged):
    column, suffixes = TRACKS[dub]
    conditions = None
    for path, source in files.items():
        match = re.fullmatch(re.escape(FMV) + r'singleconfigs/([a-z0-9_]+)\.asset', path)
        if not match:
            continue
        film = match[1]
        if film in unchanged:
            continue
        _, root, config_objects, externals = _asset(tools, source, path)
        obj = config_objects[root]
        if obj.get('fmvId') != film:
            continue
        config = obj['config']
        local = config['audioLangKey2SubtitleTrack']
        pairs = dict(zip(local['_keys'], local['_values'], strict=True))
        _check(len(pairs) == len(local['_keys']))
        pointer = pairs.get(column, config.get('defaultPlayable') if column == 0 else None)
        if not pointer or not (expected_cab := _cab(externals, pointer)):
            continue
        candidates = []
        for suffix in suffixes:
            path = FMV + film + '_others_au_' + suffix + '.playable'
            if path in files:
                cab, target, objects, ext = _asset(tools, files[path], path)
                if cab == expected_cab and target == pointer['m_PathID']:
                    candidates.append((objects, objects[target], ext))
        if len(candidates) != 1:
            continue
        objects, root, ext = candidates[0]
        if 'm_Tracks' not in root:
            continue
        bindings = {}
        conditional = False
        for obj in objects.values():
            predicate = obj.get('enableOnCondition', {})
            if predicate.get('m_PathID'):
                conditional = True
                if conditions is None:
                    conditions = _conditions(tools, files)
                value = conditions.get((_cab(ext, predicate), predicate['m_PathID']))
                if value:
                    bindings[predicate['m_FileID'], predicate['m_PathID']] = value
        for gender in (('female', 'male') if conditional else (None,)):
            performance = gender[0] + '_' + film if gender else film
            if performance in unchanged:
                continue
            clips = director.track_clips(objects, root, conditions=bindings, gender=gender, complete=True)
            if clips and all(clips):
                yield performance, objects, root, bindings, gender, clips


def _clock_rows(captions, speech, event, pcm):
    ordered = sorted(captions, key=lambda x: (x[1], x[2], x[0]))
    counts = Counter(text for text, _, _ in captions)
    previous = None
    for i, (text, start, end) in enumerate(ordered):
        anchor = previous
        previous = None
        if not re.fullmatch(r'[A-Za-z0-9_]{1,180}', text):
            continue
        matches = [(key, a, b) for key, a, b in speech if a < end and start < b]
        if len(matches) != 1:
            continue
        key, origin, stop = matches[0]
        if key != event or not origin <= start < end <= stop:
            continue
        overlaps = [(max(start, a) - origin, min(end, b) - origin) for j, (_, a, b) in enumerate(ordered)
                    if j != i and a < end and start < b]
        clock = director.audible_interval(pcm, start - origin, end - origin, overlaps)
        repeated = counts[text] > 1
        if anchor and anchor[1] > start:
            anchor = None
        if clock and (not repeated or anchor):
            identity = f'{text}@{i + 1}' if repeated else text
            yield identity, (text, *clock, anchor[0] if anchor else None, repeated)
            if not repeated and not overlaps:
                previous = (identity, end)


def _decode(decoder, folder, media_id, data):
    wem = folder / 'voice.wem'
    wav = folder / f'{media_id:016x}.wav'
    wem.write_bytes(data)
    subprocess.run([str(decoder), '-o', str(wav), str(wem)], check=True,
                   timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wave.open(str(wav))


def _build(tools, stamp, dub):
    from . import endfield_film_voice
    fixed = release.verified_films(tools, stamp, dub)
    tracks = list(_tracks(tools, _files(tools, stamp), dub, fixed))
    events = {event for *_, (_, speech) in tracks for event, _, _ in speech}
    if not events:
        return {}
    media = endfield_film_voice.recording_ids(tools, stamp, dub, events)
    results = {}
    for film, objects, root, bindings, gender, (_, speech) in tracks:
        selected = {event for event, _, _ in speech}
        if not selected <= media.keys():
            continue
        project = tools.parents[2] if tools.parent.name == 'endfield' and tools.parent.parent.name == 'data' else None
        decoder = vgmstream_executable(project)
        if decoder is None:
            raise PreparationFailure('missing_tools', 'Prepare the original voice decoder in Setup, then retry Endfield film preparation.')
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            audio, durations = {}, {}
            for event in sorted(selected):
                media_id = media[event]
                if media_id not in audio:
                    try:
                        data = release.media(tools, stamp, dub, media_id)
                    except release.UnmatchedRecording:
                        break
                    pcm = stack.enter_context(_decode(decoder, Path(folder), media_id, data))
                    audio[media_id] = pcm, sha256(data).hexdigest()
                pcm, _ = audio[media_id]
                _check(pcm.getsampwidth() == 2 and pcm.getnframes() > 0 and pcm.getframerate() > 0)
                durations[event] = pcm.getnframes() / pcm.getframerate()
            if len(durations) == len(selected):
                clips = director.track_clips(objects, root, conditions=bindings, gender=gender,
                                            durations=durations, complete=True)
                for event in sorted(selected):
                    media_id = media[event]
                    pcm, digest = audio[media_id]
                    for identity, row in _clock_rows(*clips, event, pcm):
                        _check((film, identity) not in results)
                        results[film, identity] = (*row, media_id, digest)
    return results


@lru_cache(maxsize=12)
def cues(tools, stamp, dub):
    """Keep completed cue maps per immutable edition, release, dub and reader version."""
    release.descriptor(tools, stamp)
    _check(dub in TRACKS)
    path = tools / 'endfield-releases' / 'cinematic-cues-v1' / stamp / (dub + '.json')
    prefix = (stamp + '/' + dub + '/cinematic-cues-v1\n').encode()
    if path.is_file() and path.stat().st_size <= 32 * 1024**2:
        content = path.read_bytes()
        checksum, _, body = content.partition(b'\n')
        if sha256(prefix + body).hexdigest().encode() == checksum:
            rows = json.loads(body)
            return {(film, identity): tuple(row) for film, identity, row in rows}
    result = _build(tools, stamp, dub)
    body = json.dumps([[film, identity, value] for (film, identity), value in sorted(result.items())],
                      separators=(',', ':')).encode()
    _atomic_file(path, sha256(prefix + body).hexdigest().encode() + b'\n' + body)
    return result
