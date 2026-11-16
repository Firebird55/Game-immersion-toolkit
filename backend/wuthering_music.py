"""Authored MusicSubtitle rows and complete, original shared-song contexts.

MusicSubtitleManager synchronizes captions to GetSourcePlayPosition. Display
clocks do not establish word cuts. KeepOrigin plus the matching literal Original
in other UI locales identifies the sung language independently of the voice pack.
"""
import json
import math
import re
import sqlite3
import struct
from contextlib import closing

from . import wuthering_assets as assets
from .languages import audio_locale
from .textmaps import display_text

TABLE = 'db_MusicSubTitle.db'
PREFIX = 'wuwa:music:'


def cues(db_root):
    path = db_root / TABLE
    if not path.is_file():
        return []
    result = []
    for identity, group, blob in assets._rows(path, 'SELECT Id, SubtitleGroupTag, BinData FROM musicsubtitle'):
        def number(slot, fmt):
            at = assets._field(blob, slot)
            if at is None:
                return 0
            if at + 4 > len(blob):
                raise ValueError('Incomplete authored music subtitle')
            return struct.unpack_from(fmt, blob, at)[0]
        start, end = number(2, '<f'), number(3, '<f')
        if (type(identity) is not int or identity <= 0 or number(0, '<i') != identity
                or not isinstance(group, str) or not 0 < len(group) <= 512
                or not group.isprintable() or not group.strip()
                or assets._string(blob, 1) != group or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end <= 86400):
            raise ValueError('Unsupported authored music subtitle')
        result.append((identity, group, start, end))
    if len({row[0] for row in result}) != len(result):
        raise ValueError('Duplicate authored music subtitle')
    return result


def callers(db_root):
    result = {}
    def walk(value):
        if isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict) and not value.get('Disabled'):
            if value.get('Name') == 'PostAkEvent':
                config = value.get('Params', {}).get('EventConfig', {})
                if config.get('Type') == 'MusicSubtitle':
                    group, path = config.get('MusicSubtitleGroupTag'), config.get('AkEvent')
                    event = re.fullmatch(r'/Game/Aki/WwiseAudio/Events/([A-Za-z0-9_]{1,256})\.\1', path or '')
                    if isinstance(group, str) and event:
                        result.setdefault(group, set()).add(event[1])
            for child in value.values():
                if isinstance(child, (list, dict)):
                    walk(child)
    for blob, in assets._rows(db_root / 'db_flowState.db', 'SELECT BinData FROM flowstate'):
        walk(json.loads(assets._string(blob, 6)))
    return result


def _texts(db_root, locale, ids):
    """Only exact authored lyric keys; follow the same native shard selector."""
    root = db_root / assets.TEXT_LOCALES[locale]
    table = root / 'lang_multi_text.db'
    if not table.is_file():
        return {}
    keys = [f'LyricsText_{identity}_{suffix}' for identity in ids for suffix in ('Original', 'Translation')]
    found, shard_text = {}, None
    with closing(sqlite3.connect(f'{table.resolve().as_uri()}?mode=ro', uri=True)) as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(MultiText)')}
        if not {'Id', 'Content'} <= columns:
            raise ValueError('Unsupported original lyric localization')
        redirect = 'RedirectDbIndex' if 'RedirectDbIndex' in columns else '0'
        for offset in range(0, len(keys), 500):
            batch = keys[offset:offset + 500]
            for identity, text, shard in connection.execute(
                    f'SELECT Id, Content, {redirect} FROM MultiText WHERE Id IN ({",".join("?" for _ in batch)})', batch):
                if shard not in (0, 1):
                    raise ValueError('Unsupported original lyric shard')
                if shard:
                    if shard_text is None:
                        shard_text = dict(assets._rows(root / 'lang_multi_text_1sthalf.db', 'SELECT Id, Content FROM MultiText'))
                    if identity not in shard_text:
                        raise ValueError('Incomplete original lyric shard')
                    text = shard_text[identity]
                found[identity] = text or ''
    return found


def records(db_root, locale, target_locales, event_sources, shapes):
    authored = cues(db_root)
    if not authored:
        return []
    active = callers(db_root)
    ids = [row[0] for row in authored]
    tables = {language: _texts(db_root, language, ids)
              for language in {*assets.SUPPORTED_LOCALES, locale, *target_locales}}
    groups = {}
    for cue in authored:
        groups.setdefault(cue[1], []).append(cue)
    result = []
    for group, rows in groups.items():
        rows.sort(key=lambda cue: (cue[2], cue[0]))
        # All rows must agree on the same original vocal language. Two Chinese
        # UI scripts share Mandarin; matching either literal script establishes
        # the original language, while each keeps its own official translation.
        owners = set()
        for language in assets.SUPPORTED_LOCALES:
            table = tables[language]
            if all('{KeepOrigin}' in table.get(f'LyricsText_{identity}_Original', '')
                   and (text := display_text(table.get(f'LyricsText_{identity}_Translation', '')))
                   and any(text == display_text(other.get(f'LyricsText_{identity}_Original', ''))
                           for other_language, other in tables.items() if audio_locale(other_language) != audio_locale(language))
                   for identity, _, _, _ in rows):
                owners.add(audio_locale(language))
        events = active.get(group, set())
        event = next(iter(events)) if len(events) == 1 else None
        sources = event_sources.get(event, ())
        source = sources[0] if len(sources) == 1 else None
        shape = shapes.get(source.media_id) if source else None
        playable = (owners == {audio_locale(locale)} and source and not source.authored_mute
                    and source.gender is None and shape and len(shape) == 2
                    and type(shape[0]) is int and shape[0] in (1, 2)
                    and type(shape[1]) is int and 0 < shape[1] <= 48000 * 300
                    and all(end * 48000 <= shape[1] for _, _, _, end in rows))
        previous = None
        for identity, _, start, end in rows:
            key = f'LyricsText_{identity}_Translation'
            texts = {language: display_text(table.get(key, '')) for language, table in tables.items()}
            texts = {language: text for language, text in texts.items() if text and not text.startswith('dnt/')}
            if locale not in texts:
                previous = None
                continue
            row = dict(text_id=f'{PREFIX}{identity}', source_locale=locale, source_text=texts[locale],
                       english=texts.get('en', ''), chinese=texts.get('zh-Hans', ''),
                       texts=texts, audio_locale=audio_locale(locale), dialogue_kind='music_subtitle',
                       channels=['cinematic'], audio=None, voice_status='unavailable',
                       text_capture_verified=bool(events))
            anchors = {}
            for language, table in tables.items():
                origin = table.get(f'LyricsText_{identity}_Original', '')
                if origin and '{KeepOrigin}' not in origin and language in texts:
                    anchors[language] = [display_text(origin) + ' ' + texts[language]]
            if anchors:
                row['ocr_texts'] = anchors
            if previous and previous[1] <= start:
                row['previous_text_id'] = previous[0]
            if playable:
                row.update(audio_scope='context', voice_status='voiced', audio={
                    'depot': f'Client/Content/Aki/WwiseAudio_Generated/Media/{source.media_id}.wem',
                    'locale': audio_locale(locale), 'scene_context': True, 'music_context': True,
                    'scene': group, 'event': event, 'source_clock': 'play_position',
                    'source_frames': shape[1], 'source_channels': shape[0]})
            result.append(row)
            previous = row['text_id'], end
    return result
