"""Measure audible sections of a decoded film voice track on its recording clock."""
import argparse
import json
from pathlib import Path
import wave

import numpy as np


def activity(path, *, start_ms=0, end_ms=None):
    """Report RMS activity in 10 ms windows, independent of text or speaker."""
    with wave.open(str(path)) as wav:
        rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
        if wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE' or rate % 100 or not 1 <= channels <= 16:
            raise ValueError('Expected 16-bit PCM with an integral number of samples per 10 milliseconds.')
        first = (start_ms * rate + 999) // 1000
        stop = frames if end_ms is None else end_ms * rate // 1000
        if not 0 <= first < stop <= frames:
            raise ValueError('The measurement window must fit inside the recording.')
        wav.setpos(first)
        hop = rate // 100
        threshold = (32768 * 10 ** (-48 / 20)) ** 2
        spans = []
        for base in range(first, stop, rate):
            count = min(rate, stop - base)
            data = np.frombuffer(wav.readframes(count), dtype='<i2').reshape((count, channels))
            for offset in range(0, count, hop):
                window = data[offset:offset + hop].astype(np.float64)
                if np.max(np.mean(window * window, axis=0)) < threshold:
                    continue
                position = base + offset
                if spans and position - spans[-1][1] <= rate // 4:
                    spans[-1][1] = position + len(window)
                else:
                    spans.append([position, position + len(window)])
    return [[round(lo * 1000 / rate), round(hi * 1000 / rate)] for lo, hi in spans if hi - lo >= 7 * hop]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav', type=Path, help='Original 16-bit PCM WAV decoded with vgmstream.')
    parser.add_argument('--start-ms', type=int, default=0)
    parser.add_argument('--end-ms', type=int)
    args = parser.parse_args()
    print(json.dumps({'activity_ms': activity(args.wav, start_ms=args.start_ms, end_ms=args.end_ms)}))
