"""Derive adjacent captions and independently audible occurrences from localized film timelines."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from backend import endfield_global_1_6 as profile
from scripts.import_endfield_timelines import DUBS, localized_tracks, narrative_conditions


def audible_interval(pcm, start, end, overlaps):
    rate, frames = pcm.getframerate(), pcm.getnframes()
    start_ms, end_ms = round(start * 1000), min(round(end * 1000), frames * 1000 // rate)
    if not 0 <= start_ms < end_ms:
        return None
    for left, right in overlaps:
        # Two authored boundaries can quantize to the same millisecond. Omit
        # every shared sample from the exported clips, including rounding.
        if round(left * 1000) == round(right * 1000):
            if left == start:
                start_ms = max(start_ms, math.ceil(right * 1000))
                continue
            if right == end:
                end_ms = min(end_ms, math.floor(left * 1000))
                continue
        # Include boundary samples for both the authored clock and millisecond trim.
        first = max(0, math.floor(min(left, round(left * 1000) / 1000) * rate))
        last = min(frames, math.ceil(max(right, round(right * 1000) / 1000) * rate))
        if first < last:
            pcm.setpos(first)
            if any(pcm.readframes(last - first)):
                return None
    first, last = round(start_ms * rate / 1000), round(end_ms * rate / 1000)
    if last <= first:
        return None
    pcm.setpos(first)
    return (start_ms, end_ms) if any(pcm.readframes(last - first)) else None


def derive(bundles, packages, cache, decoder, conditions=None):
    previous, extra = {}, {}
    for film, dub, captions, speech in localized_tracks(bundles, packages=packages, conditions=conditions):
        column = tuple(DUBS).index(dub)
        info = packages[dub][1].get(film)
        recording = profile.FILMS.get(film, (None,) * 4)[column]
        if not recording or not info or recording != tuple(info[:2]):
            continue
        counts = Counter(text for text, _, _ in captions)
        ordered = sorted(captions, key=lambda cue: (cue[1], cue[2], cue[0]))
        with tempfile.TemporaryDirectory() as tmp:
            pcm = None
            try:
                for i, (text, start, end) in enumerate(ordered):
                    anchor = None
                    if i:
                        prior, a, b = ordered[i - 1]
                        if (prior != text and counts[prior] == 1 and b <= start
                                and sum(x < b and a < y for _, x, y in ordered) == 1
                                and (film, prior) in profile.CUES and profile.CUES[film, prior][2 * column] is not None):
                            anchor = prior
                    known = (film, text) in profile.CUES and profile.CUES[film, text][2 * column] is not None
                    if known:
                        if anchor:
                            previous[film, dub, text] = anchor
                        continue
                    repeated = counts[text] > 1
                    if repeated and not anchor:
                        continue
                    overlaps = [(max(start, a), min(end, b)) for j, (_, a, b) in enumerate(ordered)
                                if i != j and a < end and start < b]
                    if not repeated and not overlaps:
                        continue
                    events = [(name, a, b) for name, a, b in speech if a < end and start < b]
                    if len(events) != 1:
                        continue
                    event, origin, stop = events[0]
                    if event != info[2] or not origin <= start < end <= stop:
                        continue
                    if pcm is None:
                        wem = Path(tmp) / 'speech.wem'
                        shutil.copyfile(cache / info[1], wem)
                        if sha256(wem.read_bytes()).hexdigest() != info[1]:
                            raise ValueError('Film recording checksum changed')
                        wav = wem.with_suffix('.wav')
                        subprocess.run([str(decoder), '-o', str(wav), str(wem)], capture_output=True, check=True)
                        pcm = wave.open(str(wav))
                        if (pcm.getnframes(), pcm.getframerate()) != tuple(info[3:]) or pcm.getsampwidth() != 2:
                            raise ValueError('Decoded film format changed')
                    clock = audible_interval(pcm, start - origin, end - origin,
                                             [(a - origin, b - origin) for a, b in overlaps])
                    if clock:
                        identity = f'{text}@{i + 1}' if repeated else text
                        extra[film, dub, identity] = text, *clock, repeated
                        if anchor:
                            previous[film, dub, identity] = anchor
            finally:
                if pcm:
                    pcm.close()
    return previous, extra


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('bundles', 'packages', 'speech-cache', 'decoder', 'output'):
        parser.add_argument('--' + arg, required=True, type=Path)
    parser.add_argument('--conditions', type=Path)
    args = parser.parse_args()
    result = derive(args.bundles, json.loads(args.packages.read_bytes()), args.speech_cache, args.decoder,
                    narrative_conditions(args.conditions) if args.conditions else {})
    with args.output.open('w', encoding='utf-8', newline='\n') as file:
        file.write('"""Localized film order and verified additional intervals. Generated by scripts/import_endfield_cue_context.py."""\n')
        for name, values in zip(('PREVIOUS', 'EXTRA'), result):
            file.write(f'\n{name} = {{\n')
            for key, value in sorted(values.items()):
                file.write(f'    {key!r}: {value!r},\n')
            file.write('}\n')
