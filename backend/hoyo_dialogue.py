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
RELEASE_MARKERS = {
    'genshin': ('AssetBundles/data_revision', 'AssetBundles/res_revision', 'AssetBundles/silence_revision',
                'data_versions_persist', 'res_versions_persist', 'data_versions_streaming',
                'res_versions_streaming', 'silence_versions_streaming'),
    'starrail': ('DesignData/Windows/M_DesignV.bytes', 'DesignData/Windows/M_Design_ArchiveV.bytes',
                 'Asb/Windows/M_AsbV.bytes', 'Asb/Windows/M_BlockV.bytes',
                 'Audio/AudioPackage/Windows/M_AudioV.bytes', 'Video/Windows/M_VideoV.bytes'),
}


def voice_namespace(game, locale):
    if game == 'genshin' and locale in ('zh-Hans', 'zh-Hant'):
        return 'Chinese'
    return 'English' if game == 'starrail' and locale == 'en' else VOICE_NAMES[locale]


def voice_namespaces(game, locale):
    namespace = voice_namespace(game, locale)
    # Keep existing locally verified Genshin bindings readable across the
    # correction. Star Rail uses Chinese(PRC) as its canonical namespace.
    return (namespace, 'Chinese(PRC)') if namespace == 'Chinese' else (namespace,)


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
    markers = set()
    # Text-only hotfixes can leave every voice package unchanged. Include the
    # authored data and patch manifests, but never logs, accounts or telemetry.
    metadata = ('BinaryVersion.bytes', 'ClientConfig.bytes', 'InstallVersion.bin',
                'data_versions', 'data_versions_streaming', 'res_versions', 'res_versions_streaming',
                'silence_versions', 'silence_versions_streaming', 'ctable.dat', 'ctable_streaming.dat',
                'svc_catalog')
    for layer in ('StreamingAssets', 'Persistent', 'StreamingAssets/Persistent'):
        directory = root / layer
        markers.update(directory / name for name in RELEASE_MARKERS[game] if (directory / name).is_file())
        files += [directory / name for name in metadata if (directory / name).is_file()]
        design = directory / 'DesignData'
        if design.is_dir():
            files += [p for p in design.rglob('*') if p.is_file()]
    if (install / 'config.ini').is_file():
        files.append(install / 'config.ini')
    parts = []
    for path in sorted(set(files) | markers):
        stat = path.stat()
        identity = f'{path.relative_to(install)}:{stat.st_size}:{stat.st_mtime_ns}'
        # Launchers can preserve timestamps when replacing equal-sized markers.
        # Hash the release manifests, keeping large audio/design assets stat-only.
        if path in markers and path.resolve().is_relative_to(root.resolve()):
            with path.open('rb') as stream:
                identity += ':' + hashlib.file_digest(stream, 'sha256').hexdigest()
        parts.append(identity)
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()


def inventory(install, game, locale):
    namespaces = {name.casefold() for name in voice_namespaces(game, locale)}
    root = game_data(install, game)
    result = {}
    # Base packages precede Persistent patches; duplicate IDs inside a layer
    # must not silently choose an unrelated performance.
    paths = archive_sources(install, game)
    for layer in ('StreamingAssets', 'Persistent'):
        current, ambiguous = {}, set()
        for path in paths:
            parts = path.relative_to(root).parts
            if parts[0] != layer or namespaces.isdisjoint(part.casefold() for part in parts[1:-1]):
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
    if isinstance(entry, dict) and entry.get('publisher'):
        return {**entry, 'source': source, 'file_id': f'{identity:016x}', 'locale': audio_locale(locale)}
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
        source = link.get('source')
        audio = audio_binding(source, entries, locale) if source else None
        if not audio and game == 'genshin' and locale in ('zh-Hans', 'zh-Hant') and source and source.startswith('Chinese\\'):
            audio = audio_binding('Chinese(PRC)' + source[len('Chinese'):], entries, locale)
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
    if not rows or install is not None and fingerprint(install, game) != stamp:
        raise ValueError('Subtitle data is incomplete or game files changed; previous table retained.')
    available = {code for row in rows for code in row['texts']}
    missing = [code for code in targets if resolve_locale(code, mapping) not in available]
    count = sum(bool(row['audio']) for row in rows)
    return {'format': 2, 'game': game, 'source_locale': source_locale, 'install': str(install) if install else None,
        'fingerprint': stamp, 'metadata_revision': catalog.revision, 'records': rows,
        'missing_translation_locales': missing,
        'message': f'{len(rows):,} official {source_locale} lines; {count:,} original voices' +
        ('; install the selected original voice pack through the game launcher' if not count else '')}


def extract_voice(install, game, audio):
    locale, source = audio['locale'], audio['source']
    if locale not in SUPPORTED_LOCALES or voice_hash(source) != int(audio['file_id'], 16):
        raise ValueError('Original voice identity does not match its selected locale.')
    namespaces = {name.casefold() for name in voice_namespaces(game, locale)}
    if re.split(r'[/\\]', source, maxsplit=1)[0].casefold() not in namespaces:
        raise ValueError('Original voice source crosses locales.')
    path = Path(audio['package']).resolve()
    root = game_data(install, game).resolve()
    if (path not in {p.resolve() for p in archive_sources(install, game)}
            or not path.is_relative_to(root)
            or namespaces.isdisjoint(p.casefold() for p in path.relative_to(root).parts[1:-1])):
        raise ValueError('Original voice package is outside its selected installed locale.')
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (audio['package_size'], audio['package_mtime_ns']):
        raise ValueError('Original voice package changed; refresh game data.')
    entry = VoiceEntry(path, int(audio['offset']), int(audio['size']), int(audio['file_id'], 16))
    if entry not in read_external_table(path):
        raise ValueError('Original voice bounds do not match the installed package table.')
    return entry.read()
