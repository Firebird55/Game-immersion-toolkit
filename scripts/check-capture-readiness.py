"""Check the installed OCR and screen capture path without starting a game.

Run with the Proxy Transcript virtual environment's Python from the project
root. The check is read-only apart from printing its results.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mss
from oneocr import OcrEngine
from PIL import Image, ImageDraw, ImageFont

from backend.capture import CaptureService
from backend.games import GAME_PROFILES
from backend.models import AppSettings
from backend.media_tools import ffmpeg_executable
from backend.windows import WindowInfo, find_active_game_window
from backend.bilingual import normalize_chinese


def main() -> int:
    settings = AppSettings()
    print("OCR files:")
    for name in ("oneocr.dll", "oneocr.onemodel", "onnxruntime.dll"):
        path = Path.home() / ".config" / "oneocr" / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing native OCR file: {path}")
        print(f"  {name}: {path.stat().st_size:,} bytes")

    sample = Image.new("RGB", (1150, 180), "#111820")
    draw = ImageDraw.Draw(sample)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 60)
    draw.text((35, 45), "Enemies incoming!", font=font, fill="white")
    lines = [item.get("text", "") for item in OcrEngine().recognize_pil(sample).get("lines", [])]
    if not any("enemies incoming" in line.casefold() for line in lines):
        raise RuntimeError(f"Native OCR could not read a test subtitle: {lines!r}")
    print(f"Native OCR: recognized {lines[0]!r}")

    bilingual = Image.new("RGB", (1150, 220), "#111820")
    painter = ImageDraw.Draw(bilingual)
    chinese_font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 52)
    painter.text((35, 25), "他们过来了！", font=chinese_font, fill="white")
    painter.text((35, 112), "They're coming!", font=font, fill="white")
    bilingual_lines = [item.get("text", "") for item in OcrEngine().recognize_pil(bilingual).get("lines", [])]
    if not any(normalize_chinese(line) == "他们过来了" for line in bilingual_lines):
        raise RuntimeError("Native OCR could not read the Mandarin subtitle fixture")
    print("Native OCR: Mandarin and English subtitle blocks recognized")

    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is unavailable; rerun scripts/setup.ps1")
    print(f"FFmpeg: {Path(ffmpeg).name}")
    print("Voice capture: original game files matched by visible subtitles; no audio device needed")

    with mss.MSS() as grabber:
        monitors = grabber.monitors[1:]
        if not monitors:
            raise RuntimeError("No physical display is available to capture")
        for number, monitor in enumerate(monitors, 1):
            sample_box = {
                "left": monitor["left"] + 20,
                "top": monitor["top"] + 20,
                "width": 100,
                "height": 100,
            }
            pixels = grabber.grab(sample_box)
            if pixels.size != (100, 100):
                raise RuntimeError(f"Display {number} screenshot dimensions are wrong")
            print(
                f"Display {number}: {monitor['width']}x{monitor['height']} "
                f"at ({monitor['left']}, {monitor['top']}); screenshot OK"
            )

        primary = next((item for item in monitors if item.get("is_primary")), monitors[0])
        window = WindowInfo(
            0, "Capture geometry probe", "ZenlessZoneZero.exe",
            (primary["left"], primary["top"], primary["width"], primary["height"]),
        )
        for name, region in (
            ("ZZZ dialogue", settings.region),
            ("ZZZ top-right", settings.tip_region),
            ("ZZZ cinematic", settings.cinematic_region),
            ("PRAGMATA subtitles", GAME_PROFILES["pragmata"].subtitle_region),
            ("Cyberpunk bilingual subtitles", settings.cyberpunk_region),
            ("Wuthering Waves subtitles", settings.wuwa_region),
            ("Witcher stock/dual subtitles", settings.witcher3_region),
        ):
            left, top, width, height = CaptureService._region_bounds(window, region)
            if (
                left < primary["left"] or top < primary["top"]
                or left + width > primary["left"] + primary["width"]
                or top + height > primary["top"] + primary["height"]
            ):
                raise RuntimeError(f"{name} crop falls outside the primary display")
            print(f"{name} crop: ({left}, {top}) {width}x{height}")

    active = find_active_game_window(settings)
    print(f"Game window: {active[1].title if active else 'not running; live subtitle test pending'}")
    print("Preflight passed. A game must run to verify its actual subtitle frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
