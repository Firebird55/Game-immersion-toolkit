"""Authored table evidence cannot masquerade as graph/media admission."""
import copy
import json
from types import SimpleNamespace as NS

import pytest

from backend import endfield_assets as assets
from backend import endfield_authored_validation as validation
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_audit import Catalog, ref


def original(locale='en'):
    names = ('spoken', 'player_f', 'player_m')
    audio = {assets._voice_table_id(name): {'path': 'story/' + name + '.wem',
             'wavDuration': 2, 'wavDurationEN': 3, 'wavDurationJP': 4, 'wavDurationKR': 5}
             for name in names}
    audio.update({'event': {'path': 'Play_event'}, 'placeholder': {'path': 'fake.wem', 'isPlaceholder': True},
                  'ambiguous1': {'path': 'one/duplicate.wem'}, 'ambiguous2': {'path': 'two/duplicate.wem'}})
    catalog = Catalog({'DialogTextTable': {
        'spoken': {'dialogText': ref(1), 'audioOverride': 'spoken'},
        'player': {'dialogText': ref(2), 'audioOverride': 'player'},
        'event': {'dialogText': ref(3), 'audioOverride': 'Play_event'},
        'placeholder': {'dialogText': ref(4), 'audioOverride': 'fake'},
        'ambiguous': {'dialogText': ref(5), 'audioOverride': 'duplicate'},
        'empty': {'dialogText': ref(6), 'audioOverride': ''}},
        'DialogOptionTable': {'choice': {'optionText': ref(7)}}, 'AudioDialog': audio})
    for code in {locale, 'en', 'zh-Hans'}:
        catalog.values['I18nTextTable_' + assets.TEXT_LOCALES[code]] = {
            str(i): (code + ' authored complete line ' + str(i) + '.') if i != 2
            else '{F}' + code + ' complete female sentence.{M}' + code + ' complete male sentence.'
            for i in range(1, 8)}
    return catalog


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_all_study_scripts_preserve_authored_gender_and_primary_references_without_media(locale, mode):
    catalog = original(locale)
    def forbidden():
        pytest.fail('A table-only validator must not consume unverified graph/UI hooks')
    for hook in ('mission_predecessors', 'top_dialogues', 'disabled_dialogues', 'character_speakers'):
        setattr(catalog, hook, forbidden)
    facts = validation.build(catalog, locale, ['en', 'zh-Hans'], content_mode=mode)
    rows = {row['text_id']: row for row in facts['records']}
    assert len(rows) == 8 and not facts['snapshot_ready'] and not facts['graph_ui_admission_verified']
    assert all(row['audio'] is None for row in rows.values())
    assert rows['endfield:empty']['voice_status'] == 'unknown'
    assert rows['endfield:DialogOptionTable:choice']['voice_status'] == 'unvoiced'
    assert rows['endfield:player:female']['source_text'] == locale + ' complete female sentence.'
    assert rows['endfield:player:male']['source_text'] == locale + ' complete male sentence.'
    assert set(facts['configured_voice_bindings']) == {'endfield:spoken', 'endfield:player:female', 'endfield:player:male'}
    expected_duration = {'en': 3, 'zh-Hans': 2, 'zh-Hant': 2, 'ja': 4, 'ko': 5}[locale]
    for identity, binding in facts['configured_voice_bindings'].items():
        assert binding['source'].startswith('voice/' + assets.VOICE_LOCALES[locale] + '/story/')
        assert binding['declared_positive_primary_duration'] == expected_duration
        assert binding['file_id'] == f"{assets.voice_hash(binding['source']):016x}"
        assert binding['audio_dialog_ids'] and not binding['media_presence_verified']
        assert not binding['caller_voice_enabled_verified']
        assert rows[identity]['voice_status'] == 'unavailable'
    assert validation.validate_candidate(facts, facts['records'])['ordinary_records_verified'] == 8


@pytest.mark.parametrize('change', ['text', 'translation', 'gender', 'id', 'duplicate', 'path', 'file_id', 'locale',
                                 'kind', 'choice-channel', 'choice-status', 'state', 'previous'])
def test_candidate_wrong_authored_fields_are_rejected(change):
    facts = validation.build(original(), 'en', ['zh-Hans'])
    rows = copy.deepcopy(facts['records'])
    spoken = next(row for row in rows if row['text_id'] == 'endfield:spoken')
    choice = next(row for row in rows if row['dialogue_kind'] == 'choice')
    if change == 'text': spoken['source_text'] += ' changed'
    elif change == 'translation': spoken['texts']['zh-Hans'] += ' changed'
    elif change == 'gender': next(row for row in rows if row.get('player_voice') == 'female')['player_voice'] = 'male'
    elif change == 'id': spoken['text_id'] += ':injected'
    elif change == 'duplicate': rows.append(copy.deepcopy(spoken))
    elif change in ('path', 'file_id', 'locale'):
        binding = facts['configured_voice_bindings']['endfield:spoken']
        spoken['audio'] = {key: binding[key] for key in ('source', 'file_id', 'locale')}
        spoken['audio'][{'path': 'source'}.get(change, change)] = 'incorrect'
    elif change == 'kind': spoken['dialogue_kind'] = 'radio'
    elif change == 'choice-channel': choice['channels'] = ['cinematic']
    elif change == 'choice-status': choice['voice_status'] = 'voiced'
    elif change == 'state': spoken['voice_status'] = 'probably silent'
    elif change == 'previous':
        # A predecessor authored by a table must be retained, unlike an extra
        # graph claim for which this component deliberately has no evidence.
        catalog = original()
        catalog.values['RadioTable'] = {'group': {'radioSingleDataList': [
            {'id': 'radio_first', 'radioText': ref(1)}, {'id': 'radio_second', 'radioText': ref(3)}]}}
        facts = validation.build(catalog, 'en', ['zh-Hans'])
        rows = copy.deepcopy(facts['records'])
        next(row for row in rows if row['text_id'] == 'endfield:radio_second')['previous_text_id'] = 'endfield:empty'
    with pytest.raises(ValueError):
        validation.validate_candidate(facts, rows)


def test_graph_and_media_claims_are_preserved_but_cannot_be_certified_by_tables():
    facts = validation.build(original(), 'en', ['zh-Hans'])
    rows = copy.deepcopy(facts['records'])
    spoken = next(row for row in rows if row['text_id'] == 'endfield:spoken')
    binding = facts['configured_voice_bindings']['endfield:spoken']
    spoken.update(audio={key: binding[key] for key in ('source', 'file_id', 'locale')}, voice_status='voiced',
                  channels=['dialogue', 'cinematic'], previous_text_id='endfield:unverified', original_speaker_id='operator')
    next(row for row in rows if row['text_id'] == 'endfield:empty')['voice_status'] = 'unvoiced'
    before = copy.deepcopy((facts, rows))
    report = validation.validate_candidate(facts, rows)
    assert report['unverified_claim_counts'] == {'unverified_previous_text_id': 1, 'unverified_original_speaker_id': 1,
        'unverified_graph_channels': 1, 'configured_audio_references_verified': 1,
        'playback_presence_not_certified': 1, 'unverified_silence_claims': 1}
    assert not report['snapshot_ready'] and report['unfulfilled_evidence'] == list(validation.UNFULFILLED)
    assert (facts, rows) == before


@pytest.mark.parametrize('change', ['records', 'bindings', 'controls'])
def test_changed_validation_facts_cannot_be_reused(change):
    facts = validation.build(original(), 'en', [])
    if change == 'records': facts['records'][0]['source_text'] = 'Different text'
    elif change == 'bindings': facts['configured_voice_bindings']['endfield:spoken']['source'] = 'Different recording'
    else: facts['original_table_controls'].clear()
    with pytest.raises(ValueError, match='limited-scope'):
        validation.validate_candidate(facts, facts['records'])


@pytest.mark.parametrize('change', ['missing-language', 'bad-table', 'bad-control', 'unknown-mode', 'unknown-language'])
def test_incomplete_original_source_fails(change):
    catalog = original()
    mode, locale = 'text', 'en'
    if change == 'missing-language': catalog.values['I18nTextTable_EN'] = {}
    elif change == 'bad-table': catalog.values['AudioDialog'] = []
    elif change == 'bad-control': catalog.files = {'Data/TableCfg/AudioDialog.bytes': NS(
        name='Data/TableCfg/AudioDialog.bytes', content_hashes=('unused', 'wrong'), size=30)}
    elif change == 'unknown-mode': mode = 'subtitles'
    else: locale = 'fr'
    with pytest.raises(ValueError):
        validation.build(catalog, locale, [], content_mode=mode)


def test_table_evidence_is_not_a_capture_snapshot_and_keeps_old_library(tmp_path):
    facts = validation.build(original(), 'en', [])
    path = tmp_path / 'textmap.json'
    rows = copy.deepcopy(facts['records'])
    path.write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('endfield', tmp_path)
    assert index.ready and index.entry_count == 8
    old = copy.deepcopy(index._records)
    path.write_text(json.dumps(facts), encoding='utf-8')
    assert not index.load()
    assert index.ready and index._records == old and 'retained' in index.message
