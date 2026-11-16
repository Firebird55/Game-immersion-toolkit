"""Original graph layout and stage order select off-lane/short captions safely."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from backend import endfield_assets as assets, endfield_mission_dialogue as mission
from backend.capture import _ScanOutcome
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_audit import Catalog, ref
from backend.tests.test_endfield_mission_dialogue import graph, trunk
from backend.tests.test_local_chatter import row as ocr_row
from backend.tests.test_subtitle_capture import fixture_service


def load_index(directory, rows, **metadata):
    directory.mkdir(exist_ok=True)
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows, **metadata}), encoding='utf-8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready
    return index


def test_original_top_layout_uses_same_lane_edges_and_new_ids_without_a_mission_allowlist(tmp_path, monkeypatch):
    path = mission.assets.DIALOG_GRAPHS + 'npc/new_package/renamed_graph.json'
    nodes = [trunk('a', 'new_top_first', _showAtTop=True), trunk('b', 'new_top_second', _showAtTop=True),
             trunk('c', 'bottom'), trunk('d', 'disabled_top', _showAtTop=True, disablePlayVoice=True)]
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


def test_top_dialogue_is_captured_outside_the_bottom_lane_without_silent_capture(tmp_path):
    text, bottom = 'The complete voiced caption appears above the scene.', 'An ordinary bottom-lane conversation.'
    catalog = Catalog({'DialogTextTable': {
        'top': {'dialogText': ref(1)}, 'bottom': {'dialogText': ref(2)}}})
    catalog.top_dialogues = lambda: {'top': None}
    raw = assets.authored_dialogues(catalog)
    rows = assets.dialogue_records(raw, {}, {'en': {'1': text, '2': bottom}}, 'en', {})
    for entry in rows:
        entry.update(audio={'file_id': entry['text_id']}, voice_status='voiced')
    index = load_index(tmp_path / 'language', rows, publisher_top_dialogue_cues=1)
    assert [hit.text_id for hit in index.match_full_frame_voice_lines([text])] == ['endfield:top']
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
        assert [line.text_id for line in scan().emitted_lines] == ['endfield:top']
        await asyncio.sleep(.01)
        assert len(scheduled) == 1
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
    rows = step_rows()
    index = load_index(tmp_path / 'language', rows)
    index.capture_unvoiced = True
    assert not index.match_lines(['Wait!'], exact_only=True, channel='tip')
    service, _, _, _ = fixture_service(tmp_path, game='endfield')
    settings = service.settings.get().model_copy(update={'capture_unvoiced': True, 'stable_frames': 2})
    service.settings.save(settings)
    response = {'lines': []}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    def scan(text, *, menu=False):
        response.update(lines=[ocr_row(text, .1, .3, size=(800, 200))], dialogue_menu=menu)
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
