import json

import pytest

from backend.multilingual_index import MultilingualTextIndex


def test_wrapped_full_caption_outweighs_an_exact_unrelated_phrase(tmp_path):
    def row(identity, text, voice):
        return {'text_id': identity, 'english': text, 'chinese': '', 'source_locale': 'en',
                'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en', 'audio': {'voice': voice}}
    full = 'Please get back to them immediately and STOP THEM!'
    rows = [row('cyberpunk:full', full, 1), row('cyberpunk:short', 'STOP THEM!', 2)]
    value = index(tmp_path, 'en', rows)
    observed = ['Please get back to them immediatly and', 'STOP THEM!']
    assert value.match_lines(observed).text_id == 'cyberpunk:full'
    rows.append(row('cyberpunk:another-full', full, 3))
    value = index(tmp_path, 'en', rows)
    assert value.match_lines(observed) is None
    assert value.match_lines(['STOP THEM!']).text_id == 'cyberpunk:short'


def test_a_complete_caption_is_not_limited_to_eight_sentence_fragments(tmp_path):
    text = ' '.join(f'This is sentence number {number}.' for number in range(12))
    rows = [{'text_id': 'cyberpunk:long', 'english': text, 'chinese': '', 'source_locale': 'en',
             'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en', 'audio': {'voice': 1}}]
    value = index(tmp_path, 'en', rows)
    assert value.match_lines([text]).text_id == 'cyberpunk:long'


def index(tmp_path, source='ko', rows=None):
    rows = rows or [{'text_id': 'cyberpunk:1:female', 'english': 'Stay close. I will protect you.',
        'chinese': '跟紧我。我会保护你。', 'source_locale': source, 'source_text': '가까이 있어요. 지켜줄게요.',
        'texts': {source: '가까이 있어요. 지켜줄게요.', 'en': 'Stay close. I will protect you.', 'zh-Hans': '跟紧我。我会保护你。'},
        'audio_locale': source, 'audio': {'depot': source + '/voice.wem'}, 'channels': ['dialogue', 'gameplay']}]
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'cyberpunk',
        'source_locale': source, 'records': rows}), encoding='utf-8')
    return MultilingualTextIndex('cyberpunk', tmp_path)


@pytest.mark.parametrize('lines', [
    ['가까이 있어요.', '지켜줄게요.'], ['Stay close. I will protect you.'],
    ['跟紧我。我会保护你。 Stay close. I will protect you.'],
    ['Stay close.', 'I will protect you.', '~ 가까이 있어요.', '지켜줄게요.']])
def test_unicode_source_and_dual_subtitles_resolve_one_original_performance(tmp_path, lines):
    value = index(tmp_path)
    value.target_locale = 'zh-hans'
    hit = value.match_lines(lines)
    assert hit and hit.source_language == 'ko' and hit.audio_locale == 'ko'
    assert hit.source_text == '가까이 있어요. 지켜줄게요.'
    assert hit.translation_text == '跟紧我。我会保护你。'
    value.target_locale = 'nl'
    assert value.match_lines(lines).translation_text == ''
    assert value.match_lines(lines, channel='cinematic') is None


def test_same_script_pairs_and_ambiguous_voices(tmp_path):
    row = {'text_id': 'cyberpunk:1:female', 'english': '', 'chinese': '', 'source_locale': 'fr',
        'source_text': 'Restez près de moi.', 'texts': {'fr': 'Restez près de moi.', 'de': 'Bleib in meiner Nähe.'},
        'audio_locale': 'fr', 'audio': {'depot': 'fr/one.wem'}}
    value = index(tmp_path, 'fr', [row])
    hit = value.match_lines(['Restez près de moi. ~ Bleib in meiner Nähe.'])
    assert hit and hit.source_language == 'fr'
    assert value.match_lines(['Restez près de moi. Bleib in meiner Nähe.']).source_language == 'fr'
    value = index(tmp_path, 'fr', [row, {**row, 'text_id': 'cyberpunk:2:female', 'audio': {'depot': 'fr/two.wem'}}])
    assert value.match_lines(['Restez près de moi.']) is None


def test_bad_refresh_preserves_previous_language_snapshot(tmp_path):
    value = index(tmp_path)
    (tmp_path / 'textmap.json').write_text('{bad', encoding='utf-8')
    assert not value.load() and value.ready
    assert value.match_lines(['Stay close. I will protect you.'])
