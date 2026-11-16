"""Authored speaker/caption pairs identify text without borrowing another voice."""
import json

import pytest

from backend import endfield_assets as endfield
from backend.multilingual_index import MultilingualTextIndex
from backend.voice_assets import voice_hash


CAPTIONS = {'en': 'Try it.', 'ja': '試してみよう。', 'ko': '일단 한번 해보자.',
            'zh-Hans': '试试看吧。', 'zh-Hant': '試試看吧。'}
SPEAKERS = {'en': ('Endministrator', 'Chen Qianyu'), 'ja': ('管理人', 'チェン・センユー'),
            'ko': ('관리자', '진천우'), 'zh-Hans': ('管理员', '陈千语'),
            'zh-Hant': ('管理員', '陳千語')}


def index(tmp_path, locale, *, same_speaker=False, anonymous=False):
    tables = {code: {'1': text, '2': text, '100': SPEAKERS[code][0], '200': SPEAKERS[code][1]}
              for code, text in CAPTIONS.items()}
    tables['fr'] = {'1': 'Je vais essayer.', '2': 'Essayons cela.',
                    '100': 'Administratrice', '200': 'Chen Qianyu'}
    if anonymous:
        for table in tables.values():
            table['100'] = '???'
    source = 'voice/' + endfield.VOICE_LOCALES[locale] + '/other.wem'
    key = f'{voice_hash(source):016x}'
    dialogs = {
        'radio_target': {'dialogText': {'id': 1}, 'actorName': {'id': 100},
                         'actorNameId': 'endminf', 'audioOverride': 'missing',
                         'dialogue_kind': 'radio', 'text_capture_verified': True},
        'conversation_other': {'dialogText': {'id': 2},
                               'actorName': {'id': 100 if same_speaker else 200},
                               'audioOverride': 'bound', 'dialogue_kind': 'conversation',
                               'text_capture_verified': True},
    }
    rows = endfield.dialogue_records(dialogs, {'bound': 'other.wem'}, tables, locale,
                                    {key: {'file_id': key}})
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': locale, 'records': rows}), encoding='utf-8')
    value = MultilingualTextIndex('endfield', tmp_path)
    assert value.load()
    value.player_voice = 'female'
    return value, rows


@pytest.mark.parametrize('locale', CAPTIONS)
def test_speaker_and_complete_caption_resolve_the_missing_text_only(tmp_path, locale):
    value, rows = index(tmp_path, locale)
    observed = [SPEAKERS[locale][0], CAPTIONS[locale]]
    assert value.match_lines(observed, exact_only=True) is None
    value.capture_missing_audio = True
    assert value.match_missing_audio_lines([CAPTIONS[locale]]) == []
    assert value.match_missing_audio_lines([SPEAKERS[locale][0]]) == []
    hits = value.match_missing_audio_lines(observed)
    assert len(hits) == 1
    assert hits[0].text_id == 'endfield:radio_target'
    assert hits[0].source_text == CAPTIONS[locale]
    assert hits[0].voice_status == 'unavailable'
    assert hits[0].translation_text == rows[0]['texts']['en']
    # The original competing recording remains its own independent performance.
    other = value.match_lines([SPEAKERS[locale][1], CAPTIONS[locale]], exact_only=True)
    assert other and other.text_id == 'endfield:conversation_other'
    assert other.voice_status == 'voiced'
    assert rows[0]['audio'] is None and rows[1]['audio']['source'].endswith('/other.wem')
    value.player_voice = 'male'
    assert value.match_missing_audio_lines(observed) == []


def test_same_authored_speaker_does_not_resolve_competing_performances(tmp_path):
    value, _ = index(tmp_path, 'en', same_speaker=True)
    value.capture_missing_audio = True
    assert value.match_missing_audio_lines(['Endministrator', 'Try it.']) == []
    assert value.match_lines(['Endministrator', 'Try it.'], exact_only=True) is None


def test_anonymous_punctuation_is_not_an_identifying_speaker(tmp_path):
    value, rows = index(tmp_path, 'en', anonymous=True)
    value.capture_missing_audio = True
    assert 'ocr_texts' not in rows[0]
    assert value.match_missing_audio_lines(['???', 'Try it.']) == []


def test_new_choice_or_film_without_owned_speaker_vetoes_named_caption(tmp_path):
    value, rows = index(tmp_path, 'en')
    choice = {**rows[0], 'text_id': 'endfield:new_choice', 'dialogue_kind': 'choice',
              'voice_status': 'unvoiced', 'player_voice': None}
    choice.pop('ocr_texts')
    rows.append(choice)
    endfield._guard_speaker_anchors(rows)
    assert all('en' not in row.get('ocr_texts', {}) for row in rows)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows}), encoding='utf-8')
    value = MultilingualTextIndex('endfield', tmp_path)
    assert value.load()
    value.capture_unvoiced = value.capture_missing_audio = True
    value.player_voice = 'female'
    assert value.match_missing_audio_lines(['Endministrator', 'Try it.']) == []
