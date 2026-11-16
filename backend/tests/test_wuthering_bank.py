"""Synthetic ownership graphs; no publisher bank or recording fixtures."""
import struct

import pytest

from backend.nte_assets import wwise_hash
from backend.wuthering_bank import SceneSource, scene_sources


def u32(value):
    return struct.pack('<I', value)


def children(values):
    return u32(len(values)) + b''.join(map(u32, values))


def base(parent=0, *, delay=0, properties=None, tail=None):
    properties = properties or ({36: delay} if delay else {})
    props = bytes([len(properties), *properties]) + b''.join(struct.pack('<f', x) for x in properties.values())
    # No effects/metadata, routing, random ranges, state properties or RTPCs.
    return (bytes(4) + u32(0) + u32(parent) + b'\0' + props + b'\0'
            + (tail if tail is not None else bytes.fromhex('00000000000000010000000000000000')))


def sound(media, parent, **options):
    return b'\x01\0\x14\0\x02' + u32(media) + bytes(8) + b'\x09' + base(parent, **options)


def play(target, event='owned_scene'):
    return b'\x03\x04' + u32(target) + b'\0\0\0\x04' + u32(wwise_hash(event)) + u32(30)


def bank(nodes, actions=(50,), event='owned_scene', version=172):
    nodes = [*nodes, (4, wwise_hash(event), bytes(7) + bytes([len(actions)]) + b''.join(map(u32, actions)))]
    hierarchy = u32(len(nodes)) + b''.join(bytes([kind]) + u32(len(data) + 4) + u32(key) + data
                                           for kind, key, data in nodes)
    def chunk(kind, data):
        return kind + u32(len(data)) + data
    return chunk(b'BKHD', u32(version) + u32(wwise_hash(event))) + chunk(b'HIRC', hierarchy)


def direct(*, delay=0, properties=None, tail=None):
    return [(2, 10, sound(101, 20, delay=delay, properties=properties, tail=tail)),
            (7, 20, base() + children([10])), (3, 50, play(10))]


def gendered(*, group='player_rover_gender', default='female', none=(11,), fades=bytes(9)):
    states = [(wwise_hash('male'), (10,)), (wwise_hash('female'), (11,)), (wwise_hash('none'), none)]
    switch = (base(20) + b'\x01' + u32(wwise_hash(group)) + u32(wwise_hash(default)) + b'\0'
              + children([10, 11]) + u32(3)
              + b''.join(u32(state) + children(items) for state, items in states)
              + u32(2) + u32(10) + fades + u32(11) + fades)
    return [(2, 10, sound(101, 30)), (2, 11, sound(102, 30)), (6, 30, switch),
            (7, 20, base() + children([30])), (3, 50, play(30))]


def test_exact_root_and_localized_members_establish_ownership_and_delay():
    data = bank(direct(delay=.5))
    assert scene_sources(data, 'owned_scene', {101}) == (SceneSource(101, None, 500),)
    assert not scene_sources(data, 'same_named_other_scene', {101})
    assert not scene_sources(data, 'owned_scene', {999})


@pytest.mark.parametrize('source_props,parent_props', [
    ({0: -96}, {}), ({5: -96}, {}), ({}, {0: -96}),
    ({0: -48}, {0: -48}), ({0: -96}, {5: 96}),
])
def test_muted_timing_carriers_keep_source_ownership_without_an_audible_claim(source_props, parent_props):
    nodes = direct(properties=source_props)
    nodes[1] = (7, 20, base(properties=parent_props) + children([10]))
    assert scene_sources(bank(nodes), 'owned_scene', {101}) == (SceneSource(101, None, 0, True),)


def test_unselected_language_or_music_source_is_never_inferred_from_hash():
    nodes = direct() + [(2, 90, b'bad!!' + u32(303) + b'unsupported unrelated sound')]
    assert scene_sources(bank(nodes), 'owned_scene', {101}) == (SceneSource(101, None, 0),)
    assert not scene_sources(bank(nodes), 'owned_scene', {101, 303})


@pytest.mark.parametrize('default', ['none', 'female', 'male'])
@pytest.mark.parametrize('none', [(), (11,)])
def test_gender_states_stay_explicit_even_when_native_default_is_female(default, none):
    actual = scene_sources(bank(gendered(default=default, none=none)), 'owned_scene', {101, 102})
    assert actual == (SceneSource(102, 'female', 0), SceneSource(101, 'male', 0))
    assert all(source.gender is not None for source in actual)
    # One missing member cannot silently collapse a gender switch to a default.
    assert not scene_sources(bank(gendered(default=default, none=none)), 'owned_scene', {101})


@pytest.mark.parametrize('options', [
    {'properties': {2: 100}},  # Pitch changes source clock.
    {'properties': {35: 2}},  # PlaybackSpeed changes source clock.
    {'properties': {74: 0}},  # Loop property.
    {'delay': float('nan')}, {'delay': float('inf')}, {'delay': -.5}, {'delay': .00001},
    {'tail': bytes.fromhex('00000000000000010000000000000100')},  # RTPC count.
    {'tail': bytes.fromhex('00000000000000010000000001000000')},  # State property count.
])
def test_unknown_or_dynamic_timing_fails_closed(options):
    assert not scene_sources(bank(direct(**options)), 'owned_scene', {101})


@pytest.mark.parametrize('options', [
    {'group': 'other_player_state'}, {'none': (10, 11)}, {'fades': b'\x01' + bytes(8)},
])
def test_other_switches_or_nontrivial_transitions_are_not_gender_proof(options):
    assert not scene_sources(bank(gendered(**options)), 'owned_scene', {101, 102})


@pytest.mark.parametrize('action_type', [0x1204, 0x2103, 0x0103])
def test_other_root_actions_cannot_change_or_stop_a_proven_source(action_type):
    nodes = direct() + [(3, 51, struct.pack('<H', action_type) + u32(10) + bytes(12))]
    assert not scene_sources(bank(nodes, actions=(50, 51)), 'owned_scene', {101})


def test_playing_twice_or_at_unknown_delay_is_not_one_source_clock():
    assert not scene_sources(bank(direct(), actions=(50, 50)), 'owned_scene', {101})
    nodes = direct()
    nodes[-1] = (3, 50, play(10) + b'\0')
    assert not scene_sources(bank(nodes), 'owned_scene', {101})


def test_parent_chain_and_declared_child_must_agree():
    nodes = direct()
    nodes[1] = (7, 20, base() + children([999]))
    assert not scene_sources(bank(nodes), 'owned_scene', {101})
    nodes[1] = (7, 20, base(20) + children([10, 20]))
    assert not scene_sources(bank(nodes), 'owned_scene', {101})


def test_malformed_banks_duplicate_objects_and_unsupported_versions_fail_closed():
    data = bank(direct())
    for cut in range(len(data)):
        assert not scene_sources(data[:cut], 'owned_scene', {101})
    assert not scene_sources(data + b'junk', 'owned_scene', {101})
    assert not scene_sources(bank(direct() + [direct()[0]]), 'owned_scene', {101})
    assert not scene_sources(bank(direct(), version=173), 'owned_scene', {101})
    assert not scene_sources(data, 'owned_scene', {True})
