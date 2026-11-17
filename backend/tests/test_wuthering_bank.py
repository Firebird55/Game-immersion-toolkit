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


def fixed_state(group=701, state=702, *, target=None, bus=0, props=bytes(2)):
    return b'\x04\x12' + u32(state if target is None else target) + bytes([bus]) + props + u32(group) + u32(state)


def test_immediate_fixed_unrelated_state_retains_evidence_without_selecting_voice_or_player():
    state = (701, 702)
    nodes = gendered() + [(3, 51, fixed_state(*state))]
    assert scene_sources(bank(nodes, actions=(51,50)), 'owned_scene', {101,102}) == (
        SceneSource(102,'female',0,False,(state,)),SceneSource(101,'male',0,False,(state,)))


@pytest.mark.parametrize('action',[
    fixed_state(group=wwise_hash('player_rover_gender')),fixed_state(group=0),
    fixed_state(target=900),fixed_state(bus=1),fixed_state(props=b'\x01\x3a'+u32(100)+b'\0'),
    fixed_state() + b'\0',fixed_state()[:-1],
])
def test_changed_player_delayed_malformed_or_unbounded_states_remain_unresolved(action):
    nodes=direct()+[(3,51,action)]
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


@pytest.mark.parametrize('tail',[
    bytes.fromhex('00000000000000010000000000000100'),
    bytes.fromhex('00000000000000010000000001000000'),
])
def test_unrelated_state_does_not_authorize_a_state_or_rtpc_driven_voice_path(tail):
    nodes=direct(tail=tail)+[(3,51,fixed_state())]
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


def test_fixed_scene_state_does_not_relax_shared_song_graphs():
    from backend.wuthering_bank import song_sources
    nodes=direct()+[(3,51,fixed_state())]
    nodes[0]=(2,10,nodes[0][2][:17]+b'\x08'+nodes[0][2][18:])
    assert not song_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


def event_node(identity, actions, initial=bytes(7)):
    return 4, identity, initial + bytes([len(actions)]) + b''.join(map(u32, actions))


def call_event(identity, *, tail=bytes(3)):
    return b'\x03\x21' + u32(identity) + tail


def state_event(leaf=None, call=None):
    return [(3,51,call_event(60) if call is None else call), event_node(60,[52]),
            (3,52,fixed_state() if leaf is None else leaf)]


def test_immediate_same_bank_state_only_event_keeps_both_explicit_player_sources():
    nodes=gendered()+state_event()
    assert scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101,102}) == (
        SceneSource(102,'female',0,False,((701,702),)),SceneSource(101,'male',0,False,((701,702),)))
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


def test_nested_state_only_events_retain_each_fixed_state_without_changing_source_clock():
    nodes=direct(delay=.5)+[(3,51,call_event(60)),event_node(60,[52,53]),
        (3,52,fixed_state()),(3,53,call_event(61)),event_node(61,[54]),(3,54,fixed_state(801,802))]
    assert scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101}) == (
        SceneSource(101,None,500,False,((701,702),(801,802))),)


@pytest.mark.parametrize('leaf', [
    play(10), b'\x03\x01'+u32(10)+bytes(10),
    fixed_state(group=wwise_hash('player_rover_gender')), fixed_state(group=0),
    fixed_state(target=0),fixed_state(target=900),fixed_state(bus=1),
    fixed_state(props=b'\x01\x3a'+u32(100)+b'\0'),
    fixed_state(props=b'\0\x01\x3a'+u32(100)+u32(100)),
    fixed_state()+b'\0',fixed_state()[:-1],
])
def test_child_audio_stop_rover_delays_ranges_or_malformed_states_are_never_ignored(leaf):
    assert not scene_sources(bank(direct()+state_event(leaf),actions=(51,50)), 'owned_scene',{101})


@pytest.mark.parametrize('tail', [b'\x01\0\0',b'\0\x01\x3a'+u32(100)+b'\0',
                                  b'\0\0\x01\x3a'+u32(100)+u32(100),bytes(4),bytes(2)])
def test_play_event_itself_requires_exact_immediate_no_bus_or_random_properties(tail):
    nodes=direct()+state_event(call=call_event(60,tail=tail))
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


@pytest.mark.parametrize('change',['missing-event','wrong-event-kind','missing-action','wrong-action-kind',
                                  'empty-event','cooldown','instance-limit','extra-event-bytes'])
def test_complete_child_event_metadata_and_references_are_required(change):
    nodes=direct()+state_event()
    if change=='missing-event':nodes.pop(-2)
    elif change=='wrong-event-kind':nodes[-2]=(3,60,nodes[-2][2])
    elif change=='missing-action':nodes.pop()
    elif change=='wrong-action-kind':nodes[-1]=(2,52,nodes[-1][2])
    elif change=='empty-event':nodes[-2]=event_node(60,[])
    elif change=='cooldown':nodes[-2]=event_node(60,[52],bytes(3)+struct.pack('<f',1))
    elif change=='instance-limit':nodes[-2]=event_node(60,[52],b'\0\x01'+bytes(5))
    else:nodes[-2]=(4,60,nodes[-2][2]+b'\0')
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


@pytest.mark.parametrize('cycle',['self','root','two-events','repeated-event'])
def test_event_cycles_or_shared_repeated_traversal_cannot_expand_or_select_a_source(cycle):
    nodes=direct()+state_event()
    if cycle=='self':nodes[-1]=(3,52,call_event(60))
    elif cycle=='root':nodes[-1]=(3,52,call_event(wwise_hash('owned_scene')))
    elif cycle=='two-events':nodes[-1]=(3,52,call_event(61));nodes += [event_node(61,[53]),(3,53,call_event(60))]
    else:nodes[-2]=event_node(60,[52,53,54]);nodes[-1]=(3,52,call_event(61));nodes += [
        (3,53,call_event(61)),(3,54,fixed_state()),event_node(61,[55]),(3,55,fixed_state(801,802))]
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})


@pytest.mark.parametrize('levels,accepted',[(8,True),(9,False)])
def test_state_event_depth_is_bounded_even_without_a_cycle(levels,accepted):
    nodes=direct()+[(3,51,call_event(1000))]
    for offset in range(levels):
        aid=2000+offset
        nodes += [event_node(1000+offset,[aid]),
                  (3,aid,fixed_state() if offset==levels-1 else call_event(1001+offset))]
    assert bool(scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101}))==accepted


@pytest.mark.parametrize('events,accepted',[(15,True),(16,False)])
def test_total_event_node_budget_is_independent_of_shallow_depth(events,accepted):
    nodes=direct();actions=[50]
    for offset in range(events):
        aid,event,leaf=1000+offset,2000+offset,3000+offset;actions.append(aid)
        nodes += [(3,aid,call_event(event)),event_node(event,[leaf]),(3,leaf,fixed_state())]
    assert bool(scene_sources(bank(nodes,actions=actions), 'owned_scene',{101}))==accepted


@pytest.mark.parametrize('tail',[bytes.fromhex('00000000000000010000000000000100'),
                                  bytes.fromhex('00000000000000010000000001000000')])
def test_child_states_do_not_relax_any_voice_ancestor_state_or_rtpc_guard(tail):
    assert not scene_sources(bank(direct(tail=tail)+state_event(),actions=(51,50)), 'owned_scene',{101})


def test_state_only_child_events_do_not_enable_shared_song_states_or_scene_play_delays():
    from backend.wuthering_bank import song_sources
    nodes=direct()+state_event();nodes[0]=(2,10,nodes[0][2][:17]+b'\x08'+nodes[0][2][18:])
    assert not song_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})
    nodes=direct()+state_event();nodes[2]=(3,50,play(10)[:7]+b'\x01\x3a'+u32(100)+play(10)[8:])
    assert not scene_sources(bank(nodes,actions=(51,50)), 'owned_scene',{101})
