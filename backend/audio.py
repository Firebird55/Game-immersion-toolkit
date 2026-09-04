from __future__ import annotations

import shutil
import subprocess
import threading
import time
import wave
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pyaudiowpatch as pyaudio
import webrtcvad

from .firered_vad import FireRedVad


@dataclass(slots=True)
class _AudioChunk:
    start: float
    samples: np.ndarray


@dataclass(slots=True)
class _PendingClip:
    line_id: int
    start: float
    end: float
    detected_at: float
    callback: Callable[[int, str | None, bool], None]
    minimum_end: float
    silence_seconds: float
    forced_end: bool = False
    voice_start: float | None = None
    voice_end: float | None = None


class AudioCaptureService:
    """Rolling Windows loopback recorder with lightweight speech detection."""

    def __init__(self, output_dir: Path, sample_rate: int = 48_000) -> None:
        self.output_dir = output_dir
        self.sample_rate = sample_rate
        self.channels = 2
        self._chunks: deque[_AudioChunk] = deque()
        self._pending: list[_PendingClip] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._analysis_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zzz-voice-analysis")
        self._analysis_future: Future | None = None
        self._last_analysis_at = 0.0
        self._last_committed_end = float("-inf")
        self._vad = webrtcvad.Vad(2)
        self._voice_validation_error: str | None = None
        try:
            self._voice_vad: FireRedVad | None = FireRedVad()
        except Exception as error:
            self._voice_vad = None
            self._voice_validation_error = str(error)
        self.ready = False
        self.message = "Audio capture has not started"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="zzz-audio-loopback", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        self._analysis_executor.shutdown(wait=True, cancel_futures=True)

    def status(self) -> dict[str, object]:
        message = self.message
        if self._voice_validation_error:
            message += f"; voice validation unavailable (lines skipped): {self._voice_validation_error}"
        return {"ready": self.ready, "message": message,
                "pending_clips": len(self._pending),
                "clip_mode": "adaptive-utterance",
                "voice_validation_ready": self._voice_vad is not None and not self._voice_validation_error}

    def speech_recent(self, seconds: float = 2.0) -> bool:
        now = time.monotonic()
        samples = self._samples_between(now - seconds, now)
        return self._has_speech(samples)

    def schedule_clip(
        self,
        line_id: int,
        detected_at: float,
        callback: Callable[[int, str | None, bool], None],
        *,
        pre_roll: float = 2.0,
        observed_at: float | None = None,
        chinese: str = "",
    ) -> None:
        onset = min(detected_at, observed_at if observed_at is not None else detected_at - 0.5)
        minimum_wait, maximum_wait, silence = self._utterance_timing(chinese)
        with self._lock:
            for clip in self._pending:
                if clip.line_id == line_id:
                    # A typewriter-text upgrade belongs to the same recording.
                    # Never move its start across the preceding speaker boundary.
                    if not clip.forced_end:
                        clip.end = max(clip.end, clip.detected_at + maximum_wait)
                    clip.minimum_end = max(clip.minimum_end, clip.detected_at + minimum_wait)
                    clip.silence_seconds = max(clip.silence_seconds, silence)
                    clip.callback = callback
                    return
            # First-seen OCR time is a better speaker boundary than the later
            # stable match. Partition the buffer once, with no shared audio.
            boundary = onset - 0.1
            clip_start = max(onset - pre_roll, self._last_committed_end)
            for clip in self._pending:
                if not clip.forced_end:
                    clip.end = max(clip.start, min(clip.end, boundary))
                    clip.forced_end = True
                    clip_start = max(clip_start, clip.end)
            self._pending.append(
                _PendingClip(
                    line_id=line_id,
                    start=clip_start,
                    end=onset + maximum_wait,
                    detected_at=onset,
                    callback=callback,
                    minimum_end=onset + minimum_wait,
                    silence_seconds=silence,
                )
            )

    @staticmethod
    def _utterance_timing(chinese: str) -> tuple[float, float, float]:
        syllables = sum("\u4e00" <= char <= "\u9fff" for char in chinese)
        # Text length is only a guard against early pauses, never the clip's
        # saved duration. Actual speech bounds determine the saved audio.
        return (
            max(2.0, min(25.0, syllables / 7.0)),
            max(15.0, min(75.0, syllables / 2.5 + 8.0)),
            2.0 if syllables >= 30 else 1.3,
        )

    def cancel_clip(self, line_id: int) -> None:
        with self._lock:
            self._pending = [clip for clip in self._pending if clip.line_id != line_id]

    def _run(self) -> None:
        audio = pyaudio.PyAudio()
        stream = None
        try:
            devices = list(audio.get_loopback_device_info_generator())
            if not devices:
                raise RuntimeError("No Windows WASAPI loopback device was found")
            device = devices[0]
            self.sample_rate = int(device["defaultSampleRate"])
            self.channels = int(device["maxInputChannels"])
            self.ready = True
            self.message = f"Capturing {device['name']}"
            chunk_frames = self.sample_rate // 4
            stream = audio.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=int(device["index"]),
                frames_per_buffer=chunk_frames,
            )
            while not self._stop.is_set():
                raw = stream.read(chunk_frames, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, self.channels)
                self._append_samples(samples)
        except Exception as error:
            self.ready = False
            self.message = f"Audio capture unavailable: {error}"
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio.terminate()

    def _append_samples(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        now = time.monotonic()
        start = now - (len(samples) / self.sample_rate)
        with self._lock:
            self._chunks.append(_AudioChunk(start=start, samples=samples.copy()))
            while self._chunks and self._chunks[0].start < now - 85:
                self._chunks.popleft()
            if (
                self._pending and now - self._last_analysis_at >= 0.5
                and (self._analysis_future is None or self._analysis_future.done())
            ):
                self._last_analysis_at = now
                # Never run neural inference or ffmpeg on the WASAPI read loop.
                self._analysis_future = self._analysis_executor.submit(self._process_pending, now)

    def _process_pending(self, now: float) -> None:
        with self._lock:
            pending = list(self._pending)
        for clip in pending:
            samples = self._samples_between(clip.start, min(now, clip.end))
            bounds = None
            try:
                if self._voice_vad is not None and samples.size:
                    bounds = self._utterance_bounds(
                        self._voice_vad.segments(samples, self.sample_rate),
                        clip.detected_at - clip.start,
                    )
                    self._voice_validation_error = None
            except Exception as error:
                self._voice_validation_error = str(error)
            with self._lock:
                if clip not in self._pending:
                    continue
                if bounds:
                    first, last = (clip.start + value for value in bounds)
                    clip.voice_start = min(clip.voice_start, first) if clip.voice_start is not None else first
                    clip.voice_end = max(clip.voice_end, last) if clip.voice_end is not None else last
                if not self._clip_complete(clip, now):
                    continue
                self._pending.remove(clip)
                if clip.voice_end is not None:
                    self._last_committed_end = max(
                        self._last_committed_end, min(clip.end, clip.voice_end + 0.25)
                    )
            try:
                self._finalize(clip)
            except Exception as error:
                self._voice_validation_error = f"Could not save clip: {error}"
                clip.callback(clip.line_id, None, False)

    @staticmethod
    def _clip_complete(clip: _PendingClip, now: float) -> bool:
        if now >= clip.end:
            return True
        if clip.voice_end is None:
            return now >= clip.detected_at + 3.0
        return now >= clip.minimum_end and now - clip.voice_end >= clip.silence_seconds

    def _samples_between(self, start: float, end: float) -> np.ndarray:
        pieces: list[np.ndarray] = []
        with self._lock:
            chunks = list(self._chunks)
        for chunk in chunks:
            chunk_end = chunk.start + len(chunk.samples) / self.sample_rate
            if chunk_end <= start or chunk.start >= end:
                continue
            left = max(0, round((start - chunk.start) * self.sample_rate))
            right = min(len(chunk.samples), round((end - chunk.start) * self.sample_rate))
            if right > left:
                pieces.append(chunk.samples[left:right])
        if not pieces:
            return np.empty((0, self.channels), dtype=np.float32)
        return np.concatenate(pieces, axis=0)

    def _has_speech(self, samples: np.ndarray) -> bool:
        if samples.size == 0:
            return False
        mono = samples.mean(axis=1) if samples.ndim > 1 else samples
        rms = float(np.sqrt(np.mean(np.square(mono), dtype=np.float64)))
        if rms < 0.004:
            return False
        pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes()
        frame_bytes = int(self.sample_rate * 0.03) * 2
        voiced = 0
        total = 0
        for offset in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
            total += 1
            try:
                voiced += int(self._vad.is_speech(pcm[offset : offset + frame_bytes], self.sample_rate))
            except Exception:
                continue
        return total >= 3 and voiced >= max(3, round(total * 0.08))

    def _finalize(self, clip: _PendingClip) -> None:
        if clip.voice_start is None or clip.voice_end is None:
            clip.callback(clip.line_id, None, False)
            return
        samples = self._samples_between(
            max(clip.start, clip.voice_start - 0.2),
            min(clip.end, clip.voice_end + 0.25),
        )
        if samples.size == 0:
            clip.callback(clip.line_id, None, False)
            return

        wav_path = self.output_dir / f"{clip.line_id}.wav"
        mp3_path = self.output_dir / f"{clip.line_id}.mp3"
        pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(pcm.shape[1] if pcm.ndim > 1 else 1)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(pcm.tobytes())

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            result = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "96k",
                    str(mp3_path),
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0 and mp3_path.exists():
                wav_path.unlink(missing_ok=True)
                clip.callback(clip.line_id, mp3_path.name, True)
                return
        clip.callback(clip.line_id, wav_path.name, True)

    @classmethod
    def _utterance_bounds(
        cls, segments: list[tuple[float, float]], anchor_seconds: float
    ) -> tuple[float, float] | None:
        seed = cls._select_speech_group(segments, anchor_seconds)
        if seed is None:
            return None
        # The subtitle owns this whole window until trailing silence or the
        # next subtitle. Sentence pauses must not discard subsequent phrases.
        return seed[0], max(end for start, end in segments if end >= seed[1])

    @staticmethod
    def _select_speech_group(
        segments: list[tuple[float, float]], anchor_seconds: float
    ) -> tuple[float, float] | None:
        if not segments:
            return None
        ordered = sorted(segments)
        groups: list[list[float]] = []
        for start, end in ordered:
            if groups and start - groups[-1][1] <= 0.65:
                groups[-1][1] = max(groups[-1][1], end)
            else:
                groups.append([start, end])

        def distance(group: list[float]) -> float:
            start, end = group
            if start - 0.25 <= anchor_seconds <= end + 0.35:
                return 0.0
            return min(abs(anchor_seconds - start), abs(anchor_seconds - end))

        selected = min(groups, key=distance)
        # Do not attach unrelated speech that occurs much later in the clip
        # to a silent UI notice just because it is the nearest speech available.
        if distance(selected) > 0.75:
            return None
        return selected[0], selected[1]

    def _trim_to_voice(
        self, samples: np.ndarray, anchor_seconds: float
    ) -> tuple[np.ndarray, bool]:
        if samples.size == 0:
            return samples, False
        if self._voice_vad is None:
            return samples[:0], False
        try:
            group = self._utterance_bounds(
                self._voice_vad.segments(samples, self.sample_rate), anchor_seconds
            )
            self._voice_validation_error = None
        except Exception as error:
            self._voice_validation_error = str(error)
            return samples[:0], False
        if group is None:
            return samples[:0], False

        duration = len(samples) / self.sample_rate
        start = max(0.0, group[0] - 0.25)
        end = min(duration, group[1] + 0.45)
        left = round(start * self.sample_rate)
        right = min(len(samples), round(end * self.sample_rate))
        return samples[left:right], right > left
