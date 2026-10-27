"""Common read-only PCK bindings for Genshin Impact and Honkai: Star Rail."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .languages import audio_locale
from .textmaps import display_text
from .voice_assets import VoiceEntry, read_external_table, voice_hash

SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
TEXT_LOCALES = {'en': 'EN', 'zh-Hans': 'CHS', 'zh-Hant': 'CHT', 'ja': 'JP', 'ko': 'KR',
    'fr': 'FR', 'de': 'DE', 'es-ES': 'ES', 'pt-BR': 'PT', 'ru': 'RU', 'th': 'TH', 'vi': 'VI', 'id': 'ID'}
VOICE_NAMES = {'en': 'English(US)', 'zh-Hans': 'Chinese(PRC)', 'zh-Hant': 'Chinese(PRC)',
               'ja': 'Japanese', 'ko': 'Korean'}
DATA_FOLDERS = {'genshin': ('GenshinImpact_Data', 'YuanShen_Data'), 'starrail': ('StarRail_Data',)}


def voice_namespace(game, locale):
    return 'English' if game == 'starrail' and locale == 'en' else VOICE_NAMES[locale]


def game_data(install, game):
    for name in DATA_FOLDERS[game]:
        root = install if install.name == name else install / name
        if root.is_dir():
            return root
    raise ValueError('Choose the installed game client, rather than its launcher.')


def archive_sources(install, game):
    root = game_data(install, game)
    # Restrict traversal to the official audio directories; ignore SDK/logs.
    paths = []
    for layer in ('StreamingAssets', 'Persistent'):
        for folder in ('AudioAssets', 'Audio/AudioPackage/Windows', 'Audio/GeneratedSoundBanks/Windows'):
            paths.extend((root / layer / folder).rglob('*.pck'))
    return sorted(set(paths))


def fingerprint(install, game):
    root = game_data(install, game)
    files = archive_sources(install, game)
    files += [p for p in (root / 'StreamingAssets/BinaryVersion.bytes', install / 'config.ini') if p.is_file()]
    return hashlib.sha256('\n'.join(f'{p.relative_to(install)}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
        for p in sorted(files)).encode()).hexdigest()


def inventory(install, game, locale):
    namespace = voice_namespace(game, locale).casefold()
    result = {}
    # Base packages precede Persistent patches; duplicate IDs inside a layer
    # must not silently choose an unrelated performance.
    paths = archive_sources(install, game)
    for layer in ('StreamingAssets', 'Persistent'):
        current, ambiguous = {}, set()
        for path in paths:
            if layer not in path.parts or namespace not in {part.casefold() for part in path.parts}:
                continue
            for entry in read_external_table(path):
                if entry.file_id in current and current[entry.file_id] != entry:
                    ambiguous.add(entry.file_id)
                current[entry.file_id] = entry
        for identity in ambiguous:
            current.pop(identity, None)
            result.pop(identity, None)
        result.update(current)
    return result


def audio_binding(source, entries, locale):
    identity = voice_hash(source)
    entry = entries.get(identity)
    if entry is None:
        return None
    stat = entry.package.stat()
    return {'source': source, 'file_id': f'{identity:016x}', 'package': str(entry.package),
            'offset': entry.offset, 'size': entry.size, 'package_size': stat.st_size,
            'package_mtime_ns': stat.st_mtime_ns, 'locale': audio_locale(locale)}


def records(game, links, tables, locale, entries):
    result = []
    for link in links:
        texts = {code: display_text(table.get(str(link['hash']), '')) for code, table in tables.items()}
        texts = {code: value for code, value in texts.items() if value}
        if not texts.get(locale):
            continue
        audio = audio_binding(link['source'], entries, locale) if link.get('source') else None
        voice_status = ('voiced' if audio else 'unavailable' if link.get('source')
                        else link.get('voice_status', 'unknown'))
        result.append({'text_id': game + ':' + str(link['id']), 'source_locale': locale,
            'source_text': texts[locale], 'texts': texts, 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', ''), 'audio_locale': audio_locale(locale), 'audio': audio,
            'player_voice': link.get('player_voice'), 'channels': link.get('channels', ['dialogue']),
            'voice_status': voice_status, 'dialogue_kind': link.get('dialogue_kind')})
    return result


def snapshot(game, install, stamp, catalog, rows, source_locale, targets, mapping):
    from .languages import resolve_locale
    if not rows or fingerprint(install, game) != stamp:
        raise ValueError('Subtitle data is incomplete or game files changed; previous table retained.')
    available = {code for row in rows for code in row['texts']}
    missing = [code for code in targets if resolve_locale(code, mapping) not in available]
    count = sum(bool(row['audio']) for row in rows)
    return {'format': 2, 'game': game, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'metadata_revision': catalog.revision, 'records': rows,
        'missing_translation_locales': missing,
        'message': f'{len(rows):,} official {source_locale} lines; {count:,} original voices' +
        ('; install the selected original voice pack through the game launcher' if not count else '')}


def extract_voice(install, game, audio):
    locale, source = audio['locale'], audio['source']
    if locale not in SUPPORTED_LOCALES or voice_hash(source) != int(audio['file_id'], 16):
        raise ValueError('Original voice identity does not match its selected locale.')
    namespace = voice_namespace(game, locale).casefold()
    if not source.casefold().startswith((namespace + '/', namespace + '\\')):
        raise ValueError('Original voice source crosses locales.')
    path = Path(audio['package']).resolve()
    if path not in {p.resolve() for p in archive_sources(install, game)} or namespace not in {p.casefold() for p in path.parts}:
        raise ValueError('Original voice package is outside its selected installed locale.')
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (audio['package_size'], audio['package_mtime_ns']):
        raise ValueError('Original voice package changed; refresh game data.')
    entry = VoiceEntry(path, int(audio['offset']), int(audio['size']), int(audio['file_id'], 16))
    if entry not in read_external_table(path):
        raise ValueError('Original voice bounds do not match the installed package table.')
    return entry.read()
