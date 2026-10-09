"""Offline screenshot/OCR checks; synthetic 4K fixtures use official game text.

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont
from oneocr import OcrEngine

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


def wrap(text: str, font, width: int) -> list[str]:
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


def fixture_image(game, english, chinese, language):
    image = Image.new("RGB", (3840, 2160), "#18232c")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 3840, 220), fill="#050608")
    draw.text((55, 45), f"Synthetic 4K {GAME_PROFILES[game].name} subtitle fixture; official game text",
              font=ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 34), fill="#9faebb")
    region = GAME_PROFILES[game].subtitle_region
    left, top, width, height = CaptureService._region_bounds(WindowInfo(0, "fixture", "", (0, 0, 3840, 2160)), region)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 58)
    blocks = ([chinese] if language == "zh" else [english] if language == "en" else
              [f"{chinese} ~ {english}"] if language == "dual-inline" else
              [english, "~ " + chinese] if language == "dual-wrapped" else [chinese, english])
    rows = [row for block in blocks for row in wrap(block, font, width - 150)]
    y = top + 60
    for row in rows:
        x = left + (width - font.getlength(row)) / 2
        draw.text((x, y), row, font=font, fill="white", stroke_width=2, stroke_fill="#101010")
        y += 80
    if y > top + height:
        raise ValueError("Fixture text exceeds the subtitle crop")
    return image


async def scan(image, game, indexes, voices, engine, directory, expected=None, expect_missing_voice=False):
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
    window = WindowInfo(0, profile.name, profile.process_names[0], (0, 0, *image.size))
    capture_module.find_active_game_window = lambda _: (profile, window)
    def crop(bounds):
        x, y, w, h = bounds
        return image.crop((x, y, x + w, y + h))
    service._capture = crop
    service._engine = engine
    service._event_loop = asyncio.get_running_loop()
    # Inspect production OCR, layout filtering, stability and strict voice
    # gating without touching the real transcript or scheduling clip writes.
    matched = []
    service._schedule_line_audio = lambda line, *_args, **_kwargs: matched.append(line)
    try:
        for _ in range(3):
            service._scan_once()
        lines = service.transcript.list()
        if expect_missing_voice:
            assert service.snapshot().phase == "waiting_for_voice", service.snapshot()
            assert not lines, "Missing Mandarin files must never produce a fallback capture"
            assert service.snapshot().last_ocr, "The 4K subtitle must still be recognized"
        if expected is not None:
            assert any(line.text_id == expected for line in lines), (
                game, service.snapshot().last_ocr, service.snapshot().last_cinematic_ocr)
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
    indexes = {"zzz": TextMapIndex(data / "textmaps"), "pragmata": PragmataTextIndex(data / "pragmata"),
               **{game: LocalGameTextIndex(game, data / game) for game in LOCAL_GAMES}}
    indexes["zzz"].load(); indexes["pragmata"].load()
    voices = {"zzz": VoiceAssetService(data / "voice-assets/manifest.json", decoder, output / "audio",
                data / "voice-assets/learned-manifest.json"),
              "pragmata": PragmataVoiceAssetService(data / "pragmata", decoder, output / "audio"),
              **{game: LocalVoiceAssetService(game, data / game, decoder, output / "audio") for game in LOCAL_GAMES}}
    engine = OcrEngine()
    try:
        if args.image:
            for number, path in enumerate(args.image):
                with Image.open(path) as screenshot:
                    result = await scan(screenshot.convert("RGB"), args.game, indexes, voices, engine,
                                        output / f"screenshot-{number}")
                    print(json.dumps(result, ensure_ascii=False))
            return
        for game, index in indexes.items():
            if game == "zzz":
                candidates = (record for records in index._records_by_normalized.values() for record in records
                    if index.is_capture_text(record.text_id, record.english, "dialogue"))
                record = next(r for r in candidates if 25 <= len(r.english) <= 95 and 8 <= len(r.chinese) <= 55
                              and voices[game].has_variant(r.text_id, r.english))
                text_id, english, chinese = record.text_id, record.english, record.chinese
            else:
                payload = json.loads((data / game / "textmap.json").read_text(encoding="utf-8"))
                missing_voice = game in LOCAL_GAMES and index.audio_count == 0
                record = next(r for r in payload["records"] if (r.get("audio") or missing_voice) and not r.get("player_voice")
                              and 25 <= len(r["english"]) <= 95 and 8 <= len(r["chinese"]) <= 55)
                text_id = record["text_id"]
                if game == "pragmata" and not text_id.startswith("pragmata:"):
                    text_id = "pragmata:" + text_id
                english, chinese = record["english"], record["chinese"]
            languages = ["en", "zh", "dual-inline", "dual-wrapped"] if game == "witcher3" else ["en", "zh", "bilingual"] if game == "cyberpunk" else ["en", "zh"]
            for language in languages:
                name = f"{game}-{language}"
                directory = output / name
                directory.mkdir(parents=True, exist_ok=True)
                image = fixture_image(game, english, chinese, language)
                image.save(directory / "screenshot.png")
                missing_voice = game in LOCAL_GAMES and index.audio_count == 0
                result = await scan(image, game, indexes, voices, engine, directory,
                                    expected=None if missing_voice else text_id, expect_missing_voice=missing_voice)
                identity = result['text_ids'][0] if result['text_ids'] else 'strict missing-voice suppression'
                print(f"{name}: 3840x2160 production screenshot/OCR pipeline PASS ({identity})")
    finally:
        for voice in voices.values():
            voice.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--game", choices=["zzz", "pragmata", *LOCAL_GAMES])
    parser.add_argument("--image", action="append", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "output/playwright/subtitles-4k")
    options = parser.parse_args()
    if not options.fixtures and not (options.game and options.image):
        parser.error("Choose --fixtures or --game with --image")
    asyncio.run(main(options))
