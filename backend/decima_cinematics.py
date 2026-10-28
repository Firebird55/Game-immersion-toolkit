"""Authored original-PC sequence → subtitle events → complete voice tracks.

SortedEvents are the engine's flattened sequence graph, including referenced
sequences. Subtitle pause frames are not assumed to be speech cut boundaries.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math

from .decima_archive import Cursor, invalid, safe_path
from .decima_dialogue import reference

SEQUENCE = 0x81C9E9F0A678A560
SORTED = 0x5E846155971FA4DE
SUBTITLE = 0x17F5B6C706FE44CC
WEM_EVENT = 0x3DA75F66D26BF3C6
WEM_SOUND = 0x8F8BA50D8B46CE52
WEM_LOCALIZED = 0x3DE345CD4B0C7E72
KNOWN = {SEQUENCE, SORTED, SUBTITLE, WEM_EVENT, WEM_SOUND, WEM_LOCALIZED}


def _refs(cursor):
    return [reference(cursor) for _ in range(cursor.count(100_000))]


def _sequence(body):
    c = Cursor(body)
    c.take(2 + 16 + 5)  # EntityResource flags, UUID, name hash, update frequency
    reference(c); reference(c)
    c.take(3); reference(c)
    c.take(10); reference(c); reference(c)
    _refs(c)  # entity components
    c.string()  # sequence name
    c.take(32)  # camera/loop flags and interpolation fields
    c.string()
    c.take(8)
    _refs(c)  # editor's unflattened events
    for _ in range(c.count(100_000)):
        reference(c); c.string(); c.string()  # exposed attributes
    stop, = c.unpack('i')
    events = _refs(c)
    _refs(c); _refs(c)
    c.take(7); reference(c); c.string(); c.take(13)
    c.finish()
    if not 0 <= stop <= 10_000_000:
        raise invalid('Unsupported Death Stranding sequence duration.')
    return {'stop': stop, 'events': events}


def _sorted(body):
    c = Cursor(body)
    c.take(20)
    participate, = c.unpack('B')
    event = reference(c)
    c.take(16)
    _refs(c); _refs(c); c.finish()
    if participate not in (0, 1):
        raise invalid('Unsupported Death Stranding sequence participation.')
    return event if participate else None


def _subtitle(body):
    c = Cursor(body)
    c.take(16)
    start, enabled, end = c.unpack('iBi')
    sentence = reference(c)
    pausing, fade_in, fade_out = c.unpack('Bii')
    c.finish()
    if enabled not in (0, 1) or pausing not in (0, 1) or min(start, end, fade_in, fade_out) < 0:
        raise invalid('Unsupported Death Stranding subtitle event.')
    return {'start': start, 'end': end, 'enabled': enabled, 'sentence': sentence}


def _wem_event(body):
    c = Cursor(body)
    c.take(16)
    start, enabled, end = c.unpack('iBi')
    reference(c)
    spatial, fade, destroy, duration, timing, movie, pause = c.unpack('BBBfBBB')
    sound = reference(c)
    c.finish()
    if (any(value not in (0, 1) for value in (enabled, spatial, fade, destroy, timing, movie, pause))
            or start < 0 or end < -1 or not math.isfinite(duration)):
        raise invalid('Unsupported Death Stranding cinematic audio event.')
    return {'start': start, 'end': end, 'enabled': enabled, 'sound': sound, 'spatial': spatial}


def _wem_sound(body):
    c = Cursor(body)
    c.take(16); c.string(); reference(c); c.take(137)
    result = reference(c)
    c.finish()
    return result


def _localized(body):
    c = Cursor(body)
    streaming, = c.unpack('B')
    c.take(16 + 8)
    c.take(c.count(64 * 1024 * 1024))
    flags, duration, mask = c.unpack('HfI')
    if streaming != 1 or not math.isfinite(duration) or duration <= 0 or mask >> 26:
        raise invalid('Unsupported Death Stranding cinematic voice resource.')
    result = {}
    for language in range(26):
        if not mask & (1 << language):
            continue
        path = safe_path(c.string(hashed=False))
        identity = c.take(16).hex()
        channel, offset, length, _unknown = c.unpack('IIIQ')
        if not path.startswith('ds/sounds/') or not 0 < length <= 256 * 1024 * 1024:
            raise invalid('Invalid Death Stranding cinematic voice extent.')
        result[language] = {'stream': path + '.core.stream', 'uuid': identity,
            'channel': channel, 'offset': offset, 'length': length}
    c.finish()
    return result


def objects(data):
    c, result = Cursor(data), {}
    while c.pos < len(data):
        kind, size = c.unpack('QI')
        body = c.take(size)
        if kind not in KNOWN:
            continue
        start = 2 if kind == SEQUENCE else 1 if kind == WEM_LOCALIZED else 0
        if len(body) < start + 16:
            raise invalid('Truncated Death Stranding cinematic identity.')
        identity = body[start:start + 16].hex()
        if identity in result:
            raise invalid('Duplicate Death Stranding cinematic identity.')
        result[identity] = (kind, body)
    return result


class SceneReader:
    def __init__(self, packs):
        self.packs, self.cache = packs, {}

    def load(self, path):
        if path not in self.cache:
            if len(self.cache) > 8:
                self.cache.clear()
            self.cache[path] = objects(self.packs.read(path + '.core'))
        return self.cache[path]

    def get(self, current, ref, expected=None):
        if ref is None:
            return None
        path, identity = ref
        path = path or current
        if not self.packs.has(path + '.core'):
            return None
        obj = self.load(path).get(identity)
        if obj is None:
            return None  # unneeded event types are deliberately not parsed
        if expected is not None and obj[0] != expected:
            return None
        return (path, identity, *obj)

    def groups(self, path, locale, language_id):
        result = []
        for sequence_id, (kind, body) in list(self.load(path).items()):
            if kind != SEQUENCE:
                continue
            sequence = _sequence(body)
            captions, audio = [], []
            for ref in sequence['events']:
                ordered = self.get(path, ref, SORTED)
                if ordered is None:
                    raise invalid('Missing Death Stranding flattened sequence event.')
                event = self.get(ordered[0], _sorted(ordered[3]))
                if event is None:
                    continue
                event_path, event_id, event_kind, event_body = event
                if event_kind == SUBTITLE:
                    caption = _subtitle(event_body)
                    if caption['enabled'] and caption['sentence']:
                        ref_path, identity = caption['sentence']
                        captions.append({**caption, 'sentence': (ref_path or event_path, identity)})
                elif event_kind == WEM_EVENT:
                    track = _wem_event(event_body)
                    if not track['enabled'] or track['spatial']:
                        continue
                    sound = self.get(event_path, track['sound'], WEM_SOUND)
                    wem = self.get(sound[0], _wem_sound(sound[3]), WEM_LOCALIZED) if sound else None
                    source = _localized(wem[3]).get(language_id) if wem else None
                    if wem:
                        binding = ({'kind': 'scene', 'core': path, 'sequence': sequence_id,
                            'track_event': event_id, 'locale': locale, **source} if source else None)
                        # An absent pack/recording still participates in overlap
                        # analysis; it cannot make a competing track unambiguous.
                        audio.append((track, binding))
            for track, binding in audio:
                if binding is None or not self.packs.has(binding['stream']):
                    continue
                end = track['end'] if track['end'] >= 0 else sequence['stop']
                contained = [caption for caption in captions if track['start'] <= caption['start'] < caption['end'] <= end]
                # More than one localized source occupying this caption's
                # interval needs mixing/branch context, so it remains unresolved.
                contained = [caption for caption in contained if sum(
                    other['start'] <= caption['start'] < caption['end'] <= (other['end'] if other['end'] >= 0 else sequence['stop'])
                    for other, _binding in audio) == 1]
                if contained:
                    result.append((binding, [caption['sentence'] for caption in sorted(contained, key=lambda row: row['start'])]))
        return result


def scene_bindings(packs, links, locale, language_id, progress):
    reader, groups, counts = SceneReader(packs), [], Counter()
    candidates = [path for path, dependencies in links.items()
        if not path.startswith('ds/cinematics/trials/') and
        any(item.startswith('localized/sentences/ds_lines_cutscene/') for item in dependencies) and
        any(item.startswith('ds/sounds/wwise_cinematics_sound_resource/') for item in dependencies)]
    for number, path in enumerate(candidates):
        if not packs.has(path + '.core'):
            continue
        if number % 20 == 0:
            progress(f'Reading Death Stranding cinematic event graphs ({number}/{len(candidates)})')
        counts['cinematic_graph_resources'] += 1
        groups.extend(reader.groups(path, locale, language_id))
    # The same scene can be embedded in several level resources. Only identical
    # authored source plus sentence order is deduplicated; conflicting sources
    # are not chosen by filenames or archive enumeration order.
    unique, sources_by_sentence = {}, defaultdict(set)
    for audio, sentences in groups:
        source = tuple(audio[key] for key in ('stream', 'uuid', 'offset', 'length'))
        unique.setdefault((source, tuple(sentences)), (audio, sentences))
        for sentence in sentences:
            sources_by_sentence[sentence].add(source)
    by_source = defaultdict(list)
    for (source, _sentences), value in unique.items():
        if all(len(sources_by_sentence[sentence]) == 1 for sentence in value[1]):
            by_source[source].append(value)
    result = []
    for alternatives in by_source.values():
        longest = max(alternatives, key=lambda value: len(value[1]))
        if all([sentence for sentence in longest[1] if sentence in shorter[1]] == shorter[1]
               for shorter in alternatives):
            result.append(longest)
        else:
            counts['cinematic_conflicting_caption_orders'] += 1
    counts['cinematic_complete_track_groups'] = len(result)
    counts['cinematic_conflicting_sentence_sources'] = sum(len(value) > 1 for value in sources_by_sentence.values())
    return result, counts
