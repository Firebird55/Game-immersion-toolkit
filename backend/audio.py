from __future__ import annotations

import shutil
import subprocess
import threading
import time
import wave
from collections import deque
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

    def status(self) -> dict[str, object]:
        message = self.message
        if self._voice_validation_error:
            message += f"; voice validation unavailable (lines skipped): {self._voice_validation_error}"
        return {"ready": self.ready, "message": message,
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
        pre_roll: float = 1.3,
        post_roll: float = 5.0,
    ) -> None:
        with self._lock:
            for clip in self._pending:
                if clip.line_id == line_id:
                    clip.start = min(clip.start, detected_at - pre_roll)
                    clip.end = max(clip.end, detected_at + post_roll)
                    clip.detected_at = min(clip.detected_at, detected_at)
                    clip.callback = callback
                    return
            # OCR confirms a subtitle roughly half a second after it appears.
            # Treat that inferred appearance time as the boundary between two
            # back-to-back speakers, with only a small safety overlap.
            boundary = detected_at - 0.5
            for clip in self._pending:
                if clip.start < detected_at:
                    clip.end = min(clip.end, boundary + 0.15)
            clip_start = detected_at - pre_roll
            if self._pending:
                clip_start = max(clip_start, boundary - 0.25)
            self._pending.append(
                _PendingClip(
                    line_id=line_id,
                    start=clip_start,
                    end=detected_at + post_roll,
                    detected_at=detected_at,
                    callback=callback,
                )
            )

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
            while self._chunks and self._chunks[0].start < now - 35:
                self._chunks.popleft()
            ready = [clip for clip in self._pending if clip.end <= now]
            self._pending = [clip for clip in self._pending if clip.end > now]
        for clip in ready:
            self._finalize(clip)

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
        samples = self._samples_between(clip.start, clip.end)
        samples, voiced = self._trim_to_voice(samples, clip.detected_at - clip.start)
        if not voiced or samples.size == 0:
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
            group = self._select_speech_group(
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
