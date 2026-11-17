"""Filtering a native player branch must retain complete-caption ambiguity."""
import json

import pytest

from backend.languages import audio_locale
from backend.multilingual_index import MultilingualTextIndex


def fixture(root, locale='en', genders=('female','male'), *, game='wuwa', common_full=False):
    full = 'Liora... Will you cross that dangerous boundary once more?'
    def row(identity, text, player=None):
        return {'text_id':identity, 'english':text, 'chinese':'', 'source_text':text,
            'texts':{locale:text}, 'source_locale':locale, 'audio_locale':audio_locale(locale, game),
            'audio':{'depot':identity}, 'voice_status':'voiced', 'dialogue_kind':'cinematic',
            'channels':['cinematic'], 'player_voice':player}
    rows = [row('fragment', 'Liora...'), row('independent', 'This independent caption remains unambiguous.')]
    rows += [row('whole:'+gender, full, gender) for gender in genders]
    if common_full:
        rows.append(row('other-whole', full))
    (root/'textmap.json').write_text(json.dumps({'format':2,'game':game,'source_locale':locale,'records':rows}),encoding='utf8')
    result = MultilingualTextIndex(game, root)
    assert result.ready
    return result, full


@pytest.mark.parametrize('locale', ['en','ja','ko','zh-Hans','zh-Hant'])
@pytest.mark.parametrize('multiple', [False, True])
@pytest.mark.parametrize('wrapped', [False, True])
def test_unconfigured_rover_cannot_borrow_a_fragment_from_another_recording(locale, multiple, wrapped, tmp_path):
    index, full = fixture(tmp_path, locale)
    observed = full.split(' Will ') if wrapped else [full]
    if wrapped:
        observed[1] = 'Will ' + observed[1]
    assert not index.match_lines(observed, channel='cinematic', exact_only=True, multiple=multiple)
    assert index.match_lines(['Liora...'], channel='cinematic', exact_only=True).text_id == 'fragment'
    for gender in ('female','male'):
        index.player_voice = gender
        hit = index.match_lines(observed, channel='cinematic', exact_only=True)
        assert hit and hit.text_id == 'whole:'+gender


def test_missing_selected_branch_keeps_the_complete_observation_as_a_fragment_veto(tmp_path):
    index, full = fixture(tmp_path, genders=('female',))
    index.player_voice = 'male'
    assert index.match_lines([full], channel='cinematic', exact_only=True) is None
    assert not index.match_lines([full], channel='cinematic', exact_only=True, multiple=True)
    index.player_voice = 'female'
    assert index.match_lines([full], channel='cinematic', exact_only=True).text_id == 'whole:female'


def test_unconfigured_common_duplicate_does_not_resolve_a_real_player_conflict(tmp_path):
    index, full = fixture(tmp_path, common_full=True)
    assert index.match_lines([full], channel='cinematic', exact_only=True) is None
    index.player_voice = 'female'
    assert index.match_lines([full], channel='cinematic', exact_only=True) is None


def test_an_independent_visible_caption_survives_the_owned_caption_veto(tmp_path):
    index, full = fixture(tmp_path)
    hits = index.match_lines([full, 'This independent caption remains unambiguous.'],
        channel='cinematic', exact_only=True, multiple=True)
    assert [hit.text_id for hit in hits] == ['independent']


def test_the_new_guard_does_not_change_other_game_player_filtering(tmp_path):
    index, full = fixture(tmp_path, game='cyberpunk')
    assert index.match_lines([full], channel='cinematic', exact_only=True).text_id == 'fragment'
