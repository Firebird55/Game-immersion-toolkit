"""Portable export must retain authored game guards and real missing-clip states."""
import copy
import hashlib

import pytest

from backend.prepared_library import write_prepared_library
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_prepared_session import fixture_library
from backend.tests.test_caption_occurrence_identity import records as occurrence_records
from backend.tests.test_endfield_layout_context import step_rows


def prepared(root, rows, *, game='endfield', **metadata):
    fixture_library(root / 'source', game=game)
    clip = root / 'source/tone.wav'
    archive = write_prepared_library({'format': 2, 'game': game, 'source_locale': 'en',
        'records': rows, **metadata}, root / 'library.zip', {row['text_id']: clip for row in rows if row.get('audio')})
    session = PreparedCaptureSession(root / 'application');session.import_library(archive)
    return session


def observe_twice(session, generation, sequence, text, *, menu=False, spans=None):
    positioned = {'presentation_lines': spans, 'frame_size': (1920, 1080)} if spans is not None else {}
    session.observe(generation, sequence, [text], channel='fullframe', now=sequence * .1, dialogue_menu=menu, **positioned)
    return session.observe(generation, sequence + 1, [text], channel='fullframe', now=(sequence + 1) * .1,
        dialogue_menu=menu, **positioned)


@pytest.mark.parametrize('catalog_only', [True, False])
def test_full_recording_provenance_survives_category_only_and_one_decode_failure(tmp_path, catalog_only):
    _, payload = fixture_library(tmp_path / 'source', game='endfield')
    first = payload['records'][0]
    first.update(text_capture_verified=True, original_recording_sha256=hashlib.sha256(b'authored whole WEM').hexdigest(),
        original_speaker_id='chr_authored_guide')
    second = copy.deepcopy(first)
    text = 'A different complete authored sentence still has its own playable recording.'
    second.update(text_id='owned:second', english=text, source_text=text,
        texts={'en': text, 'zh-Hans': '另一条完整的原创句子。'}, original_recording_sha256=hashlib.sha256(b'another authored WEM').hexdigest())
    payload['records'].append(second)
    clip = tmp_path / 'source/tone.wav'
    clips = {} if catalog_only else lambda row: None if row['text_id'] == first['text_id'] else clip
    archive = write_prepared_library(payload, tmp_path / 'prepared.zip', clips)
    session = PreparedCaptureSession(tmp_path / 'application');session.import_library(archive)
    stored = {row['text_id']: row for row in session.index._records}
    assert stored[first['text_id']]['original_recording_sha256'] == first['original_recording_sha256']
    assert stored[first['text_id']]['original_speaker_id'] == first['original_speaker_id']
    assert stored[first['text_id']]['voice_status'] == 'unavailable' and stored[first['text_id']]['audio'] is None
    assert session.index.audio_count == (0 if catalog_only else 1)
    generation = session.start()
    assert not session.observe(generation, 1, [first['source_text']], now=1)
    assert not session.observe(generation, 2, [first['source_text']], now=1.1)
    session.update_settings({'capture_missing_audio': True})
    generation = session.start()
    session.observe(generation, 1, [first['source_text']], now=2)
    missing = session.observe(generation, 2, [first['source_text']], now=2.1)
    assert len(missing) == 1 and missing[0]['voice_status'] == 'unavailable' and not missing[0]['has_audio']
    assert session.audio_path(missing[0]['id']) is None
    match = session.index.match_lines([first['source_text']], exact_only=True)
    assert match and not session.index.equivalent_caption_occurrence(match, match)
    if not catalog_only:
        session.observe(generation, 3, [text], now=2.2)
        voiced = session.observe(generation, 4, [text], now=2.3)
        assert len(voiced) == 1 and voiced[0]['has_audio'] and voiced[0]['voice_status'] == 'voiced'
        assert session.audio_path(voiced[0]['id']).read_bytes() == clip.read_bytes()


def test_top_caption_metadata_and_two_frame_minimum_survive_export(tmp_path):
    _, payload = fixture_library(tmp_path / 'input', game='endfield')
    row = {**payload['records'][0], 'text_id': 'endfield:top:authored', 'channels': ['dialogue', 'cinematic']}
    session = prepared(tmp_path / 'portable', [row], publisher_top_dialogue_cues=1)
    assert session.index.snapshot_metadata['publisher_top_dialogue_cues'] == 1
    session.update_settings({'stable_frames': 1})
    generation = session.start()
    assert not session.observe(generation, 1, [row['source_text']], channel='fullframe', now=1)
    emitted = session.observe(generation, 2, [row['source_text']], channel='fullframe', now=1.1)
    assert [line['text_id'] for line in emitted] == [row['text_id']]


def test_tutorial_occurrences_and_menu_fence_use_shared_desktop_policy_after_export(tmp_path):
    from backend.tests.test_prepared_training_parity import prepared_training_steps, step_spans
    session = prepared_training_steps(tmp_path)
    session.update_settings({'capture_unvoiced': True})
    generation = session.start()
    def positioned(sequence, text, **options):
        return observe_twice(session, generation, sequence, text, spans=step_spans(text), **options)
    assert not positioned(1, 'Wait!')
    positioned(3, 'Keep performing the authored training sequence.')
    assert [row['text_id'] for row in positioned(5, 'Wait!')] == [
        'endfield:DungeonCharTutorialStepTable:b_next']
    repeated = positioned(7, 'Keep performing the authored training sequence.')
    assert [row['text_id'] for row in repeated] == ['endfield:DungeonCharTutorialStepTable:b_repeat']
    positioned(9, 'Keep performing the authored training sequence.', menu=True)
    assert not positioned(11, 'Now!')


def music_rows():
    rows = occurrence_records()
    identities = {row['text_id']: row['text_id'].replace('endfield:film:', 'wuwa:music:') for row in rows}
    for row in rows:
        row.update(text_id=identities[row['text_id']], dialogue_kind='music_subtitle')
        if row.get('previous_text_id'):
            row['previous_text_id'] = identities[row['previous_text_id']]
    short = {**rows[-1], 'text_id': 'wuwa:music:short', 'source_text': 'Go!', 'english': 'Go!',
        'texts': {'en': 'Go!'}, 'previous_text_id': rows[-1]['text_id'], 'requires_previous': True}
    return rows + [short]


def test_song_occurrence_replaces_only_equivalent_alias_and_menu_drops_short_successor(tmp_path):
    rows = music_rows()
    session = prepared(tmp_path, rows, game='wuwa', publisher_song_cues=4, publisher_song_voices=1)
    generation = session.start()
    for sequence, row in zip((1, 3, 5, 7), rows):
        emitted = observe_twice(session, generation, sequence, row['source_text'])
        assert [line['text_id'] for line in emitted] == [row['text_id']]
    observe_twice(session, generation, 9, rows[0]['source_text'], menu=True)
    assert not observe_twice(session, generation, 11, 'Go!')


def test_explicit_zero_song_voices_is_retained_and_never_inferred_from_cue_count(tmp_path):
    rows = music_rows()
    session = prepared(tmp_path, rows, game='wuwa', publisher_song_cues=4, publisher_song_voices=0)
    assert session.index.snapshot_metadata['publisher_song_voices'] == 0
    generation = session.start()
    assert not observe_twice(session, generation, 1, rows[0]['source_text'])
    assert session.history.count() == 0
