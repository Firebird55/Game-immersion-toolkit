"""Match released Genshin movie names and authored subtitle intervals."""
import re
from pathlib import PurePosixPath
from subprocess import SubprocessError
from urllib.error import URLError

from . import hoyo_dialogue as common


def subtitle_cues(text):
    cues, conflicts = {}, set()
    timestamp = r'(\d{2}):([0-5]\d):([0-5]\d)[,.](\d{3})'
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n').replace('\r', '\n').strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or not re.fullmatch(r'[0-9]{1,6}', lines[0]):
            continue
        match = re.fullmatch(timestamp + r'\s*-->\s*' + timestamp, lines[1].strip())
        if not match:
            continue
        values = [int(x) for x in match.groups()]
        start, end = (h * 3600000 + m * 60000 + s * 1000 + ms for h, m, s, ms in (values[:4], values[4:]))
        content = common.display_text(' '.join(lines[2:]))
        index = int(lines[0])
        if index in cues:
            conflicts.add(index)
        elif start < end and content:
            cues[index] = (start, end, content)
    for index in conflicts:
        cues.pop(index, None)
    return cues


def _overlaps(left, right):
    return max(left[0], right[0]) < min(left[1], right[1])


def _aligned(cues, target):
    # Dubs can begin a caption at different times. Require a complete sequence
    # and an exclusive, bidirectional interval match before using its ordinal.
    aligned = {}
    shared_sequence = cues.keys() == target.keys()
    for index, cue in cues.items():
        other = target.get(index)
        if not other:
            continue
        if cue[:2] == other[:2] or (shared_sequence and _overlaps(cue, other)
                and sum(_overlaps(cue, entry) for entry in target.values()) == 1
                and sum(_overlaps(other, entry) for entry in cues.values()) == 1):
            aligned[index] = other[2]
    return aligned


def movie_records(catalog, movies, locales, source_locale, warnings):
    from .genshin_assets import TEXT_LOCALES
    if not movies or not hasattr(catalog, 'directory_text'):
        return []
    tracks = {}
    codes = {locale: {'ru': 'RU', 'th': 'TH'}.get(locale, TEXT_LOCALES[locale]) for locale in locales}
    mirror_tried = False
    for locale in locales:
        code = codes[locale]
        files = {}
        try:
            try:
                subtitles = list(catalog.directory_text('Subtitle/' + code, suffix='.srt'))
            except URLError:
                if mirror_tried:
                    raise
                from .genshin_archive_mirror import fetch_trees
                mirror_tried = True
                fetch_trees(catalog, tuple(codes.values()))
                subtitles = catalog.directory_text('Subtitle/' + code, suffix='.srt')
            for name, text in subtitles:
                path = PurePosixPath(name)
                if len(path.parts) != 1 or not path.stem.endswith('_' + code):
                    continue
                movie = path.stem.removesuffix('_' + code)
                if movie in movies:
                    files[movie] = subtitle_cues(text)
        except (URLError, TimeoutError, ConnectionError, SubprocessError, ValueError):
            warnings.append(f'Genshin movie subtitles for {locale} are unavailable. Refresh to retry this language.')
        tracks[locale] = files
    records = []
    for movie, cues in tracks[source_locale].items():
        translations = {locale: _aligned(cues, files.get(movie, {})) for locale, files in tracks.items()
                        if locale != source_locale}
        previous = None
        for index, (start, end, text) in sorted(cues.items()):
            identity = f'genshin:movie:{movie}:{index}:{start}-{end}'
            texts = {source_locale: text}
            for locale, aligned in translations.items():
                if index in aligned:
                    texts[locale] = aligned[index]
            previous_id = previous[2] if previous and previous[0] + 1 == index and previous[1] <= start else None
            records.append({'text_id': identity, 'source_locale': source_locale, 'source_text': text, 'texts': texts,
                            'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                            'audio_locale': common.audio_locale(source_locale), 'audio': None, 'voice_status': 'unknown',
                            'channels': ['cinematic'], 'dialogue_kind': 'cinematic_subtitle', 'previous_text_id': previous_id})
            previous = index, end, identity
    return records
