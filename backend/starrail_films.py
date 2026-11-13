"""Released cinematic subtitle clocks and explicitly referenced Wwise voice takes."""
import math
import re
import struct

from . import hoyo_publisher_voice as voices
from .hoyo_dialogue import audio_binding, records, voice_namespace
from .starrail_hotfix import check


def _duration(data):
    # Star Rail Wwise Vorbis v0x30 stores total PCM samples in its extended
    # format header. Other codecs may have a different clock.
    if len(data) < 86 or data[:4] != b'RIFF' or data[8:16] != b'WAVEfmt ':
        return None
    fmt_size, codec, channels, rate = struct.unpack_from('<IHHI', data, 16)
    extra, = struct.unpack_from('<H', data, 36)
    if (fmt_size, codec, extra) != (66, 0xffff, 48) or channels not in (1, 2, 6) or rate not in (44100, 48000):
        return None
    samples, = struct.unpack_from('<I', data, 44)
    return samples * 1000 // rate


def _takes(tools, catalog, locale, entries):
    from .starrail_assets import _table
    configs = _table(catalog, 'CutSceneConfig', ('CutSceneName', 'CaptionPath', 'CutScenePath'))
    voices_by_id = {r['VoiceID']: r for r in _table(catalog, 'VoiceConfig', ('VoiceID', 'VoicePath'))}
    result = {}
    for row in configs:
        path = row.get('CaptionPath')
        if not path or not row.get('VoiceID'):
            continue
        name = row['CutSceneName']
        check(re.fullmatch('[A-Za-z0-9_]+', name) and path == f'Config/CutSceneCaption/{name}_Caption.json'
              and name not in result)
        voice = voices_by_id.get(row['VoiceID'])
        if voice is None or voice.get('VoiceType') != 'Cutscene':
            continue
        source = voice['VoicePath']
        check(isinstance(source, str) and re.fullmatch('[A-Za-z0-9_-]+', source))
        variants = [('_m', 'male'), ('_f', 'female')] if voice.get('IsPlayerInvolved') else [('', None)]
        result[name] = []
        for suffix, gender in variants:
            key = f'{voice_namespace("starrail", locale)}/voice/{source}{suffix}.wem'
            audio = audio_binding(key, entries, locale)
            duration = _duration(voices.extract(audio, tools, 'starrail')) if audio else None
            result[name].append((suffix, gender, audio, duration))
    return result


def caption_rows(tools, catalog, tables, locale, entries):
    takes = _takes(tools, catalog, locale, entries)
    seen, result = set(), []
    for filename, script in catalog.caption_scripts():
        match = re.fullmatch(r'([A-Za-z0-9_]+)_Caption\.json', filename)
        check(match and match[1] not in seen and isinstance(script.get('CaptionList'), list))
        scene = match[1]
        seen.add(scene)
        for n, caption in enumerate(script['CaptionList']):
            start, end = caption.get('StartTime', 0), caption['EndTime']
            text_hash = caption['CaptionTextID']['Hash']
            check(type(text_hash) is int and all(type(v) in (int, float) and math.isfinite(v) for v in (start, end))
                  and 0 <= start < end)
            start_ms, end_ms = round(start * 1000), round(end * 1000)
            for suffix, gender, audio, duration in takes.get(scene, [('', None, None, None)]):
                link = {'id': f'film-{scene}-{n}{suffix}', 'hash': text_hash, 'player_voice': gender,
                        'dialogue_kind': 'cutscene_caption', 'voice_status': 'unavailable', 'channels': ['cinematic']}
                rows = records('starrail', [link], tables, locale, {})
                if not rows:
                    continue
                row, = rows
                if audio and duration is not None and 0 <= start_ms < end_ms <= duration:
                    row['audio'] = audio | {'start_ms': start_ms, 'end_ms': end_ms}
                    row['voice_status'] = 'voiced'
                result.append(row)
    return result
