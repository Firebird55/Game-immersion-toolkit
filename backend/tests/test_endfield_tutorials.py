"""Written tutorial bodies must survive independently of illustrative media."""
import copy
import json

import pytest

from backend import endfield_assets as assets
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure
from backend.tests.test_endfield_audit import Catalog, ref


def tutorial_catalog():
    return Catalog({
        'InstructionBook': {'new_patch_rule': {'content': ref(20), 'title': ref(21)}},
        'WikiTutorialPageTable': {'new_patch_page': {
            'content': ref(30), 'title': ref(31), 'image': 'illustration', 'video': 'separate_video'}},
        'DungeonCharTutorialStepTable': {
            'new_patch_step': {'stepDesc': ref(40), 'iconDesc': ref(41), 'stepIcon': 'skill_icon'},
            'retained_unused_step': {'stepDesc': ref(42)}},
        'DungeonCharTutorialTable': {'new_dungeon': {'tutorialStageData': [
            {'stage': 1, 'stepIds': ['new_patch_step']},
            {'stage': 2, 'stepIds': ['new_patch_step', 'missing_step']}]}}})


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_tutorial_bodies_keep_official_localizations_without_lending_video_audio(locale):
    catalog = tutorial_catalog()
    warnings = []
    dialogs = assets.narrative_dialogues(catalog, warnings)
    bodies = {key: value for key, value in dialogs.items() if value['dialogue_kind'] in {
        'instruction', 'tutorial', 'tutorial_step'}}
    assert set(bodies) == {'InstructionBook:new_patch_rule', 'WikiTutorialPageTable:new_patch_page',
                           'DungeonCharTutorialStepTable:new_patch_step'}
    assert any('missing step bodies' in warning for warning in warnings)
    assert any('no current stage reference' in warning for warning in warnings)
    tables = {language: {str(identity): f'{language} complete written explanation {identity}.'
                        for identity in (20, 21, 30, 31, 40, 41, 42)}
              for language in assets.SUPPORTED_LOCALES}
    rows = assets.dialogue_records(bodies, {'separate_video': 'unrelated.wem'}, tables, locale, {})
    assert len(rows) == 3
    for row in rows:
        LocalDialogue(**row)
        assert row['voice_status'] == 'unvoiced' and row['audio'] is None
        assert row['text_capture_verified'] is True and row['channels'] == ['tip']
        assert row['source_locale'] == locale and row['source_text'] == row['texts'][locale]
        assert row['audio_locale'] == ('zh-Hans' if locale == 'zh-Hant' else locale)
    assert {row['source_text'].split()[-1] for row in rows} == {'20.', '30.', '40.'}
    # Display headings/skill labels and missing translations cannot be borrowed.
    del tables['ja']['30']
    japanese = assets.dialogue_records(bodies, {}, tables, 'ja', {})
    assert len(japanese) == 2 and all('new_patch_page' not in row['text_id'] for row in japanese)


def test_full_frame_tutorial_text_requires_the_unvoiced_option_and_complete_body(tmp_path):
    bodies = assets.narrative_dialogues(tutorial_catalog(), [])
    text = 'Perform another basic attack to complete the training step.'
    rows = assets.dialogue_records(bodies, {}, {'en': {'40': text}}, 'en', {})
    assert len(rows) == 1
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('endfield', tmp_path)
    assert index.ready and not index.match_unvoiced_lines([text])
    index.capture_missing_audio = True
    assert not index.match_unvoiced_lines([text])
    index.capture_unvoiced = True
    hit, = index.match_unvoiced_lines([text])
    assert hit.text_id == rows[0]['text_id'] and hit.voice_status == 'unvoiced'
    assert index.is_capture_text(hit.text_id, hit.english, 'tip')
    assert not index.is_capture_text(hit.text_id, hit.english, 'dialogue')
    assert not index.match_unvoiced_lines(['Perform another basic attack'])
    assert not index.match_full_frame_voice_lines([text])


@pytest.mark.parametrize('change', [
    {'InstructionBook': {'future': {'content': []}}},
    {'WikiTutorialPageTable': {'future': {'content': {'changed': 1}}}},
    {'DungeonCharTutorialTable': {'future': {'tutorialStageData': 'changed'}}},
    {'DungeonCharTutorialTable': {'future': {'tutorialStageData': [{'stepIds': [None]}]}}},
])
def test_present_changed_tutorial_format_rejects_candidate_before_overwriting_old_snapshot(tmp_path, monkeypatch, change):
    from backend import endfield_online, endfield_release, language_worker
    catalog = tutorial_catalog()
    catalog.values.update(copy.deepcopy(change))
    catalog.stamp = 'synthetic-current'
    catalog.values['I18nTextTable_EN'].update({str(i): f'Complete official body {i}.' for i in (20, 30, 40)})
    monkeypatch.setattr(endfield_release, 'prepare', lambda *_args: catalog)
    monkeypatch.setattr(endfield_release, 'discover', lambda *_args: (catalog.stamp, b''))
    monkeypatch.setattr(endfield_release, 'voice_entries', lambda *_args: {})
    monkeypatch.setattr(endfield_online, 'film_records', lambda *_args: [])
    old = tmp_path / 'textmap.json'
    old.write_bytes(b'previous complete snapshot')
    candidate = tmp_path / 'candidate.json'
    with pytest.raises(PreparationFailure) as failure:
        language_worker.build('endfield', None, tmp_path, 'en', (), candidate)
    assert failure.value.code == 'unsupported_game_format'
    assert old.read_bytes() == b'previous complete snapshot' and not candidate.exists()
