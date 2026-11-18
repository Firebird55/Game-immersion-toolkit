"""Prepared publisher metadata must reach native positioned OCR admission."""
import copy
import json
import math
import wave
import struct

import pytest

from backend.android_host import AndroidHost
from backend.prepared_library import write_prepared_library
from backend.tests.test_prepared_session import fixture_library
from backend.tests.test_endfield_presentation import metadata, frame
from backend.endfield_presentation import validate_world_dialogue_ui
from backend.tests.test_endfield_recording_identity import pair
from backend.tests.test_nte_dialogue_context import row
from backend.tests.test_player_speaker_capture import positioned


def native_response(spans, width, height, *, include_quality=True):
    blocks = []
    for span in spans:
        rectangle = span['bounding_rect']
        xs, ys = [rectangle['x' + str(i)] for i in range(1, 5)], [rectangle['y' + str(i)] for i in range(1, 5)]
        blocks.append({'text': span['text'], 'rect': [math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))]})
    result = {'width': width, 'height': height, 'blocks': blocks}
    if include_quality:
        result['presentation_lines'] = spans
    return json.dumps(result)


def prepared_host(tmp_path, game, rows, **metadata_fields):
    fixture_library(tmp_path / 'source', game=game)
    clip = tmp_path / 'source/tone.wav'
    clips = {item['text_id']: clip for item in rows if item.get('audio')}
    if game == 'endfield':
        # Different authored takes must stay different after conversion to
        # content-addressed portable clips; identical tones are valid aliases.
        other = tmp_path / 'source/another-tone.wav'
        with wave.open(str(other), 'wb') as target:
            target.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
            target.writeframes(struct.pack('<h', -1000) * 1600)
        clips[rows[1]['text_id']] = other
    elif game == 'nte':
        for number, item in enumerate(rows[1:], 1):
            if not item.get('audio'):
                continue
            other = tmp_path / f'source/tone-{number}.wav'
            with wave.open(str(other), 'wb') as target:
                target.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
                target.writeframes(struct.pack('<h', 1000 + 1000 * number) * 1600)
            clips[item['text_id']] = other
    rows = [{**item, 'english': item.get('english', item['source_text']), 'chinese': item.get('chinese', '')} for item in rows]
    archive = write_prepared_library({'format': 2, 'game': game, 'source_locale': 'en',
        'records': rows, **metadata_fields}, tmp_path / 'library.zip',
        clips)
    reader = tmp_path / 'reader';reader.mkdir()
    host = AndroidHost(tmp_path / 'application', reader)
    host.session.import_library(archive)
    return host


def test_world_ui_metadata_survives_import_and_native_stateless_complete_caption_with_choices(tmp_path):
    host = prepared_host(tmp_path, 'endfield', pair(), publisher_world_dialogue_ui=metadata(),
        publisher_film_cues=0, publisher_top_dialogue_cues=0)
    try:
        assert host.session.index.snapshot_metadata['publisher_world_dialogue_ui'] == validate_world_dialogue_ui(metadata())
        generation = host.session.start()
        spans = frame()
        spans.append({**positioned('An authored NPC response', .55, .7, .95),
            'bounding_rect': {'x1': 1400, 'y1': 580, 'x2': 1800, 'y2': 580, 'x3': 1800, 'y3': 610, 'x4': 1400, 'y4': 610}})
        raw = native_response(spans, 1920, 1080)
        assert host.accept_ocr(generation, 1, raw) == []
        result = host.accept_ocr(generation, 2, raw)
        assert [line['text_id'] for line in result] == ['endfield:spoken']
        assert host.session.audio_path(result[0]['id']).read_bytes() == (tmp_path / 'source/tone.wav').read_bytes()
        assert host.session.contexts == {}  # Stateless world proof cannot arm predecessors.
    finally: host.close()


@pytest.mark.parametrize('change', ['no_quality', 'zero_score', 'profile_overlay', 'incomplete_body'])
def test_native_world_proof_never_invents_missing_quality_or_controls(tmp_path, change):
    host = prepared_host(tmp_path, 'endfield', pair(), publisher_world_dialogue_ui=metadata())
    try:
        spans = copy.deepcopy(frame())
        if change == 'zero_score': spans[-1]['confidence'] = 0
        elif change == 'profile_overlay':
            spans += [{'text': text, 'confidence': .99, 'bounding_rect': {'x1': 900, 'y1': y,
                'x2': 1200, 'y2': y, 'x3': 1200, 'y3': y+30, 'x4': 900, 'y4': y+30}}
                for text, y in [('Profile', 120), ('Audio Log', 170)]]
        elif change == 'incomplete_body': spans[-1]['text'] += ' Another unmatched complete sentence.'
        raw = native_response(spans, 1920, 1080, include_quality=change != 'no_quality')
        generation = host.session.start()
        for sequence in (1, 2, 3):
            assert host.accept_ocr(generation, sequence, raw) == []
        assert host.session.history.count() == 0
    finally: host.close()


def nte_rows():
    return [row('First', 'Keep watching the western entrance.'), row('Short', 'Ah?', 'First'),
        row('Elsewhere', 'Ah?'), row('Third', 'Oh!', 'Short'), row('OtherThird', 'Oh!'),
        row('UnknownUI', 'Ah?', audio=None, voice_status='unknown', dialogue_kind='uncategorized')]


def test_native_nte_uses_same_direct_graph_context_and_actual_positioned_menu_reset(tmp_path):
    host = prepared_host(tmp_path, 'nte', nte_rows())
    try:
        generation = host.session.start();sequence = 0
        def scans(text, *, menu=False, quality=True, menu_text='Owned response option'):
            nonlocal sequence
            spans = [positioned(text, .84)]
            if menu: spans.append(positioned(menu_text, .72, .7, .95))
            raw = native_response(spans, 1000, 1000, include_quality=quality)
            result = []
            for _ in range(2):
                sequence += 1;result += host.accept_ocr(generation, sequence, raw)
            return result
        assert scans('Ah?') == []
        assert [line['text_id'] for line in scans('Keep watching the western entrance.')] == ['nte:Owned:First']
        assert [line['text_id'] for line in scans('Ah?')] == ['nte:Owned:Short']
        assert scans('Oh!') == []  # A contextual line cannot authorize another edge.
        scans('Keep watching the western entrance.')
        assert host.session.nte_context.anchor == 'nte:Owned:First'
        assert scans('Ah?', menu=True) == [] and host.session.nte_context.anchor is None
        assert scans('Ah?') == []
        scans('Keep watching the western entrance.')
        assert scans('Ah?', menu=True, menu_text='Yes') == [] and host.session.nte_context.anchor is None
        scans('Keep watching the western entrance.')
        assert scans('Ah?', quality=False) == [] and host.session.nte_context.anchor is None
    finally: host.close()


def test_context_layout_absence_does_not_fall_back_to_generic_nte_predecessors(tmp_path):
    host = prepared_host(tmp_path, 'nte', nte_rows())
    try:
        generation = host.session.start()
        for sequence, text in enumerate(['Keep watching the western entrance.'] * 2 + ['Ah?'] * 3, 1):
            host.session.observe(generation, sequence, [text], now=sequence * .1)
        assert [line.text_id for line in host.session.history.list()] == ['nte:Owned:First']
    finally: host.close()


@pytest.mark.parametrize('case', ['bottom', 'left_goal', 'no_positions', 'low_confidence'])
def test_native_ocr_quality_lane_uses_the_same_complete_training_roles(tmp_path, case):
    from backend.tests.test_endfield_training_presentation import fixture, frame, STAMP
    metadata, rows = fixture()
    host = prepared_host(tmp_path, 'endfield', rows, fingerprint=STAMP,
        publisher_training_dialogue_ui=metadata)
    try:
        host.session.update_settings({'capture_unvoiced': True});generation = host.session.start()
        spans = frame()
        if case == 'left_goal':
            spans[-1]['bounding_rect'] = {'x1': 70, 'y1': 400, 'x2': 820, 'y2': 400,
                                         'x3': 820, 'y3': 424, 'x4': 70, 'y4': 424}
        if case == 'low_confidence': spans[-1]['confidence'] = .1
        raw = native_response(spans, 1920, 1080, include_quality=case != 'no_positions')
        emitted = []
        for sequence in (1, 2): emitted.extend(host.accept_ocr(generation, sequence, raw))
        assert [line['text_id'] for line in emitted] == ([rows[0]['text_id']] if case == 'bottom' else [])
        assert all(not line['has_audio'] and line['voice_status'] == 'unvoiced' for line in emitted)
        if case != 'bottom': assert all(context.anchor is None for context in host.session.floating_contexts.values())
    finally: host.close()
