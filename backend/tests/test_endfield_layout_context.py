"""Original graph layout and stage order select off-lane/short captions safely."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from backend import endfield_assets as assets, endfield_mission_dialogue as mission
from backend.capture import _ScanOutcome
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_audit import Catalog, ref
from backend.tests.test_endfield_mission_dialogue import graph, trunk
from backend.tests.test_local_chatter import row as ocr_row
from backend.tests.test_subtitle_capture import fixture_service
from backend.voice_assets import voice_hash


def load_index(directory, rows, **metadata):
    directory.mkdir(exist_ok=True)
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows, **metadata}), encoding='utf-8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready
    return index


def test_original_top_layout_uses_same_lane_edges_and_new_ids_without_a_mission_allowlist(tmp_path, monkeypatch):
    path = mission.assets.DIALOG_GRAPHS + 'npc/new_package/renamed_graph.json'
    nodes = [trunk('a', 'new_top_first', _showAtTop=True, enableEmotionVoice=True),
             trunk('b', 'new_top_second', _showAtTop=True, enableEmotionVoice=True),
             trunk('c', 'bottom'), trunk('d', 'disabled_top', _showAtTop=True, disablePlayVoice=True)]
    nodes.append(trunk('override', 'emotion_override', _showAtTop=True, isOverrideEmotionVoiceId=True))
    source = SimpleNamespace(content_hashes=('', '0' * 32))
    data = graph(nodes, [('a', 'b'), ('b', 'c'), ('c', 'd')])
    monkeypatch.setattr(mission.assets, '_files', lambda *_: {path: (None, source)})
    monkeypatch.setattr(mission.assets, '_asset', lambda *args, **kwargs:
        ('', 1, {1: {'m_Script': json.dumps(data)}}, []))
    assert mission.top_dialogues(tmp_path, 'first') == {'new_top_first': None, 'new_top_second': 'new_top_first'}
    # Ordinary changed content moves the source digest and adds a new top ID.
    source.content_hashes = '', '1' * 32
    data['nodes'].append(trunk('e', 'future_top_caption', _showAtTop=True))
    assert mission.top_dialogues(tmp_path, 'second')['future_top_caption'] is None
    assert mission.graph_summary(path, data)[1] == []


def top_rows(locale='en', *, duration=2.5, audio_change=None, media=True):
    path = 'Narrating/Future/au_future_caption.wem'
    audio = {'path': path, 'wavDuration': 3.5, 'wavDurationEN': 2.5, 'wavDurationJP': 4.5, 'wavDurationKR': 5.5}
    field = {'en': 'wavDurationEN', 'zh-Hans': 'wavDuration', 'zh-Hant': 'wavDuration',
             'ja': 'wavDurationJP', 'ko': 'wavDurationKR'}[locale]
    if duration is None:
        audio.pop(field)
    else:
        audio[field] = duration
    if audio_change:
        audio.update(audio_change)
    metadata = {assets._voice_table_id('au_future_caption'): audio}
    catalog = Catalog({'DialogTextTable': {'top': {'dialogText': ref(1), 'audioOverride': 'au_future_caption'}}})
    catalog.top_dialogues = lambda: {'top': None}
    raw = assets.authored_dialogues(catalog)
    source = 'voice/' + assets.VOICE_LOCALES[locale] + '/' + path.lower()
    entries = {f'{voice_hash(source):016x}': {'file_id': 'future-original'}} if media else {}
    rows = assets.dialogue_records(raw, assets.audio_paths(metadata),
        {locale: {'1': 'The complete voiced caption appears above the scene.'}}, locale, entries,
        primary_durations=assets.primary_voice_durations(metadata, locale))
    return rows


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_top_primary_voice_uses_the_selected_dub_duration_and_original_media(locale):
    row, = top_rows(locale)
    assert row['voice_status'] == 'voiced' and row['channels'] == ['dialogue', 'cinematic']
    assert row['audio']['locale'] == ('zh-Hans' if locale == 'zh-Hant' else locale)
    # Positive durations in the other three packs cannot certify this pack.
    assert top_rows(locale, duration=None)[0]['channels'] == ['dialogue']


@pytest.mark.parametrize('duration', [None, 0, -1, True, float('nan'), float('inf'), '2.5'])
def test_top_fallback_is_not_admitted_from_a_file_without_positive_native_duration(duration):
    row, = top_rows(duration=duration)
    assert row['voice_status'] == 'voiced' and row['audio']
    assert row['channels'] == ['dialogue']


@pytest.mark.parametrize('change', [{'isPlaceholder': True}, {'path': 'Narrating/au_other_caption.wem'},
                                  {'path': 'Narrating/au_future_caption'}, {'path': '../au_future_caption.wem'}])
def test_top_primary_binding_requires_the_authored_metadata_filename(change):
    assert top_rows(audio_change=change)[0]['channels'] == ['dialogue']


def test_top_missing_original_media_remains_unavailable_and_outside_the_full_frame_lane():
    row, = top_rows(media=False)
    assert row['voice_status'] == 'unavailable' and row['audio'] is None
    assert row['channels'] == ['dialogue']


@pytest.mark.parametrize('duration', [2.5, None])
def test_top_dialogue_is_captured_only_with_primary_duration_outside_the_bottom_lane(tmp_path, duration):
    text, bottom = 'The complete voiced caption appears above the scene.', 'An ordinary bottom-lane conversation.'
    rows = top_rows(duration=duration)
    rows.append({**rows[0], 'text_id': 'endfield:bottom', 'source_text': bottom,
                 'texts': {'en': bottom}, 'channels': ['dialogue']})
    index = load_index(tmp_path / 'language', rows, publisher_top_dialogue_cues=1)
    expected = ['endfield:top'] if duration else []
    assert [hit.text_id for hit in index.match_full_frame_voice_lines([text])] == expected
    assert not index.match_full_frame_voice_lines([bottom])
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    engine = SimpleNamespace(recognize_pil=lambda _: {'lines': [ocr_row(text, .1, .1, size=(800, 200))]})

    async def run():
        service._event_loop = asyncio.get_running_loop()
        assert not service.settings.get().capture_unvoiced
        def scan():
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                         datetime.now(timezone.utc), 'endfield')
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == expected
        await asyncio.sleep(.01)
        assert len(scheduled) == bool(duration)
    asyncio.run(run())


def step_rows():
    catalog = Catalog({'DungeonCharTutorialStepTable': {
        identity: {'stepDesc': ref(text)} for identity, text in (
            ('a_intro', 10), ('a_next', 20), ('b_intro', 10), ('b_next', 30), ('b_repeat', 10), ('b_finish', 40))},
        'DungeonCharTutorialTable': {
            'a': {'tutorialStageData': [{'stepIds': ['a_intro', 'a_next']}]},
            'b': {'tutorialStageData': [{'stepIds': ['b_intro', 'b_next', 'b_repeat', 'b_finish']}]}}})
    raw = assets.narrative_dialogues(catalog, [])
    texts = {'10': 'Keep performing the authored training sequence.', '20': 'Go!', '30': 'Wait!', '40': 'Now!'}
    return assets.dialogue_records(raw, {}, {'en': texts, 'fr': {key: 'FR ' + value for key, value in texts.items()}}, 'en', {})


def test_written_step_context_uses_native_stage_order_and_keeps_only_the_current_occurrence(tmp_path):
    from backend.endfield_training_presentation import SOURCE_ROLES
    from backend.tests.test_endfield_training_presentation import span, STAMP
    rows = step_rows()
    prefix = 'endfield:DungeonCharTutorialStepTable:'
    metadata = {'schema': 1, 'revision': STAMP, 'sources': {role: 'a'*32 for role in SOURCE_ROLES},
        'locales': {'en': {'titles': {'a': ['Operator Guide: Other'], 'b': ['Operator Guide: Current']},
            'labels': {row['text_id']: 'Battle Skill' for row in rows}, 'profile': []}},
        'stages': [{'owner': 'a', 'stage': 0, 'text_ids': [prefix + key for key in ('a_intro', 'a_next')]},
                   {'owner': 'b', 'stage': 0, 'text_ids': [prefix + key for key in ('b_intro', 'b_next', 'b_repeat', 'b_finish')]}],
        'goals': []}
    index = load_index(tmp_path / 'language', rows, fingerprint=STAMP, publisher_training_dialogue_ui=metadata)
    index.capture_unvoiced = True
    assert not index.match_lines(['Wait!'], exact_only=True, channel='tip')
    service, _, _, _ = fixture_service(tmp_path, game='endfield')
    settings = service.settings.get().model_copy(update={'capture_unvoiced': True, 'stable_frames': 2})
    service.settings.save(settings)
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    response = {'lines': []}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    def scan(text, *, menu=False):
        response.update(lines=[span('Operator Guide: Current', 80, 250, 600),
            span('Battle Skill', 850, 105, 100), span('Battle Skill', 958, 105, 100),
            span(text, 400, 820, 1120)], dialogue_menu=menu)
        return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                     datetime.now(timezone.utc), 'endfield')
    def twice(text):
        scan(text)
        return scan(text)
    # The same complete intro is shared by two stages. Only their authored
    # successors disambiguate the current short instruction and translation.
    assert not twice('Wait!').emitted_lines
    twice('Keep performing the authored training sequence.')
    assert [line.text_id for line in twice('Wait!').emitted_lines] == ['endfield:DungeonCharTutorialStepTable:b_next']
    repeated = twice('Keep performing the authored training sequence.')
    assert [line.text_id for line in repeated.emitted_lines] == ['endfield:DungeonCharTutorialStepTable:b_repeat']
    assert not any(key.endswith(':a_intro') for key in service._unvoiced_trackers)
    # A menu/epoch change cannot carry the previous training step into a new one.
    scan('Keep performing the authored training sequence.', menu=True)
    assert not twice('Now!').emitted_lines


def test_reused_stage_step_with_different_predecessors_gets_no_guessed_order():
    catalog = Catalog({'DungeonCharTutorialStepTable': {
        'first': {'stepDesc': ref(1)}, 'other': {'stepDesc': ref(2)}, 'shared': {'stepDesc': ref(3)}},
        'DungeonCharTutorialTable': {'a': {'tutorialStageData': [
            {'stepIds': ['first', 'shared']}, {'stepIds': ['other', 'shared']}]}}})
    rows = assets.narrative_dialogues(catalog, [])
    assert 'previous_mission_id' not in rows['DungeonCharTutorialStepTable:shared']
