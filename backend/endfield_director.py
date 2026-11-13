"""Authored Endfield track traversal and decoded recording interval checks."""
import math


def track_clips(objects, root, *, conditions=None, gender=None, durations=None, complete=False):
    captions, speech = [], []
    pending = [(p, None) for p in reversed(root['m_Tracks'])]
    visited = set()
    while pending:
        pointer, parent = pending.pop()
        if pointer['m_FileID']:
            if complete:
                return None
            continue
        identity = pointer['m_PathID']
        if complete and identity not in objects:
            return None
        track = objects.get(identity, {})
        if identity in visited or (parent is not None and track.get('m_Parent') != parent):
            return None
        visited.add(identity)
        if track.get('m_Muted'):
            continue
        condition = track.get('enableOnCondition', {})
        if condition.get('m_PathID'):
            selection = (conditions or {}).get((condition['m_FileID'], condition['m_PathID']))
            if selection not in ('female', 'male'):
                return None
            if selection != gender:
                continue
        pending.extend((p, pointer) for p in reversed(track.get('m_Children', ())))
        for clip in track.get('m_Clips', ()):
            ref = clip['m_Asset']
            if complete and (ref['m_FileID'] or ref['m_PathID'] not in objects):
                return None
            asset = objects.get(ref['m_PathID'], {}) if not ref['m_FileID'] else {}
            text, event = asset.get('_textId'), asset.get('_audioEventKey', '')
            if not text and not event.lower().startswith('au_vo_'):
                continue
            start, duration = clip['m_Start'], clip['m_Duration']
            if (clip.get('m_TimeScale', 1) != 1 or clip.get('m_ClipIn', 0) != 0
                    or not math.isfinite(start + duration) or start < 0 or duration <= 0):
                return None
            end = start + duration
            if (durations and event in durations and asset.get('_stopEventAtClipEnd') == 0
                    and asset.get('_exitAudioEvent', {}).get('_id') == 0):
                end = max(end, start + durations[event])
            interval = round(start, 5), round(end, 5)
            if text:
                captions.append((text, *interval))
            if event.lower().startswith('au_vo_'):
                speech.append((event, *interval))
    return captions, speech


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
