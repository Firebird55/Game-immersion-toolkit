"""Subtitle-only capture must never depend on headset audio or speech detection."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.capture import CaptureService
from backend.config import SettingsStore
from backend.models import TextMatch
from backend.storage import TranscriptStore


def fixture_service(tmp_path, channel="dialogue", mapped=True, game="zzz", text_id=None):
    match = TextMatch(game=game, text_id=text_id or f"{game}:spoken", english="Stay close to me.",
                      chinese="跟紧我。", source_ocr="Stay close to me.", score=100, kind="exact")
    index = SimpleNamespace(ready=True,
        match_lines=lambda lines, **kwargs: match if kwargs.get("channel", "dialogue") == channel else None,
        match_line_groups=lambda lines, **kwargs: [match] if channel == "cinematic" else [])
    scheduled, published = [], []
    def schedule(*args):
        scheduled.append(args)
        return True
    assets = SimpleNamespace(has_variant=lambda *_: mapped, schedule=schedule)
    async def on_line(line):
        published.append(line)
    async def ignore(*_):
        pass
    service = CaptureService(SettingsStore(tmp_path / "settings.json"), index, index,
        TranscriptStore(tmp_path / "transcript.db"), on_line, ignore, ignore, tmp_path / "audio",
        voice_assets=assets, pragmata_voice_assets=assets)
    service._engine = SimpleNamespace(recognize_pil=lambda image:
        {"lines": [{"text": "Stay close to me.", "confidence": .99}]})
    service._capture = lambda bounds: Image.new("RGB", (800, 200), (180, 160, 150))
    service._tip_tracker.configure(1)
    return service, match, scheduled, published


def test_new_voice_mapping_repairs_a_previously_unvoiced_saved_comic(tmp_path):
    service, match, scheduled, published = fixture_service(tmp_path,channel='cinematic',text_id='Comic_'+'a'*32)
    async def run():
        saved=service.transcript.add(match,'test',channel='cinematic')
        assert not saved.voiced and not saved.has_audio
        finished=[]
        assert service.repair_recorded_line(saved,completed=lambda:finished.append(True))
        scheduled[0][2](saved.id,'official-comic-test.mp3',True)
        await asyncio.sleep(.02)
        repaired=service.transcript.get(saved.id)
        assert repaired.voiced and repaired.has_audio and repaired.audio_source=='original'
        assert published[-1].id==saved.id and published[-1].has_audio
        assert finished==[True]
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


def test_historical_audio_repair_uses_its_stored_learning_locale(tmp_path):
    service, match, active_scheduled, _ = fixture_service(tmp_path)
    source = match.model_copy(update={'source_language': 'ja', 'source_locale': 'ja', 'audio_locale': 'ja',
                                      'source_text': 'ここで待っていてください。'})
    saved = service.transcript.add(source, 'test')
    saved = service.transcript.update_audio(saved.id, None, True)
    restored = []
    service.voice_assets.locale = 'zh-Hans'
    service.recorded_voice_assets = lambda line: SimpleNamespace(locale=line.source_locale,
        has_variant=lambda *_: True, schedule=lambda *args: restored.append(args) or True)
    try:
        assert service.repair_recorded_line(saved)
        assert len(restored) == 1 and not active_scheduled
        service.recorded_voice_assets = lambda _: service.voice_assets
        assert not service.repair_recorded_line(saved), 'Another language cannot repair the stored original'
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("channel", ["dialogue", "gameplay", "tip", "cinematic"])
@pytest.mark.parametrize("mapped", [True, False])
def test_zzz_channels_capture_only_subtitles_with_game_voice_mapping(tmp_path, monkeypatch, channel, mapped):
    import backend.capture as module
    service, match, scheduled, published = fixture_service(tmp_path, channel, mapped)
    monkeypatch.setattr(module, "find_active_game_window", lambda settings:
        (SimpleNamespace(id="zzz"), SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title="ZZZ")))
    async def run():
        service._event_loop = asyncio.get_running_loop()
        service._scan_once()
        service._scan_once()
        await asyncio.sleep(.02)
    try:
        asyncio.run(run())
        assert not hasattr(service, "audio")
        assert not hasattr(service, "agent_recognizer")
        assert not hasattr(service, "story_voice_resolver")
        assert len(scheduled) == len(published) == int(mapped)
        assert service.transcript.count() == int(mapped)
        if mapped:
            assert published[0].audio_pending and published[0].voiced
            assert published[0].audio_source == "original"
            assert published[0].english == match.english
            assert scheduled[0][:2] == (match.text_id, published[0].id)
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("mapped", [True, False])
def test_pragmata_uses_subtitles_and_original_assets_without_speech_gate(tmp_path, mapped):
    service, match, scheduled, published = fixture_service(tmp_path, mapped=mapped, game="pragmata")
    async def run():
        service._event_loop = asyncio.get_running_loop()
        window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title="PRAGMATA")
        region = service.settings.get().region
        for _ in range(2):
            service._scan_pragmata(window, region, service._engine, 0, datetime.now(timezone.utc))
        await asyncio.sleep(.02)
    try:
        asyncio.run(run())
        assert len(scheduled) == len(published) == int(mapped)
        if mapped:
            assert published[0].game == "pragmata" and published[0].audio_pending
    finally:
        service._executor.shutdown()


def test_certified_unvoiced_dialogue_is_opt_in_durable_and_never_schedules_audio(tmp_path):
    service, match, scheduled, published = fixture_service(tmp_path, mapped=False, game='pragmata')
    match.voice_status, match.dialogue_kind = 'unvoiced', 'conversation'

    async def run():
        service._event_loop = asyncio.get_running_loop()
        window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title='PRAGMATA')
        def scan():
            service._scan_pragmata(window, service.settings.get().region, service._engine, 0, datetime.now(timezone.utc))
        for _ in range(3):
            scan()
        assert not published and service.transcript.count() == 0
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
        assert SettingsStore(service.settings.path).get().capture_unvoiced
        for _ in range(3):
            scan()
        await asyncio.sleep(.02)
        assert len(published) == 1 and not scheduled
        line = published[0]
        assert line.voice_status == 'unvoiced' and line.dialogue_kind == 'conversation'
        assert not line.voiced and not line.has_audio and not line.audio_pending
        restarted = TranscriptStore(service.transcript.path)
        assert restarted.purge_unvoiced() == []
        assert restarted.get(line.id).voice_status == 'unvoiced'
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': False}))
        assert not service._capturable_match(match)
        assert restarted.get(line.id) is not None
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


def test_unvoiced_page_outside_caption_lane_is_stable_opt_in_and_resets_after_toggle(tmp_path, monkeypatch):
    import json
    from backend import api
    from backend.capture import _ScanOutcome
    from backend.multilingual_index import MultilingualTextIndex
    text = 'The sealed letter is waiting in your room.'
    directory = tmp_path / 'language'
    directory.mkdir()
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'cyberpunk',
        'source_locale': 'en', 'records': [{'text_id': 'letter', 'english': text, 'chinese': '',
            'source_locale': 'en', 'source_text': text, 'texts': {'en': text}, 'audio_locale': 'en',
            'audio': None, 'voice_status': 'unvoiced', 'dialogue_kind': 'readable', 'channels': ['tip']}]}), encoding='utf-8')
    index = MultilingualTextIndex('cyberpunk', directory)
    service, _, scheduled, published = fixture_service(tmp_path, game='cyberpunk')
    window = SimpleNamespace(bounds=(-1920, 0, 1920, 1080), title='Game')
    scans = []
    # A right-side page is deliberately excluded by the normal spoken-subtitle
    # lane; the silent pass reads it without borrowing a voiced match.
    response = {'lines': [{'text': text, 'bounding_rect':
        {'x1': 1400, 'y1': 120, 'x2': 1800, 'y2': 120, 'x3': 1800, 'y3': 150, 'x4': 1400, 'y4': 150}}]}
    engine = SimpleNamespace(recognize_pil=lambda image: scans.append(image.size) or response)
    async def run():
        service._event_loop = asyncio.get_running_loop()
        def scan():
            index.capture_unvoiced = service.settings.get().capture_unvoiced
            # A phone/page screen is deliberately excluded from voiced OCR on
            # every frame; it must not reset the separate silent confirmation.
            service._update_snapshot(phase='excluded_screen')
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                         datetime.now(timezone.utc), 'cyberpunk')
        scan()
        assert scans == []
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
        assert not scan().emitted_lines
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': False}))
        scan()
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
        assert not scan().emitted_lines, 'A toggle resets partial frame confirmation'
        assert len(scan().emitted_lines) == 1
        await asyncio.sleep(.02)
        assert len(published) == 1 and not scheduled
        assert published[0].dialogue_kind == 'readable' and published[0].voice_status == 'unvoiced'
        assert published[0].channel == 'tip'
        assert not scan().emitted_lines
        service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': False}))
        reopened = TranscriptStore(service.transcript.path)
        monkeypatch.setattr(api, 'runtime', SimpleNamespace(transcript=reopened,
            game_indexes={'cyberpunk': MultilingualTextIndex('cyberpunk', directory)}), raising=False)
        history = api.get_lines(limit=250, before_id=None, game='cyberpunk')
        assert [line.id for line in history] == [published[0].id]
        assert history[0].channel == 'tip'
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("game", ["zzz", "pragmata"])
def test_failed_original_extraction_keeps_subtitle_and_can_retry(tmp_path, game):
    service, match, scheduled, published = fixture_service(tmp_path, game=game)
    async def run():
        service._event_loop = asyncio.get_running_loop()
        line = service.transcript.add(match, "test")
        service._schedule_line_audio(line, 100, observed_at=99)
        scheduled[0][2](line.id, None, False)
        await asyncio.sleep(.02)
        assert len(published) == 2
        assert published[0].audio_pending and not published[1].audio_pending
        saved = service.transcript.get(line.id)
        assert saved.voiced and not saved.has_audio
        assert service.transcript.purge_unvoiced() == []
        assert service.repair_recorded_line(saved)
        scheduled[1][2](line.id, f"official-{line.id}-test.mp3", True)
        await asyncio.sleep(.02)
        assert service.transcript.get(line.id).has_audio
        assert published[-1].audio_source == "original"
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


def test_agent_routes_are_removed():
    from backend.api import app
    assert not any("/agents" in route.path for route in app.routes)


@pytest.mark.parametrize("mapped", [True, False])
def test_official_comic_publishes_once_and_survives_restart_without_voice(tmp_path, monkeypatch, mapped):
    import backend.capture as module
    from backend import api
    from backend.textmaps import TextMapIndex

    service, match, scheduled, published = fixture_service(
        tmp_path, "cinematic", mapped, text_id="Comic_" + "a" * 32)
    match.voice_status = 'voiced' if mapped else 'unvoiced'
    service.settings.save(service.settings.get().model_copy(update={'capture_unvoiced': True}))
    monkeypatch.setattr(module, "find_active_game_window", lambda settings:
        (SimpleNamespace(id="zzz"), SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title="ZZZ")))

    async def run():
        service._event_loop = asyncio.get_running_loop()
        for _ in range(5):
            service._scan_once()
        await asyncio.sleep(.02)

    try:
        asyncio.run(run())
        assert len(published) == 1
        assert len(scheduled) == int(mapped)
        assert published[0].chinese == match.chinese
        assert published[0].voiced == mapped
        assert published[0].audio_pending == mapped
        assert not published[0].has_audio
        assert service.transcript.purge_unvoiced() == []
        reopened = TranscriptStore(service.transcript.path)
        monkeypatch.setattr(api, "runtime", SimpleNamespace(
            transcript=reopened, speakers=SimpleNamespace(enrich=lambda line: line),
            game_indexes={}, textmaps=TextMapIndex), raising=False)
        lines = api.get_lines(limit=50, before_id=None, game="zzz")
        assert len(lines) == 1 and lines[0].is_comic
        assert lines[0].chinese == match.chinese
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("comic_already_saved", [False, True])
def test_comic_suffix_cannot_publish_as_unrelated_dialogue(tmp_path, monkeypatch, comic_already_saved):
    """A lower crop sees home... while the broad crop sees the full court bubble."""
    import json
    import backend.capture as module
    from backend.textmaps import TextMapIndex

    service, _, scheduled, published = fixture_service(tmp_path)
    full = ("The court proceedings will be streamed in full, and citizens are "
            "encouraged to follow the proceedings from home...")
    comic_id = "Comic_" + "b" * 32
    home_id = "GalGame_unrelated_home"
    index = TextMapIndex(tmp_path / "textmaps")
    index.data_dir.mkdir()
    for name, records in {
        "en_base": {comic_id: full, home_id: "Home."},
        "zh_base": {comic_id: "庭审将进行全程直播，市民可在家观看。", home_id: "在家吗。"},
        "en_overwrite": {}, "zh_overwrite": {},
    }.items():
        index.file_path(name).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    index.load()
    service.textmaps = index
    assert index.match_lines(["home..."]).text_id == home_id
    if comic_already_saved:
        service.transcript.add(index.match_text(full, channel="cinematic"),
                               service.session_id, channel="cinematic")
        service._cinematic_seen_ids.add(comic_id)
    service._scan_index = 1  # No periodic header/tip OCR during these three scans.
    service._tracker.configure(1)
    service._capture = lambda bounds: Image.new("RGB", (800, 200), (4, 4, 4))
    responses = iter([
        ["home..."], [full],
        ["home..."], [full],
        ["Home."], ["Home."],
    ])
    service._engine = SimpleNamespace(recognize_pil=lambda image:
        {"lines": [{"text": text, "confidence": .99} for text in next(responses)]})
    monkeypatch.setattr(module, "find_active_game_window", lambda settings:
        (SimpleNamespace(id="zzz"), SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title="ZZZ")))

    async def run():
        service._event_loop = asyncio.get_running_loop()
        for _ in range(2):
            service._scan_once()
        await asyncio.sleep(.02)
        assert service.transcript.count() == 1
        assert all(line.text_id == comic_id for line in published)
        assert all(args[0] == comic_id for args in scheduled)
        assert home_id not in service.snapshot().visible_text_ids
        # A later standalone utterance must remain eligible after the bubble clears.
        service._scan_once()
        await asyncio.sleep(.02)
        assert service.transcript.count() == 2
        assert published[-1].text_id == home_id

    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize('mapped', [True, False])
def test_centered_galgame_narration_requires_verified_voice(tmp_path, monkeypatch, mapped):
    import json
    import backend.capture as module
    from backend.textmaps import TextMapIndex
    from backend.windows import WindowInfo

    service, _, scheduled, published = fixture_service(tmp_path, mapped=mapped)
    text_id = 'GalGame_Narration_001'
    text = 'The hearing will begin shortly. Please welcome our next guest.'
    index = TextMapIndex(tmp_path / 'textmaps')
    index.data_dir.mkdir()
    for name, records in {'en_base': {text_id: text}, 'zh_base': {text_id: '听证会即将开始。请欢迎下一位嘉宾。'},
                          'en_overwrite': {}, 'zh_overwrite': {}}.items():
        index.file_path(name).write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    index.load()
    service.textmaps = index
    window = WindowInfo(1, 'Fixture game', 'game.exe', (0, 0, 1920, 1080))
    cinematic_bounds = service._region_bounds(window, service.settings.get().cinematic_region)
    def pixels(bounds):
        image = Image.new('RGB', (800, 200), (4, 4, 4))
        image.info['centered'] = bounds == cinematic_bounds
        return image
    service._capture = pixels
    service._engine = SimpleNamespace(recognize_pil=lambda image:
        {'lines': [{'text': text, 'confidence': .99}]} if image.info.get('centered') else {'lines': []})
    monkeypatch.setattr(module, 'find_active_game_window', lambda _: (SimpleNamespace(id='zzz'), window))
    async def run():
        service._event_loop = asyncio.get_running_loop()
        service._scan_once()
        await asyncio.sleep(.02)
    try:
        asyncio.run(run())
        assert service.transcript.count() == int(mapped)
        assert len(scheduled) == len(published) == int(mapped)
        if mapped:
            assert published[0].text_id == text_id
            assert published[0].channel == 'cinematic' and published[0].voiced
    finally:
        service._executor.shutdown()
