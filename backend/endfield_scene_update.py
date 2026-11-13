"""Follow a scene prefab's actual directors to its localized subtitles and original voice."""
from functools import partial
import json
import math
import re

from . import endfield_director as director, endfield_film_update as films


def _local(pointer):
    return pointer['m_PathID'] if pointer and pointer['m_FileID'] == 0 else None


def _target(externals, pointer):
    return (films._cab(externals, pointer), pointer['m_PathID']) if pointer else (None, None)


def _director_graph(prefab):
    _, root, objects, external = prefab
    transforms = {obj['m_GameObject']['m_PathID']: key for key, obj in objects.items()
                  if 'm_Father' in obj and 'm_Children' in obj}
    pending = [transforms[root]] if root in transforms else []
    active = {}
    visited = set()
    while pending:
        identity = pending.pop()
        if identity in visited or identity not in objects:
            return None
        visited.add(identity)
        transform = objects[identity]
        owner = _local(transform['m_GameObject'])
        game_object = objects.get(owner, {})
        if not game_object.get('m_IsActive'):
            continue
        components = [_local(p['component']) for p in game_object.get('m_Component', ())]
        if identity not in components:
            return None
        choices = [objects[k] for k in components if k in objects and 'm_PlayableAsset' in objects[k]
                   and objects[k].get('m_Enabled') and _local(objects[k]['m_GameObject']) == owner]
        if len(choices) > 1:
            return None
        if choices:
            active[owner] = choices[0]
        for child in transform['m_Children']:
            key = _local(child)
            if key not in objects or _local(objects[key].get('m_Father')) != identity:
                return None
            pending.append(key)
    return active, external


def _control_windows(master, prefab, expected):
    cab, root, objects, _ = master
    graph = _director_graph(prefab)
    if not graph:
        return None
    active, external = graph
    parents = [obj for obj in active.values() if _target(external, obj['m_PlayableAsset']) == (cab, root)]
    if len(parents) != 1 or parents[0].get('m_InitialTime') != 0:
        return None
    pairs = parents[0]['m_ExposedReferences']['m_References']
    exposed = {p['first']: _local(p['second']) for p in pairs}
    if len(exposed) != len(pairs):
        return None
    windows = {}
    for ptr in objects[root].get('m_Tracks', ()):
        track = objects.get(_local(ptr), {})
        role = track.get('m_Name')
        if role not in expected:
            if not track.get('m_Muted') and (role not in {'Actor', 'Light', 'Effect'} or track.get('m_Children')):
                return None
            continue
        if (role in windows or track.get('m_Muted') or track.get('m_Children')
                or _local(track.get('m_Parent')) != root or len(track.get('m_Clips', ())) != 1):
            return None
        clip, = track['m_Clips']
        asset = objects.get(_local(clip['m_Asset']), {})
        source = asset.get('sourceGameObject', {})
        child = active.get(exposed.get(source.get('exposedName')))
        if (not child or child.get('m_InitialTime') != 0 or _target(external, child['m_PlayableAsset']) != expected[role]
                or asset.get('m_Name') != 'ControlPlayableAsset' or not asset.get('updateDirector')
                or not asset.get('active') or asset.get('useAutoBinding') or asset.get('directorControlPath')
                or asset.get('searchHierarchy') or asset.get('prefabGameObject', {}).get('m_PathID')
                or source.get('defaultValue', {}).get('m_PathID') or clip.get('m_TimeScale') != 1
                or clip.get('m_ClipIn') != 0):
            return None
        start, duration = clip['m_Start'], clip['m_Duration']
        if not math.isfinite(start + duration) or start < 0 or duration <= 0:
            return None
        windows[role] = (start, start + duration)
    return windows if windows.keys() == expected.keys() else None


def _scene_clips(caption_track, audio_track, windows, *, durations=None):
    layers = []
    for role, asset in [('Others', caption_track), ('Audio', audio_track)]:
        _, root, objects, _ = asset
        clips = director.track_clips(objects, objects[root], durations=durations, complete=True)
        if not clips:
            return None
        captions, speech = clips
        if (role == 'Others' and speech) or (role == 'Audio' and captions):
            return None
        start, end = windows[role]
        rows = captions if role == 'Others' else speech
        # A caption cut off by its parent can overlap another visible sentence.
        # Dropping only that caption would make the other one look unambiguous.
        if role == 'Others' and any(start + a < end and start + b > end + 0.00001 for _, a, b in rows):
            return None
        layers.append([(key, round(start + a, 5), round(min(end, start + b), 5)) for key, a, b in rows
                       if start + a < end])
    return tuple(layers)


def tracks(tools, files, dub, unchanged):
    column, suffixes = films.TRACKS[dub]
    for config_path in files:
        match = re.fullmatch(re.escape(films.SCENES) + r'((?:[fm]_)?cutscene_[a-z0-9_]+)\.asset', config_path)
        if not match or (scene := match[1]) in unchanged:
            continue
        base = films.DIRECTORS + scene + '/'
        name = base + 'playable/' + scene
        desc = base + scene + '.json'
        prefab_path = base + 'prefab/' + scene + '.prefab'
        master_path, audio_path, default_path = name + '.playable', name + '_audio.playable', name + '_others.playable'
        if not {desc, prefab_path, master_path, audio_path, default_path} <= files.keys():
            continue
        def asset(path, classes=(114,)):
            return films._asset(tools, files[path], path, classes=classes)
        _, key, configs, external = asset(config_path)
        cfg = configs[key]
        if cfg.get('cutsceneID') != scene:
            continue
        config = cfg['config']
        schema = config['audioLangKey2SubtitleTrack']
        local = dict(zip(schema['_keys'], schema['_values'], strict=True))
        if len(local) != len(schema['_keys']):
            continue
        default = asset(default_path)
        if _target(external, config['defaultPlayable']) != default[:2]:
            continue
        ref = _target(external, local.get(column, config['defaultPlayable'] if column == 0 else None))
        candidates = [default] if column == 0 else [asset(name + '_others_au_' + suffix + '.playable')
                     for suffix in suffixes if name + '_others_au_' + suffix + '.playable' in files]
        selected = [candidate for candidate in candidates if candidate[:2] == ref]
        if len(selected) != 1:
            continue
        audio = asset(audio_path)
        _, key, texts, _ = asset(desc, (49,))
        data = json.loads(texts[key]['m_Script'])
        if (data.get('cutsceneName') != scene or str(data.get('path', '')).lower() + '.prefab' != prefab_path
                or data.get('crossSubsequenceReferenceData')):
            continue
        graph = asset(prefab_path, (1, 4, 320))
        windows = _control_windows(asset(master_path), graph, {'Audio': audio[:2], 'Others': default[:2]})
        if not windows:
            continue
        read = partial(_scene_clips, selected[0], audio, windows)
        clips = read()
        declared = {key for key in data.get('audioEvents', ()) if key.lower().startswith('au_vo_')}
        if clips and all(clips) and {e for e, _, _ in clips[1]} == declared:
            yield scene, clips, read
