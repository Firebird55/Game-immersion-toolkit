"""A Plague Tale: Innocence's original localized dialogue and narrative menus."""
from collections import Counter
import hashlib
from pathlib import Path
import re

from .plague_tale_formats import Package, bank_events, invalid, read_file, script_bundle, text_table, wwise_hash
from .preparation_errors import PreparationFailure
from .textmaps import display_text

GAME = 'plaguetaleinnocence'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'de')
VOICE_LOCALES = {'en': 'english(us)', 'fr': 'french(france)', 'de': 'german'}
TEXT_LOCALES = {'en': '01', 'fr': '02', 'de': '04', 'it': '05', 'es-ES': '03',
    'es-419': '20', 'pl': '08', 'cs': '11', 'pt-BR': '14', 'ru': '17',
    'zh-Hant': '21', 'zh-Hans': '22', 'ja': '00', 'ko': '09'}
_MEDIA = {'VO_' + name + '_MEDIA.PC.PCK' for name in
          ('AMICIA', 'D1', 'GUARD1', 'GUARD2', 'GUARD3', 'GUARD4', 'HUGO', 'LUCAS', 'MELIE', 'OTHERS', 'RODRIC')}
_STRUCTURE = 'VO_STRUCTURE.PC.PCK'


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for candidate in candidates:
        path = Path(candidate)
        if (path / 'APlagueTaleInnocence_x64.exe').is_file() and (path / 'LangDef.tsc').is_file() and (path / 'TRTEXT').is_dir():
            return path
    return None


def archive_sources(install):
    root = Path(install)
    return sorted({path for pattern in ('LangDef.tsc', 'All.psc', 'TRTEXT/tt*.pc',
        'SOUNDBANKS/VO_*.PC.PCK', 'RTC/*.DPC', 'VIDEOS/NTSC/*.bik')
        for path in root.glob(pattern) if path.is_file()})


def fingerprint(install):
    root = Path(install).resolve()
    return hashlib.sha256('|'.join(f'{path.relative_to(root).as_posix()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        for path in archive_sources(root)).encode()).hexdigest()


def _packages(install):
    return [Package(path) for path in sorted((Path(install) / 'SOUNDBANKS').glob('VO_*.PC.PCK'))]


def probe_voice_pack(install, locale):
    """Read bounded package directories only; never decode banks or recordings."""
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        language = VOICE_LOCALES[locale]
        available = {package.path.name for package in _packages(install)
                     if any(entry.language == language for entry in package.entries.values())}
        if not available:
            return 'missing'
        return 'present' if _MEDIA | {_STRUCTURE} <= available else 'incomplete'
    except (OSError, ValueError, PreparationFailure):
        return 'incomplete'


def _language_manifest(root):
    path = root / 'LangDef.tsc'
    if path.stat().st_size > 64 * 1024:
        raise invalid('Innocence language definition exceeds the supported bound.')
    manifest = {}
    for line in path.read_text('utf-8-sig').splitlines():
        if not line.strip().startswith('AddLangDefine'):
            continue
        match = re.fullmatch(r'\s*AddLangDefine\s+(\d+)\s+-?\d+\s+\d+\s+\w+\s+"([^"]+)"\s*', line)
        if not match or match[1].zfill(2) in manifest:
            raise invalid('Invalid Innocence language definition.')
        manifest[match[1].zfill(2)] = match[2].casefold()
    return manifest


def _package_order(script):
    order = []
    for line in script.splitlines():
        match = re.fullmatch(r'LoadFilePackage (VO_[A-Z0-9_]+) TRUE', line.strip())
        if match:
            name = match[1] + '.PC.PCK'
            if name in order:
                raise invalid('Ambiguous Innocence audio package load order.')
            order.append(name)
    return order


def _voice_bindings(packages, locale, order):
    language = VOICE_LOCALES[locale]
    bindings, media, unresolved, bank_count = {}, {}, set(), 0
    by_name = {package.path.name: package for package in packages}
    for name in order:
        package = by_name.get(name)
        if package is None:
            continue
        for entry in package.entries.values():
            if entry.language != language:
                continue
            if entry.kind == 'media':
                # Wwise searches the last loaded package first. All.psc loads
                # VO_D1_MEDIA last; it contains revised performances sharing
                # the original media IDs. Alphabetical order is incorrect.
                media[entry.identity] = package.path.name
            elif entry.kind == 'bank' and package.path.name == _STRUCTURE:
                events, failed = bank_events(package.read(entry), language, entry.identity)
                bank_count += 1
                unresolved.update(failed)
                for event, source in events.items():
                    if event in bindings and bindings[event] != (entry.identity, source):
                        raise invalid('Ambiguous Innocence original voice event.')
                    bindings[event] = entry.identity, source
    return bindings, media, unresolved, bank_count


def _narrative(script):
    """Authored menu fields establish text-only prose; pickup SFX are not voices."""
    narrative, speakers, counts = {}, [], Counter()
    for line in script.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == 'AddLootItem':
            if len(fields) != 13:
                raise invalid('Innocence loot schema changed.')
            counts['loot_definitions'] += 1
            # The fixed shipped pickup cue is a sound effect, not narration.
            # An unfamiliar cue requires review before asserting silence.
            if fields[3] != 'SOUND__LOOT_NORMAL':
                continue
            kind = 'collectible_lore' if fields[1].startswith('CODEX_') else 'inventory_description'
            for identity in (fields[2], fields[4]):
                if re.fullmatch(r'(?:GAME|HUD)__[A-Z0-9_]+', identity):
                    narrative[identity] = kind
        elif fields[0] == 'AddRecipe':
            if len(fields) < 11 or fields[2] not in {'UPGRADE', 'CRAFT'}:
                raise invalid('Innocence recipe schema changed.')
            counts['recipe_definitions'] += 1
            for identity in (fields[3], fields[6], fields[7]):
                if re.fullmatch(r'HUD__GAMEMENU_[A-Z0-9_]+', identity):
                    narrative[identity] = 'crafting_lore'
        elif fields[0] == 'AddVOSubtitleSpeaker':
            if len(fields) != 4:
                raise invalid('Innocence subtitle-speaker schema changed.')
            speakers.append(tuple(fields[1:]))
    return narrative, speakers, counts


def _text(value, identity):
    result = display_text(value)
    # The game ships untranslated identifiers for non-verbal performances and
    # unfinished resources. They are inventory evidence, never subtitle prose.
    if result.upper() == identity or result in {'TO BE WRITTEN', 'TBD', 'TODO'} or result.startswith('$'):
        return ''
    return result


def _kind(identity):
    category = identity.split('__')[3] if len(identity.split('__')) > 3 else ''
    if category.startswith('RTC_'):
        return 'cinematic'
    if category.startswith(('PATROL_', 'CHATTER_', 'ONOM_')):
        return 'ambient_dialogue'
    return 'dialogue'


def _speaker(identity, speakers, english):
    family = '__'.join(identity.split('__')[:2])
    candidates = [(scope, key) for owner, scope, key in speakers if owner == family]
    # Scoped replacements preserve the game's authored speaker overrides.
    key = next((key for scope, key in candidates if scope != 'DEFAULT' and identity.startswith(scope)), None)
    key = key or next((key for scope, key in candidates if scope == 'DEFAULT'), None)
    return _text(english.get(key, ''), key) or None


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported original Innocence study/audio locale')
    root = Path(install)
    if not discover_install([root]):
        raise invalid('Choose the Innocence folder containing APlagueTaleInnocence_x64.exe, LangDef.tsc and TRTEXT.')
    stamp = fingerprint(root)
    manifest = _language_manifest(root)
    if manifest.get(TEXT_LOCALES[source_locale]) != VOICE_LOCALES[source_locale]:
        raise invalid('The selected Innocence original language is absent from LangDef.tsc; verify game files.')
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    tables = {}
    for locale in selected:
        path = root / 'TRTEXT' / ('tt' + TEXT_LOCALES[locale] + '.pc')
        if TEXT_LOCALES[locale] in manifest and path.is_file():
            tables[locale] = text_table(read_file(path, 16 * 1024 * 1024))
    if source_locale not in tables:
        raise PreparationFailure('plaguetaleinnocence_missing_pack',
            'Selected Innocence text is missing. Finish the Steam download and verify game files, then prepare again.')
    progress('Reading Innocence original voice package directories and authored menu fields')
    packages = _packages(root)
    script_path = root / 'All.psc'
    script = script_bundle(read_file(script_path, 32 * 1024 * 1024)) if script_path.is_file() else ''
    narrative, speakers, counts = _narrative(script)
    bindings, media, unresolved, bank_count = _voice_bindings(packages, source_locale, _package_order(script))
    records, matched_events = [], set()
    for identity, value in tables[source_locale].items():
        texts = {locale: text for locale, table in tables.items()
                 if (text := _text(table.get(identity, ''), identity))}
        is_voice = identity.startswith('VO__')
        if is_voice:
            counts['voice_localization_identifiers'] += 1
        if not texts.get(source_locale):
            if is_voice:
                counts['voice_identifiers_without_subtitle_prose'] += 1
            continue
        audio = None
        if is_voice:
            event = wwise_hash('play_' + identity)
            if event in bindings:
                bank, source = bindings[event]
                matched_events.add(event)
                if source in media:
                    audio = {'locale': source_locale, 'bank': bank, 'event': event,
                             'media': source, 'archive': media[source], 'text_id': identity}
            state, kind = ('voiced' if audio else 'unavailable'), _kind(identity)
        else:
            state = 'unvoiced' if identity in narrative else 'unknown'
            kind = narrative.get(identity, 'ui_localization')
        records.append({'text_id': GAME + ':' + identity, 'english': texts.get('en', ''), 'chinese': '',
            'source_locale': source_locale, 'source_text': texts[source_locale], 'texts': texts,
            'audio_locale': source_locale, 'audio': audio, 'voice_status': state, 'dialogue_kind': kind,
            'speaker_english': _speaker(identity, speakers, tables.get('en', {})) if is_voice else None})
    if fingerprint(root) != stamp:
        raise PreparationFailure('plaguetaleinnocence_files_changed',
            'Innocence files changed during preparation. Wait for Steam to finish and retry.',
            game_files_changed=True, previous_snapshot_retained=True)
    voices = Counter(row['voice_status'] for row in records)
    counts.update({'voice_banks': bank_count, 'voice_events': len(bindings), 'voice_media': len(media),
        'unsupported_voice_events': len(unresolved), 'voice_events_without_selected_subtitle_prose': len(set(bindings) - matched_events),
        'realtime_cinematic_archives': len(list((root / 'RTC').glob('*.DPC'))),
        'prerendered_video_files': len(list((root / 'VIDEOS/NTSC').glob('*.bik'))),
        'script_bundle_present': int(script_path.is_file())})
    warnings = [
        'Dialogue, ambient barks and RTC cinematics share authored VO text/event bindings. Each entry plays the complete original recording; no cinematic timestamps are guessed.',
        'Nonverbal performances and placeholder identifiers have no official subtitle prose and cannot be captured from text. Other unbound UI text remains unknown.',
        'Enable Include unvoiced dialogue for authored codex, inventory and crafting descriptions. Use full-window capture or independent calibrated regions: lore panels are outside the subtitle band.',
        'Only logo Bink videos were found in the audited installation. RTC scene internals, textured writing, branching-choice layouts and external/regional releases have no separate verified binding.',
        'All three official voice languages use their own package language identifiers. A missing recording is unavailable, never silent or replaced with another language.']
    if voices['unavailable'] or not bank_count:
        warnings.append('Some selected original voices are unavailable. Finish Steam downloads and verify game files, then prepare this language again.')
    if not script_path.is_file():
        warnings.append('All.psc is missing; narrative menu silence cannot be confirmed. Verify game files and prepare again.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(root), 'fingerprint': stamp,
        'records': records, 'voice_pack_state': probe_voice_pack(root, source_locale),
        'narrative_inventory': {**counts, 'voice_counts': dict(voices),
                                'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in records))},
        'missing_translation_locales': [target for target, locale in targets.items() if locale not in tables],
        'coverage_warnings': warnings,
        'message': f"{voices['voiced']:,} original {source_locale} voices; {voices['unvoiced']:,} confirmed unvoiced narrative entries"}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', ['zh-Hans'], progress)


def extract_voice(install, audio, _executable, _destination):
    locale = audio.get('locale')
    identity = audio.get('text_id')
    if locale not in VOICE_LOCALES or not isinstance(identity, str) or not re.fullmatch(r'VO__[A-Z0-9_]+', identity):
        raise invalid('Invalid Innocence original voice reference.')
    if any(type(audio.get(key)) is not int for key in ('bank', 'event', 'media')) or audio['event'] != wwise_hash('play_' + identity):
        raise invalid('Invalid Innocence original event identity.')
    archive = audio.get('archive')
    if not isinstance(archive, str) or not re.fullmatch(r'VO_[A-Z0-9_]+_MEDIA\.PC\.PCK', archive):
        raise invalid('Invalid Innocence media package reference.')
    root, language = Path(install) / 'SOUNDBANKS', VOICE_LOCALES[locale]
    bank_package = Package(root / _STRUCTURE)
    entry = bank_package.entries.get(('bank', audio['bank'], language))
    if entry is None:
        raise invalid('Selected Innocence voice bank is missing; verify game files and prepare again.')
    events, _unresolved = bank_events(bank_package.read(entry), language, audio['bank'])
    if events.get(audio['event']) != audio['media']:
        raise invalid('Innocence voice binding changed; prepare this language again.')
    package = Package(root / archive)
    entry = package.entries.get(('media', audio['media'], language))
    if entry is None:
        raise invalid('Selected Innocence original recording is missing; verify game files and prepare again.')
    script = script_bundle(read_file(Path(install) / 'All.psc', 32 * 1024 * 1024))
    winner = None
    for name in _package_order(script):
        path = root / name
        if path.is_file() and ('media', audio['media'], language) in Package(path).entries:
            winner = name
    if winner != archive:
        raise invalid('Innocence recording override changed; prepare this language again.')
    result = package.read(entry)
    if len(result) < 12 or result[:4] != b'RIFF' or result[8:12] != b'WAVE':
        raise invalid('Unsupported Innocence original voice media.')
    return result
