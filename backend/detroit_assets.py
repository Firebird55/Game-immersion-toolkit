"""Official Detroit PC text and dependency-bound original Wwise performances."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re
import struct

from . import detroit_format as fmt
from .languages import resolve_locale
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'it', 'de', 'es-ES', 'ar', 'ja', 'pl', 'pt-PT', 'pt-BR', 'es-419', 'ru')
TEXT_LOCALES = dict(zip(
    ('fr', 'en', 'de', 'it', 'es-ES', 'nl', 'pt-PT', 'sv', 'da', 'no', 'fi', 'ru', 'pl',
     'ja', 'ko', 'zh-Hant', 'el', 'cs', 'hu', 'es-419', 'pt-BR', 'tr', 'ar', 'zh-Hans'),
    ('FRE', 'ENG', 'GER', 'ITA', 'SPA', 'DUT', 'POR', 'SWE', 'DAN', 'NOR', 'FIN', 'RUS', 'POL',
     'JPN', 'KOR', 'CHI', 'GRE', 'CZE', 'HUN', 'MEX', 'BRA', 'TUR', 'ARA', 'SCH')))
INDEX_NAME = 'BigFile_PC.idx'


def archive_sources(install):
    return sorted(path for path in install.glob('BigFile_PC.*')
                  if path.is_file() and re.fullmatch(r'BigFile_PC\.(?:idx|dat|d\d\d)', path.name))


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
                                  for path in archive_sources(install)).encode()).hexdigest()


def locale_table(tables, locale):
    # Older shipped resources use JAP; final PC resources use JPN. This is an
    # authored locale alias, never a fallback to a different spoken language.
    return tables.get(TEXT_LOCALES[locale], tables.get('JAP', {}) if locale == 'ja' else {})


def clean_text(text):
    return re.sub(r'\s+', ' ', re.sub(r'\{[^}]*\}', '', text)).strip()


def cues(text):
    matches = list(re.finditer(r'\{\*(\d+(?:-\d+)?|TC:\d+\|\d+)\}', text))
    if not matches:
        value = clean_text(text)
        return {'complete': value} if value else {}
    result = {}
    for index, match in enumerate(matches):
        value = clean_text(text[match.end():matches[index+1].start() if index+1 < len(matches) else len(text)])
        if value:
            if match[1] in result:
                # Shipped translations occasionally repeat a cue marker.
                # They can identify only the complete original performance.
                return {'complete': clean_text(text)}
            result[match[1]] = value
    return result


def ocr_pages(text):
    return [value for part in re.split(r'\{\*(?:\d+(?:-\d+)?|TC:\d+\|\d+)\}', text)
            if (value := clean_text(part))]


def cue_times(cue, times, duration):
    if cue.startswith('TC:'):
        start, end = map(int, cue[3:].split('|'))
    elif re.fullmatch(r'\d+(?:-\d+)?', cue):
        first, last = (map(int, cue.split('-')) if '-' in cue else (int(cue), int(cue)))
        if not 1 <= first <= last <= len(times):
            return None
        start, end = round(times[first-1][0] * 1000), round(times[last-1][1] * 1000)
    else:
        return None
    if not 0 <= start < end <= round(duration * 1000):
        return None
    return start, end


def unbound_status(key, paragraph, source):
    state = source.get('binding_states', {}).get(key, 'absent')
    if state not in {'absent', 'none'} or re.search(r'\{(?:S|\*)', paragraph):
        return 'unavailable', 'subtitle'
    flag = source.get('text_flags', {}).get(key)
    if flag == 2 and re.match(r'^X\d{4}[A-Z]_', key):
        return 'unvoiced', 'choice'
    if flag == 1:
        if key.startswith(('THOUGHTS_', 'GUI_ACTION_')):
            return 'unvoiced', 'choice'
        if key.startswith(('GUI_MAGAZINE_', 'GUI_NEWS_', 'GUI_OBSERVATION_', 'MENU_OBSERVATION_')):
            return 'unvoiced', 'readable'
    if re.match(r'^X\d{4}[A-Z]_', key):
        return 'unavailable', 'subtitle'
    return 'unknown', 'unclassified_text'


def bound_sound(entries, reference, key, locale):
    if not reference or reference[0] != 4091:
        return None
    performance = entries.get(tuple(reference))
    if performance is None or not performance.path.is_file():
        return None
    identity = fmt.voice_binding(fmt.component_bytes(performance))
    sound = entries.get((1033, identity))
    if sound is None or not sound.path.is_file():
        return None
    metadata = fmt.sound_metadata(sound)
    if metadata['name'] != key + '_' + TEXT_LOCALES[locale]:
        raise ValueError('Detroit authored voice locale or identity disagrees with its sound data')
    return performance, sound, metadata


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Detroit spoken language')
    try:
        return _index_language(install, data_dir, source_locale, target_locales, progress)
    except PreparationFailure:
        raise
    except (ValueError, struct.error, UnicodeError) as error:
        raise PreparationFailure('unsupported_game_format',
            'Detroit archives or original-voice metadata no longer match this reader. '
            'Finish any game update, verify its files and update the toolkit before retrying.') from error


def _index_language(install, data_dir, source_locale, target_locales, progress):
    stamp = fingerprint(install)
    entries = {(entry.kind, entry.identity): entry for entry in fmt.read_index(install / INDEX_NAME)}
    targets = {target: resolve_locale(target, set(TEXT_LOCALES)) for target in target_locales}
    locales = {source_locale, *(locale for locale in targets.values() if locale)}
    codes = {TEXT_LOCALES[locale] for locale in locales} | ({'JAP'} if 'ja' in locales else set())
    localized = [entry for entry in entries.values() if entry.kind == 1016]
    records, seen, cache, diagnostics = [], {}, {}, Counter()
    for index, entry in enumerate(localized):
        progress(f'Reading Detroit {source_locale} narrative table {index+1}/{len(localized)}')
        tables = fmt.localization(fmt.component_bytes(entry), codes)
        source = locale_table(tables, source_locale)
        for key, paragraph in source.get('texts', {}).items():
            if not clean_text(paragraph):
                diagnostics['empty_localized_records'] += 1
                continue
            reference = source['bindings'].get(key)
            performance = None
            if reference:
                identity = tuple(reference)
                if identity not in cache:
                    cache[identity] = bound_sound(entries, reference, key, source_locale)
                performance = cache[identity]
                if performance and performance[2]['name'] != key + '_' + TEXT_LOCALES[source_locale]:
                    raise ValueError('Conflicting Detroit text and original performance identity')
            translated = {locale: locale_table(tables, locale).get('texts', {}).get(key, '') for locale in locales}
            if not performance:
                status, kind = unbound_status(key, paragraph, source)
                if status == 'unknown':
                    diagnostics['excluded_system_or_unclassified_text'] += 1
                    continue
                parts = {'complete': clean_text(paragraph)}
                texts_by_locale = {locale: {'complete': clean_text(text)} for locale, text in translated.items() if clean_text(text)}
                audio, timings = None, {}
            else:
                voice, sound, metadata = performance
                status, kind = 'voiced', 'ambient' if '_PBY_' in key or '_TV_' in key else 'subtitle'
                parts = cues(paragraph)
                texts_by_locale = {locale: cues(text) for locale, text in translated.items() if text}
                timings = {cue: cue_times(cue, metadata['times'], metadata['duration']) for cue in parts}
                audio = {'index': INDEX_NAME, 'localization': entry.identity, 'key': key,
                         'performance': voice.identity, 'identity': sound.identity, 'locale': source_locale}
                if not parts or any(pair is None for pair in timings.values()):
                    diagnostics['complete_performance_records'] += 1
                    parts = {'complete': clean_text(paragraph)}
                    texts_by_locale = {locale: {'complete': clean_text(text)} for locale, text in translated.items() if clean_text(text)}
                    timings = {}
            for cue, text in parts.items():
                texts = {locale: values[cue] for locale, values in texts_by_locale.items() if cue in values}
                binding = dict(audio) if audio else None
                if binding and cue in timings:
                    binding.update(zip(('start_ms', 'end_ms'), timings[cue]))
                row = {'text_id': f'detroit:{entry.identity}:{key}:{cue}', 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                       'source_locale': source_locale, 'source_text': text, 'texts': texts,
                       'audio_locale': source_locale, 'audio': binding, 'voice_status': status, 'dialogue_kind': kind}
                if binding and not timings:
                    row['ocr_texts'] = {locale: ocr_pages(value) for locale, value in translated.items() if value}
                previous = seen.get(row['text_id'])
                # Some legacy tables reuse a paragraph key with different
                # text; retain its resource identity and OCR ambiguity.
                if previous and previous != row:
                    raise ValueError('Conflicting Detroit narrative identities')
                if not previous:
                    seen[row['text_id']] = row
                    records.append(row)
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'Detroit files changed during preparation. Finish the game update and retry.', game_files_changed=True)
    if not records:
        raise PreparationFailure('missing_voice_pack', f'Install or verify the official Detroit {source_locale} language files through Steam, then retry preparation.')
    counts = Counter(row['voice_status'] for row in records)
    diagnostics['validated_performances'] = sum(bool(value) for value in cache.values())
    warnings = [f"{counts['unavailable']:,} narrative records have no verified installed original performance; they are not classified as unvoiced.",
                'Choices, thought/action prompts, investigation clues and magazine/news text use full-frame capture with the unvoiced option.',
                'Scene writing stored only in textures, bonus-video soundtracks and speech with no authored subtitle are not per-line text/audio coverage.',
                'Repeated short wording can remain ambiguous; complete original performances are used when individual cue timings cannot be established.']
    if not counts['voiced']:
        warnings.insert(0, f'Install or verify the official {source_locale} voice files through Steam; text-only records remain available.')
    return {'format': 2, 'game': 'detroit', 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'reader_revision': LANGUAGE_INDEX_VERSION, 'records': records,
            'diagnostics': dict(diagnostics), 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if locale is None],
            'message': f"{counts['voiced']:,} official {source_locale} subtitles with original audio; {counts['unvoiced']:,} text-only narrative records; {counts['unavailable']:,} unavailable voices"}


def extract_voice(install, audio, _executable, _destination):
    if audio.get('locale') not in SUPPORTED_LOCALES or audio.get('index') != INDEX_NAME:
        raise ValueError('Invalid Detroit original voice reference')
    entries = {(entry.kind, entry.identity): entry for entry in fmt.read_index(install / INDEX_NAME)}
    localization = entries.get((1016, audio.get('localization')))
    if localization is None:
        raise ValueError('Original Detroit localization is no longer installed')
    source = locale_table(fmt.localization(fmt.component_bytes(localization)), audio['locale'])
    reference = source.get('bindings', {}).get(audio.get('key'))
    performance = bound_sound(entries, reference, audio.get('key'), audio['locale'])
    if performance is None or (performance[0].identity, performance[1].identity) != (audio.get('performance'), audio.get('identity')):
        raise ValueError('Original Detroit performance no longer matches its authored binding')
    _, sound, metadata = performance
    return fmt.read_range(sound, metadata['start'], metadata['size'])


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    if not (install / INDEX_NAME).is_file():
        return 'missing'
    try:
        entries = {(entry.kind, entry.identity): entry for entry in fmt.read_index(install / INDEX_NAME)}
        # The first authored dialogue table contains all twelve pack aliases.
        # Never interpret an exhausted bounded sample as a missing locale.
        for entry in [value for value in entries.values() if value.kind == 1016][:128]:
            source = locale_table(fmt.localization(fmt.component_bytes(entry), {TEXT_LOCALES[locale], 'JAP'}), locale)
            for key, reference in source.get('bindings', {}).items():
                if reference and reference[0] == 4091:
                    if bound_sound(entries, reference, key, locale):
                        return 'present'
                    if tuple(reference) in entries:
                        return 'incomplete'
        return 'unknown'
    except (OSError, ValueError, struct.error, UnicodeError):
        return 'unknown'
