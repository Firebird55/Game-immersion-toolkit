"""Match numbered PlotAudio performances against their authored localized film track."""
import re
import struct
import subprocess
import wave

import numpy as np


MEDIA_ROOT = 'Client/Content/Aki/WwiseAudio_Generated/Media/'
EVENT_ROOT = 'Client/Content/Aki/WwiseAudio_Generated/Event/'
MAX_SECONDS = 300


def media_id(bank, event):
    from .nte_assets import wwise_hash
    # Wwise 172, one Play action directly targeting one streamed sound.
    # Other graphs, including switches, may choose different media at runtime.
    offset = 0
    sections = {}
    while offset + 8 <= len(bank):
        kind, size = struct.unpack_from('<4sI', bank, offset)
        offset += 8
        if size > len(bank) - offset or kind in sections:
            return None
        sections[kind] = bank[offset:offset + size]
        offset += size
    header = sections.get(b'BKHD', b'')
    hierarchy = sections.get(b'HIRC', b'')
    if offset != len(bank) or len(header) < 8 or struct.unpack_from('<I', header)[0] != 172 or len(hierarchy) < 4:
        return None
    count, = struct.unpack_from('<I', hierarchy)
    offset = 4
    nodes = {}
    for _ in range(count):
        if offset + 9 > len(hierarchy):
            return None
        kind, size, key = struct.unpack_from('<BII', hierarchy, offset)
        offset += 5
        if size < 4 or size > len(hierarchy) - offset or key in nodes:
            return None
        nodes[key] = (kind, hierarchy[offset + 4:offset + size])
        offset += size
    kind, play = nodes.get(wwise_hash(event), (0, b''))
    if offset != len(hierarchy) or kind != 4 or len(play) != 12 or play[:8] != bytes(7) + b'\x01':
        return None
    kind, action = nodes.get(struct.unpack_from('<I', play, 8)[0], (0, b''))
    if kind != 3 or len(action) < 6 or action[:2] != b'\x03\x04':
        return None
    kind, sound = nodes.get(struct.unpack_from('<I', action, 2)[0], (0, b''))
    if kind != 2 or len(sound) < 18 or sound[:5] != b'\x01\x00\x14\x00\x02':
        return None
    return struct.unpack_from('<I', sound, 5)[0]


def samples(wem, decoder, directory):
    source = directory / 'performance.wem'
    output = directory / 'performance.wav'
    source.write_bytes(wem)
    output.unlink(missing_ok=True)
    try:
        subprocess.run([str(decoder), '-o', str(output), str(source)], check=True,
                   capture_output=True, timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    with wave.open(str(output)) as stream:
        rate, channels, frames = stream.getframerate(), stream.getnchannels(), stream.getnframes()
        if rate != 48000 or channels not in (1, 2) or stream.getsampwidth() != 2 or not 0 < frames <= rate * MAX_SECONDS:
            return None
        pcm = np.frombuffer(stream.readframes(frames), dtype='<i2')
    if len(pcm) != frames * channels:
        return None
    # Both sources use the same decoder. Group averaging keeps the comparison at
    # 12 kHz and removes out-of-band energy before downsampling.
    mono = pcm.reshape(frames, channels).mean(axis=1)
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(4, [280, 4500], btype='bandpass', fs=rate, output='sos'), mono)[::4]


def _peak(track, energy, sample):
    power = float(np.dot(sample, sample))
    if not power:
        return 0, 0., 0.
    size = len(sample)
    nfft = 1 << (len(track) + size - 2).bit_length()
    raw = np.fft.irfft(np.fft.rfft(track, nfft) * np.fft.rfft(sample[::-1], nfft), nfft)
    windows = energy[size:] - energy[:-size]
    corr = np.abs(raw[size - 1:len(track)]) / np.sqrt(np.maximum(windows, max(1., power * .01)) * power)
    start = int(np.argmax(corr))
    other = max(corr[:max(0, start - 2400)].max(initial=0.), corr[start + 2400:].max(initial=0.))
    return start, corr[start], other


def _performance_span(track, energy, sample):
    size = len(sample)
    start, score, other = _peak(track, energy, sample)
    if score >= .19 and other < .94 * score:
        if score >= 1.8 * other:
            return start, start + size
        # Both halves must agree if a sustained syllable also matches elsewhere.
        aligned = track[start:start + size]
        middle = size // 2
        if all(abs(np.dot(ref, mix)) > .16 * np.linalg.norm(ref) * np.linalg.norm(mix)
               for ref, mix in ((sample[:middle], aligned[:middle]), (sample[middle:], aligned[middle:]))):
            return start, start + size
    # Some dubs shorten pauses when mixing the film. Require the beginning,
    # middle and end of the same take in order, with unique matches throughout.
    if size < 6 * 6000:
        return None
    previous = first = None
    for section in np.array_split(sample, 6):
        at, score, other = _peak(track, energy, section)
        if score < .23 or other >= .90 * score:
            return None
        if previous is None:
            first = at
        elif not len(section) * .5 <= at - previous <= len(section) * 1.5:
            return None
        previous = at
    return first, previous + len(section)


def interval(track, performances, caption_ms):
    if track is None or len(performances) < 2 or any(x is None or len(x) < 1200 or len(x) > len(track) for x in performances):
        return None
    # Caption time is a search window, never a substitute for audio timing.
    # Both performances must occur at the same cue and in the recorded mix.
    origin = max(0, (caption_ms - 5000) * 12)
    finish = min(len(track), (caption_ms + 6500) * 12 + max(map(len, performances)))
    full_length = len(track)
    track = track[origin:finish]
    if any(len(x) > len(track) for x in performances):
        return None
    energy = np.r_[0., np.cumsum(track * track)]
    bounds = []
    for sample in performances:
        span = _performance_span(track, energy, sample)
        if span is None:
            return None
        bounds.append((origin + span[0], origin + span[1]))
    if max(a for a, _ in bounds) >= min(b for _, b in bounds):
        return None
    begin = min(a for a, _ in bounds) - origin
    end = max(b for _, b in bounds) - origin
    # A take can acquire a short reverb tail or be slightly retimed in the
    # film mix. Extend only to recorded silence on this voice-only track.
    peak = np.max(np.abs(track[begin:end]), initial=0.)
    before = _quiet_edge(track[:begin][::-1], peak, origin == 0)
    after = _quiet_edge(track[end:], peak, finish == full_length)
    if before is None or after is None:
        return None
    return (begin + origin - before) // 12, (end + origin + after + 11) // 12


def _quiet_edge(adjacent, peak, track_boundary):
    # Up to 1.5 seconds, using 20 ms RMS windows and 120 ms of sustained quiet.
    quiet = 0
    for pos in range(0, min(len(adjacent), 18000), 240):
        window = adjacent[pos:pos + 240]
        if np.sqrt(np.mean(window * window)) <= max(1., peak * .005):
            quiet += len(window)
            if quiet >= 1440:
                return pos + len(window)
        else:
            quiet = 0
    if track_boundary and len(adjacent) <= 18000:
        return len(adjacent)
    return None


def candidates(db_root, records, voices, locale):
    from . import wuthering_assets as assets
    code, gender_slot = assets.VOICE_LOCALES[locale]
    by_id = {row['text_id'].removeprefix('wuwa:'): row for row in records
             if row['dialogue_kind'] == 'cinematic' and row['audio'] is None}
    if not by_id:
        return []
    groups = {}
    for identity, blob in assets._rows(db_root / 'db_plot_audio.db', 'SELECT Id, BinData FROM plotaudio'):
        match = re.fullmatch(r'(.+)_([0-9]{3})', identity)
        if match and match[1] in by_id:
            depot = assets.EXTERNAL_ROOT + code + '_' + assets._string(blob, 2) + '.wem'
            valid = (assets._string(blob, 0) == identity and not assets._boolean(blob, 3)
                     and not assets._boolean(blob, gender_slot) and depot in voices)
            groups.setdefault(match[1], {})[int(match[2])] = depot if valid else None
    if not groups:
        return []
    table = db_root / 'db_cgVedio.db'
    scenes = {}
    for scene, blob in assets._rows(table, 'SELECT CgName, BinData FROM videocaption'):
        key = assets._string(blob, 4)
        if key in groups:
            at = assets._field(blob, 2)
            if at is not None and at + 4 <= len(blob):
                frame = struct.unpack_from('<i', blob, at)[0]
                if 0 <= frame <= MAX_SECONDS * 30:
                    scenes.setdefault(key, set()).add((scene, round(frame * 1000 / 30)))
    events = {}
    for scene, variant, blob in assets._rows(table, 'SELECT CgName, GirlOrBoy, BinData FROM videosound'):
        path = assets._string(blob, 3)
        match = re.fullmatch(r'/Game/Aki/WwiseAudio/Events/(play_vo_[A-Za-z0-9_]+)\.\1', path)
        if match:
            at, until = assets._field(blob, 4), assets._field(blob, 5)
            starts_at_zero = at is None or at + 4 <= len(blob) and struct.unpack_from('<i', blob, at)[0] == 0
            plays_to_end = until is None or until + 4 <= len(blob) and struct.unpack_from('<i', blob, until)[0] == -1
            events.setdefault(scene, set()).add((variant, match[1], starts_at_zero and plays_to_end))
    result = []
    for key, group in groups.items():
        if (len(group) < 2 or len(group) > 8 or sorted(group) != list(range(1, len(group) + 1))
                or not all(group.values()) or len(scenes.get(key, set())) != 1):
            continue
        scene, caption_ms = next(iter(scenes[key]))
        choices = events.get(scene, set())
        if len(choices) == 1:
            variant, event, full_scene = next(iter(choices))
            if variant == 2 and full_scene:
                result.append((by_id[key], event, [group[index] for index in sorted(group)], caption_ms))
    return result
