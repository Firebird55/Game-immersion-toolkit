"""Training roles never let left objectives select a bottom instruction."""
from copy import deepcopy
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from backend.endfield_training_presentation import (SOURCE_ROLES, compile_training_dialogue,
    observe_training_dialogue, validate_training_dialogue_ui)
from backend.tests.test_endfield_sns_presentation import span
from backend.tests.test_subtitle_capture import fixture_service
from backend.multilingual_index import MultilingualTextIndex
from backend.capture import _ScanOutcome


STAMP = 'endfield-' + '2' * 64
PREFIX = 'endfield:DungeonCharTutorialStepTable:'


def fixture():
    rows = []
    for identity, text, translation in [('future_a', 'Use the battle skill to protect the ally.', 'First translation'),
                                        ('future_b', 'Use the battle skill to protect the ally.', 'Other translation')]:
        rows.append({'text_id': PREFIX + identity, 'texts': {'en': text, 'fr': translation},
            'source_locale': 'en', 'source_text': text, 'voice_status': 'unvoiced', 'audio': None,
            'audio_locale': 'en',
            'text_capture_verified': True, 'dialogue_kind': 'tutorial_step', 'channels': ['tip']})
    metadata = {'schema': 1, 'revision': STAMP, 'sources': {role: 'a' * 32 for role in SOURCE_ROLES},
        'locales': {'en': {'titles': {'future_owner_a': ['Operator Guide: First'],
                                     'future_owner_b': ['Operator Guide: Second']},
                          'labels': {rows[0]['text_id']: 'Battle Skill', rows[1]['text_id']: 'Ultimate'},
                          'profile': ['Voice Information', 'Profile']}},
        'stages': [{'owner': 'future_owner_a', 'stage': 1, 'text_ids': [rows[0]['text_id'], rows[0]['text_id'] + '_tail']},
                   {'owner': 'future_owner_b', 'stage': 3, 'text_ids': [rows[1]['text_id'], rows[1]['text_id'] + '_tail']}],
        'goals': [{'owner': 'future_owner_a', 'texts': {'en': rows[0]['source_text']}}]}
    for row in list(rows):
        tail = deepcopy(row)
        tail['text_id'] += '_tail'
        tail['texts'] = {'en': 'A different complete training instruction.', 'fr': 'Tail translation'}
        tail['source_text'] = tail['texts']['en']
        rows.append(tail)
        metadata['locales']['en']['labels'][tail['text_id']] = 'Combo Skill'
    return metadata, rows


def frame():
    return [span('Operator Guide: First', 80, 250, 600),
            span('Battle Skill', 850, 105, 100), span('Combo Skill', 958, 105, 100),
            span('Use the battle skill to protect the ally.', 400, 820, 1120)]


def observe(metadata=None, rows=None, spans=None, **kwargs):
    original, records = fixture()
    compiled = compile_training_dialogue(metadata or original, rows or records, 'en')
    return observe_training_dialogue(compiled, frame() if spans is None else spans, (1920, 1080), **kwargs)


def test_exact_owner_complete_bottom_and_controls_select_all_original_fields():
    metadata, rows = fixture()
    before = deepcopy(rows)
    proof = observe(metadata, rows)
    assert [hit['text_id'] for hit in proof['steps']] == [rows[0]['text_id']]
    assert proof['body_groups'] == [rows[0]['source_text']]
    assert rows == before


@pytest.mark.parametrize('mutation', ['header', 'partial_body', 'control', 'confidence', 'no_box',
    'left_role', 'missing_control', 'profile', 'paragraph', 'wrong_lane'])
def test_complete_roles_and_real_ocr_evidence_are_required(mutation):
    spans = frame()
    if mutation == 'header':
        spans[0]['text'] = 'Operator Guide: Changed owner'
    elif mutation == 'partial_body':
        spans[-1]['text'] = 'Use the battle skill'
    elif mutation == 'control':
        spans[1]['text'] = 'Battle'
    elif mutation == 'confidence':
        spans[1]['confidence'] = .79
    elif mutation == 'no_box':
        spans[0].pop('bounding_rect')
    elif mutation == 'left_role':
        spans[-1] = span(spans[-1]['text'], 70, 400, 750)
    elif mutation == 'missing_control':
        del spans[1]
    elif mutation == 'profile':
        spans += [span('Voice Information', 500, 300), span('Profile', 500, 350)]
    elif mutation == 'paragraph':
        spans += [span('An unrelated paragraph begins here', 400, 790, 1120)]
    elif mutation == 'wrong_lane':
        spans[1] = span(spans[1]['text'], 850, 450, 100)
    assert not observe(spans=spans)['steps']


def test_left_goal_cannot_become_a_step_or_predecessor_even_with_same_english():
    spans = frame()
    spans[-1] = span(spans[-1]['text'], 70, 400, 750)
    spans += [span('0/1', 830, 400, 50)]
    proof = observe(spans=spans)
    assert not proof['steps'] and not proof['body_groups']
    assert proof['goal_only_caption_keys']
    assert not observe(dialogue_menu=True)['steps']


@pytest.mark.parametrize('field,value', [('voice_status', 'unknown'), ('voice_status', 'unavailable'),
    ('requires_previous', True), ('previous_text_id', 'different_original_predecessor'),
    ('audio', {'missing_original': 'not_silence'}), ('text_binding_unresolved', True),
    ('text_capture_verified', False), ('channels', ['dialogue']), ('texts', {'en': 'Use the battle skill to protect the ally.', 'fr': 'Another take'})])
def test_clipped_longer_stage_conflicts_retain_every_original_field(field, value):
    metadata, rows = fixture()
    peer = deepcopy(rows[0])
    peer['text_id'] = PREFIX + 'future_longer_peer'
    peer[field] = value
    rows.append(peer)
    config = metadata['locales']['en']
    config['labels'][peer['text_id']] = 'Battle Skill'
    metadata['stages'].append({'owner': 'future_owner_a', 'stage': 20,
                              'text_ids': [peer['text_id'], rows[2]['text_id'], rows[1]['text_id']]})
    # The first two controls can also be the visible window of this longer
    # manually scrolled stage. Its absent tail cannot establish another take.
    assert not observe(metadata, rows)['steps']


def test_other_kind_same_caption_is_a_conflict_not_an_unvoiced_identity():
    metadata, rows = fixture()
    peer = deepcopy(rows[0])
    peer.update(text_id='endfield:InstructionBook:future', dialogue_kind='document')
    rows.append(peer)
    assert not observe(metadata, rows)['steps']
    assert not observe(metadata, rows)['body_groups']


@pytest.mark.parametrize('damage', ['hash', 'revision', 'missing_row', 'duplicate_stage', 'template'])
def test_descriptor_validation_fails_closed(damage):
    metadata, rows = fixture()
    if damage == 'hash':
        metadata['sources']['step_ctrl'] = 'not-a-hash'
    elif damage == 'revision':
        metadata['revision'] = 'unbound'
    elif damage == 'missing_row':
        metadata['stages'][0]['text_ids'].append(PREFIX + 'absent')
    elif damage == 'duplicate_stage':
        metadata['stages'].append(deepcopy(metadata['stages'][0]))
    else:
        metadata['locales']['en']['titles']['future_owner_a'] = ['Operator Guide: {owner}']
    with pytest.raises(ValueError):
        compile_training_dialogue(metadata, rows, 'en')


def test_schema_canonicalization_preserves_ordered_stage_ids():
    metadata, _ = fixture()
    assert validate_training_dialogue_ui(metadata)['stages'][0]['text_ids'] == metadata['stages'][0]['text_ids']


def write_index(directory, *, metadata=None, rows=None):
    original, records = fixture()
    directory.mkdir(exist_ok=True)
    (directory/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en',
        'fingerprint': STAMP, 'publisher_training_dialogue_ui': metadata or original,
        'records': rows or records}), encoding='utf8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready, index.message
    index.capture_unvoiced = True
    return index


def test_index_keeps_all_translations_and_voice_status_without_modifying_rows(tmp_path):
    metadata, rows = fixture()
    index = write_index(tmp_path, metadata=metadata, rows=rows)
    assert not index.match_unvoiced_lines([rows[0]['source_text']])
    result = index.match_endfield_training_dialogue(frame(), (1920, 1080))
    assert len(result['hits']) == 1
    hit = result['hits'][0]
    assert hit.text_id == rows[0]['text_id'] and hit.texts == rows[0]['texts']
    assert hit.voice_status == 'unvoiced' and hit.source_ocr == rows[0]['source_text']
    assert result['owners'] == ('future_owner_a',)
    assert not index.match_unvoiced_lines([rows[0]['source_text']])
    index.capture_unvoiced = False
    assert not index.match_endfield_training_dialogue(frame(), (1920, 1080))['hits']


@pytest.mark.parametrize('condition', ['bottom', 'left_goal', 'partial_body', 'menu', 'no_metadata'])
def test_actual_capture_service_uses_only_positioned_instruction_and_no_audio(tmp_path, condition):
    metadata, rows = fixture()
    # A unique ordinary caption proves that the left-goal veto acts before
    # direct matching and before the old predecessor context can see it.
    rows[1]['texts']['en'] = rows[1]['source_text'] = 'Another completely separate original instruction.'
    index = write_index(tmp_path/'language', metadata=metadata, rows=rows)
    if condition == 'no_metadata':
        index._training_compiled = ()
        index.snapshot_metadata.pop('publisher_training_dialogue_ui')
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    lines = frame()
    if condition == 'left_goal':
        lines[-1] = span(lines[-1]['text'], 70, 400, 750)
    if condition == 'partial_body':
        lines[-1]['text'] = 'Use the battle skill'
    response = {'lines': lines, 'dialogue_menu': condition == 'menu'}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        emitted = []
        for _ in range(3):
            result = service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                            datetime.now(timezone.utc), 'endfield')
            emitted.extend(result.emitted_lines or [])
        assert [hit.text_id for hit in emitted] == ([rows[0]['text_id']] if condition == 'bottom' else [])
        assert service._endfield_tutorial.anchor == (rows[0]['text_id'] if condition == 'bottom' else None)
        await asyncio.sleep(.01)
        assert not scheduled
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
