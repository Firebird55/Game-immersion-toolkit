from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

import mss
from oneocr import OcrEngine
from PIL import Image

from .audio import AudioCaptureService
from .config import SettingsStore
from .models import CaptureRegion, CaptureSnapshot, TextMatch, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex, normalize_english
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
    emitted_lines: list[TranscriptLine] | None = None


class CaptureService:
    def __init__(
        self,
        settings: SettingsStore,
        textmaps: TextMapIndex,
        transcript: TranscriptStore,
        on_line: Callable[[TranscriptLine], Awaitable[None]],
        on_delete: Callable[[int], Awaitable[None]],
        on_status: Callable[[CaptureSnapshot], Awaitable[None]],
        audio: AudioCaptureService,
    ):
        self.settings = settings
        self.textmaps = textmaps
        self.transcript = transcript
        self.on_line = on_line
        self.on_delete = on_delete
        self.on_status = on_status
        self.audio = audio
        self.session_id = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        self._snapshot = CaptureSnapshot()
        self._snapshot_lock = threading.RLock()
        self._preview = b""
        self._preview_lock = threading.RLock()
        self._task: asyncio.Task[None] | None = None
        self._engine: OcrEngine | None = None
        self._tracker = StableMatchTracker()
        self._tip_tracker = StableMatchTracker()
        self._cinematic_tracker = StableMatchTracker()
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-ocr")
        self._scan_index = 0
        self._last_emitted_at: dict[str, float] = {}
        self._last_emitted_key_by_channel: dict[str, str] = {}
        self._last_visible_match_by_channel: dict[str, str] = {}
        self._cinematic_seen_ids: set[str] = set()
        self._cinematic_panel_text = ""
        self._excluded_screen: str | None = None

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
        self._event_loop = asyncio.get_running_loop()
        self._update_snapshot(running=True, phase="starting", message="Starting English OCR and audio")
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
                scan_started = loop.time()
                settings = self.settings.get()
                self._tracker.configure(settings.stable_frames)
                # These regions are brief and already have strict layout filters. Waiting
                # for two sparse region scans would make us miss short spoken prompts.
                self._tip_tracker.configure(1)
                self._cinematic_tracker.configure(1)
                try:
                    outcome = await loop.run_in_executor(self._executor, self._scan_once)
                    snapshot = self.snapshot()
                    await self.on_status(snapshot)
                    for line in outcome.emitted_lines or []:
                        await self.on_line(line)
                except Exception as error:
                    snapshot = self._update_snapshot(
                        running=True,
                        phase="error",
                        message="Capture encountered an error and will retry",
                        last_error=str(error),
                    )
                    await self.on_status(snapshot)
                elapsed = loop.time() - scan_started
                await asyncio.sleep(max(0.01, settings.scan_interval_ms / 1000 - elapsed))
        except asyncio.CancelledError:
            raise

    def _scan_once(self) -> _ScanOutcome:
        self._scan_index += 1
        settings = self.settings.get()
        window = find_game_window(settings)
        now = datetime.now(timezone.utc).astimezone()
        if window is None:
            self._tracker.observe(None)
            self._tip_tracker.observe(None)
            self._cinematic_tracker.observe(None)
            self._update_snapshot(
                running=True,
                phase="waiting_for_game",
                message="Waiting for ZenlessZoneZero.exe",
                window_title=None,
                window_bounds=None,
                crop_bounds=None,
                tip_crop_bounds=None,
                cinematic_crop_bounds=None,
                last_scan_at=now,
                last_error=None,
            )
            return _ScanOutcome([])

        crop_bounds = self._region_bounds(window, settings.region)
        if self._scan_index % 4 == 1:
            # One inexpensive upper-screen signature pass covers the left-side
            # Story Recap header, centered Knock Knock panel, and the HDD hub.
            header_bounds = self._region_bounds(
                window, CaptureRegion(left=0, top=0, width=0.72, height=0.42)
            )
            header_image = self._capture(header_bounds)
            if header_image.width > 1400:
                header_image.thumbnail((1400, 700), Image.Resampling.LANCZOS)
            if self._engine is None:
                self._engine = OcrEngine()
            header_response = self._engine.recognize_pil(header_image)
            header_lines = [
                line.get("text", "").strip()
                for line in header_response.get("lines", [])
                if line.get("text", "").strip()
            ]
            self._excluded_screen = self._classify_screen_header(header_lines)

        image = self._capture(crop_bounds)
        self._set_preview(image)
        if image.width > 1600:
            image.thumbnail((1600, 400), Image.Resampling.LANCZOS)
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
            return _ScanOutcome([])

        phone_screen = self._is_phone_screen(lines) or self._excluded_screen == "phone"
        excluded_screen = phone_screen or self._excluded_screen in {"story_recap", "hdd"}
        match = (
            None
            if excluded_screen
            else self.textmaps.match_lines(lines, threshold=settings.fuzzy_threshold)
        )
        monotonic_now = time.monotonic()
        speech_active = self.audio.speech_recent(1.8)
        emitted_lines: list[TranscriptLine] = []
        if match is None:
            self._tracker.observe(None if not raw_text else f"unmatched:{raw_text.casefold()}")
            phase = "unmatched" if raw_text else "listening"
            message = "Subtitle seen, but no official match" if raw_text else "Listening for English subtitles"
            match_score = None
        else:
            key = f"{match.text_id}\0{match.english}"
            redundant_visible_match = self._is_redundant_visible_match(
                "dialogue", match.english, raw_text
            )
            if not speech_active:
                self._tracker.observe(None)
            elif (
                self._tracker.observe(key)
                and not redundant_visible_match
                and self._can_emit(f"dialogue\0{key}", monotonic_now)
            ):
                line, _ = self.transcript.add_or_upgrade_recent(
                    match, self.session_id, created_at=now, channel="dialogue"
                )
                if line is not None:
                    emitted_lines.append(line)
                    self.audio.schedule_clip(line.id, monotonic_now, self._audio_ready)
            phase = "matched"
            message = "Official bilingual line matched"
            match_score = match.score

        tip_bounds = self._region_bounds(window, settings.tip_region)
        previous_snapshot = self.snapshot()
        tip_raw_text = previous_snapshot.last_tip_ocr
        tip_confidence = previous_snapshot.last_tip_ocr_confidence
        tip_match = None
        tip_match_score: float | None = None
        scan_tip = self._scan_index % 4 == 1
        if scan_tip:
            tip_image = self._capture(tip_bounds)
            tip_response = self._engine.recognize_pil(tip_image)
            tip_lines = [line.get("text", "").strip() for line in tip_response.get("lines", [])]
            tip_lines = [line for line in tip_lines if line]
            tip_raw_text = " ".join(tip_lines).strip()
            tip_confidence = self._confidence(tip_response)
            tip_match = None if excluded_screen else self.textmaps.match_lines(
                tip_lines, threshold=settings.fuzzy_threshold, channel="tip"
            )
            if tip_match is None or not speech_active:
                self._tip_tracker.observe(None if not tip_raw_text else f"unmatched:{tip_raw_text.casefold()}")
            else:
                tip_key = f"tip\0{tip_match.text_id}\0{tip_match.english}"
                if self._tip_tracker.observe(tip_key) and self._can_emit(tip_key, monotonic_now):
                    line, _ = self.transcript.add_or_upgrade_recent(
                        tip_match, self.session_id, created_at=now, channel="tip"
                    )
                    if line is not None:
                        emitted_lines.append(line)
                        self.audio.schedule_clip(line.id, monotonic_now, self._audio_ready)
                tip_match_score = tip_match.score
                if match is None:
                    phase = "matched"
                    message = "Official top-right tip matched"

        cinematic_bounds = self._region_bounds(window, settings.cinematic_region)
        cinematic_raw_text = ""
        cinematic_confidence: float | None = None
        cinematic_match_score: float | None = None
        scan_cinematic = self._scan_index % 2 == 1
        if speech_active and not excluded_screen and tip_match is None and scan_cinematic:
            cinematic_image = self._capture(cinematic_bounds)
            if cinematic_image.width > 1920:
                cinematic_image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            cinematic_response = self._engine.recognize_pil(cinematic_image)
            cinematic_lines = [
                line.get("text", "").strip() for line in cinematic_response.get("lines", [])
            ]
            cinematic_lines = [line for line in cinematic_lines if line]
            cinematic_raw_text = " ".join(cinematic_lines).strip()
            cinematic_confidence = self._confidence(cinematic_response)
            cinematic_matches = self.textmaps.match_line_groups(
                cinematic_lines,
                threshold=max(settings.fuzzy_threshold, 88),
                channel="cinematic",
            )
            normalized_panel = normalize_english(cinematic_raw_text)
            if (
                normalized_panel
                and self._cinematic_panel_text
                and not self._same_cinematic_panel(self._cinematic_panel_text, normalized_panel)
            ):
                self._cinematic_seen_ids.clear()
            if normalized_panel:
                self._cinematic_panel_text = normalized_panel

            already_matched = {
                item.text_id for item in (match, tip_match) if item is not None
            }
            new_cinematic_matches = [
                item
                for item in cinematic_matches
                if item.text_id not in self._cinematic_seen_ids
                and item.text_id not in already_matched
            ]
            self._cinematic_seen_ids.update(item.text_id for item in cinematic_matches)
            cinematic_match = new_cinematic_matches[-1] if new_cinematic_matches else None
            if cinematic_match is not None:
                cinematic_key = f"cinematic\0{cinematic_match.text_id}\0{cinematic_match.english}"
                if self._can_emit(cinematic_key, monotonic_now):
                    line, _ = self.transcript.add_or_upgrade_recent(
                        cinematic_match,
                        self.session_id,
                        created_at=now,
                        channel="cinematic",
                    )
                    if line is not None:
                        emitted_lines.append(line)
                        self.audio.schedule_clip(line.id, monotonic_now, self._audio_ready)
                cinematic_match_score = cinematic_match.score
                if match is None and tip_match is None:
                    phase = "matched"
                    message = "Voiced cinematic/comic line matched"
            else:
                cinematic_match_score = max(
                    (item.score for item in cinematic_matches), default=None
                )
        else:
            self._cinematic_tracker.observe(None)

        if excluded_screen:
            phase = "excluded_screen"
            messages = {
                "story_recap": "Story Recap ignored",
                "hdd": "HDD commission screen ignored",
                "phone": "Phone screen ignored",
            }
            message = messages.get(self._excluded_screen, "Phone screen ignored")

        self._update_snapshot(
            running=True,
            phase=phase,
            message=message,
            window_title=window.title,
            window_bounds=window.bounds,
            crop_bounds=crop_bounds,
            tip_crop_bounds=tip_bounds,
            cinematic_crop_bounds=cinematic_bounds,
            last_ocr=raw_text,
            last_ocr_confidence=confidence,
            last_tip_ocr=tip_raw_text,
            last_tip_ocr_confidence=tip_confidence,
            last_tip_match_score=tip_match_score,
            last_cinematic_ocr=cinematic_raw_text,
            last_cinematic_ocr_confidence=cinematic_confidence,
            last_cinematic_match_score=cinematic_match_score,
            last_match_score=match_score,
            last_scan_at=now,
            last_error=None,
        )
        return _ScanOutcome(emitted_lines=emitted_lines)

    def _audio_ready(self, line_id: int, audio_path: str | None, voiced: bool) -> None:
        if self._event_loop is None:
            return
        if not voiced or not audio_path:
            removed_audio = self.transcript.delete(line_id)
            self._remove_audio_file(removed_audio)
            asyncio.run_coroutine_threadsafe(self.on_delete(line_id), self._event_loop)
            return

        line = self.transcript.update_audio(line_id, audio_path, True)
        if line is None:
            self._remove_audio_file(audio_path)
            return
        asyncio.run_coroutine_threadsafe(self.on_line(line), self._event_loop)
        for removed_id, removed_audio in self.transcript.prune(keep_nonfavorite=50):
            self._remove_audio_file(removed_audio)
            asyncio.run_coroutine_threadsafe(self.on_delete(removed_id), self._event_loop)

    def _remove_audio_file(self, filename: str | None) -> None:
        if not filename:
            return
        audio_dir = self.audio.output_dir.resolve()
        path = (audio_dir / filename).resolve()
        if path.parent == audio_dir:
            path.unlink(missing_ok=True)

    def _can_emit(self, key: str, now: float, cooldown_seconds: float = 60.0) -> bool:
        channel = key.split("\0", 1)[0]
        if self._last_emitted_key_by_channel.get(channel) == key:
            return False
        # The same subtitle can be visible in both the dialogue and cinematic
        # regions. Cool down its official TextMap key globally, not per region.
        content_key = key.split("\0", 1)[1] if "\0" in key else key
        previous = self._last_emitted_at.get(content_key)
        if previous is not None and now - previous < cooldown_seconds:
            return False
        self._last_emitted_at[content_key] = now
        self._last_emitted_key_by_channel[channel] = key
        if len(self._last_emitted_at) > 2048:
            cutoff = now - cooldown_seconds
            self._last_emitted_at = {
                item_key: timestamp
                for item_key, timestamp in self._last_emitted_at.items()
                if timestamp >= cutoff
            }
        return True

    def _is_redundant_visible_match(
        self, channel: str, matched_english: str, current_ocr: str
    ) -> bool:
        """Reject a shorter match while the fuller subtitle remains visible."""
        matched = normalize_english(matched_english)
        visible = normalize_english(current_ocr)
        previous = self._last_visible_match_by_channel.get(channel)
        redundant = bool(
            previous
            # Equal frames are required to confirm typewriter completion. Only
            # a genuinely shorter match is a stale suffix of the full subtitle.
            and len(matched) < len(previous)
            and matched in previous
            and previous in visible
        )
        if not redundant:
            self._last_visible_match_by_channel[channel] = matched
        return redundant

    @staticmethod
    def _same_cinematic_panel(previous: str, current: str) -> bool:
        if not previous or not current:
            return False
        if previous in current or current in previous:
            return True
        return SequenceMatcher(None, previous, current).ratio() >= 0.48

    @staticmethod
    def _is_phone_screen(lines: list[str]) -> bool:
        text = " ".join(lines).casefold()
        strong_markers = ("daily info", "latest messages displayed above", "knock knock")
        if len(lines) >= 3 and any(marker in text for marker in strong_markers):
            return True
        secondary_markers = ("reply", "completed", "latest messages")
        return len(lines) >= 4 and sum(marker in text for marker in secondary_markers) >= 2

    @staticmethod
    def _classify_screen_header(lines: list[str]) -> str | None:
        text = " ".join(lines).casefold()
        if "story recap" in text:
            return "story_recap"
        if "knock knock" in text:
            return "phone"
        if "story commission" in text or "combat commission" in text:
            return "hdd"
        return None

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
