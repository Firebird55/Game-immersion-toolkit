"""Native player nicknames must not need fuzzy guesses or bypass dialogue vetoes."""
import json

import pytest

from backend.multilingual_index import MultilingualTextIndex
from backend.wuthering_text_templates import PlayerNameTemplates


def row(text, *, identity='spoken', status='voiced', gender=None, **extra):
    return {'text_id': identity, 'source_locale': 'en', 'source_text': text, 'english': text,
        'chinese': '', 'texts': {'en': text}, 'audio_locale': 'en', 'voice_status': status,
        'audio': {'depot': identity} if status == 'voiced' else None,
        'dialogue_kind': 'cinematic', 'channels': ['cinematic'], 'player_voice': gender, **extra}


def index(tmp_path, rows, game='wuwa'):
    (tmp_path/'textmap.json').write_text(json.dumps({'format':2,'game':game,'source_locale':'en','records':rows}),encoding='utf-8')
    result=MultilingualTextIndex(game,tmp_path);assert result.ready;return result


@pytest.mark.parametrize('name',['Rover','Alexandria','漂泊者','로버','ローバー'])
def test_complete_authored_static_words_match_exactly_without_changing_source_or_translation(tmp_path,name):
    text='{PlayerName}, we all understand the burden you carry. We are grateful.'
    lookup=index(tmp_path,[row(text)])
    hit=lookup.match_lines([text.replace('{PlayerName}',name)],channel='cinematic',exact_only=True)
    assert hit and hit.text_id=='spoken' and hit.kind=='exact' and hit.score==100
    assert hit.source_text==text and hit.english==text
    assert not lookup.match_lines([text.replace('{PlayerName}',name).replace('burden','warning')],channel='cinematic',exact_only=True)
    assert not lookup.match_lines(['We all understand the burden you carry.'],channel='cinematic',exact_only=True)


@pytest.mark.parametrize('text,observed',[
    ('{PlayerName}, thank you for protecting our quiet village.','Rover, thank you for protecting our quiet village.'),
    ('The entire village is waiting for {PlayerName} to return.','The entire village is waiting for Rover to return.'),
    ('I will remember everything you taught me, {PlayerName}.','I will remember everything you taught me, Rover.'),
])
def test_native_slot_position_is_not_hardcoded(tmp_path,text,observed):
    lookup=index(tmp_path,[row(text)])
    assert lookup.match_lines([observed],channel='cinematic',exact_only=True)


@pytest.mark.parametrize('text,observed',[
    ('{PlayerName}, hello.','Rover, hello.'),
    ('{PlayerName} and {PlayerName} remain here.','Rover and Rover remain here.'),
    ('{OtherToken}, thank you for protecting our quiet village.','Rover, thank you for protecting our quiet village.'),
    ('{PlayerName}, {TA} will protect this village.','Rover, he will protect this village.'),
    ('{PlayerName}, thank you for protecting our quiet village.','a'*33+', thank you for protecting our quiet village.'),
    ('{PlayerName}, thank you for protecting our quiet village.',', thank you for protecting our quiet village.'),
])
def test_short_static_or_unsupported_slots_or_unbounded_names_remain_unresolved(tmp_path,text,observed):
    lookup=index(tmp_path,[row(text)])
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True)


@pytest.mark.parametrize('status',['voiced','unvoiced','unknown','unavailable'])
def test_all_literal_and_template_conflicts_still_veto_a_voice(tmp_path,status):
    text='{PlayerName}, thank you for protecting our quiet village.'
    observed=text.replace('{PlayerName}','Rover')
    lookup=index(tmp_path,[row(text),row(observed,identity='conflict',status=status)])
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True)
    if status in {'unknown','unavailable'}:
        lookup.capture_missing_audio=True
        assert not lookup.match_missing_audio_lines([observed])


def test_missing_template_cannot_borrow_a_literal_voice_or_invent_silence(tmp_path):
    text='{PlayerName}, thank you for protecting our quiet village.';observed=text.replace('{PlayerName}','Rover')
    lookup=index(tmp_path,[row(text,status='unavailable',text_capture_verified=True),row(observed,identity='spoken')])
    lookup.capture_missing_audio=True
    assert not lookup.match_missing_audio_lines([observed])


def test_player_and_predecessor_and_channel_admission_remain_required(tmp_path):
    text='{PlayerName}, thank you for protecting our quiet village.';observed=text.replace('{PlayerName}','Rover')
    lookup=index(tmp_path,[row(text,gender='female',previous_text_id='before',requires_previous=True)])
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True,previous_text_id='before')
    lookup.player_voice='female'
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True)
    assert not lookup.match_lines([observed],channel='dialogue',exact_only=True,previous_text_id='before')
    assert lookup.match_lines([observed],channel='cinematic',exact_only=True,previous_text_id='before')


def test_other_game_does_not_gain_native_wuthering_slots(tmp_path):
    text='{PlayerName}, thank you for protecting our quiet village.'
    lookup=index(tmp_path,[row(text)],game='endfield')
    assert not lookup.match_lines([text.replace('{PlayerName}','Rover')],channel='cinematic',exact_only=True)


def test_another_player_branch_does_not_veto_the_configured_original(tmp_path):
    text='{PlayerName}, thank you for protecting our quiet village.';observed=text.replace('{PlayerName}','Rover')
    lookup=index(tmp_path,[row(text,gender='male'),row(text,identity='other',status='unknown',gender='female')])
    lookup.player_voice='male'
    assert lookup.match_lines([observed],channel='cinematic',exact_only=True).text_id=='spoken'
    lookup.player_voice='unconfigured'
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True)


def test_two_different_original_player_recordings_never_pick_a_default(tmp_path):
    text='{PlayerName}, thank you for protecting our quiet village.';observed=text.replace('{PlayerName}','Rover')
    lookup=index(tmp_path,[row(text,identity='male',gender='male'),row(text,identity='female',gender='female')])
    assert not lookup.match_lines([observed],channel='cinematic',exact_only=True)
    for gender in ['male','female']:
        lookup.player_voice=gender
        assert lookup.match_lines([observed],channel='cinematic',exact_only=True).text_id==gender
