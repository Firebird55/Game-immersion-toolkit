"""Local landmark fingerprints plus waveform verification for exact game clips."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import resample_poly, stft, fftconvolve

RATE = 8000
HOP = 128


def mono_audio(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    from math import gcd
    divisor = gcd(sample_rate, RATE)
    return resample_poly(samples, RATE // divisor, sample_rate // divisor).astype(np.float32)


def landmarks(samples: np.ndarray) -> list[tuple[int, int]]:
    if len(samples) < 1024:
        return []
    _, _, spectrum = stft(samples, fs=RATE, nperseg=512, noverlap=512-HOP, boundary=None)
    power = np.abs(spectrum)
    power[:12] = 0
    maxima = maximum_filter(power, size=(7, 7))
    threshold = np.maximum(power.max(axis=0, keepdims=True) * .08, .00015)
    freq, frames = np.where((power == maxima) & (power > threshold))
    order = np.argsort(frames, kind='stable')
    peaks = list(zip(frames[order].tolist(), freq[order].tolist()))
    result = []
    for i, (time, frequency) in enumerate(peaks):
        added = 0
        for other_time, other_frequency in peaks[i+1:i+60]:
            delta = other_time - time
            if delta < 3:
                continue
            if delta > 45:
                break
            # Frequency bins plus rounded inter-peak timing are invariant to
            # playback offset and gain. Timing-neighbor queries absorb jitter.
            value = (frequency << 16) | (other_frequency << 8) | (delta // 2)
            result.append((value, time))
            added += 1
            if added == 6:
                break
    return result


def waveform_score(reference: np.ndarray, observed: np.ndarray) -> tuple[float, int]:
    if len(reference) < 1600 or len(observed) < len(reference):
        return 0., 0
    reference = reference - reference.mean()
    observed = observed - observed.mean()
    dot = fftconvolve(observed, reference[::-1], mode='valid')
    energy = np.cumsum(np.r_[0., observed.astype(np.float64) ** 2])
    energy = energy[len(reference):] - energy[:-len(reference)]
    scores = np.abs(dot) / np.sqrt(np.maximum(energy * float(reference @ reference), 1e-12))
    best = int(np.argmax(scores))
    return float(scores[best]), best
