"""Direct original predecessor resolves an entire narrow-panel caption only."""
import json

import pytest

from backend.multilingual_index import MultilingualTextIndex
from backend.nte_dialogue_context import NteDialogueContext


def row(identity, text, previous=None, **changes):
    return {'text_id': 'nte:Owned:'+identity, 'source_locale': 'en', 'source_text': text,
            'audio_locale': 'en', 'texts': {'en': text}, 'audio': {'depot': identity},
            'voice_status': 'voiced', 'dialogue_kind': 'conversation', 'channels': ['dialogue'],
            **({'previous_text_id': 'nte:Owned:'+previous} if previous else {}), **changes}


def setup(tmp_path, extra=()):
    rows = [row('First', 'Keep watching the western entrance.'), row('Short', 'Ah?', 'First'),
            row('Elsewhere', 'Ah?'), row('Third', 'Oh!', 'Short'),
            row('OtherThird', 'Oh!'),
            row('SilentUI', 'Ah?', audio=None, voice_status='unknown', dialogue_kind='uncategorized'), *extra]
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.ready
    return index, NteDialogueContext()


def scan(context, index, text, now, *, scope=1, enabled=True, stable_frames=2):
    default = index.match_lines([text], exact_only=True)
    return context.match(index, [text], default, enabled=enabled, scope=scope, now=now, stable_frames=stable_frames)


def anchor(context, index, start=0, **kwargs):
    for now in (start, start+.1):
        assert scan(context, index, 'Keep watching the western entrance.', now, **kwargs).text_id == 'nte:Owned:First'


def test_stable_direct_predecessor_resolves_repeated_short_caption_and_preserves_global_ui_veto(tmp_path):
    index, context = setup(tmp_path)
    assert index.match_lines(['Ah?'], exact_only=True) is None
    assert scan(context, index, 'Ah?', 0) is None
    scan(context, index, 'Keep watching the western entrance.', 1)
    assert scan(context, index, 'Ah?', 1.1) is None
    anchor(context, index, 2)
    hit = scan(context, index, 'Ah?', 2.2)
    assert hit.text_id == 'nte:Owned:Short' and hit.source_ocr == 'Ah?' and hit.dialogue_kind == 'conversation'
    assert index.match_lines(['Ah?'], exact_only=True) is None
    assert not index.match_full_frame_voice_lines(['Ah?'])


@pytest.mark.parametrize('text', ['Noise Ah?', 'Ah? Additional text', 'Name: Ah?', 'Oh!', 'Unknown option'])
def test_fragments_speaker_stripping_and_a_second_context_edge_are_not_allowed(tmp_path, text):
    index, context = setup(tmp_path)
    anchor(context, index)
    assert scan(context, index, text, .2) is None
    assert scan(context, index, 'Ah?', .3) is None


@pytest.mark.parametrize('change', ['scope', 'disabled', 'gap', 'clock', 'blank', 'new_line'])
def test_scope_expiry_clock_regression_and_intervening_observations_clear_context(tmp_path, change):
    index, context = setup(tmp_path, [row('Other', 'Return to the warehouse immediately.')])
    anchor(context, index)
    if change == 'scope': result = scan(context, index, 'Ah?', .2, scope=2)
    elif change == 'disabled': result = scan(context, index, 'Ah?', .2, enabled=False)
    elif change == 'gap': result = scan(context, index, 'Ah?', 4)
    elif change == 'clock': result = scan(context, index, 'Ah?', -.1)
    elif change == 'blank':
        scan(context, index, '', 4); result = scan(context, index, 'Ah?', 4.1)
    else:
        scan(context, index, 'Return to the warehouse immediately.', .2)
        result = scan(context, index, 'Ah?', .3)
    assert result is None


def test_context_dependent_repeats_do_not_refresh_expiry_or_anchor_the_next_node(tmp_path):
    index, context = setup(tmp_path)
    anchor(context, index)
    for now in (1, 3, 5, 7, 9, 11):
        assert scan(context, index, 'Ah?', now).text_id == 'nte:Owned:Short'
    assert scan(context, index, 'Ah?', 13) is None
    anchor(context, index, 14)
    assert scan(context, index, 'Ah?', 14.2).text_id == 'nte:Owned:Short'
    assert scan(context, index, 'Oh!', 14.3) is None


@pytest.mark.parametrize('changes', [dict(voice_status='unavailable', audio=None),
    dict(voice_status='unknown', audio=None), dict(dialogue_kind='ambient_dialogue'),
    dict(channels=['cinematic']), dict(player_voice='male'), dict(text_binding_unresolved=True)])
def test_unavailable_other_channel_or_wrong_player_voice_is_never_borrowed(tmp_path, changes):
    index, context = setup(tmp_path)
    for item in index._records:
        if item['text_id'] == 'nte:Owned:Short': item.update(changes)
    index.player_voice = 'female'
    anchor(context, index)
    assert scan(context, index, 'Ah?', .2) is None


def test_a_single_character_is_supported_only_after_a_valid_original_predecessor(tmp_path):
    index, context = setup(tmp_path)
    index.source_locale = 'zh-Hans'
    for item in index._records:
        value = '守住西门入口。' if item['text_id'].endswith(':First') else '嗯'
        item['texts'] = {'zh-Hans': value}
        item['source_text'] = value
    # Supply the already independent ordinary exact observation; the shared
    # index intentionally does not index one-character captions.
    first = index.match_lines(['Keep watching the western entrance.'], exact_only=True)
    first = first.model_copy(update={'source_ocr': '守住西门入口。'})
    for now in (0, .1):
        context.match(index, ['守住西门入口。'], first, enabled=True, scope=None, now=now, stable_frames=2)
    assert context.match(index, ['嗯'], None, enabled=True, scope=None, now=.2, stable_frames=2).text_id == 'nte:Owned:Short'


def test_actual_index_keeps_one_character_outside_ordinary_nte_matching(tmp_path):
    rows = [row('First', 'Keep watching the western entrance.'), row('Short', 'X', 'First')]
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('nte', tmp_path); context = NteDialogueContext()
    assert index.ready and index.match_lines(['X'], exact_only=True) is None
    assert scan(context, index, 'X', 0) is None
    # Speaker/noise stripping in the ordinary matcher must not arm context.
    scan(context, index, 'Wrong speaker: Keep watching the western entrance.', .1)
    scan(context, index, 'Wrong speaker: Keep watching the western entrance.', .2)
    assert scan(context, index, 'X', .3) is None
    anchor(context, index, 1)
    assert scan(context, index, 'X', 1.2).text_id == 'nte:Owned:Short'
    assert index.match_lines(['X'], exact_only=True) is None
    assert scan(context, index, 'X', 1.3, enabled=False) is None  # Menu/excluded-screen contract.
    anchor(context, index, 2)
    assert scan(context, index, 'X', 2.2, scope=2) is None
    anchor(context, index, 3)
    index.source_locale = 'ja'
    assert scan(context, index, 'X', 3.2, scope=('ja',)) is None


def test_other_games_keep_existing_authored_one_character_index_admission(tmp_path):
    rows = [row('First', 'Keep watching the western entrance.'), row('Short', 'X', 'First')]
    for item in rows:
        item['text_id'] = item['text_id'].replace('nte:', 'endfield:')
        if item.get('previous_text_id'):
            item['previous_text_id'] = item['previous_text_id'].replace('nte:', 'endfield:')
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('endfield', tmp_path)
    assert index.ready
    assert index.match_lines(['X'], exact_only=True, previous_text_id='endfield:Owned:First').text_id == 'endfield:Owned:Short'
