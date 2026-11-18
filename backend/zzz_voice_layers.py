"""Conservative Wwise135 unconditional localized stems inside film events.

The original event may also start effects/controller output. Its one selected
language-specific Sound must be posted directly, with an unconditional mixer
ancestry. Bus Stops need complete original routing; other controls stay unknown.
"""
import math
import struct

from .wwise_tables import BankSource
from .zzz_bus_routing import separate_stop_buses


def _check(condition):
    if not condition:
        raise ValueError('Unsupported original ZZZ localized voice-layer graph.')


class _Reader:
    def __init__(self, data, start=0):
        self.data, self.position = data, start

    def take(self, size):
        _check(0 <= size <= len(self.data) - self.position)
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def byte(self):
        return self.number('B')

    def uint(self):
        return self.number('I')

    def count(self):
        value = 0
        for _ in range(5):
            byte = self.byte()
            value = value * 128 + (byte & 127)
            _check(value <= 10000)
            if byte < 128:
                return value
        raise ValueError('Unsupported original ZZZ variable integer.')

    def end(self):
        _check(self.position == len(self.data))


def _source(payload):
    _check(len(payload) >= 18 and struct.unpack_from('<I', payload, 4)[0] & 15 == 1)
    _check(payload[8] in (0, 1, 2) and payload[17] & ~0x8b == 0)
    return BankSource(struct.unpack_from('<I', payload, 9)[0], payload[8], struct.unpack_from('<I', payload, 13)[0])


def _parent(kind, payload):
    _check(kind in (2, 5, 6, 7, 9))
    reader = _Reader(payload, 18 if kind == 2 else 4)
    reader.byte()
    effects = reader.byte()
    if effects:
        reader.byte()
        reader.take(effects * 7)  # Wwise135: slot, effect ID, share-set, rendered.
    reader.byte()
    reader.uint()
    return reader.uint()


def _volume_state(payload):
    reader = _Reader(payload, 4)
    count = reader.number('H')
    _check(count <= 1)
    keys = [reader.number('H') for _ in range(count)]
    _check(keys in ([], [0]))  # State RTPC parameter zero is volume.
    values = [reader.number('f') for _ in keys]
    _check(all(math.isfinite(value) and -96 < value < 24 for value in values))
    reader.end()
    return sum(values)


def _base(payload, start, objects):
    reader = _Reader(payload, start)
    _check(reader.byte() in (0, 1) and reader.byte() == 0 and reader.byte() == 0)
    bus, parent, priority = reader.uint(), reader.uint(), reader.byte()
    _check(priority & ~3 == 0)
    keys = reader.take(reader.byte())
    _check(len(set(keys)) == len(keys) and set(keys) <= {0, 6})  # Volume/makeup gain only.
    values = [reader.number('f') for _ in keys]
    _check(all(math.isfinite(value) and -96 < value < 24 for value in values))
    gain = sum(values)
    _check(reader.byte() == 0)  # No random property ranges.
    positioning = reader.byte()
    _check(positioning in (0, 3))
    if positioning == 3:
        _check(reader.byte() == 8)  # Static listener routing.
    _check(reader.byte() == 0 and reader.uint() == 0)  # No auxiliary/reflection effects.
    _check(reader.byte() in (0, 1, 13) and reader.byte() == 1 and reader.number('H') == 0
           and reader.byte() == 0 and reader.byte() == 0)
    properties = [(reader.count(), reader.byte(), reader.byte()) for _ in range(reader.count())]
    _check(properties in ([], [(0, 2, 1)]))  # Only additive volume in dB.
    minimum = gain
    for _ in range(reader.count()):
        reader.uint()  # State group identity; no state selects a different source.
        _check(reader.byte() == 0)
        states, seen = [0.], set()
        for _ in range(reader.count()):
            state, instance = reader.uint(), reader.uint()
            _check(state not in seen and instance in objects and objects[instance][0] == 1)
            seen.add(state)
            states.append(_volume_state(objects[instance][1]))
        _check(properties == [(0, 2, 1)])
        minimum += min(states)
    _check(reader.number('H') == 0)  # No RTPC curves.
    return reader, parent, bus, minimum


def _voice_chain(objects, sound):
    current, child, seen, minimum, routed = sound, None, set(), 0., []
    while current:
        _check(current not in seen and current in objects and len(seen) < 128)
        seen.add(current)
        kind, payload = objects[current]
        _check(kind == (2 if child is None else 7))
        reader, parent, bus, gain = _base(payload, 18 if kind == 2 else 4, objects)
        minimum += gain
        if bus:
            routed.append(bus)
        if kind == 7:
            count = reader.uint()
            _check(count <= 10000)
            children = [reader.uint() for _ in range(count)]
            _check(len(set(children)) == count and child in children)
        reader.end()
        child, current = current, parent
    _check(routed and minimum > -96)
    return seen, routed


def _stop_bus(payload):
    reader = _Reader(payload, 4)
    _check(reader.number('H') == 0x0102)
    target = reader.uint()
    _check(reader.byte() == 1)  # Global Stop targeting an audio bus.
    properties = reader.byte()
    _check(properties in (0, 1))
    if properties:
        _check(reader.byte() == 0x10 and 0 <= reader.number('i') <= 86400000)  # Transition time only.
    _check(reader.byte() == 0 and reader.byte() <= 9)  # No random ranges; known fade curve.
    _check(reader.byte() & ~6 == 0 and reader.count() == 0)  # Known Stop flags, no exceptions.
    reader.end()
    return target


def unconditional_voice_layers(objects, buses=None):
    """One direct localized take; other Play roots cannot contain another voice.

    This deliberately does not simulate controller output, effects or music.
    Global bus Stops require the original Init-bank routing to exclude the
    complete voice ancestry. Other controls and conditional voices stay unknown.
    """
    _check(len(objects) <= 10000)
    sounds = {}
    for identity, (kind, payload) in objects.items():
        if kind == 2:
            sounds[identity] = (_source(payload), bool(payload[17] & 1))
    result = {}
    for event, (kind, payload) in objects.items():
        if kind != 4 or len(payload) < 5:
            continue
        try:
            count = payload[4]
            _check(2 <= count <= 64 and len(payload) == 5 + count * 4)
            actions = [struct.unpack_from('<I', payload, 5 + index * 4)[0] for index in range(count)]
            _check(len(set(actions)) == count)
            targets, stopped = [], []
            for action in actions:
                action_kind, body = objects.get(action, (0, b''))
                _check(action_kind == 3 and len(body) >= 6)
                if struct.unpack_from('<H', body, 4)[0] == 0x0102:
                    stopped.append(_stop_bus(body))
                    continue
                _check(action_kind == 3 and len(body) == 18 and struct.unpack_from('<H', body, 4)[0] == 0x0403
                       and body[10:14] == b'\0\0\0\x04')
                target = struct.unpack_from('<I', body, 6)[0]
                _check(target in objects and objects[target][0] in (2, 5, 6, 7, 9))
                targets.append(target)
            voiced = [target for target in targets if target in sounds and sounds[target][1]]
            _check(len(voiced) == 1)
            voice, = voiced
            chain, routed = _voice_chain(objects, voice)
            if stopped:
                separate_stop_buses(buses, routed, stopped)
            others = list(targets)
            others.remove(voice)
            _check(not set(others) & chain)
            for sound, (_, localized) in sounds.items():
                if not localized or sound == voice:
                    continue
                seen, current = set(), sound
                while current:
                    _check(current not in seen and current in objects and len(seen) < 128 and current not in others)
                    seen.add(current)
                    current = _parent(*objects[current])
            result[event] = sounds[voice][0]
        except (ValueError, struct.error):
            continue
    return result
