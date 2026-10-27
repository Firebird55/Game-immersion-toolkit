"""Official HEAVY RAIN text and its typed, original-language performances."""
from __future__ import annotations

import hashlib
import re
import subprocess
import struct
from pathlib import Path

from . import quantic_assets as q, quantic_legacy as legacy
from .languages import GAME_LOCALES, resolve_locale
from .media_tools import ffmpeg_executable
from .quantic_audio import decode_blocks
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = GAME_LOCALES['heavyrain']
TEXT_LOCALES = dict(zip(('fr', 'en', 'de', 'it', 'es-ES', 'nl', 'pt-PT', 'sv', 'da', 'no', 'fi', 'ru', 'pl', 'ja', 'ko', 'zh-Hant', 'zh-Hans'),
                       ('FRA', 'ENG', 'GER', 'ITA', 'SPA', 'HOL', 'POR', 'SWE', 'DAN', 'NOR', 'FIN', 'RUS', 'POL', 'JAP', 'KOR', 'CHI', 'SCH')))
LANGUAGE_IDS = {code: number for number, code in enumerate(TEXT_LOCALES.values())}
SCENE_INDEXES = ('Resources/BigFile_WIN.idx', 'Resources/GameData/GameData_WIN.idx')
VOICE_INDEXES = ('Resources/LanguageData/O-LanguageData_WIN.idx', 'Resources/LanguageData/LanguageData_WIN.idx')


def archive_sources(install):
    indexes = sorted((install / 'Resources').rglob('*.idx'))
    sources = {path for index in indexes for path in index.parent.glob(index.stem + '.*')
               if path.is_file() and re.fullmatch(r'\.(?:idx|dat|d\d\d)', path.suffix, re.I)}
    sources.update(path for name in SCENE_INDEXES if (path := (install / name).with_suffix('.pdbg')).is_file())
    return sorted(sources)


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{path.relative_to(install).as_posix()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
                                   for path in archive_sources(install)).encode()).hexdigest()


def pages(text):
    # These are authored page separators, not inferred sentence boundaries.
    return [value for part in text.split('{B}')
            if (value := re.sub(r'\s+', ' ', part.replace('{S}', '')).strip())]


def _voice_bytes(entries):
    data = None
    for entry in entries:
        if entry.size > q.METADATA_LIMIT:
            raise ValueError('HEAVY RAIN original performance exceeds the bounded reader limit')
        current = entry.read()
        if data is not None and data != current:
            raise ValueError('Conflicting HEAVY RAIN original performances in installed banks')
        data = current
    return data


def localization_names(install):
    """Read optional authored names for presentation labels, never audio joins."""
    result = {}
    for relative in SCENE_INDEXES:
        path = (install / relative).with_suffix('.pdbg')
        if not path.is_file():
            continue
        if path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError('HEAVY RAIN presentation-name table exceeds the bounded reader limit')
        with path.open('rb') as stream:
            def read(size):
                value = stream.read(size)
                if len(value) != size:
                    raise ValueError('Incomplete HEAVY RAIN presentation-name table')
                return value
            if read(20) != b'QUANTICDREAMTABINDEX' or struct.unpack('>I', read(4))[0] != 13:
                raise ValueError('Unsupported HEAVY RAIN presentation-name table')
            count = struct.unpack('>I', read(4))[0]
            if count > 1000000:
                raise ValueError('Invalid HEAVY RAIN presentation-name count')
            for _ in range(count):
                kind, version, identity, length = struct.unpack('>4I', read(16))
                if version != 1 or length > 1024:
                    raise ValueError('Unsupported HEAVY RAIN presentation-name entry')
                name = read(length).decode('ascii').rstrip('\0')
                read(24)
                if kind == 1016:
                    if identity in result and result[identity] != name:
                        raise ValueError('Conflicting HEAVY RAIN localization names')
                    result[identity] = name
            if stream.read(1):
                raise ValueError('Unsupported trailing HEAVY RAIN presentation names')
    return result


def index_language(install, _data_dir, source_locale, target_locales, progress=lambda _: None):
    try:
        return _index_language(install, source_locale, target_locales, progress)
    except PreparationFailure:
        raise
    except ValueError as error:
        raise PreparationFailure('unsupported_game_format',
            f'HEAVY RAIN game data could not be read: {error}. Update the toolkit and verify game files, then retry.') from error


def _index_language(install, source_locale, target_locales, progress):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported HEAVY RAIN study/audio language')
    stamp = fingerprint(install)
    unknown = {path.relative_to(install).as_posix() for path in (install / 'Resources').rglob('*.idx')} - set(SCENE_INDEXES + VOICE_INDEXES)
    if unknown:
        raise ValueError('Unrecognized HEAVY RAIN archives; installed patch priority needs verification')
    code, language_id = TEXT_LOCALES[source_locale], LANGUAGE_IDS[TEXT_LOCALES[source_locale]]
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    voices, containers = {}, {}
    for name in VOICE_INDEXES:
        if (install / name).is_file():
            for entry in q.read_index(install / name):
                if entry.kind == 4091:
                    voices.setdefault(entry.identity, []).append(entry)
    names_unreadable = False
    try:
        names = localization_names(install)
    except (OSError, ValueError):
        # Optional labels must not disable otherwise verified text/audio.
        names, names_unreadable = {}, True
    # The story archive extends the startup archive. Reused localization and
    # timing identities must still agree, and duplicate voice banks are checked.
    for name in SCENE_INDEXES:
        if (install / name).is_file():
            for entry in q.read_index(install / name):
                if entry.kind == 29:
                    containers.setdefault(entry.identity, []).append(entry)
    localizations, offsets, authored, diagnostics = {}, {}, set(), {}
    for number, candidates in enumerate(containers.values()):
        reader = legacy.Metadata(candidates[-1])
        refs, _ = legacy.references(reader)
        authored.update(identity for kind, identity, language in refs if kind == 4091 and language == language_id)
        if not any(kind == 1016 for kind, _, _ in refs):
            continue
        progress(f'Reading HEAVY RAIN {source_locale} dialogue container {number + 1}/{len(containers)}')
        for kind, identity, _, body in legacy.components(reader, {1016, 4092}):
            destination = offsets if kind == 4092 else localizations
            value = body if kind == 4092 else legacy.localization(body, {TEXT_LOCALES[locale] for locale in selected})
            if identity in destination and destination[identity] != value:
                raise ValueError('Conflicting HEAVY RAIN authored localization or audio timings')
            destination[identity] = value
    records, parsed = [], {}
    for localization_id, tables in localizations.items():
        source = tables.get(code, {})
        for key, text in source.get('texts', {}).items():
            source_pages = pages(text)
            reference = source.get('bindings', {}).get(key)
            if not source_pages:
                continue
            anchors = {locale: values for locale in selected
                       if (values := pages(tables.get(TEXT_LOCALES[locale], {}).get('texts', {}).get(key, '')))}
            texts = {locale: ' '.join(values) for locale, values in anchors.items()}
            silent = (source.get('text_flags', {}).get(key) == 2
                      and source.get('binding_states', {}).get(key) == 'none')
            row = {'text_id': f'heavyrain:{localization_id}:{key:08x}',
                'source_locale': source_locale, 'source_text': ' '.join(source_pages),
                'audio_locale': source_locale, 'texts': texts, 'ocr_texts': anchors,
                'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''), 'audio': None,
                'dialogue_kind': 'choice' if silent else 'thought' if '_THOUGHTS_' in names.get(localization_id, '') else 'conversation',
                'voice_status': 'unvoiced' if silent else 'unavailable' if reference or source.get('binding_states', {}).get(key) == 'unresolved' else 'unknown'}
            records.append(row)
            if not reference or reference[0] != 4091:
                continue
            identity = reference[1]
            if identity not in authored or identity not in voices:
                diagnostics['missing_original_performances'] = diagnostics.get('missing_original_performances', 0) + 1
                continue
            if identity not in parsed:
                raw = _voice_bytes(voices[identity])
                offset_id, times, _ = legacy.partition(raw)
                offset_table = offsets.get(offset_id)
                if offset_table is None:
                    raise ValueError('HEAVY RAIN original voice has no authored chunk table')
                blocks = legacy.partition_blocks(raw, offset_table)
                start, end = round(min(start for start, _ in times) * 1000), round(max(end for _, end in times) * 1000)
                if not 0 <= start < end <= len(blocks) * 1000:
                    raise ValueError('HEAVY RAIN authored subtitle timing exceeds its performance')
                parsed[identity] = (offset_id, offset_table, start, end)
            offset_id, offset_table, start, end = parsed[identity]
            voice = voices[identity][-1]
            row.update(voice_status='voiced', audio={'index': voice.index.relative_to(install).as_posix(), 'identity': identity,
                          'locale': source_locale, 'language_id': language_id, 'offset_id': offset_id,
                          'offsets': offset_table.hex(), 'start_ms': start, 'end_ms': end})
    if not records:
        raise ValueError(f'No official {source_locale} HEAVY RAIN dialogue is installed')
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'HEAVY RAIN files changed during preparation; wait for the game update to finish, then retry.', game_files_changed=True)
    voiced = sum(row['voice_status'] == 'voiced' for row in records)
    unvoiced = sum(row['voice_status'] == 'unvoiced' for row in records)
    warnings = ['Choices and thought prompts are text-only labels; their spoken responses are separate original performances.',
                'Books, newspapers and other image-only props have no verified independent text/voice schema. Global menus and chapter labels are excluded.',
                'Standalone Bink movies have not been joined to locale-specific subtitle cues; in-engine authored dialogue is indexed.']
    missing = sum(row['voice_status'] == 'unavailable' for row in records)
    if missing:
        warnings.append(f'{missing:,} authored {source_locale} voices are unavailable in the installed data; they are not treated as silent dialogue.')
    if names_unreadable:
        warnings.append('The optional presentation-name table has an unsupported format; thought labels are unavailable. Update the toolkit; verified subtitle and voice bindings remain usable.')
    elif not names:
        warnings.append('Optional presentation names are absent; thoughts and conversations cannot be inventoried separately.')
    return {'format': 2, 'game': 'heavyrain', 'source_locale': source_locale,
            'reader_revision': LANGUAGE_INDEX_VERSION, 'install': str(install), 'fingerprint': stamp,
            'records': records, 'diagnostics': diagnostics, 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if locale is None],
            'message': f'{len(records):,} official {source_locale} entries; {voiced:,} original voices; {unvoiced:,} unvoiced prompts'}


def extract_voice(install, audio, _executable, destination):
    locale, name, identity = audio.get('locale'), audio.get('index'), audio.get('identity')
    if (locale not in SUPPORTED_LOCALES or name not in VOICE_INDEXES or type(identity) is not int
            or audio.get('language_id') != LANGUAGE_IDS[TEXT_LOCALES[locale]]):
        raise ValueError('Invalid HEAVY RAIN original voice reference or locale')
    entry = next((entry for entry in q.read_index(install / name) if entry.kind == 4091 and entry.identity == identity), None)
    if entry is None:
        raise ValueError('Original HEAVY RAIN performance is no longer installed')
    raw = _voice_bytes([entry])
    if legacy.partition(raw)[0] != audio.get('offset_id'):
        raise ValueError('HEAVY RAIN original voice offset reference changed')
    encoded = audio.get('offsets', '')
    if not isinstance(encoded, str) or len(encoded) > 2 * (20 + 86400 * 8):
        raise ValueError('Invalid HEAVY RAIN authored offset table')
    blocks = legacy.partition_blocks(raw, bytes.fromhex(encoded))
    return decode_blocks(blocks, destination, executable=ffmpeg_executable(), decode=subprocess.run)
