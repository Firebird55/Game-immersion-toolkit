"""Released cinematic subtitle clocks and explicitly referenced Wwise voice takes."""
import hashlib
import math
import re
import struct

from . import hoyo_publisher_voice as voices
from .hoyo_dialogue import audio_binding, audio_locale, records, voice_namespace
from .starrail_hotfix import check
from .starrail_reviewed_films import REVIEWED_MOVIES


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


def _movie_sources(catalog):
    from .starrail_assets import _table
    configs = _table(catalog, 'VideoConfig', ('VideoID', 'VideoPath', 'CaptionPath'))
    result = {}
    for video in configs:
        caption = video.get('CaptionPath')
        if not caption:
            continue
        match = re.fullmatch(r'Config/CutSceneCaption/([A-Za-z0-9_-]+)_Caption\.json', caption)
        path, video_id = video['VideoPath'], video['VideoID']
        check(match and type(video_id) is int and video_id > 0
              and re.fullmatch(r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.usm', path, re.I)
              and type(video.get('IsPlayerInvolved', False)) is bool)
        variants = (('_m', 'male'), ('_f', 'female')) if video.get('IsPlayerInvolved') else (('', None),)
        for suffix, gender in variants:
            asset = catalog.movie_files.get((path[:-4] + suffix + '.usm').casefold())
            if asset:
                result.setdefault(match[1], []).append({'video_id': video_id, 'player_voice': gender,
                    'path': asset.name, 'size': asset.size, 'md5': asset.digest})
    return result


def _reviewed_sources(records):
    wanted = {f'starrail:{sentence}' for captions in REVIEWED_MOVIES.values() for sentence, _ in captions.values()}
    result = {}
    for row in records:
        key = row['text_id']
        audio = row.get('audio')
        if key in wanted and audio and audio.get('source') and not row.get('player_voice'):
            # A sentence with several published performances cannot identify a movie take.
            result[key] = None if key in result else audio
    return result


def _reviewed_take(tools, scene, movies, text_hash, locale, sources):
    if len(movies) != 1 or movies[0]['player_voice'] is not None:
        return None
    movie = movies[0]
    reviewed = REVIEWED_MOVIES.get((scene, movie['video_id'], movie['md5']), {}).get(text_hash)
    if not reviewed:
        return None
    sentence, hashes = reviewed
    dub = audio_locale(locale)
    expected = hashes.get(dub)
    audio = sources.get(f'starrail:{sentence}')
    if expected and audio and audio['locale'] == dub:
        raw = voices.extract(audio, tools, 'starrail')
        if hashlib.sha256(raw).hexdigest() == expected:
            return audio


def caption_rows(tools, catalog, tables, locale, entries, sentence_rows=()):
    takes = _takes(tools, catalog, locale, entries)
    movies = _movie_sources(catalog)
    reviewed = _reviewed_sources(sentence_rows)
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
                row['film_caption'] = {'scene': scene, 'start_ms': start_ms, 'end_ms': end_ms,
                                       'movies': movies.get(scene, [])}
                if audio and duration is not None and 0 <= start_ms < end_ms <= duration:
                    row['audio'] = audio | {'start_ms': start_ms, 'end_ms': end_ms}
                    row['voice_status'] = 'voiced'
                elif original := _reviewed_take(tools, scene, movies.get(scene, []), text_hash, locale, reviewed):
                    row['audio'] = original
                    row['voice_status'] = 'voiced'
                result.append(row)
    return result
