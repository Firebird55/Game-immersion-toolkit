"""Arknights: Endfield authored localization and original VFS voice bindings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .dialogue_catalog import DialogueCatalog, selected_tables
from .game_tools import download, _atomic_file
from .hoyo_dialogue import SUPPORTED_LOCALES
from .languages import audio_locale, resolve_locale
from .nte_assets import dotnet_sdk
from .textmaps import display_text
from .voice_assets import voice_hash

LANGUAGE_INDEX_VERSION = 1
TEXT_LOCALES = {'en': 'EN', 'zh-Hans': 'CN', 'zh-Hant': 'TC', 'ja': 'JP', 'ko': 'KR',
    'fr': 'FR', 'de': 'DE', 'it': 'IT', 'es-419': 'MX', 'pt-BR': 'BR', 'ru': 'RU',
    'th': 'TH', 'vi': 'VN', 'id': 'ID'}
VOICE_LOCALES = {'en': 'english', 'zh-Hans': 'chinese', 'zh-Hant': 'chinese', 'ja': 'japanese', 'ko': 'korean'}


def streaming_assets(install, layer='StreamingAssets'):
    if layer not in {'StreamingAssets', 'Persistent'}:
        raise ValueError('Invalid Endfield data layer.')
    return install / 'Endfield_Data' / layer


def archive_sources(install):
    return sorted(p for layer in ('StreamingAssets', 'Persistent')
                  for p in (streaming_assets(install, layer) / 'VFS').rglob('*') if p.suffix in {'.blc', '.chk'})


def fingerprint(install):
    return hashlib.sha256('\n'.join(f'{p.relative_to(install)}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
        for p in archive_sources(install)).encode()).hexdigest()


def ensure_extractor(directory):
    directory = directory.resolve()
    sdk = dotnet_sdk()
    if sdk is None:
        raise ValueError('Endfield needs the Microsoft .NET 10 SDK; install it and prepare game tools again.')
    code = Path(__file__).resolve().parents[1]
    manifest = json.loads((code / 'scripts/endfield-reader-sources.json').read_text())
    directory.mkdir(parents=True, exist_ok=True)
    upstream = directory / 'upstream'
    for relative, digest in manifest['files'].items():
        path = upstream / relative.removeprefix('AnimeStudio.Endfield/')
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        data = download(f'https://raw.githubusercontent.com/{manifest["repository"]}/{manifest["revision"]}/{relative}')
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Endfield reader checksum mismatch.')
        _atomic_file(path, data)
    license_text = download(f'https://raw.githubusercontent.com/{manifest["repository"]}/{manifest["revision"]}/LICENSE')
    if not license_text.startswith(b'MIT License'):
        raise ValueError('Endfield reader license notice is unavailable.')
    _atomic_file(directory / 'ENDFIELDSTUDIO-LICENSE.txt', license_text)
    sources = code / 'scripts/game-readers'
    signature = hashlib.sha256((sources / 'EndfieldReader.cs').read_bytes() +
        (sources / 'EndfieldReader.csproj').read_bytes() + json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    marker = directory / 'reader-build.json'
    target = directory / 'EndfieldReader.dll'
    try:
        previous = json.loads(marker.read_text())
        if previous['source'] == signature and previous['files'] and all(
            hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest for name, digest in previous['files'].items()):
            return target
    except (OSError, KeyError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix='endfield-build-', dir=directory) as temporary:
        build = Path(temporary)
        result = subprocess.run([str(sdk), 'build', str(sources / 'EndfieldReader.csproj'), '-c', 'Release',
            '-o', str(build / 'out'), f'-p:EndfieldSource={upstream.resolve()}',
            f'-p:BaseIntermediateOutputPath={build.resolve() / "obj"}/',
            '-p:RestoreSources=https://api.nuget.org/v3/index.json', '-p:NuGetAudit=false', '--nologo'],
            capture_output=True, timeout=240, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Endfield reader build failed; install or repair the .NET 10 SDK.')
        files = {}
        for path in (build / 'out').iterdir():
            if path.suffix not in {'.dll', '.json'}:
                continue
            data = path.read_bytes()
            files[path.name] = hashlib.sha256(data).hexdigest()
            _atomic_file(directory / path.name, data)
        _atomic_file(marker, json.dumps({'source': signature, 'files': files}).encode())
    return target


def reader(install, executable, action, request):
    sdk = dotnet_sdk()
    if sdk is None or not executable.is_file():
        raise ValueError('Prepare Endfield game tools in Setup first.')
    result = subprocess.run([str(sdk), str(executable), action, str(streaming_assets(install, request.get('layer', 'StreamingAssets')))],
        input=json.dumps(request).encode(), capture_output=True, timeout=900,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Endfield voice data could not be read; refresh installed game data and tools.')
    return result.stdout


def audio_paths(audio_dialog):
    # audioOverride is the authored source filename. AudioDialog supplies its
    # complete directory, without guessing ordinal IDs or reusing bank order.
    values, ambiguous = {}, set()
    for value in audio_dialog.values():
        path = value.get('path', '').replace('\\', '/')
        if not path or value.get('isPlaceholder'):
            continue
        name = Path(path).stem
        if name in values and values[name] != path:
            ambiguous.add(name)
        values[name] = path
    return {name: path for name, path in values.items() if name not in ambiguous}


def dialogue_records(dialogs, paths, tables, locale, entries):
    result = []
    for identity, row in dialogs.items():
        source = paths.get(row.get('audioOverride', ''))
        if not source:
            continue
        source = 'voice/' + VOICE_LOCALES[locale] + '/' + source.replace('\\', '/').lower()
        texts = {code: display_text(table.get(str(row.get('dialogText', {}).get('id')), ''))
                 for code, table in tables.items()}
        texts = {code: value for code, value in texts.items() if value}
        if not texts.get(locale):
            continue
        audio = entries.get(f'{voice_hash(source):016x}')
        result.append({'text_id': 'endfield:' + identity, 'source_locale': locale, 'source_text': texts[locale],
            'texts': texts, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
            'audio_locale': audio_locale(locale), 'audio': {**audio, 'source': source, 'locale': audio_locale(locale)} if audio else None,
            'player_voice': {'endminm': 'male', 'endminf': 'female'}.get(row.get('actorNameId')),
            'channels': ['dialogue']})
    return result


def authored_dialogues(catalog):
    dialogs = catalog.file('TableCfg/DialogTextTable.json')
    for group in catalog.file('TableCfg/RadioTable.json').values():
        for row in group.get('radioSingleDataList', []):
            identity = row.get('id')
            if identity and row.get('audioOverride'):
                dialogs[identity] = {**row, 'dialogText': row.get('radioText', {})}
    texts = catalog.file('TableCfg/TextTable.json')
    for identity, voice in catalog.file('TableCfg/TextVoIdTable.json').items():
        if identity in texts:
            dialogs[identity] = {'dialogText': texts[identity], 'audioOverride': voice}
    return dialogs


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Endfield study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('endfield', data_dir)
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales, prefix='TableCfg/I18nTextTable_')
    paths = audio_paths(catalog.file('TableCfg/AudioDialog.json'))
    progress('Reading installed Endfield original voice packages')
    inventory = []
    for layer in ('StreamingAssets', 'Persistent'):
        if (streaming_assets(install, layer) / 'VFS').is_dir():
            values = json.loads(reader(install, data_dir / 'tools/EndfieldReader.dll', 'inventory',
                                       {'language': VOICE_LOCALES[source_locale], 'layer': layer}))
            inventory.extend({**row, 'layer': layer} for row in values)
    entries = {}
    # Initial, selected locale and hotfix are explicit successive layers.
    for layer, block in dict.fromkeys((entry['layer'], entry['block']) for entry in inventory):
        current, ambiguous = {}, set()
        for entry in (row for row in inventory if row['block'] == block and row['layer'] == layer):
            key = entry['file_id']
            if key in current and current[key] != entry:
                ambiguous.add(key)
            current[key] = entry
        for key in ambiguous:
            current.pop(key, None)
            entries.pop(key, None)
        entries.update(current)
    rows = dialogue_records(authored_dialogues(catalog), paths, tables, source_locale, entries)
    if not rows or fingerprint(install) != stamp:
        raise ValueError('Endfield data is incomplete or changed; previous language table retained.')
    count = sum(bool(row['audio']) for row in rows)
    available = {code for row in rows for code in row['texts']}
    return {'format': 2, 'game': 'endfield', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'metadata_revision': catalog.revision, 'records': rows,
        'missing_translation_locales': [target for target in target_locales if resolve_locale(target, TEXT_LOCALES) not in available],
        'message': f'{len(rows):,} official {source_locale} lines; {count:,} original voices'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, executable, _destination):
    locale = audio['locale']
    if locale not in SUPPORTED_LOCALES or not audio['source'].startswith('voice/' + VOICE_LOCALES[locale] + '/'):
        raise ValueError('Endfield original voice crosses locales.')
    if f'{voice_hash(audio["source"]):016x}' != audio['file_id'] or not re.fullmatch(r'[0-9A-F]{32}\.chk', audio['chunk']):
        raise ValueError('Invalid Endfield original voice binding.')
    return reader(install, executable, 'voice', {**audio, 'language': VOICE_LOCALES[locale]})
