"""Visible world ownership distinguishes original takes without aliasing them."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from backend import endfield_presentation as ui
from backend.capture import _ScanOutcome
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_recording_identity import pair
from backend.tests.test_subtitle_capture import fixture_service


def metadata():
    return {'schema': 1, 'revision': 'endfield-' + '1' * 64,
        'sources': {key: '2' * 32 for key in ui.SOURCE_ROLES}, 'locales': {'en': {
            'auto': ['Auto', 'Auto-Play', 'Automating'], 'skip': ['Skip'], 'profile': ['Profile', 'Audio Log'],
            'speakers': {'chr_0001_example': ['Operator']}}}}


def span(text, x, y, width, height=.025):
    return {'text': text, 'confidence': .99, 'bounding_rect': {
        'x1': x*1920, 'x2': (x+width)*1920, 'x3': (x+width)*1920, 'x4': x*1920,
        'y1': y*1080, 'y2': y*1080, 'y3': (y+height)*1080, 'y4': (y+height)*1080}}


def frame(text=None):
    return [span('Auto-Play', .78, .05, .1), span('Skip', .92, .05, .06),
            span('Operator', .45, .83, .1), span(text or pair()[0]['source_text'], .1, .9, .8, .065)]


def index_for(directory, rows=None, descriptor=None):
    directory.mkdir(exist_ok=True)
    (directory/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield', 'source_locale': 'en',
        'publisher_world_dialogue_ui': descriptor or metadata(), 'records': rows or pair()}), encoding='utf8')
    index = MultilingualTextIndex('endfield', directory)
    assert index.ready, index.status()
    return index


def test_world_owns_its_recording_without_aliasing_the_profile_or_replacing_translations(tmp_path):
    rows = pair()
    rows[1]['texts']['zh-Hans'] = '另一种官方译文。'
    original = deepcopy(rows)
    index = index_for(tmp_path, rows)
    assert not index.match_lines([rows[0]['source_text']], exact_only=True)
    hit = index.match_endfield_world_caption(frame(), (1920, 1080))
    assert hit and hit.text_id == rows[0]['text_id'] and hit.texts == rows[0]['texts']
    assert index.voice_snapshot(index._signature)['records'] == [
        {**row, 'audio_scope': 'line'} for row in original]
    assert not index.match_lines([rows[0]['source_text']], exact_only=True)


@pytest.mark.parametrize('kind,status,audio', [
    ('conversation', 'voiced', {'file_id': 'another-take'}),
    ('cinematic', 'voiced', {'file_id': 'another-film'}),
    ('radio', 'voiced', {'file_id': 'another-radio'}),
    ('conversation', 'unknown', None), ('conversation', 'unavailable', None),
    ('tutorial', 'unvoiced', None),
])
def test_other_presentations_missing_and_unknown_vetoes_still_block_world_ownership(tmp_path, kind, status, audio):
    rows = pair()
    rows.append({**deepcopy(rows[0]), 'text_id': 'endfield:competing',
                 'dialogue_kind': kind, 'voice_status': status, 'audio': audio})
    index = index_for(tmp_path, rows)
    assert not index.match_endfield_world_caption(frame(), (1920, 1080))


def test_world_proof_cannot_bypass_previous_or_short_caption_guards(tmp_path):
    rows = pair()
    rows[0].update(requires_previous=True, previous_text_id='endfield:prior')
    index = index_for(tmp_path/'guarded', rows)
    assert not index.match_endfield_world_caption(frame(), (1920, 1080))
    for row in rows:
        row.update(source_text='Wait!', texts={'en': 'Wait!', 'zh-Hans': '等一下！'}, english='Wait!')
        row.pop('requires_previous', None)
        row.pop('previous_text_id', None)
    index = index_for(tmp_path/'short', rows)
    assert not index.match_endfield_world_caption(frame('Wait!'), (1920, 1080))


def test_known_sentence_inside_an_unmatched_complete_body_cannot_supply_world_ownership(tmp_path):
    index = index_for(tmp_path)
    caption = pair()[0]['source_text']
    assert index.match_endfield_world_caption(frame(caption), (1920, 1080))
    for body in (caption + ' This additional visible sentence belongs to another passage.',
                 'An additional sentence precedes this one. ' + caption):
        assert not index.match_endfield_world_caption(frame(body), (1920, 1080))


def test_world_actor_and_snapshot_must_still_be_the_current_source(tmp_path, monkeypatch):
    descriptor = metadata()
    descriptor['locales']['en']['speakers'] = {'chr_0002_other': ['Operator']}
    index = index_for(tmp_path/'actor', descriptor=descriptor)
    assert not index.match_endfield_world_caption(frame(), (1920, 1080))
    index = index_for(tmp_path/'changed')
    original = ui.observe_world_caption
    def changed(*args):
        proof = original(*args)
        index.snapshot_metadata['publisher_world_dialogue_ui']['revision'] = 'endfield-' + '3'*64
        return proof
    monkeypatch.setattr(ui, 'observe_world_caption', changed)
    assert not index.match_endfield_world_caption(frame(), (1920, 1080))


@pytest.mark.parametrize('confidence', [None, 0, .79, 1.01, True, float('nan'), float('inf')])
def test_controls_require_real_bounded_confidence(confidence):
    lines = frame()
    lines[1]['confidence'] = confidence
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))


@pytest.mark.parametrize('remove', [0, 1, 2, 3])
def test_incomplete_controls_actor_or_body_supply_no_world_proof(remove):
    lines = frame()
    lines.pop(remove)
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))


def test_profile_choice_only_unpositioned_and_changed_controls_fail_closed():
    lines = frame()
    lines.extend([span('Profile', .4, .2, .1), span('Audio Log', .6, .2, .15)])
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))
    lines = frame()
    lines[3] = span(lines[3]['text'], .7, .9, .25)
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))
    lines = frame()
    lines[0].pop('bounding_rect')
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))
    lines = frame()
    lines[0]['text'] = 'Changed control'
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))
    lines = frame()
    lines[0]['bounding_rect'], lines[1]['bounding_rect'] = lines[1]['bounding_rect'], lines[0]['bounding_rect']
    assert not ui.observe_world_caption(metadata(), lines, (1920, 1080))


def test_production_capture_can_read_complete_spoken_body_beside_choices_without_a_predecessor(tmp_path):
    index = index_for(tmp_path/'language')
    service, _, scheduled, _ = fixture_service(tmp_path, game='endfield')
    service.game_indexes = {'endfield': index}
    service.game_voice_assets = {'endfield': service.voice_assets}
    service._capture = lambda _: SimpleNamespace(size=(1920, 1080))
    service._ocr_image = lambda image, _: image
    lines = frame()
    lines += [span('Give an operator gift.', .72, .6, .25), span('Leave', .72, .7, .1)]
    engine = SimpleNamespace(recognize_pil=lambda _: {'lines': lines, 'dialogue_menu': True})
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Endfield')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        assert not service.settings.get().capture_unvoiced and not service.settings.get().capture_missing_audio
        def scan():
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                         datetime.now(timezone.utc), 'endfield')
        assert not scan().emitted_lines
        assert [hit.text_id for hit in scan().emitted_lines] == ['endfield:spoken']
        await asyncio.sleep(.01)
        assert len(scheduled) == 1
        # UI ownership is stateless; no conversation predecessor was observed.
        assert not service._endfield_conversation.observe(index, ['Wait!'], [], kind='conversation',
            channel='dialogue', scope='new-menu', now=1, stable_frames=2)
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
