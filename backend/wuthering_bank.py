"""Read a conservative Wwise-172 cinematic voice ownership graph.

Only original root Play actions and an explicit player_rover_gender state
select sources. This establishes ownership and source delay, not spoken cuts.
Exact immediate unrelated states, including state-only child events, are
retained without selecting a source.
Unsupported effects, random timing, state properties and RTPCs fail closed.
"""
from dataclasses import dataclass
import math
import struct

from .nte_assets import wwise_hash


@dataclass(frozen=True)
class SceneSource:
    media_id: int
    gender: str | None
    delay_ms: int
    authored_mute: bool = False
    fixed_states: tuple[tuple[int, int], ...] = ()


class _Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        if size < 0 or size > len(self.data) - self.offset:
            raise ValueError('Truncated cinematic bank')
        result = self.data[self.offset:self.offset + size]
        self.offset += size
        return result

    def number(self, format):
        return struct.unpack('<' + format, self.take(struct.calcsize('<' + format)))[0]

    def byte(self):
        return self.number('B')

    def uint(self):
        return self.number('I')

    def finish(self):
        _check(self.offset == len(self.data))


def _check(condition):
    if not condition:
        raise ValueError('Unsupported cinematic bank graph')


def _nodes(bank):
    _check(isinstance(bank, bytes) and len(bank) <= 8 * 1024 * 1024)
    reader, chunks = _Reader(bank), {}
    while reader.offset < len(bank):
        kind, size = reader.take(4), reader.uint()
        _check(kind not in chunks)
        chunks[kind] = reader.take(size)
    header = _Reader(chunks.get(b'BKHD', b''))
    _check(header.uint() == 172)
    reader = _Reader(chunks.get(b'HIRC', b''))
    count, result = reader.uint(), {}
    _check(count <= 10000)
    for _ in range(count):
        kind, size, key = reader.byte(), reader.uint(), reader.uint()
        _check(size >= 4 and key and key not in result)
        result[key] = kind, reader.take(size - 4)
    reader.finish()
    return result


def _base(reader, *, music=False, common_effects=None):
    _check(reader.byte() in (0, 1))  # Override parent effects.
    effects = reader.byte()
    _check(not music or effects == 0)
    if effects:
        # A zero-ID rendered slot is baked into the original source bytes.
        # Active plugins could change the source clock and are unsupported.
        _check(effects <= 4)
        bypass = reader.byte()
        slots = tuple(reader.take(6) for _ in range(effects))
        if not (effects == 1 and bypass == 0 and slots == (b'\0\0\0\0\0\x04',)):
            _check(common_effects is not None and bypass in (0, 1))
            _check(len({slot[0] for slot in slots}) == effects)
            for slot in slots:
                _check(slot[0] < 4 and slot[5] & ~1 == 0)
                common_effects(struct.unpack_from('<I', slot, 1)[0])
    _check(reader.byte() in (0, 1) and reader.byte() == 0)  # No metadata plugins.
    reader.uint()  # Output bus: it does not select a source.
    parent = reader.uint()
    _check(reader.byte() & ~3 == 0)  # Priority flags, no MIDI behavior.
    count = reader.byte()
    keys = reader.take(count)
    _check(len(set(keys)) == count and set(keys) <= ({0, 5, 6, 36, 43, 74} if music else {0, 5, 6, 36, 43}))
    properties = {key: reader.number('I' if music and key == 74 else 'f') for key in keys}
    _check(all(math.isfinite(value) for value in properties.values()))
    _check(not music or properties.get(74, 0) == 0)
    _check(reader.byte() == 0)  # No randomized property ranges.
    positioning = reader.byte()
    _check(positioning in (0, 3))
    if positioning == 3:
        _check(reader.byte() == 8)  # Listener routing, no positioning automation.
    auxiliary = reader.byte()
    _check(auxiliary & ~0x1c == 0)
    if auxiliary & 8:
        reader.take(16)
    reader.uint()  # Reflections bus.
    _check(reader.byte() in (0, 13) and reader.byte() == 1)
    _check(reader.number('H') in (0, 1))
    _check(reader.byte() == 0 and reader.byte() & ~15 == 0)
    _check(reader.byte() == 0 and reader.byte() == 0)  # No state-driven properties.
    _check(reader.number('H') == 0)  # No RTPC curves.
    milliseconds = properties.get(36, 0.) * 1000
    _check(0 <= milliseconds <= 300000 and abs(milliseconds - round(milliseconds)) < .001)
    volume, makeup = properties.get(0, 0.), properties.get(5, 0.)
    # Preserve ownership even for timing carriers. Playback eligibility is a
    # separate decision; an authored minimum fader must not become spoken audio.
    return parent, round(milliseconds), volume + makeup, min(volume, makeup) <= -96


def _children(reader):
    count = reader.uint()
    _check(count <= 10000)
    children = tuple(reader.uint() for _ in range(count))
    _check(all(children) and len(set(children)) == count)
    return children


def _node(kind, data, *, common=False, common_effects=None):
    reader = _Reader(data)
    media = None
    if kind == 2:
        _check(reader.take(5) == b'\x01\0\x14\0\x02')  # Streamed Opus WEM.
        media = reader.uint()
        reader.take(8)  # Source cache identifier and in-memory size.
        _check(media and reader.byte() == (8 if common else 9))  # Exact depot ownership.
    else:
        _check(kind in (6, 7))
    _check(common_effects is None or common)
    parent, delay, gain, muted = _base(reader, common_effects=common_effects)
    children, states = (), {}
    if kind == 6:
        _check(reader.byte() == 1 and reader.uint() == wwise_hash('player_rover_gender'))
        default = reader.uint()
        _check(default in (0, *(wwise_hash(name) for name in ('none', 'male', 'female')))
               and reader.byte() == 0)
        children = _children(reader)
        count = reader.uint()
        _check(count == 3)
        for _ in range(count):
            state = reader.uint()
            _check(state not in states)
            states[state] = _children(reader)
        male, female, none = (wwise_hash(name) for name in ('male', 'female', 'none'))
        _check(set(states) == {male, female, none}
               and len(states[male]) == len(states[female]) == 1
               and states[male] != states[female]
               and states[none] in ((), states[female])
               and set(children) == set(states[male] + states[female]))
        count = reader.uint()
        _check(count == len(children))
        parameters = set()
        for _ in range(count):
            child = reader.uint()
            _check(child in children and child not in parameters)
            parameters.add(child)
            _check(reader.take(9) == bytes(9))  # No first-only, continuation or fades.
    elif kind == 7:
        children = _children(reader)
    reader.finish()
    return parent, delay, media, children, states, gain, muted


def media_candidates(bank):
    """Candidate streamed IDs to check against real selected-dub members.

    This is an inventory filter, never a binding or a playable reference.
    """
    try:
        return frozenset(struct.unpack_from('<I', data, 5)[0]
                         for kind, data in _nodes(bank).values()
                         if kind == 2 and len(data) >= 18 and data[:5] == b'\x01\0\x14\0\x02')
    except (ValueError, TypeError, struct.error):
        return frozenset()


def _fixed_state(data):
    reader = _Reader(data)
    _check(reader.take(2) == b'\x04\x12')
    target = reader.uint()
    _check(target and reader.take(3) == bytes(3))  # Not a bus; no delay/ranges.
    group, value = reader.uint(), reader.uint()
    _check(group and value == target and group != wwise_hash('player_rover_gender'))
    reader.finish()
    return group, value


def _state_only_event(nodes, data, visited, depth=0):
    """Prove an immediate same-bank event closure contains only fixed states.

    Audio, stops, delayed actions, nonzero cooldown/instance limits, external
    events, cycles and repeated event traversal all remain unsupported. A
    bounded, unshared tree cannot hide an exponential or recursive expansion.
    """
    _check(depth < 8)
    action = _Reader(data)
    _check(action.take(2) == b'\x03\x21')
    target = action.uint()
    _check(target and action.take(3) == bytes(3))
    action.finish()
    _check(target not in visited and len(visited) < 16)
    visited.add(target)
    kind, data = nodes[target]
    _check(kind == 4)
    reader = _Reader(data)
    _check(reader.take(7) == bytes(7))
    count = reader.byte()
    _check(0 < count < 128)
    actions = [nodes[reader.uint()] for _ in range(count)]
    reader.finish()
    result = []
    for kind, data in actions:
        _check(kind == 3)
        if data[:2] == b'\x04\x12':
            result.append(_fixed_state(data))
        else:
            result.extend(_state_only_event(nodes, data, visited, depth + 1))
    return result


def _sources(bank, event, localized_media, *, common=False, root_actions=None):
    """Return proven sources in the selected dub, or no bindings on ambiguity.

    localized_media must come from actual members of that original dub depot.
    Gendered sources remain separate; an unconfigured player never selects a
    switch default. Event names and media IDs alone establish no association.
    """
    try:
        _check(isinstance(event, str) and 0 < len(event) <= 256)
        members = set(localized_media)
        _check(all(type(key) is int and 0 < key <= 0xffffffff for key in members))
        nodes = _nodes(bank)
        kind, data = nodes[wwise_hash(event)]
        _check(kind == 4)
        reader = _Reader(data)
        _check(reader.take(7) == bytes(7))
        count = reader.byte()
        _check(0 < count < 128)
        actions = [nodes[reader.uint()] for _ in range(count)]
        reader.finish()
        if root_actions is not None:
            _check(not common)
            actions = root_actions
        # Fixed immediate unrelated states cannot select these stateless source
        # paths. Every source/ancestor still rejects state properties and RTPCs;
        # the only supported selection group remains explicit Rover gender.
        # A same-bank immediate state-only event closure follows that same
        # contract. Audio/event delays and song states still fail.
        fixed_states = []
        state_events = {wwise_hash(event)}
        for action_kind, action_data in actions:
            _check(action_kind == 3 and len(action_data) >= 7)
            action_type = struct.unpack_from('<H', action_data)[0]
            _check(struct.unpack_from('<I', action_data, 2)[0] != 0)
            if action_type in (0x1204, 0x2103):
                _check(not common)
                if action_type == 0x1204:
                    fixed_states.append(_fixed_state(action_data))
                else:
                    fixed_states.extend(_state_only_event(nodes, action_data, state_events))
            else:
                _check(action_type in (0x0403, 0x0102, 0x0103))
        fixed_states = tuple(fixed_states)
        sources = []
        for key, (kind, data) in nodes.items():
            if kind != 2 or len(data) < 9 or struct.unpack_from('<I', data, 5)[0] not in members:
                continue
            path, current, gender, delay = [], key, None, 0
            gain, muted = 0., False
            while current:
                _check(current not in path)
                path.append(current)
                node_kind, node_data = nodes[current]
                parent, node_delay, media, children, states, node_gain, node_muted = _node(node_kind, node_data, common=common)
                gain += node_gain
                muted = muted or node_muted
                if current == key:
                    delay, source_media = node_delay, media
                else:
                    _check(node_delay == 0 and path[-2] in children)
                    if node_kind == 6:
                        _check(gender is None and len(path) == 2)
                        gender = next(name for name in ('male', 'female')
                                      if states[wwise_hash(name)] == (key,))
                current = parent
            target = path[1] if gender else key
            matches = 0
            for _, action in actions:
                if action[:2] in (b'\x04\x12', b'\x03\x21'):
                    continue  # Validated above; it cannot choose this path.
                destination = struct.unpack_from('<I', action, 2)[0]
                if destination not in path:
                    continue
                _check(destination == target)
                play = _Reader(action)
                _check(play.take(2) == b'\x03\x04' and play.uint() == target and play.byte() == 0)
                count = play.byte()
                _check(count in (0, 1) if common else count == 0)
                if count:
                    _check(play.byte() == 58)  # Wwise-172 action DelayTime, integer ms.
                    action_delay = play.uint()
                    _check(action_delay <= 300000)
                    delay += action_delay
                _check(play.byte() == 0 and play.byte() == 4
                       and play.uint() == wwise_hash(event) and play.uint() == 30)
                play.finish()
                matches += 1
            _check(matches == 1)
            sources.append(SceneSource(source_media, gender, delay, muted or gain <= -96, fixed_states))
        _check(len(sources) in (1, 2) and len(set(sources)) == len(sources)
              and ({source.gender for source in sources} == {None} if len(sources) == 1
                   else {source.gender for source in sources} == {'male', 'female'}))
        return tuple(sorted(sources, key=lambda source: source.gender or ''))
    except (ValueError, KeyError, StopIteration, struct.error, TypeError):
        return ()


def scene_sources(bank, event, localized_media):
    """Scene-clock sources must belong to the actual selected voice depot."""
    if not isinstance(event, str) or not 0 < len(event) <= 256:
        return ()
    try:
        localized_media = frozenset(localized_media)
    except TypeError:
        return ()
    sources = _sources(bank, event, localized_media)
    if sources:
        return sources
    try:
        from .wuthering_companion_audio import scene_actions
        actions = scene_actions(_nodes(bank), wwise_hash(event))
    except (ValueError, KeyError, TypeError, struct.error):
        return ()
    return _sources(bank, event, localized_media, root_actions=actions)


def song_sources(bank, event, common_media):
    """Single shared song synchronized by MusicSubtitle's source play position.

    A start delay changes wall time, not that source position. This separate
    contract never permits a delayed action in the ordinary scene-clock reader.
    Music tracks/playlists and player/state-dependent sources remain unresolved.
    """
    try:
        nodes = _nodes(bank)
        kind, data = nodes[wwise_hash(event)]
        _check(kind == 4)
        reader = _Reader(data)
        _check(reader.take(7) == bytes(7))
        actions = [nodes[reader.uint()] for _ in range(reader.byte())]
        reader.finish()
        _check(sum(kind == 3 and data[:2] == b'\x03\x04' for kind, data in actions) == 1)
    except (ValueError, KeyError, TypeError, struct.error):
        return ()
    sources = _sources(bank, event, common_media, common=True)
    return sources if len(sources) == 1 and sources[0].gender is None else ()
