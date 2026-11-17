"""Baker context identifies original cells without changing ordinary matching."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from backend.capture import _ScanOutcome
from backend.endfield_sns_presentation import SOURCE_ROLES, validate_sns_dialogue_ui
from backend.languages import audio_locale, normalize_text
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_subtitle_capture import fixture_service


LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
HEADERS = {'en': 'Visitor', 'zh-Hans': '禾', 'zh-Hant': '禾', 'ja': 'ホー', 'ko': '하'}
TYPING = {'en': '[Visitor] is typing...', 'zh-Hans': '[禾]输入中', 'zh-Hant': '[禾]輸入中',
          'ja': '[ホー]は入力中', 'ko': '[하]입력중'}
STOPPED = {'en': '[Visitor] has stopped typing', 'zh-Hans': '[禾]停止输入', 'zh-Hant': '[禾]停止輸入',
           'ja': '[ホー]は入力を停止', 'ko': '[하]입력중단'}
MESSAGE = {'en': 'The complete original message identifies the current authored writing state.',
           'zh-Hans': '完整的原始消息显示了当前的书写状态。', 'zh-Hant': '完整的原始訊息顯示了當前的書寫狀態。',
           'ja': 'この完全な原文メッセージが現在の入力状態を特定します。',
           'ko': '완전한 원문 메시지가 현재 입력 상태를 보여 줍니다.'}
STAMP = 'endfield-' + '1'*64


def source_rows(locale='en'):
    rows = []
    for number, texts in enumerate((TYPING, STOPPED, TYPING, MESSAGE), 1):
        texts = {**texts, 'fr': f'Explication originale différente numéro {number}.'}
        rows.append({'text_id': f'endfield:SNSDialogTable:future_new_topic:{number}', 'source_locale': locale,
            'source_text': texts[locale], 'texts': texts, 'english': texts['en'], 'chinese': texts['zh-Hans'],
            'audio_locale': audio_locale(locale, 'endfield'), 'audio': None, 'voice_status': 'unvoiced',
            'dialogue_kind': 'message_system' if number < 4 else 'message',
            'text_capture_verified': True, 'channels': ['dialogue']})
    return rows


def descriptor(rows, locale='en'):
    ids = [row['text_id'] for row in rows]
    return {'schema': 1, 'revision': STAMP, 'sources': {key: '0'*32 for key in SOURCE_ROLES},
        'locales': {locale: {'modes': ['// Baker / Messages', '// Baker / Tasks'],
                            'friends': '// Baker / Friends', 'chats': {'future_contact': HEADERS[locale]}}},
        'chains': [{'chat_id': 'future_contact', 'text_ids': ids[a:b]}
                   for a in range(3) for b in range(a+2, 5)]}


def write_index(directory, rows=None, locale='en', metadata=None):
    directory.mkdir(exist_ok=True)
    rows = rows or source_rows(locale)
    (directory/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': locale,
        'fingerprint': STAMP, 'publisher_sns_dialogue_ui': metadata or descriptor(rows, locale),
        'records': rows}), encoding='utf8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready, index.message
    return index


def span(text, x, y, width=800):
    return {'text': text, 'confidence': .99, 'bounding_rect': {
        'x1': x, 'x2': x+width, 'x3': x+width, 'x4': x,
        'y1': y, 'y2': y, 'y3': y+24, 'y4': y+24}}


def frame(locale='en'):
    return [span('// Baker / Messages', 30, 30, 450), span(HEADERS[locale], 600, 140, 650),
            *[span(texts[locale], 700, 240+i*100) for i, texts in enumerate((TYPING, STOPPED, TYPING, MESSAGE))]]


@pytest.mark.parametrize('locale', LOCALES)
def test_every_original_body_keeps_its_own_position_and_translation(tmp_path, locale):
    rows = source_rows(locale)
    index = write_index(tmp_path, rows, locale)
    assert not index.match_endfield_sns_dialogue(frame(locale), (1920, 1080))
    index.capture_unvoiced = True
    assert not index.match_unvoiced_lines([rows[0]['source_text']])
    direct = index.match_unvoiced_lines([rows[1]['source_text']])
    assert direct
    hits = index.match_endfield_sns_dialogue(frame(locale), (1920, 1080), direct=direct)
    assert [hit.text_id for hit in hits] == [row['text_id'] for row in rows[:3]]
    assert next(hit for hit in hits if hit.text_id == rows[1]['text_id']) is direct[0]
    for hit, row in zip(hits, rows, strict=False):
        assert hit.texts == row['texts'] and hit.source_text == row['source_text']
        assert hit.source_ocr == row['source_text'] and hit.voice_status == 'unvoiced'
    # No OCR alias or authored row is modified by the scoped route.
    assert all('ocr_texts' not in row for row in index.voice_snapshot(index._signature)['records'])


def test_one_character_header_requires_the_complete_long_four_cell_context(tmp_path):
    index = write_index(tmp_path, locale='zh-Hans')
    index.capture_unvoiced = True
    first = source_rows('zh-Hans')[0]['text_id']
    assert first not in {h.text_id for h in index.match_endfield_sns_dialogue(frame('zh-Hans')[:4], (1920, 1080))}
    assert first in {h.text_id for h in index.match_endfield_sns_dialogue(frame('zh-Hans'), (1920, 1080))}


@pytest.mark.parametrize('study,display', [('zh-Hans', 'en'), ('en', 'zh-Hans'), ('ja', 'en'), ('ko', 'en')])
def test_prepared_display_language_keeps_the_selected_study_text_and_all_guards(tmp_path, study, display):
    rows = source_rows(study)
    metadata = descriptor(rows, study)
    metadata['locales'].update(descriptor(rows, display)['locales'])
    index = write_index(tmp_path, rows, study, metadata)
    index.capture_unvoiced = True
    hits = index.match_endfield_sns_dialogue(frame(display), (1920, 1080))
    assert [hit.text_id for hit in hits] == [row['text_id'] for row in rows[:3]]
    for hit, row in zip(hits, rows, strict=False):
        assert hit.source_locale == study and hit.source_text == row['texts'][study]
        assert hit.audio_locale == row['audio_locale'] and hit.texts == row['texts']
        assert hit.source_ocr == row['texts'][display] and hit.voice_status == 'unvoiced'
    mixed = frame(display)[:4]
    mixed[3]['text'] = STOPPED[study]
    assert not index.match_endfield_sns_dialogue(mixed, (1920, 1080))
    assert not index.match_endfield_sns_dialogue(frame(display), (1920, 1080), dialogue_menu=True)
    # A translation alone cannot supply absent display-language controls.
    absent = write_index(tmp_path/'absent', rows, study, descriptor(rows, study))
    absent.capture_unvoiced = True
    assert not absent.match_endfield_sns_dialogue(frame(display), (1920, 1080))


@pytest.mark.parametrize('case', ['friends', 'missing_mode', 'changed_mode', 'wrong_header', 'nonadjacent',
                                'partial_body', 'intervening', 'mixed_region', 'uncertain', 'no_box', 'menu', 'paragraph'])
def test_incomplete_or_other_views_never_establish_a_scoped_system_occurrence(tmp_path, case):
    index = write_index(tmp_path, locale='zh-Hans')
    index.capture_unvoiced = True
    lines = frame('zh-Hans')
    if case == 'friends': lines[0]['text'] = '// Baker / Friends'
    elif case == 'missing_mode': lines.pop(0)
    elif case == 'changed_mode': lines[0]['text'] = 'Changed unknown mode'
    elif case == 'wrong_header': lines[1]['text'] = 'Another unknown contact'
    elif case == 'nonadjacent':
        for row in lines[3:]:
            for key in row['bounding_rect']:
                if key.startswith('y'): row['bounding_rect'][key] += 240
    elif case == 'partial_body': lines[2]['text'] = TYPING['zh-Hans'][:-2]
    elif case == 'intervening': lines.insert(3, span('Unrelated intervening message', 700, 275))
    elif case == 'mixed_region':
        for key in lines[2]['bounding_rect']:
            if key.startswith('x'): lines[2]['bounding_rect'][key] -= 650
    elif case == 'uncertain': lines[2]['confidence'] = .79
    elif case == 'no_box': lines[2].pop('bounding_rect')
    elif case == 'paragraph': lines.insert(2, span('A longer unmatched paragraph starts here', 700, 208))
    hits = index.match_endfield_sns_dialogue(lines, (1920, 1080), dialogue_menu=case == 'menu')
    assert source_rows('zh-Hans')[0]['text_id'] not in {hit.text_id for hit in hits}


@pytest.mark.parametrize('guard', ['unknown', 'unavailable', 'requires_previous', 'different_translation', 'other_kind'])
def test_all_original_voice_states_short_guards_and_other_kind_peers_still_block(tmp_path, guard):
    rows = source_rows('zh-Hans')
    metadata = descriptor(rows, 'zh-Hans')
    if guard in ('unknown', 'unavailable'):
        rows[0]['voice_status'] = guard
    elif guard == 'requires_previous':
        rows[0].update(requires_previous=True, previous_text_id='endfield:unobserved_predecessor')
    else:
        peers = deepcopy(rows)
        for row in peers: row['text_id'] = row['text_id'].replace('future_new_topic', 'future_conflicting_topic')
        if guard == 'other_kind': peers[0].update(dialogue_kind='message_voice', voice_status='unavailable')
        else: peers[0]['texts']['fr'] = 'Une autre traduction officielle de cette occurrence.'
        metadata['chains'].extend({'chat_id': 'future_contact', 'text_ids': chain['text_ids']}
                                  for chain in descriptor(peers, 'zh-Hans')['chains'])
        rows.extend(peers)
    index = write_index(tmp_path, rows, 'zh-Hans', metadata)
    index.capture_unvoiced = True
    assert rows[0]['text_id'] not in {h.text_id for h in index.match_endfield_sns_dialogue(frame('zh-Hans'), (1920, 1080))}


@pytest.mark.parametrize('change', ['missing_source', 'different_revision', 'absent_row', 'loop', 'too_many_cells'])
def test_damaged_prepared_sns_metadata_is_rejected_before_activation(tmp_path, change):
    rows = source_rows()
    meta = descriptor(rows)
    if change == 'missing_source': meta['sources'].pop('core_ctrl')
    elif change == 'different_revision': meta['revision'] = 'endfield-' + '2'*64
    elif change == 'absent_row': meta['chains'][0]['text_ids'][0] = 'endfield:SNSDialogTable:absent:1'
    elif change == 'loop': meta['chains'][0]['text_ids'][1] = meta['chains'][0]['text_ids'][0]
    else: meta['chains'][0]['text_ids'] = [row['text_id'] for row in rows] + ['endfield:SNSDialogTable:extra:5']
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en',
        'fingerprint': STAMP, 'publisher_sns_dialogue_ui': meta, 'records': rows}), encoding='utf8')
    assert not MultilingualTextIndex('endfield', tmp_path).ready


@pytest.mark.parametrize('locale,display', [(locale, locale) for locale in LOCALES]
                         + [('en', 'zh-Hans'), *((locale, 'en') for locale in LOCALES if locale != 'en')])
def test_shared_history_preserves_visual_order_existing_direct_bodies_and_no_audio(tmp_path, locale, display):
    rows = source_rows(locale)
    metadata = descriptor(rows, locale)
    metadata['locales'].update(descriptor(rows, display)['locales'])
    index = write_index(tmp_path/'language', rows, locale, metadata)
    index.capture_unvoiced = True
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    response = {'lines': frame(display)}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        def scan():
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                         datetime.now(timezone.utc), 'endfield')
        assert not scan().emitted_lines
        hits = scan().emitted_lines
        assert [hit.text_id for hit in hits] == [row['text_id'] for row in rows]
        assert [hit.texts for hit in hits] == [row['texts'] for row in rows]
        assert [normalize_text(hit.source_ocr, display) for hit in hits] == [normalize_text(row['texts'][display], display) for row in rows]
        assert not scan().emitted_lines
        response['dialogue_menu'] = True
        assert not scan().emitted_lines
        response.pop('dialogue_menu')
        assert not scan().emitted_lines
        await asyncio.sleep(.01)
        assert not scheduled
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize('condition', ['friends', 'menu', 'partial_target', 'unvoiced_disabled'])
def test_capture_admission_negatives_have_fresh_histories_not_a_positive_cooldown(tmp_path, condition):
    rows = source_rows('zh-Hans')
    index = write_index(tmp_path/'language', rows, 'zh-Hans')
    index.capture_unvoiced = True
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': condition != 'unvoiced_disabled'}))
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    lines = frame('zh-Hans')
    if condition == 'friends': lines[0]['text'] = '// Baker / Friends'
    if condition == 'partial_target': lines[2]['text'] = TYPING['zh-Hans'][:-2]
    engine = SimpleNamespace(recognize_pil=lambda _: {'lines': lines, 'dialogue_menu': condition == 'menu'})
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        emitted = []
        for _ in range(3):
            outcome = service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                            datetime.now(timezone.utc), 'endfield')
            emitted.extend(outcome.emitted_lines or [])
        assert rows[0]['text_id'] not in {hit.text_id for hit in emitted}
        if condition == 'unvoiced_disabled': assert not emitted
        await asyncio.sleep(.01)
        assert not scheduled
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
