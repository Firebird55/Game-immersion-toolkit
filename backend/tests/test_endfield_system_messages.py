"""Native System message bodies are written text; media labels are not bodies."""
import json

import pytest

from backend import endfield_assets as assets
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure
from backend.tests.test_endfield_audit import Catalog, ref


def messages():
    return Catalog({'SNSDialogTable': {'new_story_chat': {'dialogContentData': {
        '1': {'contentType': 7, 'content': ref(10), 'contentParam': ['not_a_system_voice']},
        '2': {'contentType': 5, 'content': ref(20), 'contentParam': ['unresolved_voice']},
        '3': {'contentType': 2, 'content': ref(30)},
        '4': {'contentType': 13, 'content': ref(40)}}}}})


def test_native_system_body_does_not_borrow_a_voice_or_promote_media_labels():
    warnings = []
    rows = assets.narrative_dialogues(messages(), warnings)
    selected = {key: row for key, row in rows.items() if key.startswith('SNSDialogTable:')}
    assert set(selected) == {'SNSDialogTable:new_story_chat:1', 'SNSDialogTable:new_story_chat:2'}
    written = selected['SNSDialogTable:new_story_chat:1']
    assert written['dialogue_kind'] == 'message_system' and written['voice_status'] == 'unvoiced'
    assert written['text_capture_verified'] is True and written['audioOverride'] == ''
    assert selected['SNSDialogTable:new_story_chat:2']['voice_status'] == 'unavailable'
    assert any('2 Endfield SNS media' in warning for warning in warnings)


def test_system_message_requires_the_existing_unvoiced_option(tmp_path):
    source = 'The mission contact has joined this conversation.'
    raw = assets.narrative_dialogues(messages(), [])
    records = assets.dialogue_records(raw, {}, {'en': {'10': source},
        'fr': {'10': 'Le contact de mission a rejoint cette conversation.'}}, 'en', {})
    assert len(records) == 1 and records[0]['audio'] is None
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': records}), encoding='utf-8')
    index = MultilingualTextIndex('endfield', tmp_path)
    index.target_locale = 'fr'
    index.capture_missing_audio = True
    assert not index.match_lines([source], exact_only=True)
    index.capture_unvoiced = True
    hit = index.match_lines([source], exact_only=True)
    assert hit and hit.voice_status == 'unvoiced' and hit.dialogue_kind == 'message_system'
    assert hit.translation_text == records[0]['texts']['fr']


@pytest.mark.parametrize('bad', [None, {'changed_text_slot': 10}])
def test_present_system_message_without_its_original_body_fails_instead_of_becoming_empty(bad):
    catalog = messages()
    catalog.values['SNSDialogTable']['new_story_chat']['dialogContentData']['1']['content'] = bad
    with pytest.raises(PreparationFailure) as error:
        assets.narrative_dialogues(catalog, [])
    assert error.value.code == 'unsupported_game_format'
