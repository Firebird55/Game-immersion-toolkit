"""Synthetic Endfield presentation, schema drift and missing-pack regressions."""
import json
from pathlib import Path

import pytest

from backend import endfield_assets as endfield
from backend.preparation_errors import PreparationFailure
from backend.voice_assets import voice_hash


def ref(identity):
    return {'id': identity, 'text': ''}


class Catalog:
    revision = 'a' * 40
    revision_title = 'Synthetic metadata revision'

    def __init__(self, values=None):
        self.values = {
            'DialogTextTable': {'conversation': {'dialogText': ref(1), 'audioOverride': 'voice_one'}},
            'RadioTable': {}, 'TextTable': {}, 'TextVoIdTable': {},
            'AudioDialog': {'voice_one': {'path': 'story/voice_one.wem'}},
            'I18nTextTable_EN': {'1': 'A synthetic conversation.'},
            **(values or {}),
        }

    def file(self, path, **_options):
        return self.values.get(Path(path).stem, {})


def test_every_voice_state_requires_its_own_evidence():
    dialogs = endfield.authored_dialogues(Catalog({
        'DialogTextTable': {
            'bound': {'dialogText': ref(1), 'audioOverride': 'voice_one'},
            'missing_pack': {'dialogText': ref(2), 'audioOverride': 'voice_two'},
            'missing_path': {'dialogText': ref(3), 'audioOverride': 'unresolved'},
            'empty_override': {'dialogText': ref(4), 'audioOverride': ''},
            'unknown': {'dialogText': ref(5)},
        },
        'RadioTable': {'group': {'radioSingleDataList': [
            {'id': 'event', 'radioText': ref(6), 'audioOverride': '', 'audioEvent': 'unresolved_event'},
            {'id': 'empty_radio', 'radioText': ref(7), 'audioOverride': '', 'audioEvent': ''},
        ]}},
    }))
    dialogs.update(endfield.narrative_dialogues(Catalog({'DialogOptionTable': {'choice': {'optionText': ref(8)}}}), []))
    source = 'voice/english/story/voice_one.wem'
    key = f'{voice_hash(source):016x}'
    entries = {key: {'file_id': key, 'block': 102}}
    rows = endfield.dialogue_records(dialogs, {'voice_one': 'story/voice_one.wem', 'voice_two': 'story/voice_two.wem'},
        {'en': {str(i): f'Synthetic narrative line number {i}.' for i in range(1, 9)}}, 'en', entries)
    assert {row['text_id']: row['voice_status'] for row in rows} == {
        'endfield:bound': 'voiced', 'endfield:missing_pack': 'unavailable', 'endfield:missing_path': 'unavailable',
        'endfield:empty_override': 'unknown', 'endfield:unknown': 'unknown', 'endfield:event': 'unavailable',
        'endfield:empty_radio': 'unknown', 'endfield:DialogOptionTable:choice': 'unvoiced',
    }
    assert sum(row['audio'] is not None for row in rows) == 1


def test_narrative_tables_keep_text_media_and_voice_messages_distinct():
    catalog = Catalog({
        'DialogOptionTable': {'a': {'optionText': ref(1)}},
        'Dialog2DTextTable': {'a': {'dialog2dText': ref(2)}},
        'SNSDialogOptionTable': {'a': {'optionDesc': ref(3)}},
        'SNSDialogTopicTable': {'a': {'topicStartOptionDesc': ref(4)}},
        'NarrativeNoteEntryTable': {'a': {'entryDesc': ref(5)}},
        'AIBarkText': {'a': {'barkText': ref(6)}},
        'SNSDialogTable': {'a': {'dialogContentData': {
            '1': {'contentType': 1, 'content': ref(7)},
            '2': {'contentType': 5, 'content': ref(8), 'contentParam': ['unresolved_voice_event']},
            '3': {'contentType': 4, 'content': ref(9), 'contentParam': ['preview', 'movie']},
            '4': {'contentType': 999, 'content': ref(10)},
        }}},
        'RichContentTable': {'a': {'contentList': [{'content': ref(11)}, {'content': ref(12)}]}},
    })
    warnings = []
    dialogs = endfield.narrative_dialogues(catalog, warnings)
    texts = {str(i): f'Synthetic text for presentation {i}.' for i in range(1, 13)}
    texts['12'] = '<image path="synthetic/panel" />'
    rows = endfield.dialogue_records(dialogs, {}, {'en': texts}, 'en', {})
    assert len(rows) == 9
    assert {row['dialogue_kind'] for row in rows} == {
        'choice', 'story_panel', 'message_choice', 'narrative_note', 'combat_bark', 'message', 'message_voice', 'readable'}
    assert next(row for row in rows if row['dialogue_kind'] == 'message_voice')['voice_status'] == 'unavailable'
    assert next(row for row in rows if row['dialogue_kind'] == 'combat_bark')['voice_status'] == 'unknown'
    assert next(row for row in rows if row['dialogue_kind'] == 'story_panel')['channels'] == ['cinematic']
    assert next(row for row in rows if row['dialogue_kind'] == 'readable')['channels'] == ['tip']
    assert all(row['audio'] is None for row in rows)
    assert any('2 Endfield SNS' in warning for warning in warnings)


def test_image_resource_is_not_a_readable_in_any_selected_translation():
    row = {'dialogue_kind': 'readable', 'dialogText': ref(1), 'voice_status': 'unvoiced'}
    assert not endfield.dialogue_records({'x': row}, {},
        {'en': {'1': 'Synthetic fallback label.'}, 'ja': {'1': '<IMAGE path="art/panel" />'}}, 'en', {})


def test_operator_documents_are_silent_but_voice_descriptions_follow_authored_voice_ids():
    dialogs = endfield.narrative_dialogues(Catalog({'CharacterTable': {'operator': {
        'profileRecord': [{'id': 'bio', 'recordDesc': ref(1)}],
        'profileVoice': [{'id': 'greeting', 'voiceDesc': ref(2), 'voId': 'greeting'},
                         {'id': 'future', 'voiceDesc': ref(3), 'voId': ''}],
    }}}), [])
    source = 'voice/english/operator/greeting.wem'
    key = f'{voice_hash(source):016x}'
    rows = endfield.dialogue_records(dialogs, {'greeting': 'operator/greeting.wem'},
        {'en': {'1': 'Synthetic biography.', '2': 'A synthetic greeting.', '3': 'An unbound future greeting.'}},
        'en', {key: {'file_id': key}})
    assert {row['text_id'].rsplit(':', 1)[-1]: row['voice_status'] for row in rows} == {
        'bio': 'unvoiced', 'greeting': 'voiced', 'future': 'unavailable'}
    assert next(row for row in rows if row['voice_status'] == 'voiced')['audio']['source'] == source


@pytest.mark.parametrize('values', [
    {'DialogTextTable': []},
    {'DialogTextTable': {}},
    {'DialogTextTable': {'x': {'dialogText': [1]}}},
    {'DialogTextTable': {'x': {'dialogText': ref(1), 'audioOverride': {'new': 'format'}}}},
    {'RadioTable': {'x': {'radioSingleDataList': {'changed': True}}}},
    {'TextVoIdTable': {'x': {'new': 'voice schema'}}},
    {'RadioTable': {'x': {'radioSingleDataList': [{'id': 'conversation', 'radioText': ref(1)}]}}},
])
def test_proven_core_schema_drift_is_actionable(values):
    with pytest.raises(PreparationFailure) as failure:
        endfield.authored_dialogues(Catalog(values))
    assert failure.value.code == 'unsupported_game_format'
    assert 'Update the toolkit' in str(failure.value)


@pytest.mark.parametrize('values', [
    {'SNSDialogTable': {'x': {'dialogContentData': []}}},
    {'SNSDialogTable': {'x': {'dialogContentData': {'1': {'changedTypeField': 1, 'content': ref(1)}}}}},
    {'RichContentTable': {'x': {'contentList': 'changed schema'}}},
    {'Dialog2DTextTable': {'x': {'newText': ref(1)}}},
])
def test_present_but_changed_narrative_schema_is_not_reported_as_empty(values):
    with pytest.raises(PreparationFailure, match='unsupported structure'):
        endfield.narrative_dialogues(Catalog(values), [])


def test_optional_missing_categories_warn_without_inventing_records():
    warnings = []
    assert endfield.narrative_dialogues(Catalog(), warnings) == {}
    assert any('Dialog2DTextTable' in warning for warning in warnings)
    assert any('RichContentTable' in warning for warning in warnings)


def test_reading_entry_references_do_not_silently_disappear():
    catalog = Catalog({
        'RichContentTable': {'book': {'contentList': [{'content': ref(1)}]}},
        'RadioTable': {'recording': {'radioSingleDataList': []}},
        'ReadingPopUpTable': {'a': {'contentId': 'book'}, 'b': {'contentId': 'recording'},
                             'c': {'contentId': 'future_body'}},
        'PrtsReading': {'group': {'list': {'a': {'contentId': 'book', 'overrideRadioId': 'future_audio'}}}},
        'PrtsDocument': {'a': {'contentId': 'book'}},
    })
    warnings = []
    rows = endfield.narrative_dialogues(catalog, warnings)
    assert len(rows) == 1
    assert any('2 Endfield reading entries' in warning for warning in warnings)
    assert not any('future_body' in warning or 'future_audio' in warning for warning in warnings)


def test_ambiguous_placeholder_and_unsafe_paths_never_bind_audio():
    assert endfield.audio_paths({
        'a': {'path': 'one/duplicate.wem'}, 'b': {'path': 'two/duplicate.wem'},
        'c': {'path': 'voice/placeholder.wem', 'isPlaceholder': True},
        'd': {'path': '../escape.wem'}, 'e': {'path': 'C:/private/path.wem'},
        'f': {'path': '/absolute/file.wem'},
    }) == {}


def patch_index(monkeypatch, tmp_path, catalog):
    (tmp_path / 'Endfield_Data/StreamingAssets/VFS').mkdir(parents=True)
    monkeypatch.setattr(endfield, 'DialogueCatalog', lambda *_args: catalog)
    monkeypatch.setattr(endfield, 'fingerprint', lambda _install: 'stable')
    monkeypatch.setattr(endfield, 'reader', lambda *_args: b'[]')


def test_missing_pack_has_actionable_warning_and_never_becomes_silent(tmp_path, monkeypatch):
    patch_index(monkeypatch, tmp_path, Catalog())
    result = endfield.index_language(tmp_path, tmp_path / 'private', 'en', ())
    row, = result['records']
    assert row['voice_status'] == 'unavailable'
    assert row['audio'] is None
    assert result['metadata_revision_title'] == Catalog.revision_title
    assert any('Install it through the game language settings' in warning for warning in result['coverage_warnings'])
    assert any('third-party' in warning for warning in result['coverage_warnings'])


def test_schema_failure_and_game_update_leave_existing_snapshot_untouched(tmp_path, monkeypatch):
    snapshot = tmp_path / 'textmap.json'
    previous = '{"format": 2, "records": [{"text_id": "synthetic-old"}]}'
    snapshot.write_text(previous)
    patch_index(monkeypatch, tmp_path, Catalog({'DialogTextTable': []}))
    with pytest.raises(PreparationFailure) as failure:
        endfield.index_language(tmp_path, tmp_path, 'en', ())
    assert failure.value.code == 'unsupported_game_format'
    assert snapshot.read_text() == previous
    monkeypatch.setattr(endfield, 'DialogueCatalog', lambda *_args: Catalog())
    stamps = iter(['before', 'after'])
    monkeypatch.setattr(endfield, 'fingerprint', lambda _install: next(stamps))
    with pytest.raises(PreparationFailure) as failure:
        endfield.index_language(tmp_path, tmp_path, 'en', ())
    assert failure.value.code == 'game_files_changed'
    assert failure.value.previous_snapshot_retained
    assert snapshot.read_text() == previous


@pytest.mark.parametrize('inventory', [
    {'new_entries': []},
    [{'block': [], 'file_id': '0' * 16, 'chunk': 'A' * 32 + '.chk', 'file_hash': '1', 'size': 12}],
    [{'block': 102, 'file_id': '0' * 16, 'chunk': '../untrusted.chk', 'file_hash': '1', 'size': 12}],
])
def test_new_inventory_shape_is_an_actionable_format_failure(tmp_path, monkeypatch, inventory):
    patch_index(monkeypatch, tmp_path, Catalog())
    monkeypatch.setattr(endfield, 'reader', lambda *_args: json.dumps(inventory).encode())
    with pytest.raises(PreparationFailure) as failure:
        endfield.index_language(tmp_path, tmp_path, 'en', ())
    assert failure.value.code == 'unsupported_game_format'
