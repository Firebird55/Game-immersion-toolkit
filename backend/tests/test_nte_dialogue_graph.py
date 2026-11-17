"""Owned original-style graph references; no downloaded text or game blobs."""
import copy

import pytest

from backend import nte_dialogue_graph as graph
from backend.tests.test_nte_seeded_schema import seed

TABLE = '/Game/Text/Renamed.Renamed'
NAMESPACES = {TABLE: 'Actual_Conversation'}


def text(key):
    return {'TableId': TABLE, 'Key': key}


def edge(target):
    return {'TargetIndex': target, 'EdgeIndex': -1, 'Conditions': [], 'TextArguments': [], 'EdgeData': None,
            'Text': {'Namespace': 'DlgSystem', 'Key': 'edge_next'}}


def fixture():
    package = '/Game/Dialogue/Owned'
    def ref(index, kind, name):
        return {'ObjectPath': f'{package}.{index}', 'ObjectName': f"{kind}'Owned:{name}'"}
    def node(kind, name, props):
        return {'Type': kind, 'Name': name, 'Outer': {'ObjectPath': package+'.0'}, 'Properties': props}
    nodes = [node('DlgNode_Speech', 'Speech0', {'Text': text('First'), 'Children': [edge(1)]}),
             node('DlgNode_Speech', 'Speech1', {'Text': text('Short'), 'Children': [edge(2)]}),
             node('DlgNode_End', 'End', {})]
    root = {'Type': 'DlgDialogue', 'Name': 'Owned', 'Package': package, 'Properties': {
        'Nodes': [ref(i+2, item['Type'], item['Name']) for i, item in enumerate(nodes)],
        'StartNodes': [ref(1, 'DlgNode_Start', 'Start')]}}
    return [{'asset': 'HT/Content/Dialogue/Owned.uasset',
             'exports': [root, node('DlgNode_Start', 'Start', {'Children': [edge(0)]}), *nodes]}]


def test_exact_original_namespace_and_direct_graph_reference_supply_the_pair():
    packets = fixture()
    assert graph.direct_pairs(packets, NAMESPACES) == (('nte:Actual_Conversation:First', 'nte:Actual_Conversation:Short'),)
    assert graph.direct_pairs(packets, {}) == ()


@pytest.mark.parametrize('change', ['condition', 'event', 'edge_condition', 'label', 'option', 'order',
                                    'branch', 'fan_in', 'loop', 'sequence', 'reuse', 'proxy'])
def test_no_branch_condition_event_choice_sequence_or_repeated_occurrence_is_skipped(change):
    packets = fixture(); exports = packets[0]['exports']
    source, target = exports[2]['Properties'], exports[3]['Properties']
    if change == 'condition': target['EnterConditions'] = [{'ConditionType': 'Unknown'}]
    elif change == 'event': source['EnterEvents'] = [{'EventType': 'Unknown'}]
    elif change == 'edge_condition': source['Children'][0]['Conditions'] = [{}]
    elif change == 'label': source['Children'][0]['Text'] = text('Option')
    elif change == 'option': source['Children'][0]['EdgeIndex'] = 0
    elif change == 'order': target['SequenceActorConfigs'] = [{'PlaybackOrder': '0'}]
    elif change == 'branch': source['Children'].append(edge(2))
    elif change == 'fan_in': exports[1]['Properties']['Children'].append(edge(1))
    elif change == 'loop': exports[0]['Properties']['bCanLoop'] = True
    elif change == 'sequence': target['SequenceInfo'] = {'UnresolvedSequence': 1}
    elif change == 'reuse': exports.append({'Type': 'Other', 'Properties': {'Text': text('First')}})
    else:
        exports[3]['Type'] = 'DlgNode_Proxy'
        exports[0]['Properties']['Nodes'][1]['ObjectName'] = "DlgNode_Proxy'Owned:Speech1'"
    assert graph.direct_pairs(packets, NAMESPACES) == ()


def test_participant_name_cache_and_future_target_choices_do_not_execute_at_current_entry():
    packets = fixture(); exports = packets[0]['exports']
    exports[0]['Properties']['ParticipantsData'] = [{'Key': 'Actor', 'Value': {'Events': ['EventElsewhere'],
        'Conditions': ['ConditionElsewhere']}}]
    exports[3]['Properties']['Children'][0]['Conditions'] = [{'ConditionName': 'LaterChoice'}]
    exports.append({'Type': 'Other', 'Properties': {'Text': text('Short')}})
    assert graph.direct_pairs(packets, NAMESPACES) == (('nte:Actual_Conversation:First', 'nte:Actual_Conversation:Short'),)


def test_unresolved_namespace_with_reused_key_blocks_a_guessed_target_owner():
    packets = fixture()
    packets[0]['exports'].append({'Type': 'Other', 'Properties': {'Text': {'TableId': ' ', 'Key': 'Short'}}})
    assert not graph.direct_pairs(packets, NAMESPACES | {' ': None})


@pytest.mark.parametrize('layout', ['direct', 'nested', 'inherited', 'array'])
def test_new_anonymous_enum_is_not_interpreted_regardless_of_property_name(layout):
    packets = fixture(); props = packets[0]['exports'][3]['Properties']
    if layout == 'direct':
        metadata = seed([('DlgNode_Speech', None, [('NewMode', 1, (26, (0,), None))])])
        props['NewMode'] = '0'
    elif layout == 'inherited':
        metadata = seed([('DlgNode', None, [('NewMode', 1, (26, (0,), None))]), ('DlgNode_Speech', 'DlgNode', [])])
        props['NewMode'] = '0'
    else:
        shape = (9, 'Config') if layout == 'nested' else (8, (9, 'Config'))
        metadata = seed([('DlgNode_Speech', None, [('Config', 1, shape)]),
                         ('Config', None, [('NewMode', 1, (26, (0,), None))])])
        props['Config'] = {'NewMode': '0'} if layout == 'nested' else [{'NewMode': '0'}]
    assert not graph.direct_pairs(packets, NAMESPACES, schema_usmap=metadata)


def test_known_enum_literal_is_distinct_from_anonymous_integer_preservation():
    packets = fixture()
    packets[0]['exports'][3]['Properties']['NewMode'] = 'Mood::Calm'
    metadata = seed([('DlgNode_Speech', None, [('NewMode', 1, (26, (0,), 'Mood'))])])
    assert graph.direct_pairs(packets, NAMESPACES, schema_usmap=metadata)


@pytest.mark.parametrize('props', [{}, {'Config': {}}, {'Config': [{'NewMode': '0'}]}])
def test_omitted_inline_enum_defaults_and_static_arrays_have_no_invented_order_semantics(props):
    packets = fixture(); packets[0]['exports'][3]['Properties'].update(props)
    metadata = seed([('DlgNode_Speech', None, [('Config', 2, (9, 'Config'))]),
                     ('Config', None, [('NewMode', 1, (26, (0,), None))])])
    assert not graph.direct_pairs(packets, NAMESPACES, schema_usmap=metadata)


@pytest.mark.parametrize('change', ['owner', 'missing', 'root', 'target', 'duplicate'])
def test_incomplete_or_broken_reference_fails_the_preparation(change):
    packets = fixture(); exports = packets[0]['exports']
    if change == 'owner': exports[3]['Outer']['ObjectPath'] = '/Game/Other.0'
    elif change == 'missing': exports.pop()
    elif change == 'root': exports[0]['Type'] = 'UnknownRoot'
    elif change == 'target': exports[2]['Properties']['Children'][0]['TargetIndex'] = 99
    else: packets.append(copy.deepcopy(packets[0]))
    with pytest.raises(ValueError): graph.direct_pairs(packets, NAMESPACES)


def row(key, *, gender=None, status='voiced', kind='conversation'):
    return {'text_id': f'nte:Actual_Conversation:{key}' + (':'+gender if gender else ''),
            'audio': {'depot': key}, 'voice_status': status, 'dialogue_kind': kind,
            **({'player_voice': gender} if gender else {})}


def test_annotations_preserve_existing_audio_and_match_original_player_voice_variants():
    pairs = graph.direct_pairs(fixture(), NAMESPACES)
    records = [row(key, gender=gender) for key in ('First', 'Short') for gender in ('male', 'female')]
    originals = [r['audio'].copy() for r in records]
    assert graph.annotate(records, pairs) is records
    assert [r['audio'] for r in records] == originals
    assert all(r.get('previous_text_id') == 'nte:Actual_Conversation:First:'+r['player_voice']
               for r in records if ':Short:' in r['text_id'])
    # Exercise the actual normal worker's record-validation boundary. Context
    # metadata must use the shared persisted contract, not private extra keys.
    from backend.local_game import LocalDialogue
    validated = [LocalDialogue(english='', chinese='', **r) for r in records]
    assert all(not r.requires_previous for r in validated)


@pytest.mark.parametrize('status,kind', [('unknown', 'conversation'), ('unavailable', 'conversation'),
                                       ('unvoiced', 'conversation'), ('voiced', 'ambient_dialogue')])
def test_context_does_not_reclassify_unresolved_or_other_presentations(status, kind):
    records = [row('First'), row('Short', status=status, kind=kind)]
    graph.annotate(records, graph.direct_pairs(fixture(), NAMESPACES))
    assert not any('previous_text_id' in r for r in records)
