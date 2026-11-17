"""Owned graph evidence reaches only the narrow NTE capture lane."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from PIL import Image

from backend.models import CaptureRegion
from backend.multilingual_index import MultilingualTextIndex
from backend.nte_dialogue_graph import annotate, direct_pairs
from backend.tests.test_nte_dialogue_graph import fixture, NAMESPACES
from backend.tests.test_player_speaker_capture import positioned
from backend.tests.test_subtitle_capture import fixture_service


def test_real_capture_dispatch_requires_stable_graph_anchor_and_clears_on_choice_menu(tmp_path):
    def row(key, text, *, status='voiced'):
        return dict(text_id='nte:Actual_Conversation:'+key, english=text, chinese='', source_locale='en',
            source_text=text, texts={'en': text}, audio_locale='en', voice_status=status,
            audio={'voice': key} if status=='voiced' else None, channels=['dialogue'], dialogue_kind='conversation')
    opening = 'Keep watching the western entrance.'
    rows = [row('First', opening), row('Short', 'Ah?'), row('Elsewhere', 'Ah?'), row('UI', 'Ah?', status='unknown')]
    annotate(rows, direct_pairs(fixture(), NAMESPACES))
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.ready and index.match_lines(['Ah?'], exact_only=True) is None
    service, _, scheduled, published = fixture_service(tmp_path, game='nte')
    service.game_indexes['nte'] = index
    service.game_voice_assets['nte'] = service.pragmata_voice_assets
    service._capture = lambda _: Image.new('RGB', (1000, 1000))
    service._ocr_image = lambda image, _: image
    window = SimpleNamespace(handle=1, bounds=(0,0,1000,1000), title='Owned capture fixture')
    response = {'lines': []}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    region = CaptureRegion(left=0, top=0, width=1, height=1)
    emitted = []
    def scans(text, count=3, *, menu=False):
        response['lines'] = [positioned(text, .84)] if text else []
        if menu: response['lines'].append(positioned('Owned response option', .72, .7, .95))
        for _ in range(count):
            outcome=service._scan_pragmata(window,region,engine,0,datetime.now(timezone.utc),'nte')
            emitted.extend(outcome.emitted_lines)
    async def replay():
        service._event_loop=asyncio.get_running_loop()
        scans('Ah?')
        assert not emitted and not scheduled
        scans(opening)
        scans('Ah?')
        assert [line.text_id for line in emitted]==['nte:Actual_Conversation:First','nte:Actual_Conversation:Short']
        assert index.match_lines(['Ah?'], exact_only=True) is None
        scans(opening)
        assert service._nte_dialogue.anchor=='nte:Actual_Conversation:First'
        scans('Ah?',menu=True)
        assert service._nte_dialogue.anchor is None
        scans('Ah?')
        assert len(emitted)==2
        await asyncio.sleep(.02)
    try:
        asyncio.run(replay())
        assert len(scheduled)==len(published)==2
        assert all(line.channel=='dialogue' for line in published)
    finally:
        service._executor.shutdown()
