"""A missing conditional performance cannot veto a different selected player."""
import json

import pytest

from backend.multilingual_index import MultilingualTextIndex


@pytest.mark.parametrize('game', ['nte', 'genshin', 'starrail', 'zzz', 'endfield', 'wuwa'])
def test_missing_conditional_voice_is_scoped_to_player_and_changes_without_reloading(tmp_path, game):
    text = 'A complete synthetic caption shared by both protagonists.'
    common = {'source_locale': 'en', 'source_text': text, 'texts': {'en': text},
              'audio_locale': 'en', 'dialogue_kind': 'conversation'}
    records = [{**common, 'text_id': f'{game}:123:female', 'player_voice': 'female',
                'audio': None, 'voice_status': 'unavailable'},
               {**common, 'text_id': f'{game}:123:male', 'player_voice': 'male',
                'audio': {'file': 'owned-male.wem'}, 'voice_status': 'voiced'}]
    payload = {'format': 2, 'game': game, 'source_locale': 'en', 'records': records}
    (tmp_path / 'textmap.json').write_text(json.dumps(payload))
    value = MultilingualTextIndex(game, tmp_path)
    assert value.ready
    value.capture_unvoiced = True
    for selected in ['unconfigured', 'female', 'male', 'female', 'unconfigured', 'male']:
        value.player_voice = selected
        result = value.match_lines([text], exact_only=True)
        assert bool(result) == (selected == 'male')
        if result:
            assert result.text_id == f'{game}:123:male'
    # A separate presentation still blocks selection for the configured male.
    records.append({**common, 'text_id': f'{game}:prompt', 'audio': None, 'voice_status': 'unknown'})
    (tmp_path / 'textmap.json').write_text(json.dumps(payload))
    assert value.load()
    assert value.match_lines([text], exact_only=True) is None


def test_zzz_distinct_authored_caption_still_identifies_its_player_without_configuration(tmp_path):
    text = 'A unique synthetic male protagonist caption.'
    records = [{'text_id': 'zzz:fixture:male', 'player_voice': 'male', 'source_locale': 'en',
                'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en',
                'audio': {'file': 'owned-male.wem'}},
               {'text_id': 'zzz:fixture:female', 'player_voice': 'female', 'source_locale': 'en',
                'source_text': 'A different synthetic female caption.',
                'texts': {'en': 'A different synthetic female caption.'}, 'audio_locale': 'en',
                'audio': None, 'voice_status': 'unavailable'}]
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'zzz',
        'source_locale': 'en', 'records': records}))
    value = MultilingualTextIndex('zzz', tmp_path)
    assert value.match_lines([text], exact_only=True).text_id == 'zzz:fixture:male'


@pytest.mark.parametrize('game', ['nte', 'genshin'])
def test_unresolved_silent_source_cannot_be_captured_through_a_valid_translation(tmp_path, game):
    source, translation, alias = ('An unresolved synthetic source branch.',
                                 '待确认的合成译文。', 'A synthetic rendered alias.')
    unresolved = {'text_id': game + ':diagnostic', 'source_locale': 'en', 'source_text': source,
                  'texts': {'en': source, 'zh-Hans': translation}, 'audio_locale': 'en',
                  'audio': None, 'voice_status': 'unvoiced', 'text_binding_unresolved': True,
                  'ocr_texts': {'en': [alias]}}
    control = {**unresolved, 'text_id': game + ':control',
               'source_text': 'An independently resolved synthetic caption.',
               'texts': {'en': 'An independently resolved synthetic caption.'},
               'text_binding_unresolved': False, 'ocr_texts': {}}
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': game,
        'source_locale': 'en', 'records': [unresolved, control]}))
    value = MultilingualTextIndex(game, tmp_path)
    assert value.ready
    for enabled in (False, True):
        value.capture_unvoiced = enabled
        for observed in (source, translation, alias):
            assert value.match_lines([observed], exact_only=True) is None
            assert value.match_unvoiced_lines([observed]) == []
        hit = value.match_lines([control['source_text']], exact_only=True)
        assert bool(hit) == enabled
        if hit:
            assert hit.text_id == control['text_id'] and hit.voice_status == 'unvoiced'
