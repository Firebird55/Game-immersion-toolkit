"""Released cinematic subtitle clocks and explicitly referenced Wwise voice takes."""
import hashlib
import math
import re
import struct

from . import hoyo_publisher_voice as voices
from .hoyo_dialogue import audio_binding, audio_locale, records, voice_namespace
from .starrail_hotfix import check
from .starrail_reviewed_films import REVIEWED_MOVIES, MOVIE_AUDIO_CUTS


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
        check(re.fullmatch('[A-Za-z0-9_-]+', name) and path == f'Config/CutSceneCaption/{name}_Caption.json'
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


def _mission_captions(catalog, task_ids, video_id, default, locale):
    from .starrail_assets import _table
    lang = {'en': 'EN', 'ja': 'JP', 'ko': 'KR', 'zh-Hans': 'CN'}[audio_locale(locale)]
    paths = _table(catalog, 'PerformanceVideo', ('PerformanceID', 'PerformancePath'))
    selected, alternatives = set(), set()
    for perf in paths:
        path = perf['PerformancePath']
        mission = re.fullmatch(r'Config/Level/Mission/(\d+)/Act/Act(\d+)\.json', path)
        if not mission or int(mission[1]) not in task_ids:
            continue
        # Performance IDs can alias another authored Act file. The explicit
        # path and the movie's mission owner establish this join.
        for sequence in catalog.file(path).get('OnStartSequece', []):
            for task in sequence.get('TaskList', []):
                if task.get('$type') == 'RPG.GameCore.PlayVideo' and task.get('VideoID') == video_id:
                    selected.add(task.get('OverrideCaptionPath', default))
                if task.get('$type') != 'RPG.GameCore.PredicateTaskList':
                    continue
                predicate = task.get('Predicate', {})
                if predicate.get('$type') != 'RPG.GameCore.ByCurrentAudioLanguage':
                    continue
                for field in ('SuccessTaskList', 'FailedTaskList'):
                    plays = [action for action in task.get(field, []) if action.get('$type') == 'RPG.GameCore.PlayVideo'
                             and action.get('VideoID') == video_id]
                    for action in plays:
                        caption = action.get('OverrideCaptionPath', default)
                        alternatives.add(caption)
                        if (predicate['AudioLanguage'] == lang) == (field == 'SuccessTaskList'):
                            selected.add(caption)
    return selected, alternatives


def _movie_sources(catalog, scripts, locale):
    from .starrail_assets import _table
    configs = _table(catalog, 'VideoConfig', ('VideoID', 'VideoPath', 'CaptionPath'))
    result, conditional = {}, set()
    script_paths = {'Config/CutSceneCaption/' + filename for filename, _ in scripts if '/' not in filename}
    declared = {row.get('CaptionPath') for row in configs}
    # An unlisted numbered script can identify a mission worth reading. Its
    # name alone never binds a movie. Only the PlayVideo action does that.
    orphan_stems = {re.sub(r'_\d+_Caption\.json$', '', path) for path in script_paths - declared
                    if re.search(r'_\d+_Caption\.json$', path)}
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
        available, tasks = [], set()
        for suffix, gender in variants:
            asset = catalog.movie_files.get((path[:-4] + suffix + '.usm').casefold())
            if asset:
                available.append({'video_id': video_id, 'player_voice': gender, 'path': asset.name,
                                  'size': asset.size, 'md5': asset.digest})
                tasks.update(getattr(asset, 'task_ids', ()))
        selected = {caption}
        if tasks and re.sub(r'(?:_\d+)?_Caption\.json$', '', caption) in orphan_stems:
            eligible, alternatives = _mission_captions(catalog, tasks, video_id, caption, locale)
            if eligible and caption in alternatives and len(alternatives) > 1:
                selected = eligible
                conditional.update(alternatives)
        for path in selected:
            selected_scene = re.fullmatch(r'Config/CutSceneCaption/([A-Za-z0-9_-]+)_Caption\.json', path)
            check(selected_scene)
            if available:
                result.setdefault(selected_scene[1], []).extend(available)
    suppressed = {path.rsplit('/', 1)[1][:-len('_Caption.json')] for path in conditional} - result.keys()
    if any(filename.startswith('BattleCollegeCaption/') for filename, _ in scripts):
        for video in _table(catalog, 'LoopCGConfig', ('VideoID', 'VideoPath', 'CaptionPath')):
            caption = video.get('CaptionPath')
            if not caption:
                continue
            match = re.fullmatch(r'Config/BattleCollegeCaption/([A-Za-z0-9_-]+)\.json', caption)
            path, video_id = video['VideoPath'], video['VideoID']
            check(match and type(video_id) is int and video_id > 0
                  and re.fullmatch(r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.usm', path, re.I)
                  and type(video.get('IsPlayerInvolved', False)) is bool)
            variants = (('_m', 'male'), ('_f', 'female')) if video.get('IsPlayerInvolved') else (('', None),)
            scene = 'BattleCollegeCaption/' + match[1]
            for suffix, gender in variants:
                asset = catalog.movie_files.get((path[:-4] + suffix + '.usm').casefold())
                if asset:
                    result.setdefault(scene, []).append({'video_id': video_id, 'player_voice': gender,
                                                          'path': asset.name, 'size': asset.size, 'md5': asset.digest})
    return result, suppressed


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


def _movie_take(catalog, scene, movies, text_hash, locale, cache, player_voice=None):
    from . import starrail_movie_audio as movie_audio, starrail_movie_metadata as metadata
    source = getattr(catalog, 'movie_audio_source', None)
    movies = [movie for movie in movies if movie['player_voice'] == player_voice]
    if not source or not source[2] or len(movies) != 1:
        return None
    dub = audio_locale(locale)
    movie = movies[0]
    profiles = {digest: cuts for (name, video, lang, digest), cuts in MOVIE_AUDIO_CUTS.items()
                if (name, video, lang) == (scene, movie['video_id'], dub) and text_hash in cuts}
    if not profiles:
        return None
    directory, stamp, revision = source
    asset = catalog.movie_files[movie['path'].casefold()]
    identity = asset.name, dub
    if identity not in cache:
        try:
            formats = cache.get('formats')
            if formats is None:
                formats = metadata.load(directory, revision)
                cache['formats'] = formats
            cache[identity] = movie_audio.binding(directory, stamp, asset, dub, formats)
        except metadata.MovieFormatUnavailable:
            cache[identity] = None
            catalog.movie_audio_incomplete = True
    selected = cache[identity]
    if selected:
        binding, duration = selected
        cuts = profiles.get(binding['recording_sha256'])
        if cuts and (window := cuts.get(text_hash)) and 0 <= window[0] < window[1] <= duration:
            return binding | {'start_ms': window[0], 'end_ms': window[1]}
        catalog.movie_audio_incomplete = True


def caption_rows(tools, catalog, tables, locale, entries, sentence_rows=()):
    from .starrail_assets import _player_row
    takes = _takes(tools, catalog, locale, entries)
    scripts = list(catalog.caption_scripts())
    movies, suppressed = _movie_sources(catalog, scripts, locale)
    reviewed = _reviewed_sources(sentence_rows)
    seen, identities, result, movie_cache = set(), set(), [], {}
    for filename, script in scripts:
        match = re.fullmatch(r'([A-Za-z0-9_-]+)_Caption\.json', filename)
        tutorial = re.fullmatch(r'BattleCollegeCaption/([A-Za-z0-9_-]+)\.json', filename)
        check((match or tutorial) and isinstance(script.get('CaptionList'), list))
        scene = match[1] if match else 'BattleCollegeCaption/' + tutorial[1]
        check(scene not in seen)
        seen.add(scene)
        identity = getattr(catalog, 'caption_identities', {}).get(filename, scene)
        check((identity == scene or re.fullmatch(r'design_[0-9a-f]{16}', identity)) and identity not in identities)
        identities.add(identity)
        if scene in suppressed and scene not in takes:
            continue
        for n, caption in enumerate(script['CaptionList']):
            start, end = caption.get('StartTime', 0), caption['EndTime']
            text_hash = caption['CaptionTextID']['Hash']
            check(type(text_hash) is int and all(type(v) in (int, float) and math.isfinite(v) for v in (start, end))
                  and 0 <= start < end)
            start_ms, end_ms = round(start * 1000), round(end * 1000)
            movie_sources = movies.get(scene, [])
            # VideoConfig authors both protagonist files independently. Keep a
            # missing counterpart visible, and never reuse the other movie's
            # audio merely because the captions and display clocks are shared.
            variants = [('_m', 'male', None, None), ('_f', 'female', None, None)] if any(
                movie['player_voice'] is not None for movie in movie_sources) else [('', None, None, None)]
            for suffix, gender, audio, duration in takes.get(scene, variants):
                link = {'id': f'film-{identity}-{n}{suffix}', 'hash': text_hash, 'player_voice': gender,
                        'dialogue_kind': 'cutscene_caption', 'voice_status': 'unavailable', 'channels': ['cinematic']}
                rows = records('starrail', [link], tables, locale, {})
                if not rows:
                    continue
                row, = rows
                if gender:
                    row = _player_row(row, gender)
                row['film_caption'] = {'scene': scene, 'start_ms': start_ms, 'end_ms': end_ms,
                                       'movies': movies.get(scene, [])}
                if audio and duration is not None and 0 <= start_ms < end_ms <= duration:
                    row['audio'] = audio | {'start_ms': start_ms, 'end_ms': end_ms}
                    row['voice_status'] = 'voiced'
                elif original := _reviewed_take(tools, scene, movies.get(scene, []), text_hash, locale, reviewed):
                    row['audio'] = original
                    row['voice_status'] = 'voiced'
                elif original := _movie_take(catalog, scene, movie_sources, text_hash, locale, movie_cache, gender):
                    row['audio'] = original
                    row['voice_status'] = 'voiced'
                result.append(row)
    return result
