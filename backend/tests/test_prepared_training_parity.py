"""Actual portable libraries keep original training roles and body-only context."""
from copy import deepcopy

import pytest

from backend.endfield_training_presentation import SOURCE_ROLES, validate_training_dialogue_ui
from backend.prepared_library import write_prepared_library
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_endfield_layout_context import step_rows
from backend.tests.test_endfield_sns_presentation import span
from backend.tests.test_endfield_training_presentation import fixture, frame, STAMP


def prepared_training_steps(root):
    rows = step_rows()
    prefix = 'endfield:DungeonCharTutorialStepTable:'
    metadata = {'schema': 1, 'revision': STAMP, 'sources': {role: 'a' * 32 for role in SOURCE_ROLES},
        'locales': {'en': {'titles': {'a': ['Operator Guide: Other'], 'b': ['Operator Guide: Current']},
            'labels': {row['text_id']: 'Battle Skill' for row in rows}, 'profile': []}},
        'stages': [{'owner': 'a', 'stage': 0, 'text_ids': [prefix + key for key in ('a_intro', 'a_next')]},
                   {'owner': 'b', 'stage': 0, 'text_ids': [prefix + key for key in ('b_intro', 'b_next', 'b_repeat', 'b_finish')]}],
        'goals': []}
    return prepare(root, metadata, rows)


def step_spans(text, owner='Current'):
    return [span('Operator Guide: ' + owner, 80, 250, 600), span('Battle Skill', 850, 105, 100),
            span('Battle Skill', 958, 105, 100), span(text, 400, 820, 1120)]


def prepare(root, metadata=None, rows=None, **changes):
    original, records = fixture()
    root.mkdir(parents=True, exist_ok=True)
    payload = {'format': 2, 'game': 'endfield', 'source_locale': 'en', 'fingerprint': STAMP,
        'records': [dict(english=row['source_text'], chinese='', **row)
                    if 'english' not in row else row for row in (records if rows is None else rows)],
        'publisher_training_dialogue_ui': original if metadata is None else metadata, **changes}
    archive = write_prepared_library(payload, root / 'library.zip', {})
    session = PreparedCaptureSession(root / 'application');session.import_library(archive)
    return session


def observe(session, sequence, spans, *, menu=False, positioned=True):
    return session.observe(session.generation, sequence, [row['text'] for row in spans], channel='fullframe',
        presentation_lines=spans if positioned else None, frame_size=(1920, 1080) if positioned else None,
        dialogue_menu=menu, now=sequence * .1)


def test_written_role_descriptor_survives_writer_import_and_restart_with_exact_original_fields(tmp_path):
    metadata, rows = fixture()
    session = prepare(tmp_path, metadata, rows)
    canonical = validate_training_dialogue_ui(metadata)
    assert session.index.snapshot_metadata['publisher_training_dialogue_ui'] == canonical
    assert not session.index.match_endfield_training_dialogue(frame(), (1920, 1080))['hits']
    session.update_settings({'capture_unvoiced': True});session.start()
    assert not observe(session, 1, frame())
    emitted = observe(session, 2, frame())
    assert [line['text_id'] for line in emitted] == [rows[0]['text_id']]
    assert emitted[0]['texts'] == rows[0]['texts'] and not emitted[0]['has_audio']
    reopened = PreparedCaptureSession(tmp_path / 'application')
    assert reopened.index.snapshot_metadata['publisher_training_dialogue_ui'] == canonical
    assert reopened.history.list()[0].text_id == rows[0]['text_id']


@pytest.mark.parametrize('damage', ['positions', 'left_goal', 'confidence', 'control', 'partial', 'owner', 'menu', 'opt_out'])
def test_portable_training_never_learns_a_left_goal_or_incomplete_body(tmp_path, damage):
    session = prepare(tmp_path);session.update_settings({'capture_unvoiced': damage != 'opt_out'});session.start()
    spans = deepcopy(frame())
    if damage == 'left_goal': spans[-1] = span(spans[-1]['text'], 70, 400, 750)
    if damage == 'confidence': spans[-1]['confidence'] = .1
    if damage == 'control': spans[1]['text'] = 'Unknown changed label'
    if damage == 'partial': spans[-1]['text'] = 'Use the battle skill'
    if damage == 'owner': spans[0]['text'] = 'A changed training header'
    for sequence in (1, 2, 3):
        assert not observe(session, sequence, spans, menu=damage == 'menu', positioned=damage != 'positions')
    assert session.history.count() == 0
    assert all(context.anchor is None for context in session.floating_contexts.values())


@pytest.mark.parametrize('change', [{'game': 'nte'}, {'fingerprint': 'endfield-' + '7' * 64}])
def test_portable_training_descriptor_cannot_cross_its_game_or_publisher_revision(tmp_path, change):
    with pytest.raises(ValueError, match='original game|different revisions'):
        prepare(tmp_path, **change)


def test_old_snapshot_without_role_evidence_cannot_capture_even_a_complete_unique_training_body(tmp_path):
    from backend.tests.test_prepared_capture_parity import prepared
    session = prepared(tmp_path, step_rows())
    session.update_settings({'capture_unvoiced': True});session.start()
    for sequence in (1, 2, 3):
        assert not observe(session, sequence, step_spans('Keep performing the authored training sequence.'))
    assert session.history.count() == 0
    assert all(context.anchor is None for context in session.floating_contexts.values())


@pytest.mark.parametrize('change', ['left_goal', 'owner'])
def test_role_or_owner_change_cannot_keep_a_previous_training_branch_armed(tmp_path, change):
    session = prepared_training_steps(tmp_path)
    session.update_settings({'capture_unvoiced': True});session.start()
    anchor = step_spans('Keep performing the authored training sequence.')
    observe(session, 1, anchor);observe(session, 2, anchor)
    assert session.floating_contexts['tutorial'].anchor is not None
    if change == 'left_goal':
        current = [*anchor[:-1], span(anchor[-1]['text'], 70, 400, 750)]
    else:
        current = step_spans('Keep performing the authored training sequence.', 'Other')
    observe(session, 3, current)
    for sequence in (4, 5):
        assert not observe(session, sequence, step_spans('Wait!'))
