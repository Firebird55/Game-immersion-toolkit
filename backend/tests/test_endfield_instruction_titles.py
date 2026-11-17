"""Original book headings identify repeated bodies without changing translations."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from backend import endfield_assets as assets
from backend.capture import _ScanOutcome
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_audit import Catalog, ref
from backend.tests.test_subtitle_capture import fixture_service
from backend.voice_assets import voice_hash


def source_rows(locale='en', *, second_title=True):
    books = {'future_event_one': {'content': ref(11), 'title': ref(12)},
             'future_event_two': {'content': ref(21), **({'title': ref(22)} if second_title else {})}}
    tables = {code: {'11': code + ' Complete participation rules. Claim the complete published reward.',
                     '21': code + ' Complete participation rules. Claim the complete published reward.',
                     '12': code + ' First event details', '22': code + ' Second event details'}
              for code in assets.SUPPORTED_LOCALES}
    # The observed body repeats, but choosing an arbitrary row would replace
    # an official translation. The title must select its actual book.
    tables['fr'] = {'11': 'Première explication officielle.', '21': 'Autre explication officielle.',
                    '12': 'Premier événement', '22': 'Autre événement'}
    catalog = Catalog({'InstructionBook': books})
    dialogs = assets.narrative_dialogues(catalog, [])
    return assets.dialogue_records(dialogs, {}, tables, locale, {}), books, tables


def write_index(directory, rows, locale='en'):
    directory.mkdir(exist_ok=True)
    (directory/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': locale, 'records': rows}), encoding='utf8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready
    return index


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_new_book_ids_and_complete_localized_title_select_their_own_official_texts(tmp_path, locale):
    rows, _, tables = source_rows(locale)
    index = write_index(tmp_path, rows, locale)
    for row in rows:
        LocalDialogue(**row)
        assert row['audio'] is None and row['voice_status'] == 'unvoiced'
        assert row['channels'] == ['tip'] and row['text_capture_verified']
        assert row['source_text'] == row['texts'][locale]
    assert rows[0]['texts'] != rows[1]['texts']
    index.capture_missing_audio = True
    assert not index.match_unvoiced_lines([tables[locale]['12'], rows[0]['source_text']])
    index.capture_unvoiced = True
    assert not index.match_unvoiced_lines([rows[0]['source_text']])
    for row in rows:
        anchor, = row['ocr_texts'][locale]
        hit, = index.match_unvoiced_lines([anchor])
        assert hit.text_id == row['text_id'] and hit.texts == row['texts']
        assert hit.voice_status == 'unvoiced' and hit.source_text == row['source_text']
        assert not index.match_full_frame_voice_lines([anchor])


@pytest.mark.parametrize('change', ['missing_title', 'unresolved_title', 'changed_title_shape', 'runtime_title'])
def test_missing_or_unresolved_title_never_bypasses_an_unnamed_competing_body(tmp_path, change):
    rows, books, tables = source_rows(second_title=False)
    if change != 'missing_title':
        books['future_event_two']['title'] = [] if change == 'changed_title_shape' else ref(22)
        if change == 'unresolved_title':
            for table in tables.values():
                table.pop('22')
        elif change == 'runtime_title':
            for table in tables.values():
                table['22'] = 'Unresolved {current_event} title'
        dialogs = assets.narrative_dialogues(Catalog({'InstructionBook': books}), [])
        rows = assets.dialogue_records(dialogs, {}, tables, 'en', {})
    index = write_index(tmp_path, rows)
    index.capture_unvoiced = True
    assert all('en' not in row.get('ocr_texts', {}) for row in rows)
    assert not index.match_unvoiced_lines([tables['en']['12'], rows[0]['source_text']])
    assert all(row['voice_status'] == 'unvoiced' and row['audio'] is None for row in rows)


def test_title_alone_unknown_title_and_partial_body_do_not_identify_a_book(tmp_path):
    rows, _, tables = source_rows()
    index = write_index(tmp_path, rows)
    index.capture_unvoiced = True
    assert not index.match_unvoiced_lines([tables['en']['12']])
    assert not index.match_unvoiced_lines(['A changed unknown heading', rows[0]['source_text']])
    assert not index.match_unvoiced_lines([tables['en']['12'], 'en Complete participation rules.'])


def test_changed_original_heading_updates_only_recognition_context():
    before, books, tables = source_rows()
    tables = deepcopy(tables)
    tables['en']['12'] = 'Updated original first event heading'
    dialogs = assets.narrative_dialogues(Catalog({'InstructionBook': books}), [])
    after = assets.dialogue_records(dialogs, {}, tables, 'en', {})
    for old, new in zip(before, after, strict=True):
        assert {k: v for k, v in old.items() if k != 'ocr_texts'} == {
            k: v for k, v in new.items() if k != 'ocr_texts'}
    assert after[0]['ocr_texts']['en'][0].startswith(tables['en']['12'] + ' ')


@pytest.mark.parametrize('kind', ['conversation', 'radio'])
def test_book_title_never_restores_a_speaker_anchor_vetoed_by_the_written_body(tmp_path, kind):
    body = 'A complete repeated explanation also has a separate original recording.'
    dialogs = {'book': {'dialogText': ref(1), 'instruction_title': ref(2),
                        'dialogue_kind': 'instruction', 'voice_status': 'unvoiced'},
               'spoken': {'dialogText': ref(1), 'actorName': ref(3),
                          'dialogue_kind': kind, 'audioOverride': 'bound'}}
    tables = {'en': {'1': body, '2': 'A unique book heading', '3': 'A visible speaker'}}
    path = 'voice/english/original.wem'
    key = f'{voice_hash(path):016x}'
    rows = assets.dialogue_records(dialogs, {'bound': 'original.wem'}, tables, 'en',
                                   {key: {'file_id': key}})
    assert [r['voice_status'] for r in rows] == ['unvoiced', 'voiced']
    assert all('ocr_texts' not in row for row in rows)
    index = write_index(tmp_path, rows)
    index.capture_unvoiced = True
    assert not index.match_lines(['A visible speaker', body], exact_only=True)
    assert not index.match_unvoiced_lines(['A unique book heading', body])


@pytest.mark.parametrize('presentation', ['complete', 'title_only', 'body_only', 'partial_body', 'changed_title'])
def test_capture_joins_separate_positioned_title_and_wrapped_body_only_with_unvoiced_enabled(tmp_path, presentation):
    rows, _, tables = source_rows()
    index = write_index(tmp_path/'language', rows)
    index.capture_unvoiced = True
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    def span(text, y):
        return {'text': text, 'confidence': .99, 'bounding_rect': {
            'x1': 300, 'x2': 1500, 'x3': 1500, 'x4': 300,
            'y1': y, 'y2': y, 'y3': y+35, 'y4': y+35}}
    body = rows[0]['source_text'].split('. ', 1)
    lines = [span(tables['en']['12'], 200), span(body[0]+'.', 250), span(body[1], 295)]
    lines = {'complete': lines, 'title_only': [lines[0]], 'body_only': lines[1:],
             'partial_body': lines[:2],
             'changed_title': [span('Changed heading', 200), *lines[1:]]}[presentation]
    response = {'lines': lines}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        def scan():
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                         datetime.now(timezone.utc), 'endfield')
        assert not scan().emitted_lines and not scan().emitted_lines
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
        assert not scan().emitted_lines
        emitted = scan().emitted_lines
        if presentation == 'complete':
            hit, = emitted
            assert hit.text_id == rows[0]['text_id'] and hit.texts == rows[0]['texts']
            assert hit.voice_status == 'unvoiced'
        else:
            # Each negative has fresh history: deduplication of a preceding
            # positive must never conceal an incorrect recognition result.
            assert not emitted
        await asyncio.sleep(.01)
        assert not scheduled
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
