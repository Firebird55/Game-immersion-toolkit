from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import io
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable
from pathlib import Path

import mss
from oneocr import OcrEngine
from PIL import Image

from .config import SettingsStore
from .games import GAME_PROFILES
from .models import CaptureRegion, CaptureSnapshot, TextMatch, TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex, normalize_english
from .bilingual import normalize_subtitle
from .pragmata import PragmataTextIndex
from .hito import HitoTextIndex
from .pragmata_audio import PragmataVoiceAssetService
from .windows import WindowInfo, executable_path_for_window, find_active_game_window, find_game_window
from .voice_assets import VoiceAssetService


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
        pragmata: PragmataTextIndex | None,
        transcript: TranscriptStore,
        on_line: Callable[[TranscriptLine], Awaitable[None]],
        on_delete: Callable[[int], Awaitable[None]],
        on_status: Callable[[CaptureSnapshot], Awaitable[None]],
        audio_dir: Path,
        voice_assets: VoiceAssetService | None = None,
        pragmata_voice_assets: PragmataVoiceAssetService | None = None,
        hito: HitoTextIndex | None = None,
        game_indexes: dict | None = None,
        game_voice_assets: dict | None = None,
    ):
        self.settings = settings
        self.textmaps = textmaps
        self.pragmata = pragmata
        self.hito = hito
        self.game_indexes = game_indexes or {}
        self.game_voice_assets = game_voice_assets or {}
        self.transcript = transcript
        self.on_line = on_line
        self.on_delete = on_delete
        self.on_status = on_status
        self.audio_dir = audio_dir
        self.voice_assets = voice_assets
        self.pragmata_voice_assets = pragmata_voice_assets
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
        self._scan_epoch = 0
        self._scan_index = 0
        self._last_emitted_at: dict[str, float] = {}
        self._last_emitted_key_by_channel: dict[str, str] = {}
        self._last_visible_match_by_channel: dict[str, str] = {}
        self._visible_match_started: dict[str, tuple[str, float]] = {}
        self._cinematic_seen_ids: set[str] = set()
        self._cinematic_panel_text = ""
        self._excluded_screen: str | None = None
        self._visual_novel_layout = False
        self._visible_text_by_channel: dict[str, tuple[float, list[str]]] = {}

    def snapshot(self) -> CaptureSnapshot:
        with self._snapshot_lock:
            return self._snapshot.model_copy(deep=True)

    def _update_snapshot(self, **changes: object) -> CaptureSnapshot:
        if changes.get("phase") in {"stopped", "starting", "error", "waiting_for_game", "excluded_screen"}:
            self._visible_text_by_channel.clear()
            changes["visible_text_ids"] = []
        with self._snapshot_lock:
            self._snapshot = self._snapshot.model_copy(update=changes)
            return self._snapshot.model_copy(deep=True)

    def preview_bytes(self) -> bytes:
        with self._preview_lock:
            return self._preview

    def preview_for_region(self, region: CaptureRegion) -> bytes:
        active = find_active_game_window(self.settings.get())
        if active is None:
            return b""
        image = self._capture(self._region_bounds(active[1], region))
        return self._encode_preview(image)

    def start(self) -> bool:
        if self._task and not self._task.done():
            return False
        self._event_loop = asyncio.get_running_loop()
        self._update_snapshot(running=True, phase="starting", message="Starting subtitle OCR and original game voices")
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
                    scan = loop.run_in_executor(self._executor, self._scan_once)
                    outcome = await asyncio.wait_for(asyncio.shield(scan), timeout=12)
                    snapshot = self.snapshot()
                    await self.on_status(snapshot)
                    if outcome and outcome.emitted_lines:
                        for line in outcome.emitted_lines:
                            if line.game == "hito":
                                await self.on_line(line)
                    # Subtitle-confirmed lines publish while their original
                    # game files are decoded asynchronously.
                except asyncio.TimeoutError:
                    # A native OCR call can occasionally stop returning. Rotate
                    # the worker and engine so capture resumes instead of
                    # leaving a stale screen classification in the UI forever.
                    self._scan_epoch += 1
                    self._executor.shutdown(wait=False, cancel_futures=True)
                    self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-ocr")
                    self._engine = None
                    self._excluded_screen = None
                    self._tracker.observe(None)
                    self._tip_tracker.observe(None)
                    self._cinematic_tracker.observe(None)
                    snapshot = self._update_snapshot(
                        running=True,
                        phase="error",
                        message="OCR stalled; capture recovered automatically",
                        last_error="A scan exceeded 12 seconds and was replaced",
                    )
                    await self.on_status(snapshot)
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
        epoch = self._scan_epoch
        self._scan_index += 1
        settings = self.settings.get()
        active = find_active_game_window(settings)
        now = datetime.now(timezone.utc).astimezone()
        if active is None:
            self._excluded_screen = None
            self._tracker.observe(None)
            self._tip_tracker.observe(None)
            self._cinematic_tracker.observe(None)
            self._update_snapshot(
                running=True,
                phase="waiting_for_game",
                message="Waiting for a supported game",
                active_game=None,
                window_title=None,
                window_bounds=None,
                crop_bounds=None,
                tip_crop_bounds=None,
                cinematic_crop_bounds=None,
                last_scan_at=now,
                last_error=None,
            )
            return _ScanOutcome([])

        profile, window = active

        engine = self._engine
        if engine is None:
            engine = OcrEngine()
            self._engine = engine

        if profile.id in self.game_indexes:
            region = getattr(settings, f"{profile.id}_region")
            index = self.game_indexes[profile.id]
            index.player_voice = settings.cyberpunk_v_voice
            return self._scan_pragmata(window, region, engine, epoch, now, game=profile.id)
        if profile.id == "pragmata":
            return self._scan_pragmata(window, profile.subtitle_region, engine, epoch, now)
        if profile.id == "hito":
            return self._scan_hito(window, engine, epoch, now)

        crop_bounds = self._region_bounds(window, settings.region)
        # Normal 3D interactions and voiced visual-novel scenes use nearly the
        # same bottom dialogue box. The visual-novel presentation has a stable,
        # nearly-black filmstrip across the top; sample it every scan so a line
        # shown immediately after a transition is classified correctly.
        layout_probe = self._capture(self._region_bounds(
            window, CaptureRegion(left=0, top=0, width=1, height=.10)))
        self._visual_novel_layout = self._is_visual_novel_layout(layout_probe)
        if self._scan_index % 4 == 1:
            # One inexpensive upper-screen signature pass covers the left-side
            # Story Recap header, centered Knock Knock panel, and the HDD hub.
            header_bounds = self._region_bounds(
                window, CaptureRegion(left=0, top=0, width=1, height=0.55)
            )
            header_image = self._capture(header_bounds)
            if header_image.width > 1400:
                header_image.thumbnail((1400, 700), Image.Resampling.LANCZOS)
            header_response = engine.recognize_pil(header_image)
            if epoch != self._scan_epoch:
                return _ScanOutcome([])
            header_lines = [
                line.get("text", "").strip()
                for line in header_response.get("lines", [])
                if line.get("text", "").strip()
            ]
            self._excluded_screen = self._classify_screen_header(header_lines)
        image = self._capture(crop_bounds)
        self._set_preview(image)
        dialogue_box_layout = self._has_dialogue_box(image)
        if image.width > 1600:
            image.thumbnail((1600, 400), Image.Resampling.LANCZOS)
        response = engine.recognize_pil(image)
        if epoch != self._scan_epoch:
            return _ScanOutcome([])
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
                active_game="zzz",
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
        dialogue_match = (
            None
            if excluded_screen
            else self.textmaps.match_lines(lines, threshold=settings.fuzzy_threshold)
        )
        # Short voiced remarks during free-roam gameplay are rendered as white
        # outlined text directly over the scene. They use OngoingLevel TextMap
        # records rather than the normal GalGame dialogue family. Only consider
        # that family when the broad dark interaction box is absent.
        gameplay_match = (
            None
            if excluded_screen or dialogue_box_layout or self._visual_novel_layout
            else self.textmaps.match_lines(
                lines, threshold=settings.fuzzy_threshold, channel="gameplay"
            )
        )
        raw_match = gameplay_match or dialogue_match
        match_channel = "gameplay" if gameplay_match is not None else "dialogue"
        # The large bottom dialogue box in normal 3D gameplay is interaction
        # text, not spoken audio. Only that exact text is blocked; cinematic,
        # comic and top-right channels remain independently eligible.
        unvoiced_gameplay_dialogue = bool(
            dialogue_match and dialogue_box_layout and not self._visual_novel_layout
            and not self._mapped_voice(dialogue_match)
        )
        match = None if unvoiced_gameplay_dialogue or not self._mapped_voice(raw_match) else raw_match
        blocked_unvoiced_ids = (
            {dialogue_match.text_id} if unvoiced_gameplay_dialogue else set()
        )
        monotonic_now = time.monotonic()
        self._observe_visible_matches(
            match_channel, [match.text_id] if match else [], monotonic_now
        )
        emitted_lines: list[TranscriptLine] = []
        if match is None:
            self._tracker.observe(None if not raw_text else f"unmatched:{raw_text.casefold()}")
            phase = "unmatched" if raw_text else "listening"
            message = "Subtitle seen, but no official match" if raw_text else "Reading English subtitles"
            match_score = None
        else:
            key = f"{match.text_id}\0{match.english}"
            fresh_match = self._is_fresh_match(match_channel, key, monotonic_now)
            redundant_visible_match = self._is_redundant_visible_match(
                match_channel, match.english, raw_text
            )
            if fresh_match and (
                self._tracker.observe(key)
                and not redundant_visible_match
                and self._can_emit(f"{match_channel}\0{key}", monotonic_now)
            ):
                line, _ = self.transcript.add_or_upgrade_recent(
                    match, self.session_id, created_at=now, channel=match_channel
                )
                if line is not None:
                    emitted_lines.append(line)
                    self._schedule_line_audio(
                        line, monotonic_now,
                        observed_at=self._visible_match_started[match_channel][1],
                    )
            phase = "matched"
            message = (
                "Voiced gameplay subtitle matched"
                if match_channel == "gameplay"
                else "Official bilingual line matched"
            )
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
            tip_response = engine.recognize_pil(tip_image)
            if epoch != self._scan_epoch:
                return _ScanOutcome([])
            tip_lines = [line.get("text", "").strip() for line in tip_response.get("lines", [])]
            tip_lines = [line for line in tip_lines if line]
            tip_raw_text = " ".join(tip_lines).strip()
            tip_confidence = self._confidence(tip_response)
            tip_match = None if excluded_screen else self.textmaps.match_lines(
                tip_lines, threshold=settings.fuzzy_threshold, channel="tip"
            )
            if not self._mapped_voice(tip_match):
                tip_match = None
            tip_key = (
                f"tip\0{tip_match.text_id}\0{tip_match.english}"
                if tip_match is not None
                else ""
            )
            self._observe_visible_matches("tip", [tip_match.text_id] if tip_match else [], monotonic_now)
            fresh_tip = bool(tip_key) and self._is_fresh_match(
                "tip", tip_key, monotonic_now
            )
            if tip_match is None:
                self._tip_tracker.observe(None if not tip_raw_text else f"unmatched:{tip_raw_text.casefold()}")
            else:
                if (
                    fresh_tip
                    and self._tip_tracker.observe(tip_key)
                    and self._can_emit(tip_key, monotonic_now)
                ):
                    line, _ = self.transcript.add_or_upgrade_recent(
                        tip_match, self.session_id, created_at=now, channel="tip"
                    )
                    if line is not None:
                        emitted_lines.append(line)
                        self._schedule_line_audio(
                            line, monotonic_now,
                            observed_at=self._visible_match_started["tip"][1],
                        )
                tip_match_score = tip_match.score
                if match is None:
                    phase = "matched"
                    message = "Official top-right tip matched"

        cinematic_bounds = self._region_bounds(window, settings.cinematic_region)
        cinematic_raw_text = ""
        cinematic_confidence: float | None = None
        cinematic_match_score: float | None = None
        # A comic bubble can be added and voiced between two alternating scans.
        # Once the filmstrip layout is visible, inspect it on every pass; retain
        # the cheaper alternating cadence for ordinary gameplay/cutscenes.
        scan_cinematic = self._visual_novel_layout or self._scan_index % 2 == 1
        # Visible subtitles and exact game-file mappings confirm the voice.
        if not excluded_screen and tip_match is None and scan_cinematic:
            cinematic_image = self._capture(cinematic_bounds)
            if cinematic_image.width > 1920:
                cinematic_image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            cinematic_response = engine.recognize_pil(cinematic_image)
            if epoch != self._scan_epoch:
                return _ScanOutcome([])
            cinematic_lines = self._spatial_text_groups(cinematic_response)
            cinematic_raw_text = " ".join(cinematic_lines).strip()
            cinematic_confidence = self._confidence(cinematic_response)
            cinematic_matches = self.textmaps.match_line_groups(
                cinematic_lines,
                threshold=max(settings.fuzzy_threshold, 88),
                channel="cinematic",
            )
            cinematic_matches = [item for item in cinematic_matches if self._mapped_voice(item)]
            self._observe_visible_matches("cinematic", [item.text_id for item in cinematic_matches], monotonic_now)
            normalized_panel = normalize_subtitle(cinematic_raw_text)
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
                and item.text_id not in blocked_unvoiced_ids
            ]
            emitted_cinematic_matches: list[TextMatch] = []
            for cinematic_match in new_cinematic_matches:
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
                        emitted_cinematic_matches.append(cinematic_match)
                        self._cinematic_seen_ids.add(cinematic_match.text_id)
                        self._schedule_line_audio(
                            line, monotonic_now,
                            observed_at=monotonic_now,
                        )
            if emitted_cinematic_matches:
                cinematic_match_score = max(item.score for item in emitted_cinematic_matches)
                if match is None and tip_match is None:
                    phase = "matched"
                    count = len(emitted_cinematic_matches)
                    message = (
                        "Voiced cinematic/comic line matched"
                        if count == 1
                        else f"{count} voiced cinematic/comic lines matched"
                    )
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
        elif unvoiced_gameplay_dialogue:
            phase = "excluded_screen"
            message = "Unvoiced gameplay dialogue ignored"

        self._update_snapshot(
            running=True,
            active_game="zzz",
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
            visible_text_ids=self._visible_text_ids(monotonic_now),
        )
        return _ScanOutcome(emitted_lines=emitted_lines)

    def _scan_pragmata(
        self,
        window: WindowInfo,
        region: CaptureRegion,
        engine: OcrEngine,
        epoch: int,
        now: datetime,
        game: str = "pragmata",
    ) -> _ScanOutcome:
        """Capture PRAGMATA's shared lower subtitle lane.

        Radio messages, cinematics and walk-and-talk dialogue use the same
        speaker-plus-body layout. Matching exclusively against the official
        conv/cutscene MSG families and exact original voice mappings keeps HUD,
        credits and unvoiced UI copy out of the transcript.
        """
        self._excluded_screen = None
        crop_bounds = self._region_bounds(window, region)
        image = self._capture(crop_bounds)
        self._set_preview(image)
        if image.width > 1600:
            image.thumbnail((1600, 570), Image.Resampling.LANCZOS)
        response = engine.recognize_pil(image)
        if epoch != self._scan_epoch:
            return _ScanOutcome([])
        lines = [
            str(line.get("text", "")).strip()
            for line in response.get("lines", [])
            if str(line.get("text", "")).strip()
        ]
        raw_text = " ".join(lines)
        confidence = self._confidence(response)
        index = self.pragmata if game == "pragmata" else self.game_indexes.get(game)
        if index is None or not index.ready or (game != "pragmata" and index.audio_count == 0):
            self._tracker.observe(None)
            status = index.status() if index else {"message": "PRAGMATA index unavailable"}
            self._update_snapshot(
                running=True,
                phase="loading_textmaps" if index is None or not index.ready else "waiting_for_voice",
                message=str(status["message"]),
                active_game=game,
                window_title=window.title,
                window_bounds=window.bounds,
                crop_bounds=crop_bounds,
                tip_crop_bounds=None,
                cinematic_crop_bounds=None,
                last_ocr=raw_text,
                last_ocr_confidence=confidence,
                last_match_score=None,
                last_scan_at=now,
                last_error=None,
            )
            return _ScanOutcome([])

        settings = self.settings.get()
        match = index.match_lines(lines, threshold=max(84.0, settings.fuzzy_threshold))
        if not self._mapped_voice(match):
            match = None
        monotonic_now = time.monotonic()
        self._observe_visible_matches(game, [match.text_id] if match else [], monotonic_now)
        emitted: list[TranscriptLine] = []
        match_score = match.score if match else None
        if match is None:
            self._tracker.observe(None if not raw_text else f"unmatched:{raw_text.casefold()}")
            phase = "unmatched" if raw_text else "listening"
            message = f"Reading {GAME_PROFILES[game].name} subtitles"
        else:
            key = f"{game}\0{match.text_id}\0{match.english}"
            fresh = self._is_fresh_match(game, key, monotonic_now)
            # Two equal scans avoid committing typewriter/transition fragments.
            if (
                fresh
                and self._tracker.observe(key)
                and self._can_emit(key, monotonic_now)
            ):
                line, _ = self.transcript.add_or_upgrade_recent(
                    match, self.session_id, created_at=now, channel="dialogue"
                )
                if line is not None:
                    emitted.append(line)
                    observed_at = self._visible_match_started[game][1]
                    self._schedule_line_audio(line, monotonic_now, observed_at=observed_at)
            phase = "matched"
            message = f"{GAME_PROFILES[game].name} subtitle matched to original Mandarin voice"

        self._tip_tracker.observe(None)
        self._update_snapshot(
            running=True,
            phase=phase,
            message=message,
            active_game=game,
            window_title=window.title,
            window_bounds=window.bounds,
            crop_bounds=crop_bounds,
            tip_crop_bounds=None,
            cinematic_crop_bounds=None,
            last_ocr=raw_text,
            last_ocr_confidence=confidence,
            last_tip_ocr="",
            last_tip_ocr_confidence=None,
            last_tip_match_score=None,
            last_cinematic_ocr="",
            last_cinematic_ocr_confidence=None,
            last_cinematic_match_score=None,
            last_match_score=match_score,
            last_scan_at=now,
            last_error=None,
            visible_text_ids=self._visible_text_ids(monotonic_now),
        )
        return _ScanOutcome(emitted_lines=emitted)

    def _scan_hito(
        self, window: WindowInfo, engine: OcrEngine, epoch: int, now: datetime
    ) -> _ScanOutcome:
        settings = self.settings.get()
        index = self.hito
        if index:
            index.ensure_game_files(executable_path_for_window(window))
        emitted: list[TranscriptLine] = []
        observations: dict[str, tuple[tuple[int, int, int, int], str, float | None, TextMatch | None]] = {}
        visible_ids: list[str] = []
        screen = self._capture(window.bounds) if settings.hito_auto_regions else None
        detected = self._hito_box_regions(screen) if screen is not None else {}
        for channel, region, tracker in (
            ("dialogue", settings.hito_region, self._tracker),
            ("tip", settings.hito_tip_region, self._tip_tracker),
        ):
            region = detected.get(channel, region)
            bounds = self._region_bounds(window, region)
            if screen is None:
                image = self._capture(bounds)
            else:
                x, y = bounds[0] - window.bounds[0], bounds[1] - window.bounds[1]
                image = screen.crop((x, y, x + bounds[2], y + bounds[3]))
            if channel == "dialogue":
                self._set_preview(image)
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
            response = engine.recognize_pil(image)
            if epoch != self._scan_epoch:
                return _ScanOutcome([])
            lines = self._hito_ocr_lines(image, response, engine)
            raw = " ".join(lines)
            match = index.match_lines(lines) if index and index.ready else None
            observations[channel] = (bounds, raw, self._confidence(response), match)
            if match:
                visible_ids.append(match.text_id)
                key = f"hito\0{match.text_id}\0{match.english}\0{match.chinese}"
                if tracker.observe(key):
                    emitted.append(self.transcript.add_or_touch_hito(
                        match, self.session_id, created_at=now, channel=channel
                    ))
            else:
                tracker.observe(None if not raw else f"hito-unmatched:{raw}")

        bounds, raw, confidence, match = observations["dialogue"]
        tip_bounds, tip_raw, tip_confidence, tip_match = observations["tip"]
        ready = bool(index and index.ready)
        any_match = match or tip_match
        self._update_snapshot(
            running=True,
            phase="matched" if any_match else "listening" if ready else "loading_textmaps",
            message=(
                "Hito bilingual game text matched" if any_match
                else "Waiting for verified Hito dialogue" if ready
                else index.message if index else "Hito game-file reader unavailable"
            ),
            active_game="hito",
            window_title=window.title,
            window_bounds=window.bounds,
            crop_bounds=bounds,
            tip_crop_bounds=tip_bounds,
            cinematic_crop_bounds=None,
            last_ocr=raw,
            last_ocr_confidence=confidence,
            last_match_score=match.score if match else None,
            last_tip_ocr=tip_raw,
            last_tip_ocr_confidence=tip_confidence,
            last_tip_match_score=tip_match.score if tip_match else None,
            last_cinematic_ocr="",
            last_cinematic_ocr_confidence=None,
            last_cinematic_match_score=None,
            last_scan_at=now,
            last_error=None,
            visible_text_ids=list(dict.fromkeys(visible_ids)),
        )
        return _ScanOutcome(emitted)

    @staticmethod
    def _hito_box_regions(image: Image.Image) -> dict[str, CaptureRegion]:
        """Locate Hito's outlined message panels at the current game zoom."""
        import numpy as np

        scaled = image.copy()
        scaled.thumbnail((960, 960), Image.Resampling.BILINEAR)
        pixels = np.asarray(scaled.convert('RGB'), dtype=np.int16)
        height, width = pixels.shape[:2]
        white = (pixels.min(axis=2) > 180) & (pixels.max(axis=2) - pixels.min(axis=2) < 35)
        edges = []
        for y in range(height):
            transitions = np.diff(np.pad(white[y].astype(np.int8), (1, 1)))
            for left, right in zip(np.where(transitions == 1)[0], np.where(transitions == -1)[0]):
                if right - left >= width * .18 and left < width * .65 and right > width * .4:
                    if edges and y - edges[-1][0] <= 3 and abs(left - edges[-1][1]) < 5 and abs(right - edges[-1][2]) < 5:
                        continue
                    edges.append((y, left, right))
        panels = []
        for i, (top, left, right) in enumerate(edges):
            for bottom, bl, br in edges[i+1:]:
                if not height * .04 < bottom - top < height * .35 or abs(left-bl) > 6 or abs(right-br) > 6:
                    continue
                sides = white[top:bottom+1, max(0,left-5):min(width,left+6)].any(axis=1)
                if sides.mean() < .65:
                    continue
                panels.append((top, bottom, left, right))
        result = {}
        for channel, candidates in (
            ('dialogue', [p for p in panels if p[0] > height * .5]),
            ('tip', [p for p in panels if p[1] < height * .5]),
        ):
            if not candidates:
                continue
            top, bottom, left, right = max(candidates, key=lambda p: (p[3]-p[2]) * (p[1]-p[0]))
            # The bottom panel has a speaker glyph in its left column.
            inset = (right-left) * (.18 if channel == 'dialogue' else .02)
            x = (left + inset) / width
            y = (top + 3) / height
            result[channel] = CaptureRegion(left=x, top=y, width=(right-3)/width-x, height=(bottom-3)/height-y)
        return result

    @staticmethod
    def _hito_ocr_lines(image: Image.Image, response: dict, engine: OcrEngine) -> list[str]:
        """Read highlighted Hanzi separately from the surrounding Latin text."""
        import numpy as np

        rows = response.get("lines", [])
        original = [str(row.get("text", "")).strip() for row in rows if str(row.get("text", "")).strip()]
        pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
        orange = (pixels[:, :, 0] > pixels[:, :, 2] + 45) & (pixels[:, :, 0] > 120) & (pixels[:, :, 1] > 60)
        if np.count_nonzero(orange) < 40:
            return original
        mask = Image.fromarray(np.repeat((orange.astype(np.uint8) * 255)[:, :, None], 3, axis=2))
        highlighted = [row for row in engine.recognize_pil(mask).get("lines", [])
                       if re.search(r"[\u3400-\u9fff]", str(row.get("text", ""))) and row.get("bounding_rect")]
        if not highlighted or any(not row.get("bounding_rect") for row in rows):
            return original

        def bounds(row):
            rect = row["bounding_rect"]
            return (min(rect[f"x{i}"] for i in range(1, 5)), min(rect[f"y{i}"] for i in range(1, 5)),
                    max(rect[f"x{i}"] for i in range(1, 5)), max(rect[f"y{i}"] for i in range(1, 5)))

        remaining = list(highlighted)
        result = []
        for row in rows:
            left, top, right, bottom = bounds(row)
            # Ruby pinyin sits immediately above a highlighted Hanzi word.
            annotation = any(
                min(right, bounds(word)[2]) - max(left, bounds(word)[0]) > (right - left) * .6
                and bottom <= bounds(word)[1] + (bounds(word)[3] - bounds(word)[1]) * .15
                and bounds(word)[1] - bottom < bounds(word)[3] - bounds(word)[1]
                and bottom - top < (bounds(word)[3] - bounds(word)[1]) * .75
                for word in highlighted)
            if annotation:
                continue
            replacements = [word for word in remaining
                            if min(bottom, bounds(word)[3]) - max(top, bounds(word)[1])
                            > min(bottom - top, bounds(word)[3] - bounds(word)[1]) * .5
                            and min(right, bounds(word)[2]) - max(left, bounds(word)[0])
                            > min(right - left, bounds(word)[2] - bounds(word)[0]) * .5]
            if not replacements or not row.get("words"):
                result.append(str(row.get("text", "")))
                continue
            pieces = []
            for word in row["words"]:
                wl, wt, wr, wb = bounds(word)
                if any(min(wr, bounds(chinese)[2]) - max(wl, bounds(chinese)[0]) > (wr - wl) * .4
                       for chinese in replacements):
                    continue
                pieces.append((wl, str(word["text"])))
            for word in replacements:
                pieces.append((bounds(word)[0], str(word["text"])))
                remaining.remove(word)
            result.append(" ".join(text for _, text in sorted(pieces)))
        return result

    def _assets_for(self, game: str):
        if game == "zzz":
            return self.voice_assets
        if game == "pragmata":
            return self.pragmata_voice_assets
        return self.game_voice_assets.get(game)

    def _mapped_voice(self, match: TextMatch | None) -> bool:
        if match is None:
            return False
        assets = self._assets_for(match.game)
        return bool(assets and assets.has_variant(match.text_id, match.english))

    def _observe_visible_matches(self, channel: str, text_ids: list[str], now: float) -> None:
        self._visible_text_by_channel[channel] = (now, text_ids)

    @staticmethod
    def _spatial_text_groups(response: dict) -> list[str]:
        """Reassemble OCR rows into comic bubbles using their screen geometry."""
        positioned = []
        fallback = []
        for line in response.get("lines", []):
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            fallback.append(text)
            rectangle = line.get("bounding_rect") or {}
            try:
                xs = [float(rectangle[f"x{index}"]) for index in range(1, 5)]
                ys = [float(rectangle[f"y{index}"]) for index in range(1, 5)]
            except (KeyError, TypeError, ValueError):
                continue
            left, right = min(xs), max(xs)
            top, bottom = min(ys), max(ys)
            if right > left and bottom > top:
                positioned.append({
                    "text": text,
                    "left": left,
                    "right": right,
                    "top": top,
                    "bottom": bottom,
                })
        if len(positioned) != len(fallback):
            return fallback

        positioned.sort(key=lambda item: (item["top"], item["left"]))
        groups: list[dict] = []
        for item in positioned:
            item_height = item["bottom"] - item["top"]
            best_group = None
            best_distance = float("inf")
            for group in groups:
                group_height = max(1.0, group["line_height"])
                vertical_gap = item["top"] - group["bottom"]
                if vertical_gap < -max(item_height, group_height) or vertical_gap > max(
                    48.0, group_height * 2.4
                ):
                    continue
                overlap = min(item["right"], group["right"]) - max(
                    item["left"], group["left"]
                )
                narrow_width = min(
                    item["right"] - item["left"],
                    group["right"] - group["left"],
                )
                aligned = abs(item["left"] - group["line_left"]) <= max(
                    60.0, group_height * 3.0
                )
                if overlap < narrow_width * 0.18 and not aligned:
                    continue
                distance = abs(vertical_gap) + abs(item["left"] - group["line_left"]) * 0.15
                if distance < best_distance:
                    best_group = group
                    best_distance = distance
            if best_group is None:
                groups.append({
                    "lines": [item],
                    "left": item["left"],
                    "right": item["right"],
                    "top": item["top"],
                    "bottom": item["bottom"],
                    "line_left": item["left"],
                    "line_height": item_height,
                })
                continue
            best_group["lines"].append(item)
            best_group["left"] = min(best_group["left"], item["left"])
            best_group["right"] = max(best_group["right"], item["right"])
            best_group["bottom"] = max(best_group["bottom"], item["bottom"])
            best_group["line_left"] = item["left"]
            best_group["line_height"] = (best_group["line_height"] + item_height) / 2

        # Comic dialogue advances horizontally. Several bubbles may become
        # visible before one OCR pass, and ordering them by vertical position
        # would put an upper-right bubble before a lower-left bubble. Preserve
        # the game's reading sequence: columns left-to-right, then top-to-bottom
        # only when multiple bubbles occupy the same column.
        groups.sort(key=lambda group: (group["left"], group["top"]))
        return [
            " ".join(
                item["text"]
                for item in sorted(group["lines"], key=lambda row: (row["top"], row["left"]))
            )
            for group in groups
        ]

    def _visible_text_ids(self, now: float) -> list[str]:
        return list(dict.fromkeys(
            text_id
            for seen_at, text_ids in self._visible_text_by_channel.values()
            if now - seen_at <= 2.0
            for text_id in text_ids
        ))

    def _schedule_line_audio(self, line: TranscriptLine, now: float, *, observed_at: float) -> None:
        assets = self._assets_for(line.game)
        if not assets or not assets.has_variant(line.text_id, line.english):
            return
        # Publish the official bilingual subtitle immediately, independently of
        # output devices, game volume, or the time needed to decode the WEM.
        confirmed = self.transcript.update_audio(line.id, None, True)
        if confirmed is None or self._event_loop is None:
            return
        pending = confirmed.model_copy(update={"audio_pending": True, "audio_source": "original"})
        asyncio.run_coroutine_threadsafe(self.on_line(pending), self._event_loop)

        def publish(line_id: int, filename: str | None, voiced: bool) -> None:
            current = self.transcript.get(line_id)
            if current is None or current.text_id != line.text_id:
                self._remove_audio_file(filename)
                return
            self._audio_ready(line_id, filename, voiced)

        if not assets.schedule(line.text_id, line.id, publish, line.english):
            publish(line.id, None, False)

    def _audio_ready(self, line_id: int, audio_path: str | None, voiced: bool) -> None:
        if self._event_loop is None:
            return
        # Extraction failure must not erase a subtitle whose mapping already
        # confirms the voice. Playback can be retried from the original files.
        line = self.transcript.update_audio(line_id, audio_path if voiced else None, True)
        if line is None:
            self._remove_audio_file(audio_path)
            return
        asyncio.run_coroutine_threadsafe(self.on_line(line), self._event_loop)
        for removed_id, removed_audio in self.transcript.prune(keep_nonfavorite=50):
            self._remove_audio_file(removed_audio)
            asyncio.run_coroutine_threadsafe(self.on_delete(removed_id), self._event_loop)

    def _story_original_ready(self, line_id: int, text_id: str, audio_path: str) -> None:
        if self._event_loop is None:
            self._remove_audio_file(audio_path)
            return
        current = self.transcript.get(line_id)
        if current is None or current.text_id != text_id:
            self._remove_audio_file(audio_path)
            return
        previous = self.transcript.audio_path(line_id)
        line = self.transcript.update_audio(line_id, audio_path, True)
        if line is None:
            self._remove_audio_file(audio_path)
            return
        if previous and previous != audio_path:
            self._remove_audio_file(previous)
        asyncio.run_coroutine_threadsafe(self.on_line(line), self._event_loop)

    def repair_recorded_line(self, line: TranscriptLine) -> bool:
        assets = self._assets_for(line.game)
        if not assets or not line.voiced or (line.audio_source == "original" and line.has_audio):
            return False
        if not assets.has_variant(line.text_id, line.english):
            return False

        def ready(line_id: int, audio_path: str | None, voiced: bool) -> None:
            if voiced and audio_path:
                self._story_original_ready(line_id, line.text_id, audio_path)

        return assets.schedule(line.text_id, line.id, ready, line.english)

    def _remove_audio_file(self, filename: str | None) -> None:
        if not filename:
            return
        audio_dir = self.audio_dir.resolve()
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

    def _is_fresh_match(
        self, channel: str, key: str, now: float, max_age: float = 3.0
    ) -> bool:
        previous = self._visible_match_started.get(channel)
        if previous is None or previous[0] != key:
            self._visible_match_started[channel] = (key, now)
            return True
        return now - previous[1] <= max_age

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
    def _dark_fraction(image: Image.Image, threshold: int) -> float:
        probe = image.convert('L')
        probe.thumbnail((240, 120), Image.Resampling.BILINEAR)
        histogram = probe.histogram()
        total = max(1, sum(histogram))
        return sum(histogram[:threshold]) / total

    @classmethod
    def _is_visual_novel_layout(cls, top_probe: Image.Image) -> bool:
        # The supplied filmstrip reference is >99% below luma 20 in this strip;
        # ordinary gameplay remains far above it. The high cutoff avoids
        # treating a merely dark/night scene as the visual-novel frame.
        return cls._dark_fraction(top_probe, 20) >= .93

    @classmethod
    def _has_dialogue_box(cls, image: Image.Image) -> bool:
        # Inspect the central lower half of the configured dialogue crop. Both
        # gameplay and visual-novel boxes are broad, near-black rectangles;
        # plain anime subtitles and comic speech bubbles are not.
        width, height = image.size
        box = image.crop((round(width * .15), round(height * .45),
                          round(width * .85), height))
        return cls._dark_fraction(box, 50) >= .65

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
