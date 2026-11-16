"""Authored occurrence preference must preserve complete original identities."""
import copy
import json

import pytest

from backend.endfield_caption_context import EndfieldCaptionContext
from backend.models import TextMatch
from backend.multilingual_index import MultilingualTextIndex


TEXT = 'The same exact caption returns during this presentation.'


def records(status='voiced'):
    base = {'source_locale': 'en', 'source_text': TEXT, 'english': TEXT, 'chinese': '',
            'texts': {'en': TEXT, 'ko': 'An independently authored Korean translation.'},
            'audio_locale': 'en', 'audio': {'source': 'original-whole-context'} if status == 'voiced' else None,
            'audio_scope': 'context', 'voice_status': status, 'dialogue_kind': 'cinematic',
            'channels': ['cinematic'], 'text_capture_verified': True}
    first = {**base, 'text_id': 'endfield:film:first'}
    anchor_text = 'This independent complete caption establishes the following occurrence.'
    anchor = {**base, 'text_id': 'endfield:film:anchor', 'source_text': anchor_text, 'english': anchor_text,
              'texts': {'en': anchor_text}, 'previous_text_id': first['text_id']}
    later = {**base, 'text_id': 'endfield:film:later', 'previous_text_id': anchor['text_id']}
    return copy.deepcopy([first, anchor, later])


def index(root, rows):
    (root / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en',
                                                  'publisher_film_cues': 3, 'records': rows}))
    result = MultilingualTextIndex('endfield', root)
    assert result.ready
    return result


def displayed(identity, status='voiced'):
    # TextMatch intentionally has no original audio reference. A copied or
    # selected display model must not authorize equivalence of its source rows.
    return TextMatch(game='endfield', text_id=identity, english=TEXT, chinese='', source_ocr=TEXT,
                     score=100, kind='exact', source_locale='en', source_text=TEXT, audio_locale='en',
                     voice_status=status, dialogue_kind='cinematic', audio_scope='context',
                     texts={'en': TEXT})


@pytest.mark.parametrize('change', [
    {'audio': {'source': 'different-original'}},
    {'texts': {'en': TEXT, 'ko': 'A different official Korean translation.'}},
    {'audio_scope': 'paragraph'}, {'dialogue_kind': 'conversation'},
    {'channels': ['dialogue']}, {'player_voice': 'male'},
    {'speaker_english': 'Another authored speaker'},
    {'ocr_texts': {'en': ['Another full authored anchor.']}},
])
def test_identical_display_models_never_override_a_different_complete_source_identity(change, tmp_path):
    rows = records(); rows[2].update(change)
    value = index(tmp_path, rows); value.player_voice = 'male'
    assert not value.equivalent_caption_occurrence(displayed(rows[0]['text_id']), displayed(rows[2]['text_id']))


@pytest.mark.parametrize('status', ['voiced', 'unvoiced', 'unknown', 'unavailable'])
def test_only_real_voice_or_confirmed_unvoiced_rows_have_an_equivalent_occurrence(status, tmp_path):
    rows = records(status)
    value = index(tmp_path, rows)
    first, second = displayed(rows[0]['text_id'], status), displayed(rows[2]['text_id'], status)
    assert value.equivalent_caption_occurrence(first, second) == (status in {'voiced', 'unvoiced'})


def test_default_context_behavior_and_other_observations_stay_guarded(tmp_path):
    rows = records(); value = index(tmp_path, rows)
    def sequence(prefer, conflicting=False):
        context = EndfieldCaptionContext(); last = None
        for number, row in enumerate(rows):
            direct = value.match_full_frame_voice_lines([row['source_text']])
            if number == 2 and conflicting:
                direct.append(value.match_lines([rows[1]['source_text']], exact_only=True, channel='cinematic'))
            for frame in (0, 1):
                last = context.observe(value, [row['source_text']], direct, channel='cinematic', kind='cinematic',
                    scope=1, now=number + frame * .1, stable_frames=2, prefer_authored_occurrence=prefer)
        return last
    assert sequence(False) is None
    assert sequence(True).text_id == rows[2]['text_id']
    assert sequence(True, conflicting=True) is None
