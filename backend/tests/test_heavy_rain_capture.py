"""Authored scene context must confirm each overlapping original separately."""
import json
from datetime import datetime, timezone

from backend.capture import CaptureService
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_subtitle_capture import fixture_service


def make_index(tmp_path, duplicate=False):
    rows = []
    for identity, text in [('100:00000001', 'Pap!'), ('200:00000002', 'Pap!'),
                           ('100:00000003', 'Rustig aan, jullie rennen me nog omver!')]:
        rows.append({'text_id': 'heavyrain:' + identity, 'source_locale': 'nl', 'audio_locale': 'nl',
            'source_text': text, 'texts': {'nl': text, 'zh-Hans': '合成的官方测试文本。'},
            'audio': {'identity': identity}})
    if duplicate:
        rows.append({**rows[0], 'text_id': 'heavyrain:100:00000004', 'audio': {'identity': 'other-child'}})
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'heavyrain', 'source_locale': 'nl', 'records': rows}))
    return MultilingualTextIndex('heavyrain', tmp_path), rows


def test_confirmed_authored_group_captures_overlapping_speakers_independently(tmp_path):
    index, rows = make_index(tmp_path)
    service, _, _, _ = fixture_service(tmp_path, game='heavyrain')
    queued = []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: queued.append(line)
    texts = ['Pap!', rows[2]['source_text']]
    try:
        assert index.match_text('Pap!') is None
        captures = []
        for stamp in [0, .25, .5]:
            hits = service._heavy_rain_matches(index, texts, stamp, ('account', 'window', 'language'), 2)
            captures += service._emit_heavy_rain_matches(hits, stamp, datetime.now(timezone.utc))
        assert {hit.text_id for hit in captures} == {rows[0]['text_id'], rows[2]['text_id']}
        assert len(captures) == len(queued) == service.transcript.count() == 2
        assert not service._heavy_rain_matches(index, ['Pap!'], .75, ('other-account', 'window', 'language'), 2)
    finally:
        service._executor.shutdown()


def test_scene_context_expires_clears_on_menu_and_cannot_guess_within_group(tmp_path):
    index, rows = make_index(tmp_path)
    service, _, _, _ = fixture_service(tmp_path)
    try:
        for stamp in [0, .25]:
            service._heavy_rain_matches(index, [rows[2]['source_text']], stamp, ('scope',), 2)
        assert service._heavy_rain_matches(index, ['Pap!'], 1, ('scope',), 2)[0].text_id == rows[0]['text_id']
        assert not service._heavy_rain_matches(index, ['Pap!'], 13, ('scope',), 2)
        for stamp in [14, 14.25]:
            service._heavy_rain_matches(index, [rows[2]['source_text']], stamp, ('scope',), 2)
        assert not service._heavy_rain_matches(index, ['Pap!'], 14.5, ('scope',), 2, menu=True)
        assert not service._heavy_rain_matches(index, ['Pap!'], 14.75, ('scope',), 2)
        for stamp in [15, 15.25]:
            service._heavy_rain_matches(index, [rows[2]['source_text']], stamp, ('scope',), 2)
        service._update_snapshot(phase='error')
        assert not service._heavy_rain_matches(index, ['Pap!'], 15.5, ('scope',), 2)
        index, _ = make_index(tmp_path, duplicate=True)
        assert not index.match_lines(['Pap!'], context_groups={'heavyrain:100'})
        assert not index.match_lines(['Papp!'], context_groups={'heavyrain:100'})
    finally:
        service._executor.shutdown()
