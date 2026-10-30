"""Portal (Steam 400): official Source captions and original voice bindings."""
from collections import Counter
from functools import lru_cache
import hashlib
from pathlib import Path
import re

from .preparation_errors import PreparationFailure
from .source_formats import invalid, keyvalues
from .source_dialogue import (SourceFiles, caption_pages, captions, clean_caption,
    decode_performance, mapping, pack_performance, reference_signature,
    resolve_sequence, sound_events, steam_language, text_table)
from .source_scene import caption_sequences, scene_image

GAME = 'portal'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'de', 'ru', 'es-ES', 'zh-Hant')
TEXT_LOCALES = dict(zip(
    ('en', 'fr', 'de', 'ru', 'da', 'nl', 'fi', 'it', 'ja', 'no', 'pl', 'pt-PT',
     'zh-Hans', 'es-ES', 'sv', 'zh-Hant', 'ko', 'bg', 'cs', 'el', 'hu', 'pt-BR',
     'ro', 'es-419', 'th', 'tr', 'uk'),
    ('english', 'french', 'german', 'russian', 'danish', 'dutch', 'finnish', 'italian',
     'japanese', 'norwegian', 'polish', 'portuguese', 'schinese', 'spanish', 'swedish',
     'tchinese', 'koreana', 'bulgarian', 'czech', 'greek', 'hungarian', 'brazilian',
     'romanian', 'latam', 'thai', 'turkish', 'ukrainian')))


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for value in candidates:
        path = Path(value)
        if (path / 'hl2.exe').is_file() and (path / 'portal/gameinfo.txt').is_file() and (path / 'portal/portal_pak_dir.vpk').is_file():
            return path
    return None


def archive_sources(install):
    install = Path(install)
    result = set()
    for directory, stems in [('portal', ('portal_pak', 'portal_sound_vo_')), ('hl2', ('hl2_misc', 'hl2_sound_misc'))]:
        root = install / directory
        for path in root.glob('*.vpk'):
            if path.name.startswith(stems) and path.is_file():
                result.add(path)
    root = install / 'portal'
    for pattern in ('resource/closecaption_*.txt', 'resource/closecaption_*.dat', 'resource/portal_*.txt', 'scripts/*.txt', 'scenes/*.image'):
        result.update(path for path in root.glob(pattern) if path.is_file())
    result.update(path for path in (install / 'hl2/scripts').glob('*.txt') if path.is_file())
    if (root / 'gameinfo.txt').is_file():
        result.add(root / 'gameinfo.txt')
    manifest = install.parent.parent / 'appmanifest_400.acf'
    if manifest.is_file():
        result.add(manifest)
    return sorted(result)


def fingerprint(install):
    install = Path(install)
    return hashlib.sha256('|'.join(f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
                                  for path in archive_sources(install)).encode()).hexdigest()


def _files(install):
    return SourceFiles(install, ['portal/portal_pak_dir.vpk', 'hl2/hl2_misc_dir.vpk'], ['portal', 'hl2'])


def _voices(install, locale):
    native = TEXT_LOCALES[locale]
    archives = [f'portal/portal_sound_vo_{native}_dir.vpk']
    # Portal's shared pak contains English recordings. A selected language in
    # Steam is not evidence that these shared files were dubbed. A localized
    # request can use only its independently identified voice archive.
    if locale == 'en' and steam_language(install, 400) == 'english':
        archives.append('portal/portal_pak_dir.vpk')
    return SourceFiles(install, archives)


@lru_cache(maxsize=6)
def _probe(install, locale, _stamp):
    voices = _voices(Path(install), locale)
    sample = next((name for name in voices.entries if name.startswith('sound/vo/aperture_ai/') and name.endswith('.wav')), None)
    if sample is None:
        return 'missing'
    return 'present' if _binding('probe', ((sample, 0),), voices, locale) else 'incomplete'


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        return _probe(str(install), locale, fingerprint(install))
    except (OSError, ValueError):
        return 'incomplete'


def _binding(token, sequence, voices, locale):
    if not sequence or len(sequence) > 64:
        return None
    parts = []
    for member, at_ms in sequence:
        ref = voices.locate(member)
        if not ref:
            return None
        # Missing numbered VPK chunks are incomplete packs, not silent lines.
        archive = next((item for item in voices.archives if item.path == voices.install / ref['archive']), None)
        entry = archive.entries[member] if archive else None
        if entry is None:
            return None
        if entry.length and entry.archive != 0x7FFF:
            chunk = archive.path.with_name(archive.path.name[:-8] + f'_{entry.archive:03d}.vpk')
            if not chunk.is_file() or chunk.stat().st_size < entry.offset + entry.length:
                return None
        parts.append({'member': member, 'at_ms': at_ms, **ref})
    result = {'token': token, 'locale': locale, 'parts': parts}
    if token == 'portal.song_credits':
        result['playback_scope'] = 'full_track'
    result['binding_hash'] = reference_signature(result)
    return result


def _nonverbal(raw):
    clean = clean_caption(raw)
    return '<sfx>' in raw.casefold() or bool(re.fullmatch(r'(?:\[[^\]]+\]|\*[^*]+\*)', clean))


def _credits(files):
    if not files.locate('scripts/credits.txt'):
        return [], []
    groups = mapping(mapping(keyvalues(files.read('scripts/credits.txt'))).get('credits.txt', []))
    tokens, prose = [], []
    for value, _font in groups.get('outrosonglyrics', []):
        match = re.fullmatch(r'\[\d+(?:\.\d+)?\](.*)', value, re.S)
        if not match:
            raise invalid('Unsupported Portal credits timeline.')
        value = re.sub(r'<<<\d+>>>', '', match[1]).lstrip('*').strip()
        if value.startswith('#'):
            tokens.append(value[1:].casefold())
        elif value and value not in {'&', '^', '...', 'PS:', 'PPS:', 'PPPS:'}:
            prose.append(value)
    return list(dict.fromkeys(tokens)), list(dict.fromkeys(prose))


def _row(identity, texts, locale, audio, kind, status=None, pages=None):
    return {'text_id': f'{GAME}:{identity}', 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', ''), 'source_locale': locale,
            'source_text': texts[locale], 'texts': texts, 'audio_locale': locale,
            'audio': audio, 'voice_status': status or ('voiced' if audio else 'unavailable'),
            'dialogue_kind': kind, 'ocr_texts': pages or {key: [value] for key, value in texts.items()}}


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Portal spoken language')
    install = Path(install)
    stamp = fingerprint(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    files, voices = _files(install), _voices(install, source_locale)
    tables, ui = {}, {}
    for locale in sorted(selected):
        native = TEXT_LOCALES[locale]
        if files.locate(f'resource/closecaption_{native}.txt') and files.locate(f'resource/closecaption_{native}.dat'):
            tables[locale] = captions(files, native)
        if files.locate(f'resource/portal_{native}.txt'):
            ui[locale] = text_table(files.read(f'resource/portal_{native}.txt'), native)
    if source_locale not in tables:
        raise PreparationFailure('missing_voice_pack', 'Portal text resources are missing. Select the official language in Steam Properties → Language, finish the download and verify game files.')
    progress(f'Reading Portal {source_locale} captions and original scene bindings')
    events, missing_scripts = sound_events(files)
    scenes = scene_image(files.read('scenes/scenes.image')) if files.locate('scenes/scenes.image') else {}
    sequences = caption_sequences(scenes)
    records, diagnostics, matched = [], Counter(), set()
    diagnostics.update({'sound_events': len(events), 'scenes': len(scenes), 'missing_sound_scripts': len(missing_scripts),
                        'caption_tokens': len(tables[source_locale])})
    for token, raw in tables[source_locale].items():
        if _nonverbal(raw):
            diagnostics['excluded_sound_effect_captions'] += 1
            continue
        texts = {locale: clean_caption(table[token]) for locale, table in tables.items()
                 if token in table and clean_caption(table[token])}
        if source_locale not in texts:
            continue
        sequence = resolve_sequence(token, events, sequences)
        audio = _binding(token, sequence, voices, source_locale)
        matched.update(member for member, _time in sequence)
        kind = 'commentary' if token.startswith('#commentary') else 'ambient' if token.startswith('npc_floorturret.') else 'subtitle'
        records.append(_row('caption:' + token, texts, source_locale, audio, kind,
                            pages={locale: caption_pages(table[token]) for locale, table in tables.items() if token in table}))
        if not sequence:
            diagnostics['unresolved_caption_bindings'] += 1
        elif len(sequence) > 1:
            diagnostics['timed_composite_captions'] += 1
    lyric_tokens, prose = _credits(files)
    if lyric_tokens:
        # Keep authored localized fragments separate: the current lyric must
        # not reveal the rest of the song or prevent the next fragment appearing.
        # Translated lyrics are not evidence of an original dubbed performance.
        sequence = resolve_sequence('portal.song_credits', events, sequences) if source_locale == 'en' else ()
        audio = _binding('portal.song_credits', sequence, voices, source_locale)
        for token in lyric_tokens:
            texts = {locale: table[token].strip() for locale, table in ui.items() if table.get(token, '').strip()}
            if source_locale in texts:
                records.append(_row('credits:song:' + token, texts, source_locale, audio, 'song_full_track'))
                diagnostics['credits_lyric_pages'] += 1
    # The authored report/letter headings are literal English terminal text,
    # distinct from the localized lyric tokens. Do not relabel them by UI locale.
    if source_locale == 'en':
        for number, text in enumerate(prose):
            records.append(_row(f'credits:report:{number}', {'en': text}, source_locale, None, 'readable', 'unvoiced'))
    diagnostics['credits_report_texts'] = len(prose)
    diagnostics['voices_without_resolved_caption'] = sum(member.startswith(('sound/vo/', 'sound/npc/turret_floor/', 'sound/commentary/'))
        and member.endswith(('.wav', '.mp3')) and member not in matched for member in voices.entries)
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'Portal files changed during preparation. Finish the Steam update and retry.', game_files_changed=True)
    counts = Counter(record['voice_status'] for record in records)
    warnings = [
        'Randomized turret captions and obsolete captions without unique authored sound bindings remain unavailable; they are not silent dialogue.',
        'Developer commentary is indexed from caption filenames. A translated commentary subtitle never licenses borrowing an English recording for another study language.',
        'Credit lyric pages match the complete original English song; display/typewriter timings are not asserted as per-line recording cut points.',
        'Credit report headings are confirmed text-only English readables. Use full-frame capture; bottom-only subtitle calibration misses the terminal and commentary panel.',
        'Wall graffiti, signs and in-world writing stored in textures, startup movies and unsubtitled radio/speech have no native text/audio binding in this reader.',
        'Custom VPKs, loose audio overrides and mods are outside the official-resource reader.']
    if not counts['voiced']:
        warnings.insert(0, f'Install the official Portal {source_locale} voice pack in Steam Properties → Language, finish the download and verify files. English shared recordings are never substituted. For a moved English install, use Steam to verify the folder so its completed language manifest is available.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'reader_revision': LANGUAGE_INDEX_VERSION, 'records': records,
            'diagnostics': dict(diagnostics), 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if locale not in tables],
            'message': f"{counts['voiced']:,} official {source_locale} entries with original audio; {counts['unvoiced']:,} text-only readables; {counts['unavailable']:,} unavailable voices"}


def index_install(install, data_dir, progress=lambda _: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, _destination):
    locale, token = audio.get('locale'), audio.get('token')
    if locale not in SUPPORTED_LOCALES or not isinstance(token, str):
        raise invalid('Invalid Portal original voice reference.')
    files, voices = _files(install), _voices(install, locale)
    events, _missing = sound_events(files)
    scenes = scene_image(files.read('scenes/scenes.image')) if files.locate('scenes/scenes.image') else {}
    sequence = resolve_sequence(token, events, caption_sequences(scenes))
    if token == 'portal.song_credits' and locale != 'en':
        raise invalid('Portal credit song has no verified selected-language dub.')
    expected = _binding(token, sequence, voices, locale)
    if expected is None or expected != audio:
        raise invalid('Portal original voice binding changed; refresh game data.')
    return pack_performance([voices.read_ref(part) for part in expected['parts']])


decode_voice_source = decode_performance
