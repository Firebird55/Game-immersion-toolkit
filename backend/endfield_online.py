"""Range-addressed original audio for the audited Global Windows release."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import struct
import urllib.request

from . import endfield_global_1_6 as profile
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
    start, end = profile.CUES[film, caption][2 * dub:2 * dub + 2]
    if recording is None or start is None or end is None:
        _invalid()
    media, _digest = recording
    return {'publisher': RELEASE, 'film': film, 'caption': caption,
            'file_id': f'{media:016x}', 'locale': audio_locale(locale), 'start_ms': start, 'end_ms': end}


def film_records(catalog, tables, locale):
    if catalog.revision != TEXT_REVISION:
        return []
    refs = catalog.file('TableCfg/TextTable.json')
    rows = []
    dub = DUBS.index(LANGUAGES[locale])
    for (film, caption), clocks in profile.CUES.items():
        if clocks[2 * dub] is None:
            continue
        key = str(refs[caption]['id'])
        texts = {code: display_text(values[key]) for code, values in tables.items()}
        if not all(texts.values()):
            raise ValueError('Endfield cinematic localization is incomplete.')
        rows.append({'text_id': f'endfield:film:{film}:{caption}', 'source_locale': locale,
                     'source_text': texts[locale], 'texts': texts, 'english': texts.get('en', ''),
                     'chinese': texts.get('zh-Hans', ''), 'audio_locale': audio_locale(locale),
                     'audio': _film_audio(film, caption, locale), 'voice_status': 'voiced',
                     'dialogue_kind': 'cinematic', 'channels': ['cinematic'],
                     'player_voice': 'female' if film.startswith('f_') else 'male' if film.startswith('m_') else None})
    return rows


def extract(audio, tools):
    locale = audio['locale']
    if audio.get('publisher') != RELEASE or locale not in LANGUAGES:
        _invalid()
    dub = LANGUAGES[locale]
    if 'film' in audio:
        film, caption = audio['film'], audio['caption']
        if (film, caption) not in profile.CUES or audio != _film_audio(film, caption, locale):
            _invalid()
        identity, digest = profile.FILMS[film][DUBS.index(dub)]
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
