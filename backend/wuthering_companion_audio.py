"""Prove that a bounded common-music companion cannot change a scene voice.

This does not select, export or render interactive music. Every source and
inherited node is parsed, even where an unposted ancestor's selector is not
executed. A selector is interpreted only below an actual Play target. Unknown
executed leaves, callbacks and dynamic voice properties fail closed. A static
stock compressor is accepted only on a proven common-only SFX subtree; this
establishes the independent original voice source, never a game mixer render.
"""
import math
import struct

from .nte_assets import wwise_hash
from .wuthering_bank import _Reader, _base, _check, _children, _node


def _finite(reader, kind='d'):
    value = reader.number(kind)
    _check(math.isfinite(value) and abs(value) <= 1e12)
    return value


def _list(reader):
    count = reader.uint()
    _check(count <= 128)
    return tuple(reader.uint() for _ in range(count))


def _transitions(reader):
    targets = []
    count = reader.uint()
    _check(count <= 128)
    for _ in range(count):
        targets.extend(_list(reader))
        targets.extend(_list(reader))
        reader.take(12)  # Source fade, interpolation and offset: music only.
        _check(reader.uint() <= 9)
        reader.uint()  # Cue hash, never an event.
        _check(reader.byte() in (0, 1))
        reader.take(12)  # Destination fade.
        reader.uint()  # Destination cue hash.
        targets.append(reader.uint())
        _check(reader.number('H') <= 4 and reader.number('H') <= 9)
        _check(reader.byte() in (0, 1) and reader.byte() in (0, 1))
        _check(reader.byte() == 0)  # No transition object.
    return targets


def _music(kind, data):
    reader = _Reader(data)
    leaves, references = [], []
    if kind == 11:
        count = reader.uint()
        _check(0 < count <= 32)
        media = set()
        for _ in range(count):
            _check(reader.take(5) == b'\x01\0\x14\0\x02')
            identity = reader.uint()
            _check(identity and identity not in media)
            media.add(identity)
            reader.take(8)
            _check(reader.byte() == 8)  # Common streamed Opus, never a dub.
        _check(reader.byte() == 0)  # No MIDI target/tempo override.
        count = reader.uint()
        _check(0 < count <= 128)
        for _ in range(count):
            reader.uint()  # Subtrack index, no external invocation.
            _check(reader.uint() in media)
            reader.uint()  # Source cache ID.
            _check(reader.uint() == 0)  # No event clip/callback.
            for _ in range(4):
                _finite(reader)
        _check(0 < reader.uint() <= 128 and reader.uint() == 0)  # No automation.
        parent, *_ = _base(reader, music=True)
        children = ()
        _check(reader.byte() == 0 and 0 <= reader.number('i') <= 300000)
    else:
        _check(kind in (10, 12, 13) and reader.byte() in (0, 6))
        parent, *_ = _base(reader, music=True)
        children = _children(reader)
        _check(len(children) <= 128)
        _finite(reader)
        _finite(reader)
        _check(0 < _finite(reader, 'f') <= 1000)
        _check(0 < reader.byte() <= 32 and 0 < reader.byte() <= 32)
        _check(reader.byte() in (0, 1) and reader.uint() == 0)  # No stingers.
        if kind == 10:
            duration, count = _finite(reader), reader.uint()
            _check(duration > 0 and count <= 128)
            for _ in range(count):
                reader.uint()
                _check(0 <= _finite(reader) <= duration)
                marker = bytearray()
                while True:
                    value = reader.byte()
                    if not value:
                        break
                    marker.append(value)
                    _check(len(marker) <= 512)
                marker.decode('utf8')
        else:
            references.extend(_transitions(reader))
            if kind == 12:
                _check(reader.byte() in (0, 1))
                depth = reader.uint()
                _check(depth <= 4)
                arguments = tuple(reader.uint() for _ in range(depth))
                _check(all(arguments) and wwise_hash('player_rover_gender') not in arguments)
                _check(all(reader.byte() in (0, 1) for _ in range(depth)))
                size = reader.uint()
                _check(0 < size <= 128 * 12 and size % 12 == 0)
                _check(reader.byte() in (0, 1))
                tree, visited = reader.take(size), set()

                def visit(index, level):
                    _check(0 <= index < size // 12 and index not in visited)
                    visited.add(index)
                    _, destination, _, probability = struct.unpack_from('<IIHH', tree, index * 12)
                    _check(probability <= 100)
                    if level == depth:
                        leaves.append(destination)  # Unresolved values stay unresolved.
                    else:
                        first, count = destination & 65535, destination >> 16
                        _check(count > 0 and first + count <= size // 12)
                        keys = [struct.unpack_from('<I', tree, i * 12)[0] for i in range(first, first + count)]
                        _check(len(set(keys)) == len(keys))
                        for i in range(first, first + count):
                            visit(i, level + 1)

                visit(0, 0)
                _check(len(visited) == size // 12)
            else:
                count, visited = reader.uint(), 0
                _check(0 < count <= 128)

                def item(depth=0):
                    nonlocal visited
                    _check(depth < 8 and visited < count)
                    visited += 1
                    segment, _, nchildren, mode = (reader.uint() for _ in range(4))
                    reader.number('h')  # Music-only loop count.
                    _check(reader.number('h') == 0 and reader.number('h') == 0)
                    reader.uint()  # Playlist weight.
                    reader.number('H')  # Avoid repeats.
                    _check(reader.byte() in (0, 1) and reader.byte() in (0, 1))
                    _check(nchildren <= 128)
                    if nchildren:
                        _check(segment == 0 and mode in (0, 1, 2, 3))
                        for _ in range(nchildren):
                            item(depth + 1)
                    else:
                        _check(mode == 0xffffffff and segment in children)
                        leaves.append(segment)

                item()
                _check(visited == count and set(leaves) == set(children))
    reader.finish()
    return parent, children, tuple(leaves), tuple(references)


def _action(data):
    reader = _Reader(data)
    kind, target = reader.number('H'), reader.uint()
    _check(target and reader.byte() == 0)  # Exact object scope, never a bus.
    count = reader.byte()
    _check(count <= 2)
    keys = reader.take(count)
    _check(len(set(keys)) == count and set(keys) <= {58, 59})
    properties = dict(zip(keys, (reader.uint() for _ in keys)))
    _check(all(value <= 300000 for value in properties.values()) and reader.byte() == 0)
    return reader, kind, target, properties


def scene_actions(nodes, root):
    """Return only the unchanged immediate root sound actions after full proof."""
    music, ordinary, posted, stops, events = {}, {}, [], [], set()
    common_sources, localized_sources, effect_nodes = set(), set(), set()

    def static_compressor(key):
        kind, raw = nodes[key]
        _check(kind == 17)
        reader = _Reader(raw)
        _check(reader.uint() == 0x006c0003 and reader.uint() == 31)
        for _ in range(7):
            _finite(reader, 'f')
        _check(all(reader.byte() in (0, 1) for _ in range(3)))
        # No plugin media, RTPC, state properties/groups or property curves.
        _check(reader.take(7) == bytes(7))
        reader.finish()


    def hierarchy(key, path=()):
        _check(key not in path and len(path) < 16)
        if key in music or key in ordinary:
            return
        _check(len(music) + len(ordinary) < 128)
        kind, data = nodes[key]
        if kind in (10, 11, 12, 13):
            value = _music(kind, data)
            music[key] = value
        else:
            _check(kind in (2, 6, 7))
            base_offset = 18 if kind == 2 else 0
            _check(len(data) > base_offset + 1)
            effects = data[base_offset + 1] != 0
            if effects:
                effect_nodes.add(key)
            common = effects or kind == 2 and data[17] == 8
            value = _node(kind, data, common=common,
                          common_effects=static_compressor if effects else None)
            ordinary[key] = value
            if kind == 2:
                (common_sources if common else localized_sources).add(key)
                _check(common or value[1] == 0)  # This new context route starts the voice at scene zero.
        parent, children = (value[0], value[1]) if key in music else (value[0], value[3])
        if parent:
            hierarchy(parent, path + (key,))
            container = music.get(parent) or ordinary.get(parent)
            declared = container[1] if parent in music else container[3]
            _check(key in declared)
        for child in children:
            # Parent backlinks are checked separately; allow that declared edge
            # without treating the ordinary parent/child pair as a graph cycle.
            if child not in music and child not in ordinary:
                hierarchy(child)
            child_value = music.get(child) or ordinary.get(child)
            _check(child_value[0] == key)

    def event(key, delay=0, depth=0):
        _check(depth < 8 and key not in events and len(events) < 16)
        events.add(key)
        kind, data = nodes[key]
        _check(kind == 4)
        reader = _Reader(data)
        _check(reader.take(7) == bytes(7))
        count = reader.byte()
        _check(0 < count < 128)
        actions = [nodes[reader.uint()] for _ in range(count)]
        reader.finish()
        retained = []
        for kind, data in actions:
            _check(kind == 3)
            action, operation, target, properties = _action(data)
            elapsed = delay + properties.get(58, 0)
            _check(elapsed <= 300000)
            if operation == 0x2103:
                _check(set(properties) <= {58})
                action.finish()
                event(target, elapsed, depth + 1)
            elif operation == 0x0103:
                _check(action.byte() == 4 and action.byte() & ~6 == 0)
                _check(action.byte() == 0)  # Exact empty exception list.
                action.finish()
                hierarchy(target)
                _check(target in music)
                stops.append(target)
            else:
                _check(operation == 0x0403 and set(properties) <= {58})
                _check(action.byte() == 4 and action.uint() == root and action.uint() == 30)
                action.finish()
                hierarchy(target)
                if target in music:
                    posted.append(target)
                else:
                    _check(depth == 0 and elapsed == 0 and not properties)
                    retained.append((kind, data))
        return retained

    retained = event(root)
    _check(posted and stops and retained)
    # Every declared inherited child is common music; no stopped or played
    # subtree can share a localized source/ancestor. No external hierarchy.
    _check(not set(music) & set(ordinary))
    for key, (parent, children, _, references) in music.items():
        _check((not parent or parent in music) and all(child in music for child in children))
        _check(all(target in (0, 0xffffffff) or target in music for target in references))
    for parent, _, _, children, *_ in ordinary.values():
        _check((not parent or parent in ordinary) and all(child in ordinary for child in children))
    for key in (*music, *ordinary):
        path = set()
        while key:
            _check(key not in path and len(path) < 16)
            path.add(key)
            key = (music.get(key) or ordinary[key])[0]
    # Effects on another posted branch cannot authorize effects on the voice.
    # Follow every declared descendant, rather than relying on node ordering.
    def descendants(key, path=()):
        _check(key not in path and len(path) < 16)
        children = ordinary[key][3]
        return {key} | set().union(*(descendants(child, path + (key,)) for child in children))

    for key in effect_nodes:
        affected = descendants(key)
        _check(affected & common_sources and not affected & localized_sources)
    executed = set()

    def execute(key):
        if key in executed:
            return
        executed.add(key)
        _, children, leaves, _ = music[key]
        _check(all(leaf in children for leaf in leaves))
        for child in children:
            execute(child)

    for key in posted:
        execute(key)
    return retained
