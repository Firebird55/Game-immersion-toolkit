"""Original SQLite/FlatBuffer text and dub bindings without desktop discovery.

Inputs must already belong to the caller's verified original table/index set.
Parsing records never authenticates a publisher source or materializes audio.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct

from .preparation_errors import PreparationFailure
from .text_display import display_text
from .wuthering_locales import SUPPORTED_LOCALES, VOICE_LOCALES, TEXT_LOCALES


MUSIC_SUBTITLE_TABLE = 'db_MusicSubTitle.db'


EXTERNAL_ROOT = "Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/"


FLOATING_SUBTITLES = 'db_FloatingSubtitle.db'


NARRATIVE_TABLES = ('db_flowState.db', 'db_cgVedio.db', 'db_infodisplay.db', FLOATING_SUBTITLES)


def _field(blob: bytes, slot: int) -> int | None:
    if len(blob) < 8 or slot < 0:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata is truncated or uses an unsupported format.')
    table = struct.unpack_from("<I", blob)[0]
    if table < 4 or table + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid table offset.')
    vtable = table - struct.unpack_from("<i", blob, table)[0]
    if vtable < 4 or vtable + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid field table.')
    size, object_size = struct.unpack_from('<HH', blob, vtable)
    if size < 4 or size % 2 or vtable + size > len(blob) or object_size < 4 or table + object_size > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has invalid table bounds.')
    offset = 4 + slot * 2
    if offset >= size:
        return None
    relative = struct.unpack_from("<H", blob, vtable + offset)[0]
    if relative and not 4 <= relative < object_size:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata has an invalid field offset.')
    return table + relative if relative else None


def _string(blob: bytes, slot: int) -> str:
    offset = _field(blob, slot)
    if offset is None:
        return ""
    if offset + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains a truncated string reference.')
    position = offset + struct.unpack_from("<I", blob, offset)[0]
    if position <= offset or position + 4 > len(blob):
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains an invalid string reference.')
    size = struct.unpack_from("<I", blob, position)[0]
    if size > len(blob) - position - 4:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains a truncated string.')
    try:
        return blob[position + 4:position + 4 + size].decode("utf-8")
    except UnicodeDecodeError:
        raise PreparationFailure('unsupported_format', 'Wuthering dialogue metadata contains invalid text encoding.') from None


def _boolean(blob: bytes, slot: int) -> bool:
    offset = _field(blob, slot)
    return bool(blob[offset]) if offset is not None else False


def _rows(path: Path, query: str) -> list:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        return connection.execute(query).fetchall()


def _text_table(db_root: Path, locale: str) -> dict:
    directory = db_root / TEXT_LOCALES[locale]
    path = directory / 'lang_multi_text.db'
    columns = {row[1] for row in _rows(path, 'PRAGMA table_info(MultiText)')}
    if not {'Id', 'Content'} <= columns:
        raise PreparationFailure('unsupported_format', 'Wuthering localization table schema changed; update the toolkit.')
    rows = _rows(path, 'SELECT Id, Content' + (', RedirectDbIndex' if 'RedirectDbIndex' in columns else ', 0') + ' FROM MultiText')
    redirects = {index for _, _, index in rows if index}
    if redirects - {1}:
        raise PreparationFailure('unsupported_format', 'Wuthering localization uses an unsupported text shard; update the toolkit.')
    shard = {}
    if redirects:
        if not (directory / 'lang_multi_text_1sthalf.db').is_file():
            raise PreparationFailure('incomplete_game_data', 'Wuthering localization text shard is missing; verify game files and retry.')
        shard = dict(_rows(directory / 'lang_multi_text_1sthalf.db', 'SELECT Id, Content FROM MultiText'))
        if any(identity not in shard for identity, _, index in rows if index):
            raise PreparationFailure('incomplete_game_data', 'Wuthering redirected localization entries are incomplete; verify game files and retry.')
    # Base Content can be a placeholder even when nonempty. Only the authored
    # RedirectDbIndex selects the shard; never borrow another locale's text.
    return {identity: (shard[identity] if index else content) or '' for identity, content, index in rows}


def _narrative_refs(db_root: Path) -> dict[str, list[tuple[str, str]]]:
    refs = {}
    def add(identity, kind, status):
        if isinstance(identity, str) and identity:
            value = (kind, status)
            if value not in refs.setdefault(identity, []):
                refs[identity].append(value)
    def walk(value, mode=None):
        if isinstance(value, list):
            # Flow mode persists through sequential actions and their options.
            for item in value:
                if isinstance(item, dict) and item.get('Disabled'):
                    continue
                if isinstance(item, dict) and item.get('Name') == 'SetPlotMode':
                    mode = item.get('Params', {}).get('Mode', mode)
                walk(item, mode)
        elif isinstance(value, dict):
            if value.get('Disabled'):
                return
            if value.get('Name') == 'ShowCenterText':
                add(value.get('Params', {}).get('TidCenterText'), 'story_card', 'unknown')
            if 'TidTalkOption' in value:
                add(value['TidTalkOption'], 'choice', 'unvoiced')
            if 'TidTalk' in value:
                kind = value.get('Type', 'Talk')
                message_type = value.get('MessageType', {}).get('Type')
                audio_event = value.get('TalkAkEvent') or value.get('TalkEndAkEvent') or value.get('UniversalTone')
                status = 'unavailable' if value.get('PlayVoice') or audio_event else 'unknown'
                if value.get('PlayVoice') is False and not audio_event:
                    status = 'unvoiced'
                category = 'dialogue'
                if kind == 'PhoneMessage':
                    if message_type in {'Emoji', 'Attachment'}:
                        category = None
                    elif message_type == 'Voice':
                        category, status = 'message', 'unavailable'
                    elif message_type == 'SystemTip':
                        category = 'message'
                        if status == 'unknown':
                            status = 'unvoiced'
                    else:
                        category = None
                elif kind in {'Option', 'SystemOption'}:
                    category = 'choice'
                    if status == 'unknown':
                        status = 'unvoiced'
                elif mode == 'PhoneMessage' and kind == 'Talk':
                    category = 'message'
                    if status == 'unknown':
                        status = 'unvoiced'
                elif kind in {'CenterText', 'AvgCenterText', 'AvgNarration'}:
                    category = 'story_card'
                elif kind in {'NoTextItem', 'QTE'}:
                    category = None
                elif mode == 'Prompt':
                    category = 'ambient'
                if category:
                    add(value['TidTalk'], category, status)
            for child in value.values():
                if isinstance(child, (list, dict)):
                    walk(child, mode)
    path = db_root / 'db_flowState.db'
    if path.is_file():
        for identity, blob in _rows(path, 'SELECT StateKey, BinData FROM flowstate'):
            if _string(blob, 0) != identity:
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow identities do not match their metadata.')
            try:
                actions = json.loads(_string(blob, 6))
            except (ValueError, TypeError):
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow actions use an unsupported format.') from None
            if not isinstance(actions, list):
                raise PreparationFailure('unsupported_format', 'Wuthering story-flow actions use an unsupported container.')
            walk(actions)
    path = db_root / 'db_cgVedio.db'
    if path.is_file():
        for blob, in _rows(path, 'SELECT BinData FROM videocaption'):
            # IsPlaySubtitleVoice false does not mean silent: speech may be
            # embedded in the video. Never substitute the whole movie track.
            add(_string(blob, 4), 'cinematic', 'unavailable')
    path = db_root / 'db_infodisplay.db'
    if path.is_file():
        for blob, in _rows(path, 'SELECT BinData FROM infodisplay'):
            add(_string(blob, 4), 'readable', 'unavailable' if _string(blob, 6) else 'unknown')
    path = db_root / FLOATING_SUBTITLES
    if path.is_file():
        for blob, in _rows(path, 'SELECT BinData FROM floatingsubtitle2d'):
            add(_string(blob, 2), 'floating_caption', 'unknown')
        for blob, in _rows(path, 'SELECT BinData FROM floatingsubtitle3d'):
            # A named 3D audio cue alone does not identify an exact localized WEM.
            add(_string(blob, 1), 'floating_caption', 'unavailable' if _string(blob, 16) else 'unknown')
    return refs


def build_records(db_root: Path, files: list[str]) -> list[dict]:
    return [row for row in build_language_records(db_root, files, 'zh-Hans', ['en']) if row['english']]


def build_language_records(db_root: Path, files: list[str], source_locale: str, target_locales) -> list[dict]:
    from .languages import audio_locale
    if not (db_root / TEXT_LOCALES[source_locale] / 'lang_multi_text.db').is_file():
        raise ValueError('Install the selected official Wuthering text pack before preparing it.')
    tables = {locale: _text_table(db_root, locale) for locale in {source_locale, *target_locales}}
    if not any(display_text(text) for text in tables[source_locale].values()):
        raise ValueError('The selected official Wuthering text pack is empty; no other language was substituted.')
    sources = {path.casefold(): path for path in files if path.startswith(EXTERNAL_ROOT) and path.endswith('.wem')}
    code, gender_slot = VOICE_LOCALES[source_locale]
    records = []
    narrative = _narrative_refs(db_root)
    emitted = set()
    def text_fields(identity):
        texts = {locale: value for locale, table in tables.items() if (value := display_text(table.get(identity, '')))}
        return {'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                'source_text': texts.get(source_locale, ''), 'source_locale': source_locale,
                'texts': texts, 'audio_locale': audio_locale(source_locale)}
    def category(identity):
        kinds = {kind for kind, _ in narrative.get(identity, [])}
        return next((kind for kind in ('cinematic', 'story_card', 'message', 'readable', 'ambient', 'choice', 'dialogue', 'floating_caption') if kind in kinds), 'dialogue')
    for identity, blob in _rows(db_root / 'db_plot_audio.db', 'SELECT Id, BinData FROM plotaudio'):
        text = display_text(tables[source_locale].get(identity, ''))
        if not text or _string(blob, 0) != identity:
            continue
        fields = text_fields(identity)
        emitted.add(identity)
        filename = _string(blob, 2)
        for variant in (['female', 'male'] if _boolean(blob, gender_slot) else [None]):
            suffix = '_F' if variant == 'female' else '_M' if variant else ''
            resource = EXTERNAL_ROOT + code + '_' + filename + suffix + '.wem'
            mapped = sources.get(resource.casefold()) if not _boolean(blob, 3) and '{' not in filename else None
            records.append({'text_id': f'wuwa:{identity}' + (f':{variant}' if variant else ''), **fields,
                'audio': {'depot': mapped, 'locale': audio_locale(source_locale)} if mapped else None, 'player_voice': variant,
                'voice_status': 'voiced' if mapped else 'unavailable', 'dialogue_kind': category(identity)})
    for identity, evidence in narrative.items():
        if identity in emitted:
            continue
        fields = text_fields(identity)
        if not fields['source_text']:
            continue
        statuses = {status for _, status in evidence}
        # Any voiced or unresolved context prevents calling a shared ID silent.
        status = 'unavailable' if 'unavailable' in statuses else 'unknown' if 'unknown' in statuses else 'unvoiced'
        records.append({'text_id': f'wuwa:{identity}', **fields, 'audio': None,
                        'voice_status': status, 'dialogue_kind': category(identity)})
    return records


def required_tables(locales):
    """The same native table selection for ordinary and context-owned plans."""
    names = {'db_plot_audio.db', MUSIC_SUBTITLE_TABLE, *NARRATIVE_TABLES}
    for locale in locales:
        code = TEXT_LOCALES[locale]
        names.update((code + '/lang_multi_text.db', code + '/lang_multi_text_1sthalf.db'))
    return names
