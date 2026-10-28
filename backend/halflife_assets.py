"""Original Half-Life (Steam 70), with explicit limits on uncaptioned speech.

GoldSrc sentence filenames are never promoted to official dialogue text.
This reader supports authored screen messages and inventories original speech;
the latter remains unavailable for text capture without an official text bind.
"""
from collections import Counter, defaultdict
import hashlib
from pathlib import Path

from .goldsrc_formats import GoldSrcFiles, single_sample, sentences, titles
from .preparation_errors import PreparationFailure
from .source_formats import invalid, safe_name
from .textmaps import display_text

GAME = 'halflife'
LANGUAGE_INDEX_VERSION = 1
TEXT_LOCALES = {'en': 'english', 'fr': 'french', 'de': 'german', 'it': 'italian',
               'es-ES': 'spanish', 'zh-Hans': 'schinese', 'zh-Hant': 'tchinese', 'ko': 'koreana'}
SUPPORTED_LOCALES = tuple(TEXT_LOCALES)
VOICE_LOCALES = TEXT_LOCALES
CAPTURE_CAPABILITIES = {'voiced': False, 'unvoiced': True,
    'reason': 'Original Half-Life has no official spoken subtitle track. Verified speech bindings and audio-based capture are not implemented.'}


def mount(locale):
    return 'valve' if locale == 'en' else 'valve_' + TEXT_LOCALES[locale]


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for candidate in candidates:
        path = Path(candidate)
        if (path / 'hl.exe').is_file() and (path / 'valve/liblist.gam').is_file():
            return path
    return None


def archive_sources(install):
    install = Path(install)
    result = []
    for locale in SUPPORTED_LOCALES:
        files = GoldSrcFiles(install, mount(locale))
        result.extend(archive.path for archive in files.archives)
        for name in ('titles.txt', 'sound/sentences.txt', 'liblist.gam'):
            if path := files.loose(name):
                result.append(path)
        for directory, suffix in [('maps', '.bsp'), ('sound', '.wav')]:
            result.extend(path for name in files.names(directory, suffix) if (path := files.loose(name)))
    return sorted(set(result))


def fingerprint(install):
    install = Path(install).resolve()
    return hashlib.sha256('|'.join(f'{path.relative_to(install).as_posix()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        for path in archive_sources(install)).encode()).hexdigest()


def probe_voice_pack(install, locale):
    """Cheap presence probe, deliberately independent of transcript readiness."""
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        files = GoldSrcFiles(install, mount(locale))
        if not files.root.is_dir():
            return 'missing'
        # These are stable base-game speech families. Never inspect English
        # when probing a different official language mount.
        present = False
        for family in ('scientist', 'barney', 'holo', 'gman'):
            path = next((files.root / 'sound' / family).glob('*.wav'), None)
            if path and files.loose(path.relative_to(files.root).as_posix()) and path.stat().st_size:
                present = True
                break
        present |= any(name.startswith(('sound/scientist/', 'sound/barney/', 'sound/holo/', 'sound/gman/'))
                       and name.endswith('.wav') and archive.entries[name][1] > 0
                       for name, archive in files.entries.items())
        return 'present' if present else 'incomplete'
    except (OSError, ValueError):
        return 'incomplete'


def _tables(install, locales):
    result = {}
    for locale in locales:
        files = GoldSrcFiles(install, mount(locale))
        if files.has('titles.txt'):
            result[locale] = titles(files.read('titles.txt', 16 * 1024 * 1024), locale)
    return result


def _row(identity, texts, source, kind, state):
    pages = {locale: list(dict.fromkeys(display_text(line) for line in value.splitlines() if display_text(line)))
             for locale, value in texts.items()}
    texts = {locale: display_text(value) for locale, value in texts.items()}
    return {'text_id': GAME + ':' + identity, 'english': texts.get('en', ''), 'chinese': '',
            'source_locale': source, 'source_text': texts[source], 'texts': texts, 'audio_locale': source,
            'audio': None, 'voice_status': state, 'dialogue_kind': kind,
            'ocr_texts': pages, 'ocr_english': pages.get('en')}


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported original Half-Life study/audio locale')
    install = Path(install)
    if not discover_install([install]):
        raise invalid('Choose the original Half-Life folder containing hl.exe and valve/liblist.gam.')
    files = GoldSrcFiles(install, mount(source_locale))
    if not files.has('titles.txt'):
        raise PreparationFailure('halflife_language_pack_missing',
            'The selected original Half-Life language pack is missing. Choose this language in Steam game Properties, '
            'wait for its download, then prepare again. English files are never used as a substitute.')
    stamp = fingerprint(install)
    progress('Reading original Half-Life screen messages and speech inventory')
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, 'en', *(locale for locale in targets.values() if locale)}
    tables = _tables(install, selected)
    table = tables[source_locale]
    base = GoldSrcFiles(install, 'valve')
    counts, kinds, title_uses, inline = Counter(), Counter(), defaultdict(list), []
    maps = sorted(set(base.names('maps', '.bsp')) | set(files.names('maps', '.bsp')))
    for number, name in enumerate(maps):
        if number % 20 == 0:
            progress(f'Reading Half-Life map message bindings ({number}/{len(maps)})')
        own_map = files.has(name)
        source = files if own_map else base
        entities = source.map_entities(name, source_locale if own_map else 'en')
        counts['maps'] += 1
        for ordinal, entity in enumerate(entities):
            category = entity.get('classname', '').casefold()
            kinds[category] += 1
            if category == 'env_message' and entity.get('message'):
                key = entity['message'].casefold()
                title_uses[key].append(entity)
                if key not in table:
                    counts['screen_messages_without_selected_text'] += 1
            elif category == 'game_text' and entity.get('message'):
                # Common map prose is authored English; do not relabel it as
                # another language merely because a dub overlay is selected.
                if not own_map:
                    counts['inline_messages_without_selected_locale'] += 1
                    continue
                identity = f'map:{name}:{ordinal}'
                inline.append(_row(identity, {source_locale: entity['message']}, source_locale, 'screen_message', 'unvoiced'))
            elif category == 'worldspawn' and entity.get('chaptertitle'):
                title_uses[entity['chaptertitle'].casefold()].append(entity)
    records = list(inline)
    for key, entry in table.items():
        if not entry['text']:
            continue
        uses = title_uses.get(key, [])
        # env_message explicitly has an optional messagesound. Any authored
        # sound keeps this text unknown; the filename is not speech evidence.
        state = 'unvoiced' if uses and all(not item.get('messagesound') for item in uses) else 'unknown'
        raw = {locale: rows[key]['text'] for locale, rows in tables.items() if key in rows and rows[key]['text']}
        records.append(_row('title:' + key, raw, source_locale,
                            'screen_message' if uses else 'title_localization', state))
    definitions = sentences(files.read('sound/sentences.txt')) if files.has('sound/sentences.txt') else []
    # Localized packs sometimes omit definitions and rely on common control
    # data. Inventory that fallback as metadata only, never local text/audio.
    if not definitions and source_locale != 'en' and base.has('sound/sentences.txt'):
        definitions = sentences(base.read('sound/sentences.txt'))
        counts['common_sentence_control_table'] = 1
    samples = files.names('sound', '.wav')
    counts['original_wav_files'] = len(samples)
    counts['sentence_definitions'] = len(definitions)
    counts['repeated_sentence_identifiers'] = len(definitions) - len({name for name, _sequence in definitions})
    for _name, sequence in definitions:
        sample = single_sample(sequence)
        counts['single_sample_sentences' if sample else 'assembled_or_parameterized_sentences'] += 1
        if sample and not files.has(sample):
            counts['single_sample_sentences_without_selected_recording'] += 1
    counts['scripted_sentence_entities'] = kinds['scripted_sentence']
    counts['scripted_sequence_entities'] = kinds['scripted_sequence'] + kinds['aiscripted_sequence']
    counts['ambient_sound_entities'] = kinds['ambient_generic']
    counts['announcement_entities'] = kinds['speaker']
    counts['scientist_entities'] = kinds['monster_scientist'] + kinds['monster_sitting_scientist']
    counts['security_guard_entities'] = kinds['monster_barney']
    counts['soldier_entities'] = kinds['monster_human_grunt']
    counts['gman_entities'] = kinds['monster_gman']
    counts['screen_message_entities'] = kinds['env_message'] + kinds['game_text']
    counts['title_entries'] = len(table)
    counts['speech_entries_with_verified_authored_text'] = 0
    if fingerprint(install) != stamp:
        raise PreparationFailure('halflife_files_changed',
            'Half-Life files changed during preparation. Wait for Steam to finish, then retry.',
            game_files_changed=True, previous_snapshot_retained=True)
    voices = Counter(row['voice_status'] for row in records)
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': records,
        'missing_translation_locales': [target for target, locale in targets.items() if not locale or locale not in tables],
        'voice_pack_state': probe_voice_pack(install, source_locale),
        'capture_capabilities': {**CAPTURE_CAPABILITIES, 'unvoiced': bool(voices['unvoiced'])},
        'narrative_inventory': {**counts, 'voice_counts': dict(voices),
            'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in records))},
        'coverage_warnings': [
            'Original Half-Life (Steam 70) has no official spoken subtitle track. Speech capture is not ready; WAV inventory alone cannot provide official dialogue text.',
            'Enable Include unvoiced dialogue for confirmed sound-free screen messages. Their positions vary, so use full-window text capture; ordinary conversations, barks, announcements and scripted speech remain unsupported.',
            'Sentence definitions contain sample names and pitch, trim and timing controls. These are not transcripts; no filename, speech-recognition result or inferred translation is treated as official text.',
            'Unreferenced titles and messages with attached sound remain unknown. World textures, signs, credits rendered from textures and any unresolved title/script bindings are outside confirmed coverage.',
            'All eight official voice languages use independent original-game mounts. Missing localized text or recordings never borrow English. Only installed English files received native validation; other languages have schema and encoding tests.',
            'Half-Life: Source is a separate edition. Its shared Half-Life 2 captions provide a partial HEV-suit research lead, but complete assembly timing and original-game audio capture remain unimplemented. No Source edition audio or text is silently substituted.',
            'Chinese and Korean authored titles can be decoded, but known game-side rendering issues may prevent usable on-screen OCR. No installed-game files are modified.'],
        'message': f"{voices['unvoiced']:,} confirmed unvoiced screen messages; spoken-dialogue capture is not ready (no official subtitle bindings)."}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', ['zh-Hans'], progress)


def extract_voice(install, audio, _executable, _destination):
    """Only exact original samples; no speech rows currently claim a text bind."""
    locale = audio.get('locale')
    member = safe_name(audio.get('member'))
    if locale not in SUPPORTED_LOCALES or not member.startswith('sound/') or not member.endswith('.wav'):
        raise invalid('Invalid original Half-Life voice reference.')
    data = GoldSrcFiles(install, mount(locale)).read(member)
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE' or hashlib.sha256(data).hexdigest() != audio.get('sha256'):
        raise invalid('Original Half-Life sample changed; prepare the language again.')
    return data
