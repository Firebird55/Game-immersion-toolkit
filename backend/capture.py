from __future__ import annotations

import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

import mss
from oneocr import OcrEngine
from PIL import Image

from .config import SettingsStore
from .models import CaptureRegion, CaptureSnapshot, TextMatch, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex
from .windows import WindowInfo, find_game_window


class StableMatchTracker:
    def __init__(self, required_frames: int = 2, blank_reset_frames: int = 2):
        self.required_frames = required_frames
        self.blank_reset_frames = blank_reset_frames
        self.candidate: str | None = None
        self.count = 0
        self.blank_count = 0
        self.emitted = False

    def configure(self, required_frames: int) -> None:
        self.required_frames = max(1, required_frames)

    def observe(self, key: str | None) -> bool:
        if key is None:
            self.blank_count += 1
            if self.blank_count >= self.blank_reset_frames:
                self.candidate = None
                self.count = 0
                self.emitted = False
            return False

        self.blank_count = 0
        if key != self.candidate:
            self.candidate = key
            self.count = 1
            self.emitted = False
        else:
            self.count += 1

        if self.count >= self.required_frames and not self.emitted:
            self.emitted = True
            return True
        return False


@dataclass(slots=True)
class _ScanOutcome:
    emitted_line: TranscriptLine | None = None


class CaptureService:
    def __init__(
        self,
        settings: SettingsStore,
        textmaps: TextMapIndex,
        transcript: TranscriptStore,
        on_line: Callable[[TranscriptLine], Awaitable[None]],
        on_status: Callable[[CaptureSnapshot], Awaitable[None]],
    ):
        self.settings = settings
        self.textmaps = textmaps
        self.transcript = transcript
        self.on_line = on_line
        self.on_status = on_status
        self.session_id = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        self._snapshot = CaptureSnapshot()
        self._snapshot_lock = threading.RLock()
        self._preview = b""
        self._preview_lock = threading.RLock()
        self._task: asyncio.Task[None] | None = None
        self._engine: OcrEngine | None = None
        self._tracker = StableMatchTracker()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-ocr")

    def snapshot(self) -> CaptureSnapshot:
        with self._snapshot_lock:
            return self._snapshot.model_copy(deep=True)

    def _update_snapshot(self, **changes: object) -> CaptureSnapshot:
        with self._snapshot_lock:
            self._snapshot = self._snapshot.model_copy(update=changes)
            return self._snapshot.model_copy(deep=True)

    def preview_bytes(self) -> bytes:
        with self._preview_lock:
            return self._preview

    def preview_for_region(self, region: CaptureRegion) -> bytes:
        window = find_game_window(self.settings.get())
        if window is None:
            return b""
        image = self._capture(self._region_bounds(window, region))
        return self._encode_preview(image)

    def start(self) -> bool:
        if self._task and not self._task.done():
            return False
        self._update_snapshot(running=True, phase="starting", message="Starting English OCR")
        self._task = asyncio.create_task(self._run(), name="zzz-capture")
        return True

    async def stop(self) -> bool:
        if not self._task or self._task.done():
            self._update_snapshot(running=False, phase="stopped", message="Capture is stopped")
            return False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        snapshot = self._update_snapshot(running=False, phase="stopped", message="Capture is stopped")
        await self.on_status(snapshot)
        return True

    async def close(self) -> None:
        await self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                settings = self.settings.get()
                self._tracker.configure(settings.stable_frames)
                try:
                    outcome = await loop.run_in_executor(self._executor, self._scan_once)
                    snapshot = self.snapshot()
                    await self.on_status(snapshot)
                    if outcome.emitted_line is not None:
                        await self.on_line(outcome.emitted_line)
                except Exception as error:
                    snapshot = self._update_snapshot(
                        running=True,
                        phase="error",
                        message="Capture encountered an error and will retry",
                        last_error=str(error),
                    )
                    await self.on_status(snapshot)
                await asyncio.sleep(settings.scan_interval_ms / 1000)
        except asyncio.CancelledError:
            raise

    def _scan_once(self) -> _ScanOutcome:
        settings = self.settings.get()
        window = find_game_window(settings)
        now = datetime.now(timezone.utc).astimezone()
        if window is None:
            self._tracker.observe(None)
            self._update_snapshot(
                running=True,
                phase="waiting_for_game",
                message="Waiting for ZenlessZoneZero.exe",
                window_title=None,
                window_bounds=None,
                crop_bounds=None,
                last_scan_at=now,
                last_error=None,
            )
            return _ScanOutcome()

        crop_bounds = self._region_bounds(window, settings.region)
        image = self._capture(crop_bounds)
        self._set_preview(image)
        if self._engine is None:
            self._engine = OcrEngine()
        response = self._engine.recognize_pil(image)
        lines = [line.get("text", "").strip() for line in response.get("lines", [])]
        lines = [line for line in lines if line]
        raw_text = " ".join(lines).strip()
        confidence = self._confidence(response)

        if not self.textmaps.ready:
            self._tracker.observe(None)
            self._update_snapshot(
                running=True,
                phase="loading_textmaps",
                message=self.textmaps.status()["message"],
                window_title=window.title,
                window_bounds=window.bounds,
                crop_bounds=crop_bounds,
                last_ocr=raw_text,
                last_ocr_confidence=confidence,
                last_match_score=None,
                last_scan_at=now,
                last_error=None,
            )
            return _ScanOutcome()

        match = self.textmaps.match_lines(lines, threshold=settings.fuzzy_threshold)
        emitted_line: TranscriptLine | None = None
        if match is None:
            self._tracker.observe(None if not raw_text else f"unmatched:{raw_text.casefold()}")
            phase = "unmatched" if raw_text else "listening"
            message = "Subtitle seen, but no official match" if raw_text else "Listening for English subtitles"
            match_score = None
        else:
            key = f"{match.text_id}\0{match.english}"
            if self._tracker.observe(key):
                emitted_line = self.transcript.add(match, self.session_id, created_at=now)
            phase = "matched"
            message = "Official bilingual line matched"
            match_score = match.score

        self._update_snapshot(
            running=True,
            phase=phase,
            message=message,
            window_title=window.title,
            window_bounds=window.bounds,
            crop_bounds=crop_bounds,
            last_ocr=raw_text,
            last_ocr_confidence=confidence,
            last_match_score=match_score,
            last_scan_at=now,
            last_error=None,
        )
        return _ScanOutcome(emitted_line=emitted_line)

    @staticmethod
    def _region_bounds(window: WindowInfo, region: object) -> tuple[int, int, int, int]:
        window_x, window_y, window_width, window_height = window.bounds
        left = window_x + round(window_width * region.left)
        top = window_y + round(window_height * region.top)
        width = max(50, round(window_width * region.width))
        height = max(50, round(window_height * region.height))
        return left, top, width, height

    @staticmethod
    def _capture(bounds: tuple[int, int, int, int]) -> Image.Image:
        left, top, width, height = bounds
        with mss.mss() as capture:
            shot = capture.grab({"left": left, "top": top, "width": width, "height": height})
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def _set_preview(self, image: Image.Image) -> None:
        encoded = self._encode_preview(image)
        with self._preview_lock:
            self._preview = encoded

    @staticmethod
    def _encode_preview(image: Image.Image) -> bytes:
        preview = image.copy()
        preview.thumbnail((1200, 500), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        preview.save(buffer, format="JPEG", quality=78, optimize=True)
        return buffer.getvalue()

    @staticmethod
    def _confidence(response: dict[str, object]) -> float | None:
        confidences: list[float] = []
        for line in response.get("lines", []):
            for word in line.get("words", []):
                confidence = word.get("confidence")
                if isinstance(confidence, (int, float)):
                    confidences.append(float(confidence))
        if not confidences:
            return None
        return round(sum(confidences) / len(confidences) * 100, 1)
