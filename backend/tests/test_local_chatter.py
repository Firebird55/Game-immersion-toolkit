"""Extra regions must not turn response menus or HUD into Mandarin speech."""
from datetime import datetime, timezone
from types import SimpleNamespace
import time

import pytest

from backend.capture import CaptureService
from backend.models import CaptureRegion
from backend.tests.test_subtitle_capture import fixture_service


def row(text, left, top, width=.25, height=.03, size=(1000, 1000)):
    x, y, w, h = left*size[0], top*size[1], width*size[0], height*size[1]
    return {"text": text, "bounding_rect": {"x1": x, "y1": y, "x2": x+w, "y2": y,
                                            "x3": x+w, "y3": y+h, "x4": x, "y4": y+h}}


@pytest.mark.parametrize("game", ["cyberpunk", "wuwa", "witcher3"])
def test_response_choices_are_removed_and_block_extra_voice_region(game):
    region = CaptureRegion(left=0, top=0, width=1, height=1)
    response = {"lines": [row("Stay close to me.", .25, .88), row("I believe so.", .71, .65), row("Talk", .5, .78), row("Verbena", .5, .77)]}
    result = CaptureService._local_subtitle_rows(response, (1000, 1000), region, game)
    assert [r["text"] for r in result["lines"]] == ["Stay close to me."]
    assert result["dialogue_menu"]


@pytest.mark.parametrize('game,left', [('portal', .02), ('persona5royal', .68)])
def test_new_game_calibration_keeps_off_center_authored_captions(tmp_path, game, left):
    import asyncio
    service, match, scheduled, published = fixture_service(tmp_path, game=game)
    service.game_indexes = {game: service.textmaps}
    service.game_voice_assets = {game: service.voice_assets}
    service.textmaps.audio_count = 1
    service.textmaps.match_lines = lambda lines, **_: match if match.english in lines else None
    service._engine = SimpleNamespace(recognize_pil=lambda _: {'lines': [
        row(match.english, left, .20, size=(800, 200))]})

    async def run():
        service._event_loop = asyncio.get_running_loop()
        window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title=game)
        for _ in range(2):
            service._scan_pragmata(window, getattr(service.settings.get(), game + '_region'),
                service._engine, 0, datetime.now(timezone.utc), game=game)
        await asyncio.sleep(.02)
    try:
        asyncio.run(run())
        assert len(scheduled) == len(published) == 1
        assert published[0].game == game and published[0].audio_source == 'original'
    finally:
        service._executor.shutdown()


def test_persona_floating_voices_are_exact_stable_and_never_borrow_choice_audio(tmp_path):
    import asyncio
    import json
    from backend.capture import _ScanOutcome
    from backend.multilingual_index import MultilingualTextIndex

    texts = {'first': 'An enemy is approaching from the western corridor.',
             'second': 'We should meet near the station after school.',
             'choice_voice': 'I will help you after the battle.', 'short': 'Hello!'}
    records = [{'text_id': key, 'english': text, 'source_locale': 'en', 'source_text': text,
                'texts': {'en': text}, 'audio_locale': 'en', 'audio': {'name': key},
                'voice_status': 'voiced', 'channels': ['dialogue']} for key, text in texts.items()]
    records.append({**records[2], 'text_id': 'choice_silent', 'audio': None,
                    'voice_status': 'unvoiced', 'dialogue_kind': 'choice'})
    directory = tmp_path / 'language'
    directory.mkdir()
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'persona5royal',
        'source_locale': 'en', 'records': records}), encoding='utf-8')
    index = MultilingualTextIndex('persona5royal', directory)
    assert index.ready
    service, _, scheduled, published = fixture_service(tmp_path, game='persona5royal')
    service.game_indexes = {'persona5royal': index}
    service.game_voice_assets = {'persona5royal': service.voice_assets}
    window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title='Persona')
    response = {'lines': [row(texts['first'], .60, .10), row(texts['second'], .05, .40),
                          row(texts['choice_voice'], .35, .60), row(texts['short'], .10, .80)]}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    async def run():
        service._event_loop = asyncio.get_running_loop()
        def scan():
            return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                          datetime.now(timezone.utc), 'persona5royal')
        # Full-frame voice support works independently of the silent toggle.
        assert not service.settings.get().capture_unvoiced
        assert scan().emitted_lines == []
        assert {line.text_id for line in scan().emitted_lines} == {'first', 'second'}
        assert scan().emitted_lines == []
        await asyncio.sleep(.02)
        assert len(scheduled) == len(published) == 2
        response['lines'] = [row(texts['first'].replace('western', 'westernmost'), .6, .1)]
        assert not scan().emitted_lines and not scan().emitted_lines
        index.capture_unvoiced = True
        assert not index.match_full_frame_voice_lines([texts['choice_voice']])
        assert not index.match_full_frame_voice_lines([texts['short']])
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("game", ["cyberpunk", "wuwa", "witcher3"])
@pytest.mark.parametrize("blocked", ["main", "menu", "unmapped", "fuzzy", "disabled", "short", "unpositioned", "none"])
def test_auxiliary_capture_requires_position_exact_voice_and_consecutive_frames(tmp_path, game, blocked):
    service, match, _, _ = fixture_service(tmp_path, game=game)
    service.game_indexes = {game: service.textmaps}
    service.game_voice_assets = {game: SimpleNamespace(has_variant=lambda *_: blocked != "unmapped")}
    if blocked == "fuzzy":
        match.kind, match.score = "fuzzy", 99
    text = "Talk" if blocked == "short" else match.english
    response = {"lines": [{"text": text}] if blocked == "unpositioned" else [row(text, .3, .2)]}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title=game)
    service.settings.save(service.settings.get().model_copy(update={f"{game}_capture_chatter": blocked != "disabled"}))
    scheduled = []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: scheduled.append(line)
    main = match if blocked == "main" else None
    try:
        for _ in range(2):
            service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), game,
                                        main, dialogue_menu=blocked == "menu")
        assert service.transcript.count() == (1 if blocked == "none" else 0)
        if scheduled:
            assert scheduled[0].channel == ("tip" if game == "wuwa" else "gameplay")
            # Overlapping lower and world crops cannot repeat the same voice.
            assert not service._can_emit(f"{game}\0{match.text_id}\0{match.english}", time.monotonic())
    finally:
        service._executor.shutdown()


def test_blank_frame_resets_auxiliary_confirmation(tmp_path):
    service, match, _, _ = fixture_service(tmp_path, game="cyberpunk")
    service.game_indexes = {"cyberpunk": service.textmaps}
    service.game_voice_assets = {"cyberpunk": service.voice_assets}
    response = {"lines": [row(match.english, .3, .2)]}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title="fixture")
    try:
        service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "cyberpunk", None)
        response["lines"] = []
        service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "cyberpunk", None)
        response["lines"] = [row(match.english, .3, .2)]
        service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "cyberpunk", None)
        assert service.transcript.count() == 0
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("menu", [True, False])
def test_wuwa_centered_cards_require_dark_scene_and_no_choice_menu(tmp_path, dark, menu):
    from PIL import Image
    service, match, _, _ = fixture_service(tmp_path, game="wuwa")
    service.game_indexes = {"wuwa": service.textmaps}
    service.game_voice_assets = {"wuwa": service.voice_assets}
    service._capture = lambda bounds: Image.new("RGB", (800, 300), "black" if dark else "white")
    service._schedule_line_audio = lambda *_args, **_kwargs: None
    engine = SimpleNamespace(recognize_pil=lambda _: {"lines": [row(match.english, .3, .2)]})
    window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title="fixture")
    try:
        for _ in range(2):
            service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "wuwa", None,
                                        dialogue_menu=menu, presentation="cinematic")
        assert service.transcript.count() == int(dark and not menu)
        if dark and not menu:
            assert service.snapshot().cinematic_crop_bounds is not None
    finally:
        service._executor.shutdown()


def test_exact_auxiliary_lookup_never_searches_unrelated_dialogue(tmp_path, monkeypatch):
    import json
    from backend.local_game import LocalGameTextIndex
    import backend.local_game as module
    (tmp_path / "textmap.json").write_text(json.dumps({"records": [{
        "text_id": "wuwa:1", "english": "Stay close to me.", "chinese": "一定要紧紧跟着我。", "audio": {"file": "official"}}]}), encoding="utf-8")
    index = LocalGameTextIndex("wuwa", tmp_path)
    monkeypatch.setattr(module.process, "extract", lambda *_args, **_kwargs: pytest.fail("Exact channels must not search the whole index"))
    assert index.match_lines(["Stay close to me."], exact_only=True).kind == "exact"
    assert index.match_lines(["一定要紧紧跟着我。"], exact_only=True).kind == "exact"
    assert index.match_lines(["Stay close to us."], exact_only=True) is None
    assert index.match_lines(["一定要紧紧跟着你。"], exact_only=True) is None


def test_stopping_capture_clears_auxiliary_confirmation_and_freshness(tmp_path):
    service, match, _, _ = fixture_service(tmp_path, game="cyberpunk")
    service.game_indexes = {"cyberpunk": service.textmaps}
    service.game_voice_assets = {"cyberpunk": service.voice_assets}
    engine = SimpleNamespace(recognize_pil=lambda _: {"lines": [row(match.english, .3, .2)]})
    window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title="fixture")
    try:
        service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "cyberpunk", None)
        keys = set(service._local_chatter_trackers)
        assert keys
        service._update_snapshot(phase="stopped")
        assert not service._local_chatter_trackers
        assert not keys & service._visible_match_started.keys()
        service._scan_local_chatter(window, engine, 0, datetime.now(timezone.utc), "cyberpunk", None)
        assert service.transcript.count() == 0
    finally:
        service._executor.shutdown()


def test_short_spoken_caption_is_preserved_inside_its_caption_band():
    region = CaptureRegion(left=0, top=0, width=1, height=1)
    response = {"lines": [row("Attack!", .4, .82), row("Verbena", .5, .97)]}
    result = CaptureService._local_subtitle_rows(response, (1000, 1000), region, "witcher3")
    assert [r["text"] for r in result["lines"]] == ["Attack!"]
