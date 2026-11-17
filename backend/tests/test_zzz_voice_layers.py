"""Owned Wwise135 fixtures; no publisher assets or captured recordings."""
import struct

import pytest

from backend.honkai_assets import BankSource
from backend.nte_assets import wwise_hash
from backend.zzz_voice_layers import unconditional_voice_layers


def variable(value):
    parts = [value & 127]
    while value > 127:
        value >>= 7
        parts.append(128 | (value & 127))
    return bytes(reversed(parts))


def base(parent, *, bus=0, gain=None, property_id=0, states=0, randomized=False, rtpc=False, aux=False):
    data = bytes(3) + struct.pack('<IIB', bus, parent, 0)
    data += bytes(1) if gain is None else struct.pack('<BBf', 1, property_id, gain)
    data += bytes([int(randomized), 0, int(aux)]) + bytes(4) + bytes([0, 1]) + bytes(4)
    if states:
        data += bytes([1, 0, 2, 1, 1]) + struct.pack('<IB', 900, 0) + variable(states)
        data += b''.join(struct.pack('<II', 1000 + i, 80) for i in range(states))
    else:
        data += bytes(2)
    return data + struct.pack('<H', int(rtpc))


def source(identity, parent, *, localized=True, **options):
    return struct.pack('<IIBIIB', identity, 262145, 0, 123 if localized else 456, 104, int(localized)) + base(parent, **options)


def play(identity, target, action=0x0403):
    return struct.pack('<IHI', identity, action, target) + bytes([0, 0, 0, 4]) + struct.pack('<I', 77)


def stop_bus(identity=42, target=70, *, bus=True, prop=16, flags=6, exceptions=0):
    return struct.pack('<IHIBBBiBBBB', identity, 0x0102, target, int(bus), 1, prop, 1000, 0, 4, flags, exceptions)


def objects_with_bus_stop(**options):
    objects = synthetic_objects()
    objects[42] = (3, stop_bus(**options))
    event = wwise_hash('Play_ActualLayer')
    objects[event] = (4, struct.pack('<IBIII', event, 3, 40, 41, 42))
    return objects


def synthetic_objects(event='Play_ActualLayer', *, gain=-3., states=0, state_volume=-5., voice_options=None):
    return {
        10: (2, source(10, 20, **(voice_options or {}))),
        20: (7, struct.pack('<I', 20) + base(0, bus=66, gain=gain, states=states) + struct.pack('<II', 1, 10)),
        30: (2, source(30, 0, localized=False, bus=67)),
        40: (3, play(40, 10)), 41: (3, play(41, 30)),
        80: (1, struct.pack('<IHHf', 80, 1, 0, state_volume)),
        wwise_hash(event): (4, struct.pack('<IBII', wwise_hash(event), 2, 40, 41)),
    }


@pytest.mark.parametrize('states', [0, 2, 130])
def test_original_direct_localized_stem_is_independent_of_other_play_roots_and_volume_states(states):
    objects = synthetic_objects(states=states)
    result = unconditional_voice_layers(objects)
    assert result == {wwise_hash('Play_ActualLayer'): BankSource(123, 0, 104)}
    # Other unrelated, separately posted voices in a future larger bank are not this event.
    objects[60] = (2, source(60, 0, bus=68))
    assert unconditional_voice_layers(objects) == result


@pytest.mark.parametrize('options', [
    {'gain': -94., 'states': 2}, {'states': 2, 'state_volume': -96.},
    {'voice_options': {'gain': 1., 'property_id': 2}},
    {'voice_options': {'gain': 1., 'property_id': 15}},
    {'voice_options': {'gain': 1., 'property_id': 36}},
    {'voice_options': {'randomized': True}}, {'voice_options': {'rtpc': True}}, {'voice_options': {'aux': True}},
])
def test_inaudible_state_pitch_delay_trim_randomness_and_rtpc_do_not_certify_a_whole_take(options):
    assert unconditional_voice_layers(synthetic_objects(**options)) == {}


@pytest.mark.parametrize('case', ['stop', 'duplicate_voice', 'indirect_voice', 'wrong_child', 'cycle', 'missing_parent', 'voice_switch', 'conditional_other_voice', 'effects'])
def test_action_player_and_reciprocal_parent_ambiguities_remain_unresolved(case):
    objects = synthetic_objects()
    if case == 'stop':
        objects[41] = (3, play(41, 30, 0x0102))
    elif case == 'duplicate_voice':
        objects[41] = (3, play(41, 10))
    elif case == 'indirect_voice':
        objects[40] = (3, play(40, 20))
    elif case == 'wrong_child':
        objects[20] = (7, objects[20][1][:-4] + struct.pack('<I', 999))
    elif case == 'cycle':
        objects[20] = (7, struct.pack('<I', 20) + base(20, bus=66) + struct.pack('<II', 1, 10))
    elif case == 'missing_parent':
        objects[10] = (2, source(10, 999))
    elif case == 'voice_switch':
        objects[20] = (6, objects[20][1])
    elif case == 'conditional_other_voice':
        objects[30] = (6, struct.pack('<I', 30) + base(0, bus=67))
        objects[60] = (2, source(60, 30))
    else:
        raw = objects[10][1]
        objects[10] = (2, raw[:19] + b'\x01' + raw[20:])
    assert unconditional_voice_layers(objects) == {}


def test_global_bus_stop_needs_the_original_separate_routing_graph():
    objects = objects_with_bus_stop()
    assert unconditional_voice_layers(objects) == {}
    assert unconditional_voice_layers(objects, {66: 80, 70: 80, 80: 0}) == {
        wwise_hash('Play_ActualLayer'): BankSource(123, 0, 104)}
    assert unconditional_voice_layers(objects, {66: 70, 70: 0}) == {}
    objects[10] = (2, source(10, 20, bus=99))
    assert unconditional_voice_layers(objects, {66: 80, 99: 80, 70: 80, 80: 0}) == {}


@pytest.mark.parametrize('options', [{'bus': False}, {'prop': 15}, {'flags': 7}, {'exceptions': 1}])
def test_stop_delay_unknown_flags_and_exceptions_cannot_bypass_original_voice_routing(options):
    assert unconditional_voice_layers(objects_with_bus_stop(**options), {66: 80, 70: 80, 80: 0}) == {}
