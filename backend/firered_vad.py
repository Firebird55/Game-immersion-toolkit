from __future__ import annotations

import os
import struct
import threading
from pathlib import Path

from .runtime_bundle import discover_layout

import kaldi_native_fbank as knf
import numpy as np
import onnxruntime as ort


def _read_binary_int(handle) -> int:
    if handle.read(1) != b"\x04":
        raise RuntimeError("Invalid FireRedVAD CMVN integer")
    return struct.unpack("<i", handle.read(4))[0]


def _load_cmvn(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as handle:
        if handle.read(2) != b"\0B":
            raise RuntimeError("Invalid FireRedVAD CMVN header")
        token = b""
        while not token.endswith(b" "):
            token += handle.read(1)
        dtype, item_size = (("<f8", 8) if token == b"DM " else ("<f4", 4))
        rows = _read_binary_int(handle)
        columns = _read_binary_int(handle)
        matrix = np.frombuffer(handle.read(rows * columns * item_size), dtype=dtype).reshape(
            rows, columns
        )
    dimensions = columns - 1
    count = matrix[0, dimensions]
    means = matrix[0, :dimensions] / count
    variances = matrix[1, :dimensions] / count - means * means
    return means.astype(np.float32), (1 / np.sqrt(np.maximum(variances, 1e-20))).astype(
        np.float32
    )


class FireRedVad:
    """Adapter around the portable FireRedVAD voice validation model."""

    def __init__(self) -> None:
        # Keep the capture model with the portable Proxy Transcript project.
        # The legacy GameSentenceMiner installation is an optional fallback.
        layout = discover_layout()
        project_assets = layout.resource_root / "assets" / "fireredvad"
        legacy_assets = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "gamesentenceminer"
            / "resources"
            / "GameSentenceMiner"
            / "assets"
            / "fireredvad"
        )
        if layout.mode == 'bundle':
            # A developer installation must never mask missing/tampered frozen
            # resources, and capture must never load sherpa's adjacent DLL set.
            model_path = layout.resource('assets/fireredvad/fireredvad_vad.onnx')
            cmvn_path = layout.resource('assets/fireredvad/cmvn.ark')
        else:
            asset_dir = project_assets if (project_assets / "fireredvad_vad.onnx").is_file() else legacy_assets
            model_path = asset_dir / "fireredvad_vad.onnx"
            cmvn_path = asset_dir / "cmvn.ark"
        if not model_path.exists() or not cmvn_path.exists():
            raise FileNotFoundError("FireRedVAD assets are missing; run Proxy Transcript setup")

        self._means, self._inverse_std = _load_cmvn(cmvn_path)
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._lock = threading.Lock()
        self._options = knf.FbankOptions()
        self._options.frame_opts.samp_freq = 16_000
        self._options.frame_opts.frame_length_ms = 25
        self._options.frame_opts.frame_shift_ms = 10
        self._options.frame_opts.dither = 0.0
        self._options.frame_opts.snip_edges = True
        self._options.mel_opts.num_bins = 80
        self._options.mel_opts.debug_mel = False

    @staticmethod
    def _resample_mono(samples: np.ndarray, source_rate: int) -> np.ndarray:
        mono = samples.mean(axis=1) if samples.ndim > 1 else samples
        if source_rate == 16_000:
            return mono.astype(np.float32, copy=False)
        output_length = max(1, round(len(mono) * 16_000 / source_rate))
        source_points = np.arange(len(mono), dtype=np.float64)
        target_points = np.linspace(0, max(0, len(mono) - 1), output_length)
        return np.interp(target_points, source_points, mono).astype(np.float32)

    def segments(self, samples: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
        if samples.size == 0:
            return []
        audio = self._resample_mono(samples, sample_rate)
        audio_int16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        fbank = knf.OnlineFbank(self._options)
        fbank.accept_waveform(16_000, audio_int16.tolist())
        frames = [fbank.get_frame(index) for index in range(fbank.num_frames_ready)]
        if not frames:
            return []
        features = np.vstack(frames).astype(np.float32)
        features = (features - self._means) * self._inverse_std
        with self._lock:
            output = self._session.run(None, {"feat": features[np.newaxis, :, :]})[0]
        probabilities = np.asarray(output, dtype=np.float32).squeeze()
        if probabilities.ndim == 0:
            probabilities = probabilities.reshape(1)
        return self._postprocess(probabilities, len(audio) / 16_000)

    @staticmethod
    def _postprocess(probabilities: np.ndarray, duration: float) -> list[tuple[float, float]]:
        # Five-frame smoothing and frame-based speech/silence thresholds.
        smoothed = np.convolve(probabilities, np.ones(5) / 5, mode="full")[: len(probabilities)]
        for index in range(min(4, len(probabilities))):
            smoothed[index] = probabilities[: index + 1].mean()
        predictions = smoothed >= 0.4

        segments: list[tuple[int, int]] = []
        candidate: int | None = None
        speech_start: int | None = None
        silence_start: int | None = None
        for index, is_speech in enumerate(predictions):
            if speech_start is None:
                if is_speech and candidate is None:
                    candidate = index
                elif not is_speech:
                    candidate = None
                elif candidate is not None and index - candidate >= 20:
                    speech_start = max(0, candidate - 5)
                    silence_start = None
            else:
                if not is_speech and silence_start is None:
                    silence_start = index
                elif is_speech:
                    silence_start = None
                elif silence_start is not None and index - silence_start >= 20:
                    segments.append((speech_start, silence_start))
                    speech_start = None
                    candidate = None
                    silence_start = None
        if speech_start is not None:
            segments.append((speech_start, len(predictions)))

        return [
            (round(start * 0.01, 3), min(duration, round(end * 0.01 + 0.025, 3)))
            for start, end in segments
            if end - start >= 20
        ]
