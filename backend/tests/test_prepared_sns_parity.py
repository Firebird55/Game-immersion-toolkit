"""Original Baker cells must survive portable export and positioned native OCR."""
from copy import deepcopy

import pytest

from backend.prepared_library import write_prepared_library
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_endfield_sns_presentation import LOCALES, STAMP, descriptor, frame, source_rows


def prepare(root, study='en', display='en', **changes):
    rows = source_rows(study)
    for row in rows:
        row['source_locale'] = study
    metadata = descriptor(rows, study)
    metadata['locales'].update(descriptor(rows, display)['locales'])
    payload = {'format': 2, 'game': 'endfield', 'source_locale': study,
        'fingerprint': STAMP, 'records': rows, 'publisher_sns_dialogue_ui': metadata, **changes}
    root.mkdir(parents=True, exist_ok=True)
    archive = write_prepared_library(payload, root / 'library.zip', {})
    session = PreparedCaptureSession(root / 'application')
    session.import_library(archive)
    return session, rows


@pytest.mark.parametrize('study', LOCALES)
@pytest.mark.parametrize('display', ['en', 'zh-Hans'])
def test_exported_original_cells_keep_study_translations_and_visual_order(tmp_path, study, display):
    session, rows = prepare(tmp_path, study, display)
    session.update_settings({'capture_unvoiced': True})
    generation = session.start()
    spans = frame(display)
    expected = [row['text_id'] for row in rows]
    assert session.index.snapshot_metadata['publisher_sns_dialogue_ui']['revision'] == STAMP
    for sequence in (1, 2):
        emitted = session.observe(generation, sequence, [span['text'] for span in spans], channel='fullframe',
            presentation_lines=spans, frame_size=(1920, 1080), now=sequence * .1)
        if sequence == 1:
            assert not emitted
    assert [line['text_id'] for line in emitted] == expected
    for line, row in zip(emitted, rows):
        assert line['source_locale'] == study and line['source_text'] == row['texts'][study]
        assert line['voice_status'] == 'unvoiced' and not line['has_audio']
    # Import and process death preserve the original UI proof and saved lines.
    restarted = PreparedCaptureSession(tmp_path / 'application')
    assert restarted.history.count() == len(expected)
    assert restarted.index.snapshot_metadata['publisher_sns_dialogue_ui'] == session.index.snapshot_metadata['publisher_sns_dialogue_ui']


@pytest.mark.parametrize('case', ['opt_out', 'menu', 'no_positions', 'partial', 'wrong_header', 'low_confidence'])
def test_native_library_never_turns_partial_or_unpositioned_cells_into_aliases(tmp_path, case):
    session, _ = prepare(tmp_path)
    session.update_settings({'capture_unvoiced': case != 'opt_out'})
    generation = session.start()
    spans = deepcopy(frame())
    if case == 'partial': spans = spans[:3]  # One cell cannot identify a chain.
    elif case == 'wrong_header': spans[1]['text'] = 'Another contact'
    elif case == 'low_confidence':
        for span in spans[2:]: span['confidence'] = .2
    for sequence in (1, 2):
        session.observe(generation, sequence, [span['text'] for span in spans], channel='fullframe',
            presentation_lines=None if case == 'no_positions' else spans,
            frame_size=(1920, 1080), dialogue_menu=case == 'menu', now=sequence * .1)
    identities = {line.text_id for line in session.history.list()}
    assert 'endfield:SNSDialogTable:future_new_topic:1' not in identities
    assert 'endfield:SNSDialogTable:future_new_topic:3' not in identities


@pytest.mark.parametrize('changes', [{'game': 'nte'}, {'fingerprint': 'endfield-' + '2' * 64}])
def test_portable_boundary_rejects_cross_game_or_cross_revision_original_ui(tmp_path, changes):
    with pytest.raises(ValueError, match='original game|different revisions'):
        prepare(tmp_path, **changes)
