"""Complete original scene recordings for authored captions without safe line cuts."""
from collections import defaultdict
from contextlib import ExitStack
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import tempfile

from . import endfield_film_update as films, endfield_scene_update as scenes
from .game_tools import _atomic_file
from .languages import audio_locale
from .preparation_errors import PreparationFailure
from .textmaps import display_text


def _audible(pcm, start, end):
    first = max(0, round(start * pcm.getframerate()))
    last = min(pcm.getnframes(), round(end * pcm.getframerate()))
    if first >= last:
        return False
    pcm.setpos(first)
    # Some original silent stretches decode to sparse +/-1 LSB noise. This is
    # not evidence of a spoken caption and must not borrow later scene speech.
    return any(abs(sample) > 1 for sample, in struct.iter_unpack('<h', pcm.readframes(last - first)))


def _contexts(captions, speech, recordings, known):
    grouped = defaultdict(list)
    for text, start, end in captions:
        if re.fullmatch(r'[A-Za-z0-9_]{1,180}', text) and text not in known:
            grouped[text].append((start, end))
    for text, occurrences in grouped.items():
        chosen = []
        for start, end in occurrences:
            matches = [(event, origin) for event, origin, stop in speech if origin < end and start < stop]
            if len(matches) != 1:
                break
            event, origin = matches[0]
            recording = recordings.get(event)
            if recording is None or not _audible(recording[2], start - origin, end - origin):
                break
            chosen.append(recording)
        else:
            # A repeated caption may share a context recording only when every
            # occurrence identifies that exact recording, never another take.
            if chosen and len({(row[0], row[1]) for row in chosen}) == 1:
                media, digest, pcm = chosen[0]
                yield text, (media, digest, pcm.getnframes() * 1000 // pcm.getframerate())
                continue
        yield text, None


def _build(tools, stamp, dub):
    from . import endfield_film_voice
    fixed = films.release.verified_films(tools, stamp, dub)
    column, suffixes = films.TRACKS[dub]
    known = defaultdict(set)
    for (film, text), clocks in films.profile.CUES.items():
        if film in fixed and clocks[2 * column] is not None:
            known[film].add(text)
    from .endfield_global_cue_context import EXTRA
    for (film, language, _), entry in EXTRA.items():
        if film in fixed and language in suffixes:
            known[film].add(entry[0])
    for (film, _), entry in films.cues(tools, stamp, dub).items():
        known[film].add(entry[0])
    files = films._files(tools, stamp)
    tracks = list(films._tracks(tools, files, dub, frozenset()))
    tracks.extend(scenes.tracks(tools, files, dub, frozenset()))
    tracks = [(film, clips) for film, clips, _ in tracks if any(text not in known[film] for text, _, _ in clips[0])]
    events = {event for _, (_, speech) in tracks for event, _, _ in speech}
    media = endfield_film_voice.recording_ids(tools, stamp, dub, events) if events else {}
    result = {}
    decoder = films.vgmstream_executable()
    if media and decoder is None:
        raise PreparationFailure('missing_tools', 'Prepare the original voice decoder in Setup, then retry Endfield film preparation.')
    with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
        recordings, decoded = {}, {}
        for event, identity in media.items():
            if identity not in decoded:
                try:
                    data = films.release.media(tools, stamp, dub, identity)
                except films.release.UnmatchedRecording:
                    continue
                pcm = stack.enter_context(films._decode(decoder, Path(temporary), identity, data))
                films._check(pcm.getsampwidth() == 2 and pcm.getnframes() > 0 and pcm.getframerate() > 0)
                decoded[identity] = identity, sha256(data).hexdigest(), pcm
            recordings[event] = decoded[identity]
        for film, (captions, speech) in tracks:
            for text, source in _contexts(captions, speech, recordings, known[film]):
                films._check((film, text) not in result)
                result[film, text] = source
    return result


@lru_cache(maxsize=12)
def cues(tools, stamp, dub):
    films.release.descriptor(tools, stamp)
    films._check(dub in films.TRACKS)
    version = 'cinematic-context-v1'
    path = tools / 'endfield-releases' / version / stamp / (dub + '.json')
    prefix = f'{stamp}/{dub}/{version}\n'.encode()
    if path.is_file() and path.stat().st_size <= 32 * 1024**2:
        checksum, _, body = path.read_bytes().partition(b'\n')
        if sha256(prefix + body).hexdigest().encode() == checksum:
            return {(film, text): tuple(source) if source else None for film, text, source in json.loads(body)}
    result = _build(tools, stamp, dub)
    body = json.dumps([[film, text, source] for (film, text), source in sorted(result.items())], separators=(',', ':')).encode()
    _atomic_file(path, sha256(prefix + body).hexdigest().encode() + b'\n' + body)
    return result


def audio(stamp, film, caption, locale, source):
    identity, digest, end_ms = source
    return {'publisher': stamp, 'snapshot': stamp, 'film': film, 'caption': caption,
            'file_id': f'{identity:016x}', 'locale': audio_locale(locale), 'start_ms': 0,
            'end_ms': end_ms, 'recording_sha256': digest, 'context_source': True}


def records(catalog, tables, locale, refs, existing):
    from .endfield_online import LANGUAGES
    rows = []
    for (film, caption), source in catalog.context_cues(LANGUAGES[locale]).items():
        if (film, caption) in existing or caption not in refs:
            continue
        key = str(refs[caption]['id'])
        texts = {code: display_text(values.get(key)) for code, values in tables.items()}
        player = 'female' if film.startswith('f_') else 'male' if film.startswith('m_') else None
        for code, text in texts.items():
            if '{F}' in text or '{M}' in text:
                films._check(player is not None and text.startswith('{F}') and text.count('{F}') == text.count('{M}') == 1)
                texts[code] = text[3:].split('{M}')[player == 'male'].strip()
        texts = {code: value for code, value in texts.items() if value}
        if not texts.get(locale):
            continue
        rows.append({'text_id': f'endfield:film:{film}:{caption}', 'source_locale': locale,
                     'source_text': texts[locale], 'texts': texts, 'english': texts.get('en', ''),
                     'chinese': texts.get('zh-Hans', ''), 'audio_locale': audio_locale(locale),
                     'audio': audio(catalog.revision, film, caption, locale, source) if source else None,
                     'audio_scope': 'context' if source else 'line',
                     'voice_status': 'voiced' if source else 'unknown', 'text_capture_verified': True,
                     'dialogue_kind': 'cinematic', 'channels': ['cinematic'], 'player_voice': player})
    return rows
