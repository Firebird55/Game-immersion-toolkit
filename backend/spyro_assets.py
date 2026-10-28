"""Spyro Reignited Trilogy: authored dialogue, cinematic pages and Wwise voices."""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
from pathlib import Path
import struct

from .preparation_errors import PreparationFailure
from .spyro_unreal import Cursor, Package, PakSet, invalid, read_locres
from .textmaps import display_text

GAME = 'spyro'
LANGUAGE_INDEX_VERSION = 1
# The public study locale stays Norwegian (no); Unreal uses nb and Wwise no.
# pt is the game's Brazilian Portuguese pack, and latam is Latin American Spanish.
TEXT_LOCALES = {'en': 'en-US', 'fr': 'fr', 'it': 'it', 'de': 'de', 'es-ES': 'es',
    'ar': 'ar', 'da': 'da', 'nl': 'nl', 'fi': 'fi', 'no': 'nb', 'pl': 'pl',
    'pt-BR': 'pt', 'es-419': 'es-419', 'sv': 'sv'}
VOICE_LOCALES = {**TEXT_LOCALES, 'en': 'English(US)', 'no': 'no', 'es-419': 'latam'}
SUPPORTED_LOCALES = tuple(TEXT_LOCALES)
_SOUND = 'Falcon/Plugins/Sound/Content/'
_WWISE = 'Falcon/Content/WwiseAudio/Windows/'


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for candidate in candidates:
        path = Path(candidate)
        if (path / 'Spyro.exe').is_file() and (path / 'Falcon/Content/Paks/pakchunk0-WindowsNoEditor.pak').is_file():
            return path
    return None


def fingerprint(install):
    paths = sorted((install / 'Falcon/Content/Paks').glob('pakchunk*.pak'))
    return hashlib.sha256('|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in paths).encode()).hexdigest()


def wwise_hash(value):
    result = 2166136261
    for byte in value.lower().encode('utf-8'):
        result = ((result * 16777619) & 0xFFFFFFFF) ^ byte
    return result


def read_bank(data, language):
    """Wwise 128 event → one Play action → one localized Vorbis source.

    Embedded and streamed media share the same authored source IDs. Random,
    switch and multiple-action events are counted but never guessed.
    """
    cursor = Cursor(data)
    objects, media, chunks = {}, {}, {}
    while cursor.pos < len(data):
        kind, size = cursor.unpack('4sI')
        start = cursor.pos
        body = cursor.take(size)
        if kind in chunks:
            raise invalid('Duplicate Spyro sound-bank chunk.')
        chunks[kind] = (start, body)
    header = chunks.get(b'BKHD', (0, b''))[1]
    if len(header) < 12 or struct.unpack_from('<I', header)[0] != 128 or struct.unpack_from('<I', header, 8)[0] != wwise_hash(language):
        raise invalid('Spyro voice bank does not match the selected language.')
    hierarchy = Cursor(chunks.get(b'HIRC', (0, b''))[1])
    for _ in range(hierarchy.count()):
        kind, size = hierarchy.unpack('BI')
        payload = hierarchy.take(size)
        if len(payload) < 4:
            raise invalid()
        identity = struct.unpack_from('<I', payload)[0]
        if identity in objects:
            raise invalid('Duplicate Spyro sound-bank object.')
        objects[identity] = kind, payload
    if hierarchy.pos != len(hierarchy.data):
        raise invalid()
    index = chunks.get(b'DIDX', (0, b''))[1]
    start, body = chunks.get(b'DATA', (0, b''))
    if len(index) % 12:
        raise invalid()
    for identity, offset, size in struct.iter_unpack('<III', index):
        if identity in media or not size or offset + size > len(body):
            raise invalid('Spyro embedded voice exceeds bank bounds.')
        media[identity] = (start + offset, size)
    events, unresolved = {}, set()
    for identity, (kind, payload) in objects.items():
        if kind != 4:
            continue
        unresolved.add(identity)
        if len(payload) != 9 or payload[4] != 1:
            continue
        action_kind, action = objects.get(struct.unpack_from('<I', payload, 5)[0], (0, b''))
        if action_kind != 3 or len(action) < 10 or action[4:6] != b'\x03\x04':
            continue
        sound_kind, sound = objects.get(struct.unpack_from('<I', action, 6)[0], (0, b''))
        # 0x40001 is the shipped Vorbis codec; bit 0 establishes localization.
        if sound_kind != 2 or len(sound) < 18 or struct.unpack_from('<I', sound, 4)[0] != 0x40001 or not sound[17] & 1:
            continue
        source = struct.unpack_from('<I', sound, 9)[0]
        # A prefetched bank fragment must not be mistaken for the complete
        # performance. The shipped packs use only resident (0) or stream (2).
        if sound[8] not in (0, 2) or (sound[8] == 0) != (source in media):
            continue
        events[identity] = source
        unresolved.remove(identity)
    return events, media, unresolved


def _banks(archives, locale):
    prefix = _WWISE + VOICE_LOCALES[locale] + '/'
    bindings = defaultdict(list)
    unresolved = set()
    count = 0
    for path in sorted(archives.entries):
        if not path.startswith(prefix) or not path.endswith('.bnk'):
            continue
        events, embedded, failed = read_bank(archives.read(path), VOICE_LOCALES[locale])
        count += 1
        unresolved.update(failed)
        for event, media in events.items():
            media_path = prefix + str(media) + '.wem'
            available = media in embedded or media_path in archives.entries
            bindings[event].append({'bank': path, 'event': event, 'media': media,
                'locale': locale, 'embedded': media in embedded, 'available': available})
    # Identical copies are harmless; conflicting media require an authored
    # context the reader does not have, so they remain unavailable.
    return {event: refs[0] for event, refs in bindings.items()
            if len({ref['media'] for ref in refs}) == 1}, unresolved, count


@lru_cache(maxsize=2)
def _present_packs(install, _stamp):
    archives = PakSet(Path(install))
    return frozenset(locale for locale, native in VOICE_LOCALES.items() if any(
        path.startswith(_WWISE + native + '/') and path.endswith('.bnk') for path in archives.entries))


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        return 'present' if locale in _present_packs(str(install), fingerprint(install)) else 'missing'
    except (OSError, ValueError):
        return 'incomplete'


def _clean(value):
    return display_text(value.replace('{N}', ' ').replace('\n', ' '))


def _localized(text, tables):
    if not text:
        return {}
    namespace, key, source = text
    native = tables.get('en', {}).get((namespace, key))
    result = {}
    for locale, table in tables.items():
        value = table.get((namespace, key))
        if value and (not native or value[0] == native[0]):
            result[locale] = value[1]
        elif locale == 'en' and source:
            result[locale] = source
    return result


def _table_path(virtual):
    if not virtual.startswith('/Sound/'):
        raise invalid('Unsupported Spyro subtitle table reference.')
    return _SOUND + virtual[len('/Sound/'):] + '.uasset'


def _subtitle_field(row, prefix):
    values = [value for key, value in row.items() if key.startswith(prefix + '_')]
    if len(values) != 1:
        raise invalid('Unsupported Spyro cinematic subtitle row.')
    return values[0]


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Spyro study/audio locale')
    stamp = fingerprint(install)
    archives = PakSet(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    voice_tables, menu_tables = {}, {}
    for locale in selected:
        for collection, tables in [('VoiceLocalizations', voice_tables), ('MenuLocalizations', menu_tables)]:
            path = f'Falcon/Content/Localization/{collection}/{TEXT_LOCALES[locale]}/{collection}.locres'
            if path in archives.entries:
                tables[locale] = read_locres(archives.read(path, 16 * 1024 * 1024))
    if source_locale not in voice_tables:
        raise PreparationFailure('spyro_missing_pack',
            'The selected Spyro localization is missing. Select the language in Steam Properties → Language, finish its download, and verify game files.')
    progress(f'Reading Spyro {source_locale} original voice banks')
    bindings, unresolved, bank_count = _banks(archives, source_locale)
    dialogue, subtitles, counts = {}, defaultdict(list), Counter()
    for path in sorted(archives.entries):
        if not path.endswith('.uasset') or not (path.startswith(_SOUND + 'VO_Spyro') and '/Levels/' not in path or path.startswith(_SOUND + 'Subtitles/')):
            continue
        package = Package(archives.read(path, 4 * 1024 * 1024))
        if len(package.exports) != 1 or package.exports[0][0] != 'DataTable':
            continue
        kind, rows = package.table(archives.read(path[:-7] + '.uexp', 16 * 1024 * 1024))
        if kind == 'TfbDialogueTableRow':
            counts['dialogue_tables'] += 1
            for identity, row in rows.items():
                dialogue[path, identity] = row
        elif kind == 'tfbSubtitleDataTableRow':
            counts['cinematic_subtitle_tables'] += 1
            for row in rows.values():
                target = _table_path(package.import_path(_subtitle_field(row, 'tfbDialogueDataTable')))
                identity = _subtitle_field(row, 'RowName')
                split = _subtitle_field(row, 'SplitIndex')
                if type(split) is not int or split < 0:
                    raise invalid()
                subtitles[target, identity].append(split)
                counts['cinematic_subtitle_pages'] += 1
        else:
            raise invalid('Unsupported Spyro dialogue table type.')
    records, matched_events = [], set()
    for (path, identity), row in dialogue.items():
        raw = _localized(row.get('Text'), voice_tables)
        texts = {locale: _clean(value) for locale, value in raw.items()}
        if not texts.get(source_locale):
            counts['dialogue_rows_without_selected_text'] += 1
            continue
        voiced_line = row.get('VoicedLine')
        if not isinstance(voiced_line, tuple) or len(voiced_line) != 2:
            raise invalid('Missing Spyro authored voice field.')
        event_name = voiced_line[0].rsplit('.', 1)[-1] if voiced_line[0] != 'None' else identity
        event = wwise_hash(event_name)
        ref = bindings.get(event)
        audio = None
        if ref:
            matched_events.add(event)
            if ref['available']:
                audio = {key: value for key, value in ref.items() if key != 'available'}
        # tx_ is the shipped text-only row family, always with an explicit null
        # VoicedLine. Null vo_ rows are cinematic events, not silent dialogue.
        state = ('voiced' if audio else 'unavailable' if ref or event in unresolved or identity.startswith('vo_') or voiced_line[0] != 'None'
                 else 'unvoiced' if identity.startswith('tx_') and voiced_line == ('None', '') else 'unknown')
        cinematic = bool(row.get('IsSubtitle')) or (path, identity) in subtitles
        pages = {}
        for locale, value in raw.items():
            splits = value.split('{N}')
            # Retain every authored page, including ordinary dialogue pages.
            # Cinematic SplitIndex addresses the same localized line pages.
            pages[locale] = list(dict.fromkeys(_clean(part) for part in splits if _clean(part)))
        speakers = _localized(row.get('DisplayName'), voice_tables)
        category = 'cinematic' if cinematic else 'dialogue'
        records.append({'text_id': f'{GAME}:dialogue:{identity}', 'english': texts.get('en', ''),
            'chinese': '', 'source_locale': source_locale, 'source_text': texts[source_locale],
            'texts': texts, 'audio_locale': source_locale, 'audio': audio, 'voice_status': state,
            'speaker_english': _clean(speakers['en']) if speakers.get('en') else None,
            'dialogue_kind': category, 'ocr_texts': pages, 'ocr_english': pages.get('en')})
        counts['spyro_' + path.split('VO_Spyro')[1][0] + '_rows'] += 1
    if len({record['text_id'] for record in records}) != len(records):
        raise invalid('Ambiguous Spyro dialogue identity.')
    counts['unresolved_cinematic_row_references'] = sum(key not in dialogue for key in subtitles)
    counts['voice_banks'] = bank_count
    counts['voice_events'] = len(bindings)
    counts['voice_events_without_dialogue_text'] = len(set(bindings) - matched_events)
    counts['unsupported_voice_events'] = len(unresolved)
    # Menu/epilogue localization has no explicit silence evidence in locres.
    # Keep it separate from the authored text-only dialogue family.
    for (namespace, key), (_hash, text) in menu_tables.get(source_locale, {}).items():
        texts = {locale: _clean(table[namespace, key][1]) for locale, table in menu_tables.items()
                 if (namespace, key) in table and table[namespace, key][0] == _hash}
        if not texts.get(source_locale):
            continue
        identity = hashlib.sha256((namespace + '\0' + key).encode()).hexdigest()[:24]
        records.append({'text_id': f'{GAME}:local:{identity}', 'english': texts.get('en', ''),
            'chinese': '', 'source_locale': source_locale, 'source_text': texts[source_locale],
            'texts': texts, 'audio_locale': source_locale, 'audio': None, 'voice_status': 'unknown',
            'dialogue_kind': 'ui_localization'})
    if fingerprint(install) != stamp:
        raise PreparationFailure('spyro_files_changed', 'Spyro game files changed during preparation. Wait for Steam to finish and retry.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    warnings = ['Cinematic subtitle pages match the complete authored voice event; scene timeline times are not audio-file cut points.',
        'Localized speech events with no authored dialogue text are inventoried but cannot be matched from OCR. Nonverbal sound effects are outside the transcript.',
        'Menu and epilogue localization remains unknown voice status. Explicit tx_ dialogue rows with null VoicedLine are text-only; missing vo_ audio is unavailable.']
    if not bank_count:
        warnings.append('The selected voice pack is missing. Select the language in Steam Properties → Language, finish the download, and verify game files.')
    if counts['unresolved_cinematic_row_references']:
        warnings.append('Some cinematic subtitle references could not be resolved; verify game files and refresh the index.')
    unavailable = sum(record['voice_status'] == 'unavailable' for record in records)
    if unavailable and bank_count:
        warnings.append(f'{unavailable:,} authored voice events have no complete recording binding in the selected installed pack. They remain audio unavailable; verify game files to rule out an incomplete download.')
    voiced = sum(record['audio'] is not None for record in records)
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': records, 'narrative_inventory': dict(counts),
        'coverage_warnings': warnings,
        'missing_translation_locales': [target for target, locale in targets.items() if not any(locale in row['texts'] for row in records)],
        'message': f'{len(records):,} official {source_locale} entries; {voiced:,} original voices'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, _destination):
    locale = audio.get('locale')
    if locale not in VOICE_LOCALES or type(audio.get('event')) is not int or type(audio.get('media')) is not int:
        raise invalid('Invalid Spyro original voice reference.')
    prefix = _WWISE + VOICE_LOCALES[locale] + '/'
    bank = audio.get('bank')
    if not isinstance(bank, str) or not bank.startswith(prefix) or '/' in bank[len(prefix):] or not bank.endswith('.bnk'):
        raise invalid('Invalid Spyro voice-bank locale.')
    archives = PakSet(install)
    data = archives.read(bank)
    events, embedded, _unresolved = read_bank(data, VOICE_LOCALES[locale])
    media = events.get(audio['event'])
    if media != audio['media'] or audio.get('embedded') is not (media in embedded):
        raise invalid('Spyro original voice binding changed; refresh game data.')
    if media in embedded:
        start, size = embedded[media]
        result = data[start:start + size]
    else:
        result = archives.read(prefix + str(media) + '.wem')
    if len(result) < 12 or result[:4] != b'RIFF' or result[8:12] != b'WAVE':
        raise invalid('Unsupported Spyro original voice media.')
    return result
