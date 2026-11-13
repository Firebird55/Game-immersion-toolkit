"""Range-addressed original audio for the audited Global Windows release."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import struct
import urllib.request

from . import endfield_cinematic_profile as profile
from . import endfield_global_cue_context as context
from . import endfield_metadata, endfield_vfs
from .game_tools import _atomic_file
from .languages import audio_locale
from .preparation_errors import PreparationFailure
from .textmaps import display_text
from .voice_assets import voice_hash

RELEASE = 'global-1.6.4-11529267-11'
TEXT_REVISION = 'd847759f71d4549aba4727b3b0ac1a1ad0e37742'
CDN = 'https://beyond.hg-cdn.com/YDUTE5gscDZ229CW/1.6/resource/Windows/main/11529267-11_hMnwm6yYFPbPuRKr/files/'
DUBS = ('chinese', 'english', 'japanese', 'korean')
LANGUAGES = {'zh-Hans': 'chinese', 'zh-Hant': 'chinese', 'en': 'english', 'ja': 'japanese', 'ko': 'korean'}


def _invalid():
    raise ValueError('Endfield original voice does not match the verified publisher release.')


def _read_range(path, total, offset, length):
    if not 0 < length <= endfield_vfs.MAX_VOICE or not 0 <= offset <= total - length:
        _invalid()
    end = offset + length - 1
    request = urllib.request.Request(CDN + path, headers={
        'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=35) as response:
        if (response.status != 206 or response.geturl() != request.full_url
                or response.headers.get('Content-Range') != f'bytes {offset}-{end}/{total}'):
            _invalid()
        data = response.read(length + 1)
    if len(data) != length:
        _invalid()
    return data


def _verified(path, limit, digest, fetch):
    if path.is_file() and path.stat().st_size <= limit:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == digest:
            return data
    data = fetch()
    if len(data) > limit or hashlib.sha256(data).hexdigest() != digest:
        _invalid()
    _atomic_file(path, data)
    return data


class _PackageSource:
    def __init__(self, tools, spec):
        self.path, self.total, self.base, self.size, length, digest = spec
        self.header = _verified(tools / 'endfield-publisher' / 'headers' / digest, length, digest,
                                lambda: _read_range(self.path, self.total, self.base, length))

    def read(self, offset, length):
        if not 0 <= offset <= self.size - length or length < 0:
            _invalid()
        if offset + length <= len(self.header):
            return self.header[offset:offset + length]
        return _read_range(self.path, self.total, self.base + offset, length)


@lru_cache(maxsize=8)
def _inventory(tools, dub):
    params = endfield_metadata.parameters(tools)
    entries, ambiguous = {}, set()
    for spec in profile.PACKAGES[dub]:
        package = endfield_vfs.Package(_PackageSource(tools, spec), params)
        for entry in package.entries:
            if entry.identity in entries:
                ambiguous.add(entry.identity)
            else:
                entries[entry.identity] = (package, entry)
    for identity in ambiguous:
        entries.pop(identity)
    return entries


def voice_entries(tools, locale):
    return {f'{key:016x}': {'publisher': RELEASE, 'file_id': f'{key:016x}'}
            for key in _inventory(tools, LANGUAGES[locale])}


def _film_audio(film, caption, locale):
    dub = DUBS.index(LANGUAGES[locale])
    recording = profile.FILMS[film][dub]
    extra = context.EXTRA.get((film, ('cn', 'en', 'jp', 'ko')[dub], caption))
    start, end = extra[1:3] if extra else profile.CUES[film, caption][2 * dub:2 * dub + 2]
    if recording is None or start is None or end is None:
        _invalid()
    media, _digest = recording
    return {'publisher': RELEASE, 'film': film, 'caption': caption,
            'file_id': f'{media:016x}', 'locale': audio_locale(locale), 'start_ms': start, 'end_ms': end}


def film_records(catalog, tables, locale):
    live = {}
    if catalog.revision == TEXT_REVISION:
        accepted = profile.FILMS
    elif hasattr(catalog, 'verified_films'):
        accepted = catalog.verified_films(LANGUAGES[locale])
        if hasattr(catalog, 'updated_cues'):
            live = catalog.updated_cues(LANGUAGES[locale])
    else:
        return []
    if not accepted and not live:
        return []
    refs = catalog.file('TableCfg/TextTable.json')
    rows = []
    dub = DUBS.index(LANGUAGES[locale])
    track = ('cn', 'en', 'jp', 'ko')[dub]
    cues = {(film, caption): (caption, False) for (film, caption), clocks in profile.CUES.items()
            if film in accepted and clocks[2 * dub] is not None}
    cues.update({(film, identity): (caption, conditional)
                 for (film, language, identity), (caption, _, _, conditional) in context.EXTRA.items()
                 if language == track and film in accepted})
    cues.update({key: (entry[0], entry[4]) for key, entry in live.items()})
    for (film, caption), (text_ref, conditional) in cues.items():
        reference = refs.get(text_ref)
        if not isinstance(reference, dict) or reference.get('id') is None:
            continue
        key = str(reference['id'])
        texts = {code: display_text(values.get(key)) for code, values in tables.items()}
        if not all(texts.values()):
            continue
        entry = live.get((film, caption))
        if entry:
            audio = _updated_audio(film, caption, locale, entry, catalog.revision)
            anchor = entry[3]
        else:
            audio = _film_audio(film, caption, locale)
            anchor = context.PREVIOUS.get((film, track, caption)) or profile.SCENE_PREVIOUS.get((film, caption))
        rows.append({'text_id': f'endfield:film:{film}:{caption}', 'source_locale': locale,
                     'previous_text_id': f'endfield:film:{film}:{anchor}' if anchor else None,
                     'requires_previous': conditional,
                     'source_text': texts[locale], 'texts': texts, 'english': texts.get('en', ''),
                     'chinese': texts.get('zh-Hans', ''), 'audio_locale': audio_locale(locale),
                     'audio': audio, 'voice_status': 'voiced',
                     'dialogue_kind': 'cinematic', 'channels': ['cinematic'],
                     'player_voice': 'female' if film.startswith('f_') else 'male' if film.startswith('m_') else None})
    return rows


def _updated_audio(film, caption, locale, entry, stamp):
    _, start, end, _, _, media, digest = entry
    return {'publisher': stamp, 'film': film, 'caption': caption, 'file_id': f'{media:016x}',
            'locale': audio_locale(locale), 'start_ms': start, 'end_ms': end, 'snapshot': stamp,
            'recording_sha256': digest}


def extract(audio, tools):
    locale = audio['locale']
    if locale not in LANGUAGES:
        _invalid()
    dub = LANGUAGES[locale]
    if 'recording_sha256' in audio:
        from . import endfield_film_update, endfield_release
        stamp = audio.get('snapshot')
        if audio.get('publisher') != stamp:
            _invalid()
        film, caption = audio['film'], audio['caption']
        entry = endfield_film_update.cues(tools, stamp, dub).get((film, caption))
        if not entry or audio != _updated_audio(film, caption, locale, entry, stamp):
            _invalid()
        return endfield_release.media(tools, stamp, dub, entry[5], entry[6])
    if audio.get('publisher') != RELEASE:
        _invalid()
    if 'film' in audio:
        film, caption = audio['film'], audio['caption']
        track = ('cn', 'en', 'jp', 'ko')[DUBS.index(dub)]
        if ((film, caption) not in profile.CUES and (film, track, caption) not in context.EXTRA
                or {key: value for key, value in audio.items() if key != 'snapshot'} != _film_audio(film, caption, locale)):
            _invalid()
        identity, digest = profile.FILMS[film][DUBS.index(dub)]
        if 'snapshot' in audio:
            from . import endfield_release
            if film not in endfield_release.verified_films(tools, audio['snapshot'], dub):
                _invalid()
            return endfield_release.media(tools, audio['snapshot'], dub, identity, digest)
    else:
        source = audio.get('source', '')
        if not source.startswith('voice/' + dub + '/') or not source.endswith('.wem'):
            _invalid()
        identity, digest = voice_hash(source), None
        if audio.get('file_id') != f'{identity:016x}':
            _invalid()

    def download():
        match = _inventory(tools, dub).get(identity)
        if not match:
            _invalid()
        package, entry = match
        data = package.voice(entry)
        if len(data) != struct.unpack_from('<I', data, 4)[0] + 8:
            _invalid()
        return data

    try:
        if digest:
            return _verified(tools / 'endfield-publisher' / 'speech' / digest,
                             endfield_vfs.MAX_VOICE, digest, download)
        return download()
    except OSError as error:
        raise PreparationFailure('publisher_unavailable',
            'The Endfield publisher recording is unavailable. Check the connection and retry.') from error
