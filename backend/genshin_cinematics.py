"""Match released Genshin movie names and authored subtitle intervals."""
import hashlib
import re
from pathlib import PurePosixPath
from subprocess import SubprocessError
from urllib.error import URLError

from . import hoyo_dialogue as common
from .languages import normalize_text

OPENING_MOVIE = 'MDAQ001_OPNew_Part1'
OPENING_SOURCES = ('vo_op_cs_paimon_01.wem', 'vo_op_cs_paimon_02.wem', 'vo_op_cs_paimon_03.wem',
                   'vo_op_cs_kiana_01.wem', 'vo_op_cs_heroine_01.wem', 'vo_op_cs_kiana_02.wem')
VERIFIED_OPENING_AUDIO = {
    'en': ('Outlanders, your journey ends here', 'ccb2294bc9cfbb8d5d3acfdab248d34bdbfee4f7fa603f67750bdd7faf805178'),
    'zh-Hans': ('外来之人，你们的旅途到此为止', '8879787f422285dafbd054e143d537670a070fdd6cf4eea72d81b7ed9284ba82'),
    'zh-Hant': ('外來之人，你們的旅途到此為止', '8879787f422285dafbd054e143d537670a070fdd6cf4eea72d81b7ed9284ba82'),
    'ko': ('이방인, 너희의 여정은 여기까지다', '6b5346ff856f84961f7a96262e3c6c99af2b9943ba0e176fb5c5690a1b5b5138')}


def verified_opening_conflict(dialogue, read_audio):
    """Identify the one reviewed opening performance from the actual regional package bytes."""
    for row in dialogue:
        if row['text_id'] != 'genshin:3500404':
            continue
        evidence = VERIFIED_OPENING_AUDIO.get(row.get('source_locale'))
        audio = row.get('audio')
        if (not evidence or not audio or row['source_text'] != evidence[0]
                or audio.get('locale') != common.audio_locale(row['source_locale'])):
            return None
        source = audio['source'].lower().replace('\\', '/').partition('/')[2]
        if source != 'vo_aq/vo_cs/vo_op_cs_kiana_01.wem':
            return None
        try:
            recording = read_audio(audio)
        except (TimeoutError, OSError, ValueError):
            return None
        if hashlib.sha256(recording).hexdigest() == evidence[1]:
            return row['text_id']
        return None


def opening_performances(movies, dialogue, locale):
    """Verify the entire six-line opening against the locale's own timed cue sequence."""
    cues = [row for row in movies if row['text_id'].startswith(f'genshin:movie:{OPENING_MOVIE}:')]
    if not cues:
        return []
    expected_ids = {'genshin:' + str(3500400 + index) for index in range(1, len(OPENING_SOURCES) + 1)}
    lines = {}
    for row in dialogue:
        if row['text_id'] in expected_ids:
            if row['text_id'] in lines:
                return []
            lines[row['text_id']] = row
    cursor, matched, result = 0, [], []
    for index, source in enumerate(OPENING_SOURCES, start=1):
        line = lines.get('genshin:' + str(3500400 + index))
        if not line:
            return []
        expected = normalize_text(line['source_text'])
        combined, members = '', []
        while cursor < len(cues) and len(combined) < len(expected):
            cue = cues[cursor]
            ordinal = cue['text_id'].split(':')[-2]
            if ordinal != str(cursor + 1):
                return []
            combined += normalize_text(cue['source_text'])
            members.append(cue)
            cursor += 1
        if combined != expected or not members:
            return []
        matched.append((line, source, members))
    if cursor != len(cues):
        return []

    for line, source, members in matched:
        audio = line.get('audio')
        if not audio or audio.get('locale') != common.audio_locale(locale):
            continue
        relative = audio['source'].lower().replace('\\', '/').partition('/')[2]
        if relative != 'vo_aq/vo_cs/' + source:
            continue
        # A divided subtitle displays only part of a single clean WEM. Publish
        # that complete performance under its own identity, never split the WEM by display time.
        if len(members) == 1:
            row = members[0]
        else:
            start = members[0]['text_id'].rsplit(':', 1)[1].split('-')[0]
            end = members[-1]['text_id'].rsplit('-', 1)[1]
            row = {'text_id': f"genshin:movie:{OPENING_MOVIE}:performance-{line['text_id'].split(':')[1]}:{start}-{end}",
                   'source_locale': locale, 'audio_locale': common.audio_locale(locale), 'channels': ['cinematic'],
                   'member_text_ids': [cue['text_id'] for cue in members]}
            result.append(row)
        row.update(source_text=line['source_text'], texts=line['texts'], english=line['english'],
                   chinese=line['chinese'], audio=audio, voice_status='voiced', dialogue_kind='cinematic_performance')
    return result


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
