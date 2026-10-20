"""Overlapping captions confirm independently without relaxing ambiguity."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_subtitle_capture import fixture_service


def make_index(tmp_path, duplicate=False):
    rows = []
    for identity, text in [('main', 'Welkom terug in het laboratorium.'),
                           ('background', 'Ik zei dat het bijna klaar is!'),
                           ('wrapped', 'Kom alstublieft terug en help ons onmiddellijk!'),
                           ('fragment', 'help ons onmiddellijk!')]:
        rows.append({'text_id': 'beyond:synthetic:' + identity, 'source_locale': 'nl', 'audio_locale': 'nl',
            'source_text': text, 'texts': {'nl': text, 'zh-Hans': '合成的官方测试文本。'},
            'audio': {'identity': identity}})
    if duplicate:
        rows.append({**rows[2], 'text_id': 'beyond:synthetic:ambiguous', 'audio': {'identity': 'other-voice'}})
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': rows}), encoding='utf-8')
    return MultilingualTextIndex('beyond', tmp_path), rows


def test_overlapping_speakers_confirm_and_queue_their_own_originals(tmp_path):
    index, rows = make_index(tmp_path)
    service, _, _, _ = fixture_service(tmp_path, game='beyond')
    queued, captured = [], []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: queued.append(line)
    try:
        for stamp, texts in [(0, [rows[0]['source_text']]), (.25, [rows[0]['source_text'], rows[1]['source_text']]),
                             (.5, [rows[0]['source_text'], rows[1]['source_text']]), (.75, [rows[1]['source_text']])]:
            hits = service._quantic_matches(index, texts, stamp, ('account', 'window', 'nl'), 2)
            captured += service._emit_quantic_matches(hits, stamp, datetime.now(timezone.utc))
        assert {line.text_id for line in captured} == {row['text_id'] for row in rows[:2]}
        assert len(captured) == len(queued) == service.transcript.count() == 2
        assert all(line.source_locale == line.audio_locale == 'nl' for line in captured)
        # An account switch discards a pending one-frame observation.
        hits = service._quantic_matches(index, [rows[0]['source_text']], 1, ('other-account', 'window', 'nl'), 2)
        assert not service._emit_quantic_matches(hits, 1, datetime.now(timezone.utc))
        assert not service._quantic_matches(index, [rows[0]['source_text']], 1.25, ('other-account', 'window', 'nl'), 2, menu=True)
    finally:
        service._executor.shutdown()


def test_wrapped_caption_wins_over_fragment_and_ambiguous_wrap_cannot_supply_one(tmp_path):
    index, rows = make_index(tmp_path)
    observed = ['Kom alstublieft terug en', 'help ons onmiddellijk!', rows[1]['source_text']]
    assert {hit.text_id for hit in index.match_simultaneous_lines(observed)} == {rows[2]['text_id'], rows[1]['text_id']}
    index, rows = make_index(tmp_path, duplicate=True)
    assert {hit.text_id for hit in index.match_simultaneous_lines(observed)} == {rows[1]['text_id']}
    assert index.match_simultaneous_lines(['7654', 'LOOK MOVE', 'O □ + ☆']) == []


def test_single_ocr_dropout_does_not_discard_a_pending_caption(tmp_path):
    index, rows = make_index(tmp_path)
    service, _, _, _ = fixture_service(tmp_path, game='beyond')
    service._schedule_line_audio = lambda *_args, **_kwargs: None
    captured = []
    try:
        for stamp, texts in [(0, [rows[0]['source_text']]), (.25, []), (.5, [rows[0]['source_text']])]:
            hits = service._quantic_matches(index, texts, stamp, ('account', 'window', 'nl'), 2)
            captured += service._emit_quantic_matches(hits, stamp, datetime.now(timezone.utc))
        assert len(captured) == 1
    finally:
        service._executor.shutdown()


def test_long_dropout_never_confirms_a_stale_caption(tmp_path):
    index, rows = make_index(tmp_path)
    service, _, _, _ = fixture_service(tmp_path, game='beyond')
    try:
        for stamp in (0, 1):
            hits = service._quantic_matches(index, [rows[0]['source_text']], stamp, ('account', 'window', 'nl'), 2)
            assert not service._emit_quantic_matches(hits, stamp, datetime.now(timezone.utc))
    finally:
        service._executor.shutdown()


def test_observed_chinese_context_resolves_a_dutch_performance_beside_another_speaker(tmp_path, monkeypatch):
    first = {'text_id': 'beyond:ONE:1', 'source_locale': 'nl', 'audio_locale': 'nl',
             'source_text': 'Goed.', 'texts': {'nl': 'Goed.', 'zh-Hans': '好的'}, 'audio': {'identity': 'first'}}
    other = {**first, 'text_id': 'beyond:OTHER:1', 'audio': {'identity': 'other'}}
    paired = {**first, 'text_id': 'beyond:ONE:context-100-900', 'source_text': 'Goed. We gaan naar huis.',
              'texts': {'nl': 'Goed. We gaan naar huis.', 'zh-Hans': '好的 我们回家吧。'},
              'ocr_texts': {'nl': ['We gaan naar huis.'], 'zh-Hans': ['我们回家吧。']},
              'member_text_ids': ['beyond:ONE:1', 'beyond:ONE:2'], 'audio': {'identity': 'pair'}}
    collision = {**other, 'text_id': 'beyond:COLLISION:1', 'source_text': 'Een andere tekst.',
                 'texts': {'nl': 'Een andere tekst.', 'zh-Hans': '我们回家吧。'}}
    background = {**first, 'text_id': 'beyond:BACKGROUND:complete', 'source_text': 'Het is bijna klaar!',
                  'texts': {'nl': 'Het is bijna klaar!', 'zh-Hans': '快准备好了！'}, 'audio': {'identity': 'background'}}
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'nl',
        'records': [first, other, paired, collision, background]}), encoding='utf-8')
    index = MultilingualTextIndex('beyond', tmp_path); index.target_locale = 'zh-Hans'
    service, _, _, _ = fixture_service(tmp_path, game='beyond')
    service.game_indexes = {'beyond': index}
    service.game_voice_assets = {'beyond': SimpleNamespace(locale='nl', has_variant=lambda *_: True)}
    queued, captured = [], []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: queued.append(line)
    window = SimpleNamespace(handle=0, bounds=(0, 0, 1920, 1080), title='Synthetic BEYOND')
    try:
        for stamp, lines in [(0, ['好的']), (.25, ['好的']),
                             (.5, ['我们回家吧。', '快准备好了！']), (.75, ['我们回家吧。', '快准备好了！'])]:
            monkeypatch.setattr('backend.capture.time.monotonic', lambda stamp=stamp: stamp)
            engine = SimpleNamespace(recognize_pil=lambda _, lines=lines: {'lines': [{'text': line} for line in lines]})
            captured += service._scan_pragmata(window, service.settings.get().beyond_region, engine, 0,
                                               datetime.now(timezone.utc), game='beyond').emitted_lines
        assert {line.text_id for line in captured} == {paired['text_id'], background['text_id']}
        assert len(captured) == len(queued) == service.transcript.count() == 2
        assert all(line.source_locale == line.audio_locale == 'nl' and line.translation_locale == 'zh-Hans' for line in captured)
    finally:
        service._executor.shutdown()
