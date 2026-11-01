"""Custom display names are screen labels, never original-voice identities."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.models import CaptureRegion
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_subtitle_capture import fixture_service


BODY = 'I will go to the station first. You can collect the supplies.'


def positioned(text, top, left=.3, right=.7):
    return {'text': text, 'confidence': .99, 'bounding_rect': {
        'x1': left * 1000, 'x2': right * 1000, 'x3': right * 1000, 'x4': left * 1000,
        'y1': top * 1000, 'y2': top * 1000, 'y3': (top + .025) * 1000, 'y4': (top + .025) * 1000}}


def record(identity, text, *, voice='authored-test-voice'):
    # Synthetic authored bindings exercise capture dispatch, not native playback.
    return dict(text_id=identity, english=text, chinese='', source_locale='en',
        source_text=text, texts={'en': text}, audio_locale='en', audio={'voice': voice},
        speaker_english='Zero', channels=['dialogue'])


@pytest.mark.parametrize('observed_name', ['GameRiot', 'DifferentPlayer', 'A Player Name', '旅行者'])
@pytest.mark.parametrize('ambiguous', [False, True])
def test_custom_speaker_label_never_selects_an_original_voice(tmp_path, observed_name, ambiguous):
    rows = [record('nte:authored:caption', BODY)]
    if ambiguous:
        rows.append(record('nte:other:caption', BODY, voice='other-authored-voice'))
    service, _, scheduled, published = fixture_service(tmp_path, game='nte')
    (tmp_path / 'textmap.json').write_text(json.dumps(
        {'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.ready
    service.game_indexes['nte'] = index
    service.game_voice_assets['nte'] = service.pragmata_voice_assets
    service._capture = lambda _: Image.new('RGB', (1000, 1000))
    service._ocr_image = lambda image, _: image
    response = {'lines': [positioned(observed_name, .76, .46, .54),
        positioned('I will go to the station first.', .82),
        positioned('You can collect the supplies.', .85)]}
    service._engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1000, 1000), title='Synthetic game')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        for _ in range(3):
            service._scan_pragmata(window, CaptureRegion(left=0, top=0, width=1, height=1),
                service._engine, 0, datetime.now(timezone.utc), 'nte')
        await asyncio.sleep(.01)
    try:
        asyncio.run(run())
        assert len(scheduled) == len(published) == int(not ambiguous)
        if published:
            assert published[0].text_id == rows[0]['text_id']
            assert published[0].speaker_english == 'Zero'
            assert published[0].english == BODY
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize('name_only', [False, True])
def test_supplied_partial_player_screenshot_waits_and_name_only_never_captures(tmp_path, name_only):
    corpus = Path(__file__).resolve().parents[2] / 'tests/fixtures/game-screenshots/manifest.json'
    case = next(row for row in json.loads(corpus.read_text())['cases'] if row['id'] == 'nte-17')
    assert case['partial'] and case['speaker_kind'] == 'custom_player_name'
    service, _, scheduled, published = fixture_service(tmp_path, game='nte')
    # Include a deliberate name collision to prove it cannot be spoken merely
    # because the same text exists in the authored database.
    # An explicitly synthetic longer catalog row proves the typewriter prefix
    # is not completed from the catalog. It is not the game's unseen wording.
    longer = case['expected_captions'][0] + ' [synthetic unseen continuation]'
    rows = [record('nte:synthetic:body', longer), record('nte:synthetic:name', case['speaker'])]
    (tmp_path / 'textmap.json').write_text(json.dumps(
        {'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}), encoding='utf-8')
    service.game_indexes['nte'] = MultilingualTextIndex('nte', tmp_path)
    service.game_voice_assets['nte'] = service.pragmata_voice_assets
    service._capture = lambda _: Image.new('RGB', (1000, 1000))
    service._ocr_image = lambda image, _: image
    response = {'lines': [positioned(case['speaker'], .76, .46, .54)]}
    if not name_only:
        response['lines'].append(positioned(case['expected_captions'][0], .82))
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1000, 1000), title='Synthetic game')
    try:
        for _ in range(4):
            assert not service._scan_pragmata(window, CaptureRegion(left=0, top=0, width=1, height=1),
                engine, 0, datetime.now(timezone.utc), 'nte').emitted_lines
        assert not scheduled and not published and service.transcript.count() == 0
    finally:
        service._executor.shutdown()
