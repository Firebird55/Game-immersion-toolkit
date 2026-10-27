import json

import pytest

from backend.multilingual_index import MultilingualTextIndex


def test_chinese_voice_pack_identity_is_game_specific(tmp_path):
    # Tomb Raider ships separate packs. Endfield explicitly shares Mandarin.
    for game, voice in [('shadowofthetombraider', 'zh-Hant'), ('riseofthetombraider', 'zh-Hant'), ('endfield', 'zh-Hans')]:
        folder = tmp_path / game; folder.mkdir()
        row = {'text_id': game + ':synthetic', 'english': 'A separate original performance.',
               'chinese': '', 'source_locale': 'zh-Hant', 'source_text': '不同的原始配音',
               'texts': {'zh-Hant': '不同的原始配音'}, 'audio_locale': voice, 'audio': {'locale': voice, 'voice': 1}}
        payload = {'format': 2, 'game': game, 'source_locale': 'zh-Hant', 'records': [row]}
        path = folder / 'textmap.json'
        path.write_text(json.dumps(payload), encoding='utf-8')
        assert MultilingualTextIndex(game, folder).ready
        row['audio_locale'] = 'zh-Hans' if voice == 'zh-Hant' else 'zh-Hant'
        path.write_text(json.dumps(payload), encoding='utf-8')
        rejected = MultilingualTextIndex(game, folder)
        assert not rejected.ready and 'voice locale' in rejected.message


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
    assert value.match_lines(['Restez près', 'de moi.', '~ Bleib in', 'meiner Nähe.']).text_id == row['text_id']
    value = index(tmp_path, 'fr', [row, {**row, 'text_id': 'cyberpunk:2:female', 'audio': {'depot': 'fr/two.wem'}}])
    assert value.match_lines(['Restez près de moi.']) is None


def test_bad_refresh_preserves_previous_language_snapshot(tmp_path):
    value = index(tmp_path)
    (tmp_path / 'textmap.json').write_text('{bad', encoding='utf-8')
    assert not value.load() and value.ready
    assert value.match_lines(['Stay close. I will protect you.'])


def test_full_screen_silent_match_is_opt_in_exact_and_excludes_voiced_collisions(tmp_path):
    def row(identity, text, status, channel='cinematic'):
        return {'text_id': identity, 'english': text, 'chinese': '', 'source_locale': 'en',
                'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en',
                'audio': {'voice': identity} if status == 'voiced' else None,
                'voice_status': status, 'channels': [channel]}
    text = 'The sealed letter is waiting in your room.'
    shared = 'This identical text also has an original voice.'
    value = index(tmp_path, 'en', [row('letter', text, 'unvoiced'),
        row('missing', 'This line has a missing voice package.', 'unavailable'),
        row('silent-choice', shared, 'unvoiced'), row('voiced-choice', shared, 'voiced')])
    assert value.match_unvoiced_lines([text]) == []
    value.capture_unvoiced = True
    assert [hit.text_id for hit in value.match_unvoiced_lines([text])] == ['letter']
    assert value.match_unvoiced_lines(['The sealed leter is waiting in your room.']) == []
    assert value.match_unvoiced_lines(['This line has a missing voice package.']) == []
    assert value.match_unvoiced_lines([shared]) == []


def test_repeated_silent_prompts_cannot_choose_an_unrelated_scene_translation(tmp_path):
    row = {'text_id': 'first', 'english': 'Tell me more.', 'chinese': '', 'source_locale': 'en',
           'source_text': 'Tell me more.', 'texts': {'en': 'Tell me more.', 'fr': 'Première traduction.'},
           'audio_locale': 'en', 'audio': None, 'voice_status': 'unvoiced'}
    second = {**row, 'text_id': 'second', 'texts': {'en': 'Tell me more.', 'fr': 'Autre traduction.'}}
    value = index(tmp_path, 'en', [row, second])
    value.capture_unvoiced = True
    assert value.match_lines(['Tell me more.']) is None
    assert value.match_unvoiced_lines(['Tell me more.']) == []


def test_unvoiced_toggle_requires_explicit_evidence_and_exact_text(tmp_path):
    rows = []
    for status, text in [('voiced', 'Follow the guide into the station.'),
                         ('unvoiced', 'The guide left a message for you.'),
                         ('unavailable', 'The guide is waiting by the station.'),
                         ('unknown', 'A note about the station.')]:
        rows.append({'text_id': 'cyberpunk:' + status, 'english': text, 'chinese': '',
            'source_locale': 'en', 'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en',
            'audio': {'file': 'station.wem'} if status == 'voiced' else None,
            'voice_status': status, 'dialogue_kind': 'conversation', 'channels': ['dialogue']})
    value = index(tmp_path, 'en', rows)
    assert value.match_text(rows[0]['source_text']).voice_status == 'voiced'
    assert value.match_text(rows[1]['source_text']) is None
    value.capture_unvoiced = True
    silent = value.match_text(rows[1]['source_text'])
    assert silent.voice_status == 'unvoiced' and silent.dialogue_kind == 'conversation'
    assert value.match_text('The guide left a mesage for you.') is None
    assert value.match_text(rows[1]['source_text'], channel='tip') is None
    assert all(value.match_text(row['source_text']) is None for row in rows[2:])
    assert value.status()['voice_counts'] == dict.fromkeys(('voiced', 'unvoiced', 'unavailable', 'unknown'), 1)
    assert value.status()['dialogue_coverage']['conversation']['unvoiced'] == 1
    value.capture_unvoiced = False
    assert value.match_text(rows[1]['source_text']) is None
    # A malformed replacement must never downgrade an audio binding to silence.
    rows[0]['voice_status'] = 'unvoiced'
    value.path.write_text(json.dumps({'format': 2, 'game': 'cyberpunk', 'source_locale': 'en', 'records': rows}))
    assert not value.load() and value.match_text(rows[0]['source_text']).voice_status == 'voiced'


def test_unvoiced_text_cannot_disambiguate_a_simultaneous_voice(tmp_path):
    text = 'You should come over here immediately.'
    common = dict(english=text, chinese='', source_locale='en', source_text=text,
                  texts={'en': text}, audio_locale='en')
    value = index(tmp_path, 'en', [dict(common, text_id='cyberpunk:spoken', audio={'file': 'one.wem'}),
                                  dict(common, text_id='cyberpunk:silent', audio=None, voice_status='unvoiced')])
    assert value.match_text(text).text_id == 'cyberpunk:spoken'
    value.capture_unvoiced = True
    assert value.match_text(text) is None
