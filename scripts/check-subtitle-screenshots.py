"""Offline screenshot/OCR checks; synthetic fixtures use official game text.

Run --fixtures on a configured Windows PC, or --game <id> --image <screenshot>
to inspect actual screenshots without launching or modifying a game.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont
from oneocr import OcrEngine
from rapidfuzz import fuzz

import backend.capture as capture_module
from backend.capture import CaptureService
from backend.config import SettingsStore
from backend.games import GAME_PROFILES
from backend.game_assets import LOCAL_GAMES
from backend.local_game import LocalGameTextIndex
from backend.local_voice import LocalVoiceAssetService
from backend.pragmata import PragmataTextIndex
from backend.pragmata_audio import PragmataVoiceAssetService
from backend.storage import TranscriptStore
from backend.textmaps import TextMapIndex
from backend.voice_assets import VoiceAssetService
from backend.windows import WindowInfo
from backend.bilingual import normalize_subtitle

RESOLUTIONS = [(800, 600), (1280, 720), (1366, 768), (1280, 800), (1920, 1080),
               (1920, 1200), (2560, 1440), (3440, 1440), (3840, 2160), (5120, 1440)]


def wrap(text: str, font, width: int) -> list[str]:
    if '\n' in text:
        return [row for paragraph in text.splitlines() for row in wrap(paragraph, font, width)]
    rows, current = [], ""
    words = list(text) if any("\u3400" <= c <= "\u9fff" for c in text) else text.split()
    separator = "" if words == list(text) else " "
    for word in words:
        candidate = current + (separator if current else "") + word
        if current and font.getlength(candidate) > width:
            rows.append(current); current = word
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows


def fixture_image(game, english, chinese, language, resolution=(3840, 2160), font_scale=1.0):
    screen_width, screen_height = resolution
    density = screen_height / 2160
    image = Image.new("RGB", resolution, "#18232c")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, screen_width, round(220 * density)), fill="#050608")
    draw.text((round(55 * density), round(45 * density)), f"Synthetic {screen_width}x{screen_height} {GAME_PROFILES[game].name}; official game text",
              font=ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", max(10, round(34 * density))), fill="#9faebb")
    region = GAME_PROFILES[game].subtitle_region
    left, top, width, height = CaptureService._region_bounds(WindowInfo(0, "fixture", "", (0, 0, *resolution)), region)
    blocks = ([chinese] if language == "zh" else [english] if language == "en" else
              [f"{chinese} ~ {english}"] if language == "dual-inline" else
              [english, "~ " + chinese] if language == "dual-wrapped" else [chinese, english])
    rows = []
    for block in blocks:
        font_path = r"C:\Windows\Fonts\malgun.ttf" if any('\uac00' <= char <= '\ud7af' for char in block) else r"C:\Windows\Fonts\msyh.ttc"
        font = ImageFont.truetype(font_path, max(10, round(58 * density * font_scale)))
        rows.extend((row, font) for row in wrap(block, font, width - round(150 * density)))
    y = top + round(60 * density)
    if game == 'nte':
        # Reviewed NTE captions sit below the speaker/HUD strip. Short mixed
        # Chinese/Latin lines above this band are intentionally rejected.
        y = max(y, round(screen_height * .81))
    if game == 'heavyrain':
        # The reviewed PC subtitle lane is below documents and thought options.
        y = max(y, round(screen_height * .81))
    for row, font in rows:
        x = left + (width - font.getlength(row)) / 2
        draw.text((x, y), row, font=font, fill="white", stroke_width=max(1, round(2 * density)), stroke_fill="#101010")
        y += round(80 * density * font_scale)
    if y > top + height:
        raise ValueError("Fixture text exceeds the subtitle crop")
    return image


async def scan(image, game, indexes, voices, engine, directory, expected=None, expect_missing_voice=False, expected_ocr=None, origin=(0, 0)):
    directory.mkdir(parents=True, exist_ok=True)
    captured = []
    async def on_line(line):
        captured.append(line)
    async def ignore(*_):
        pass
    service = CaptureService(SettingsStore(directory / "settings.json"), indexes["zzz"], indexes["pragmata"],
        TranscriptStore(directory / f"transcript-{time.time_ns()}.db"), on_line, ignore, ignore, directory / "audio",
        voice_assets=voices["zzz"], pragmata_voice_assets=voices["pragmata"],
        game_indexes={game: indexes[game] for game in LOCAL_GAMES},
        game_voice_assets={game: voices[game] for game in LOCAL_GAMES})
    original = capture_module.find_active_game_window
    profile = GAME_PROFILES[game]
    window = WindowInfo(0, profile.name, profile.process_names[0], (*origin, *image.size))
    capture_module.find_active_game_window = lambda _: (profile, window)
    def crop(bounds):
        x, y, w, h = bounds
        x -= origin[0]; y -= origin[1]
        return image.crop((x, y, x + w, y + h))
    service._capture = crop
    service._prepare_window_capture = lambda _: None
    service._engine = engine
    service._event_loop = asyncio.get_running_loop()
    service._tip_tracker.configure(1)
    service._cinematic_tracker.configure(1)
    # Inspect production OCR, layout filtering, stability and strict voice
    # gating without touching the real transcript or scheduling clip writes.
    matched = []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: matched.append(line)
    try:
        # Observe the production stability gate and duplicate suppression over
        # five consecutive frames, with the same per-channel tracker settings.
        for _ in range(5):
            service._scan_once()
        lines = service.transcript.list()
        if expect_missing_voice:
            assert service.snapshot().phase == "waiting_for_voice", service.snapshot()
            assert not lines, "Missing Mandarin files must never produce a fallback capture"
            assert service.snapshot().last_ocr, "The subtitle must still be recognized"
        if expected_ocr:
            score = fuzz.ratio(normalize_subtitle(expected_ocr), normalize_subtitle(service.snapshot().last_ocr))
            assert score >= 85, (game, image.size, "Subtitle OCR diverged", score, service.snapshot().last_ocr)
        if expected is not None:
            assert any(line.text_id == expected for line in lines), (
                game, service.snapshot().phase, expected, [line.text_id for line in lines],
                service.snapshot().last_ocr, service.snapshot().last_cinematic_ocr)
            assert len(lines) == 1, f"Duplicate bilingual screenshot capture: {game}"
        result = {"game": game, "resolution": list(image.size), "phase": service.snapshot().phase,
                  "ocr": service.snapshot().last_ocr, "text_ids": [line.text_id for line in lines]}
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        capture_module.find_active_game_window = original
        service._executor.shutdown(wait=False, cancel_futures=True)


async def main(args):
    data = ROOT / "data"
    output = args.output.resolve()
    decoder = data / "voice-assets/vgmstream/vgmstream-cli.exe"
    def source(game):
        return data / game if not args.game or args.game == game else output / "unused" / game
    indexes = {"zzz": TextMapIndex(source("zzz") if args.game and args.game != "zzz" else data / "textmaps"), "pragmata": PragmataTextIndex(source("pragmata")),
               **{game: LocalGameTextIndex(game, source(game)) for game in LOCAL_GAMES}}
    if not args.game or args.game == "zzz":
        indexes["zzz"].load()
    if not args.game or args.game == "pragmata":
        indexes["pragmata"].load()
    voices = {"zzz": VoiceAssetService((data / "voice-assets" if not args.game or args.game == "zzz" else source("zzz")) / "manifest.json", decoder, output / "audio",
                (data / "voice-assets" if not args.game or args.game == "zzz" else source("zzz")) / "learned-manifest.json"),
              "pragmata": PragmataVoiceAssetService(source("pragmata"), decoder, output / "audio"),
              **{game: LocalVoiceAssetService(game, source(game), decoder, output / "audio") for game in LOCAL_GAMES}}
    if args.source_locale:
        from backend.multilingual_index import MultilingualTextIndex
        if args.game not in {*LOCAL_GAMES, 'pragmata', 'zzz'}:
            raise ValueError('Select a local game for a prepared language fixture')
        directory = data / 'languages' / args.game / args.source_locale
        indexes[args.game] = MultilingualTextIndex(args.game, directory)
        voices[args.game].close()
        voices[args.game] = (PragmataVoiceAssetService(directory, decoder, output / 'audio', tools_dir=data / args.game / 'tools')
            if args.game == 'pragmata' else LocalVoiceAssetService(args.game, directory, decoder, output / 'audio',
                                                tools_dir=data / args.game / 'tools'))
    engine = OcrEngine()
    try:
        if args.source_locale and args.fixtures:
            game, index = args.game, indexes[args.game]
            payload = json.loads(index.path.read_text(encoding='utf-8'))
            row = next(r for r in payload['records'] if r.get('audio') and not r.get('player_voice')
                       and 35 <= len(r['source_text']) <= 80 and len(r['texts']) > 1
                       and (hit := index.match_lines([r['source_text']])) and hit.text_id == r['text_id'])
            target = next(text for locale, text in row['texts'].items() if locale != args.source_locale)
            for resolution in args.resolution or [(1280, 720), (1920, 1080), (3840, 2160)]:
                for language in ('en', 'zh', 'dual-inline', 'dual-wrapped'):
                    directory = output / f'{game}-{args.source_locale}-{resolution[0]}x{resolution[1]}-{language}'
                    directory.mkdir(parents=True, exist_ok=True)
                    image = fixture_image(game, row['source_text'], target, language, resolution)
                    image.save(directory / 'screenshot.png')
                    await scan(image, game, indexes, voices, engine, directory, expected=row['text_id'])
                    print(f'{game} {args.source_locale} {resolution} {language}: synthetic production OCR PASS', flush=True)
            return
        if args.image:
            for number, path in enumerate(args.image):
                with Image.open(path) as screenshot:
                    result = await scan(screenshot.convert("RGB"), args.game, indexes, voices, engine,
                                        output / f"screenshot-{number}")
                    print(json.dumps(result, ensure_ascii=False))
            return
        for game, index in indexes.items():
            if args.game and args.game != game:
                continue
            def unique_match(record):
                en_match, zh_match = index.match_lines([record.english]), index.match_lines([record.chinese])
                expected = record.text_id
                if game == 'pragmata' and not expected.startswith('pragmata:'):
                    expected = 'pragmata:' + expected
                return en_match and zh_match and en_match.text_id == zh_match.text_id == expected
            if game == "zzz":
                candidates = (record for records in index._records_by_normalized.values() for record in records
                    if index.is_capture_text(record.text_id, record.english, "dialogue"))
                record = next(r for r in candidates if 25 <= len(r.english) <= 95 and 8 <= len(r.chinese) <= 55
                              and voices[game].has_variant(r.text_id, r.english) and unique_match(r))
                text_id, english, chinese = record.text_id, record.english, record.chinese
            else:
                payload = json.loads((data / game / "textmap.json").read_text(encoding="utf-8"))
                missing_voice = game in LOCAL_GAMES and index.audio_count == 0
                candidates = (r for r in payload["records"] if (r.get("audio") or missing_voice) and not r.get("player_voice")
                              and 25 <= len(r["english"]) <= 95 and 8 <= len(r["chinese"]) <= 55)
                record = next(r for r in candidates if missing_voice or unique_match(SimpleNamespace(**r)))
                text_id = record["text_id"]
                if game == "pragmata" and not text_id.startswith("pragmata:"):
                    text_id = "pragmata:" + text_id
                english, chinese = record["english"], record["chinese"]
            languages = ["en", "zh", "dual-inline", "dual-wrapped"] if game == "witcher3" else ["en", "zh", "bilingual"] if game == "cyberpunk" else ["en", "zh"]
            resolutions = args.resolution or (RESOLUTIONS if args.resolution_matrix else [(3840, 2160)])
            for resolution in resolutions:
                for font_scale in args.font_scale or [1.0]:
                    for language in languages:
                        label = f"{resolution[0]}x{resolution[1]}-font{font_scale:g}"
                        name = f"{game}-{language}"
                        directory = output / label / name
                        directory.mkdir(parents=True, exist_ok=True)
                        image = fixture_image(game, english, chinese, language, resolution, font_scale)
                        image.save(directory / "screenshot.png")
                        missing_voice = game in LOCAL_GAMES and index.audio_count == 0
                        expected_ocr = english if language == "en" else chinese if language == "zh" else None
                        result = await scan(image, game, indexes, voices, engine, directory,
                                            expected=None if missing_voice else text_id, expect_missing_voice=missing_voice,
                                            expected_ocr=expected_ocr, origin=(-resolution[0], 120))
                        identity = result['text_ids'][0] if result['text_ids'] else 'strict missing-voice suppression'
                        print(f"{name}: {label} production screenshot/OCR pipeline PASS ({identity})", flush=True)
    finally:
        for voice in voices.values():
            voice.close()


if __name__ == "__main__":
    def resolution(value):
        try:
            width, height = map(int, value.lower().split("x"))
            if 320 <= width <= 15360 and 240 <= height <= 8640:
                return width, height
        except ValueError:
            pass
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT within 320x240 and 15360x8640")

    def font_scale(value):
        try:
            scale = float(value)
            if .5 <= scale <= 2:
                return scale
        except ValueError:
            pass
        raise argparse.ArgumentTypeError("Font scale must be between 0.5 and 2")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--game", choices=["zzz", "pragmata", *LOCAL_GAMES])
    parser.add_argument('--source-locale', help='Explicitly prepared multilingual snapshot; fixtures remain synthetic')
    parser.add_argument("--image", action="append", type=Path)
    parser.add_argument("--resolution-matrix", action="store_true")
    parser.add_argument("--resolution", action="append", type=resolution)
    parser.add_argument("--font-scale", action="append", type=font_scale)
    parser.add_argument("--output", type=Path, default=ROOT / "output/playwright/subtitles-4k")
    options = parser.parse_args()
    if not options.fixtures and not (options.game and options.image):
        parser.error("Choose --fixtures or --game with --image")
    asyncio.run(main(options))
