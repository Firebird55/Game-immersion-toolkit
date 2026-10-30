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
from .languages import audio_locale, resolve_locale
from .nte_assets import dotnet_sdk
from .preparation_errors import PreparationFailure
from .textmaps import display_text
from .voice_assets import voice_hash

LANGUAGE_INDEX_VERSION = 3
TEXT_LOCALES = {'en': 'EN', 'zh-Hans': 'CN', 'zh-Hant': 'TC', 'ja': 'JP', 'ko': 'KR',
    'fr': 'FR', 'de': 'DE', 'it': 'IT', 'es-419': 'MX', 'pt-BR': 'BR', 'ru': 'RU',
    'th': 'TH', 'vi': 'VN', 'id': 'ID'}
VOICE_LOCALES = {'en': 'english', 'zh-Hans': 'chinese', 'zh-Hant': 'chinese', 'ja': 'japanese', 'ko': 'korean'}
# Capability is independent of which optional voice packs happen to be installed.
# Traditional Chinese is a subtitle script paired with the same Mandarin audio.
SUPPORTED_LOCALES = tuple(VOICE_LOCALES)


def streaming_assets(install, layer='StreamingAssets'):
    if layer not in {'StreamingAssets', 'Persistent'}:
        raise ValueError('Invalid Endfield data layer.')
    return install / 'Endfield_Data' / layer


def archive_sources(install):
    return sorted(p for layer in ('StreamingAssets', 'Persistent')
                  for p in (streaming_assets(install, layer) / 'VFS').rglob('*') if p.suffix.lower() in {'.blc', '.chk'})


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


def _audio_source(value):
    _mapping(value)
    if 'path' not in value or not isinstance(value['path'], str):
        _unsupported()
    path = value['path'].replace('\\', '/')
    if not path or value.get('isPlaceholder'):
        return None
    if path.startswith('/') or ':' in path or any(part in {'', '.', '..'} for part in path.split('/')):
        return None
    return path


def audio_paths(audio_dialog):
    # audioOverride is the authored source filename. AudioDialog supplies its
    # complete directory, without guessing ordinal IDs or reusing bank order.
    values, ambiguous = {}, set()
    for value in _mapping(audio_dialog).values():
        path = _audio_source(value)
        if not path:
            continue
        name = Path(path).stem
        if name in values and values[name] != path:
            ambiguous.add(name)
        values[name] = path
    return {name: path for name, path in values.items() if name not in ambiguous}


def audio_id_paths(audio_dialog):
    # AIBarkText and AudioDialog use the same authored voice-ID key. Keep this
    # namespace separate from filename stems, which can be ambiguous.
    return {identity: path for identity, row in _mapping(audio_dialog).items() if (path := _audio_source(row))}


def dialogue_records(dialogs, paths, tables, locale, entries, *, audio_ids=None, coverage=None):
    result = []
    for identity, row in dialogs.items():
        if row.get('dialogue_kind') == 'readable' and any('<image' in table.get(str(row['dialogText']['id']), '').lower()
                                                       for table in tables.values()):
            continue
        source = ((audio_ids or {}).get(row['audio_id']) if 'audio_id' in row
                  else paths.get(row.get('audioOverride', '')))
        source = ('voice/' + VOICE_LOCALES[locale] + '/' + source.replace('\\', '/').lower()) if source else None
        texts = {code: display_text(table.get(str(row.get('dialogText', {}).get('id')), ''))
                 for code, table in tables.items()}
        texts = {code: value for code, value in texts.items() if value}
        if not texts.get(locale):
            continue
        audio = entries.get(f'{voice_hash(source):016x}') if source else None
        voice_status = ('voiced' if audio else 'unavailable' if row.get('audioOverride') or row.get('audioEvent') or 'audio_id' in row
                        else row.get('voice_status', 'unknown'))
        if coverage is not None:
            reason = ('missing_source_metadata' if not source else 'missing_locale_recording') if voice_status == 'unavailable' else voice_status
            coverage[reason] = coverage.get(reason, 0) + 1
        result.append({'text_id': 'endfield:' + identity, 'source_locale': locale, 'source_text': texts[locale],
            'texts': texts, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
            'audio_locale': audio_locale(locale), 'audio': {**audio, 'source': source, 'locale': audio_locale(locale)} if audio else None,
            'player_voice': {'endminm': 'male', 'endminf': 'female'}.get(row.get('actorNameId')),
            'voice_status': voice_status, 'dialogue_kind': row.get('dialogue_kind', 'conversation'),
            'channels': row.get('channels', ['dialogue'])})
    return result


def _unsupported():
    raise PreparationFailure('unsupported_game_format',
        'Endfield narrative data uses an unsupported structure. Update the toolkit and retry preparation; '
        'the previous language table is retained.')


def _mapping(value):
    if not isinstance(value, dict):
        _unsupported()
    return value


def _text_ref(value):
    if not isinstance(value, dict) or type(value.get('id')) not in {int, str}:
        _unsupported()
    return value


def _table(catalog, name, warnings=None):
    options = {'optional': True} if warnings is not None else {}
    values = _mapping(catalog.file('TableCfg/' + name + '.json', **options))
    if not values and warnings is not None:
        warnings.append(f'Endfield {name} is absent or empty; its narrative category is not prepared.')
    return values


def authored_dialogues(catalog):
    dialogs = {}
    primary = _table(catalog, 'DialogTextTable')
    if not primary:
        _unsupported()
    for identity, row in primary.items():
        _mapping(row)
        _text_ref(row.get('dialogText'))
        if 'audioOverride' in row and not isinstance(row['audioOverride'], str):
            _unsupported()
        # An empty override is not proof that the presentation has no voice;
        # the runtime may use another event/default. Only text-only tables below
        # establish silence without a verified recording.
        dialogs[identity] = {**row, 'voice_status': 'unknown',
                             'dialogue_kind': 'conversation'}
    for group in _table(catalog, 'RadioTable').values():
        rows = _mapping(group).get('radioSingleDataList')
        if not isinstance(rows, list):
            _unsupported()
        for row in rows:
            _mapping(row)
            identity = row.get('id')
            if not isinstance(identity, str) or not identity:
                _unsupported()
            _text_ref(row.get('radioText'))
            if not isinstance(row.get('audioOverride', ''), str):
                _unsupported()
            if identity in dialogs:
                _unsupported()
            dialogs[identity] = {**row, 'dialogText': row['radioText'], 'dialogue_kind': 'radio',
                'voice_status': 'unknown',
                'channels': ['dialogue', 'gameplay']}
    texts = _table(catalog, 'TextTable')
    for identity, voice in _table(catalog, 'TextVoIdTable').items():
        if not isinstance(voice, str):
            _unsupported()
        if identity in texts:
            if identity in dialogs:
                _unsupported()
            dialogs[identity] = {'dialogText': _text_ref(texts[identity]), 'audioOverride': voice,
                                'dialogue_kind': 'narration', 'channels': ['cinematic', 'dialogue']}
    return dialogs


def narrative_dialogues(catalog, warnings):
    """Explicit narrative tables, never arbitrary localization/menu strings.

    The installed UI distinguishes text SNS cells (1), voice cells (5) and
    image/video cells. RichContent renders <image> paragraphs as artwork.
    Preserve these boundaries rather than inferring silence from absent audio.
    """
    dialogs = {}

    def add(identity, reference, kind, channel, status='unvoiced', voice=''):
        dialogs[identity] = {'dialogText': _text_ref(reference), 'dialogue_kind': kind,
                            'channels': [channel], 'voice_status': status, 'audioOverride': voice}

    for name, field, kind, channel, status in (
        ('DialogOptionTable', 'optionText', 'choice', 'dialogue', 'unvoiced'),
        ('Dialog2DTextTable', 'dialog2dText', 'story_panel', 'cinematic', 'unvoiced'),
        ('SNSDialogOptionTable', 'optionDesc', 'message_choice', 'dialogue', 'unvoiced'),
        ('SNSDialogTopicTable', 'topicStartOptionDesc', 'message_choice', 'dialogue', 'unvoiced'),
        ('NarrativeNoteEntryTable', 'entryDesc', 'narrative_note', 'tip', 'unvoiced'),
    ):
        for identity, row in _table(catalog, name, warnings).items():
            add(f'{name}:{identity}', _mapping(row).get(field), kind, channel, status)

    for identity, row in _table(catalog, 'AIBarkText', warnings).items():
        key = f'AIBarkText:{identity}'
        add(key, _mapping(row).get('barkText'), 'combat_bark', 'gameplay', 'unavailable')
        # Installed AIBarkCtrl uses barkTextId for the text lookup and the
        # corresponding voId to stop playback. No text/fuzzy/ordinal join.
        dialogs[key]['audio_id'] = identity

    unsupported_messages = 0
    for identity, group in _table(catalog, 'SNSDialogTable', warnings).items():
        for number, row in _mapping(_mapping(group).get('dialogContentData')).items():
            _mapping(row)
            content_type = row.get('contentType')
            if type(content_type) is not int:
                _unsupported()
            if content_type == 1:
                add(f'SNSDialogTable:{identity}:{number}', row.get('content'), 'message', 'dialogue')
            elif content_type == 5:
                parameters = row.get('contentParam')
                if not isinstance(parameters, list) or not all(isinstance(value, str) for value in parameters):
                    _unsupported()
                # Only an exact AudioDialog source can bind this event. Generic
                # Wwise events remain unavailable, never guessed by bank order.
                add(f'SNSDialogTable:{identity}:{number}', row.get('content'), 'message_voice', 'dialogue',
                    'unavailable', parameters[0] if parameters else '')
            else:
                unsupported_messages += 1
    if unsupported_messages:
        warnings.append(f'{unsupported_messages:,} Endfield SNS media, system or unsupported cells are excluded; '
                        'image/video contents and future message types need separate coverage.')

    rich_contents = _table(catalog, 'RichContentTable', warnings)
    for identity, row in rich_contents.items():
        paragraphs = _mapping(row).get('contentList')
        if not isinstance(paragraphs, list):
            _unsupported()
        for number, paragraph in enumerate(paragraphs):
            add(f'RichContentTable:{identity}:{number}', _mapping(paragraph).get('content'), 'readable', 'tip')

    radios = _table(catalog, 'RadioTable')
    reading_links = list(_table(catalog, 'ReadingPopUpTable', warnings).values())
    reading_links.extend(_table(catalog, 'PrtsDocument', warnings).values())
    for group in _table(catalog, 'PrtsReading', warnings).values():
        reading_links.extend(_mapping(_mapping(group).get('list')).values())
    unresolved_readings = 0
    for row in reading_links:
        _mapping(row)
        reference, override = row.get('contentId'), row.get('overrideRadioId', '')
        if not isinstance(reference, str) or not isinstance(override, str):
            _unsupported()
        if (reference not in rich_contents and reference not in radios) or (override and override not in radios):
            unresolved_readings += 1
    if unresolved_readings:
        warnings.append(f'{unresolved_readings:,} Endfield reading entries reference content outside the supported '
                        'rich-text/radio tables; those document bodies are unavailable.')

    # Operator profile playback explicitly pairs voiceDesc and voId; profile
    # documents use a separate text-only recordDesc widget in the installed UI.
    for identity, character in _table(catalog, 'CharacterTable', warnings).items():
        _mapping(character)
        for field, text_field, kind in (('profileVoice', 'voiceDesc', 'operator_voice'),
                                       ('profileRecord', 'recordDesc', 'operator_record')):
            items = character.get(field)
            if not isinstance(items, list):
                _unsupported()
            for row in items:
                _mapping(row)
                if not isinstance(row.get('id'), str) or not row['id']:
                    _unsupported()
                voice = row.get('voId', '')
                if not isinstance(voice, str):
                    _unsupported()
                add(f'CharacterTable:{identity}:{field}:{row["id"]}', row.get(text_field), kind,
                    'dialogue' if field == 'profileVoice' else 'tip',
                    'unavailable' if field == 'profileVoice' else 'unvoiced', voice)
    return dialogs


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Endfield study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('endfield', data_dir)
    try:
        tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales, prefix='TableCfg/I18nTextTable_')
    except ValueError:
        _unsupported()
    audio_dialog = _table(catalog, 'AudioDialog')
    if not audio_dialog:
        _unsupported()
    paths = audio_paths(audio_dialog)
    audio_ids = audio_id_paths(audio_dialog)
    progress('Reading installed Endfield original voice packages')
    inventory = []
    for layer in ('StreamingAssets', 'Persistent'):
        if (streaming_assets(install, layer) / 'VFS').is_dir():
            values = json.loads(reader(install, data_dir / 'tools/EndfieldReader.dll', 'inventory',
                                       {'language': VOICE_LOCALES[source_locale], 'layer': layer}))
            if not isinstance(values, list) or any(not isinstance(row, dict) or
                not {'block', 'file_id', 'chunk', 'file_hash', 'size'} <= row.keys() or
                type(row['block']) is not int or type(row['size']) is not int or row['size'] <= 0 or
                not isinstance(row['chunk'], str) or not re.fullmatch(r'[0-9A-F]{32}\.chk', row['chunk']) or
                not isinstance(row['file_hash'], str) or not re.fullmatch(r'-?\d+', row['file_hash']) or
                not isinstance(row['file_id'], str) or not re.fullmatch('[0-9a-f]{16}', row['file_id'])
                for row in values):
                _unsupported()
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
    warnings = []
    dialogs = authored_dialogues(catalog)
    dialogs.update(narrative_dialogues(catalog, warnings))
    coverage = {name: 0 for name in ('voiced', 'unvoiced', 'unknown', 'missing_source_metadata', 'missing_locale_recording')}
    rows = dialogue_records(dialogs, paths, tables, source_locale, entries, audio_ids=audio_ids, coverage=coverage)
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed',
            'Endfield files changed during preparation. Wait for the game update to finish, then retry; '
            'the previous language table is retained.', game_files_changed=True, previous_snapshot_retained=True)
    if not rows:
        _unsupported()
    count = sum(bool(row['audio']) for row in rows)
    unknown = sum(row['voice_status'] == 'unknown' for row in rows)
    selected_block = {'chinese': 101, 'english': 102, 'japanese': 103, 'korean': 104}[VOICE_LOCALES[source_locale]]
    if not any(row['block'] == selected_block for row in inventory):
        warnings.append('The selected Endfield voice package was not found in the installed audio inventory. '
                        'Install it through the game language settings and refresh game data.')
    if coverage['missing_source_metadata']:
        warnings.append(f'{coverage["missing_source_metadata"]:,} Endfield voice references have no usable source in the '
                        'current AudioDialog metadata, including unresolved audio events. They remain unavailable; '
                        'installing a voice package cannot repair missing metadata. Refresh toolkit/game metadata when available.')
    if coverage['missing_locale_recording']:
        warnings.append(f'{coverage["missing_locale_recording"]:,} known Endfield voice paths have no recording in the '
                        f'installed {source_locale} audio. Some recordings exist only in particular locales; '
                        'these lines remain unavailable and another language is never substituted.')
    if unknown:
        warnings.append(f'{unknown:,} Endfield narrative lines have unverified voice status and are excluded from silent capture.')
    warnings.append('Endfield coverage is partial: cinematic/video soundtracks and image-only comics or storyboard panels '
                    'do not have verified per-line bindings. Rich-content images are excluded. '
                    'The third-party metadata snapshot may lag the installed game.')
    available = {code for row in rows for code in row['texts']}
    return {'format': 2, 'game': 'endfield', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'metadata_revision': catalog.revision, 'metadata_revision_title': getattr(catalog, 'revision_title', ''),
        'records': rows, 'coverage_warnings': warnings, 'voice_coverage': coverage,
        'missing_translation_locales': [target for target in target_locales if resolve_locale(target, TEXT_LOCALES) not in available],
        'message': f'{len(rows):,} authored {source_locale} lines; {count:,} original voices; partial presentation coverage'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, executable, _destination):
    locale = audio['locale']
    if locale not in SUPPORTED_LOCALES or not audio['source'].startswith('voice/' + VOICE_LOCALES[locale] + '/'):
        raise ValueError('Endfield original voice crosses locales.')
    if f'{voice_hash(audio["source"]):016x}' != audio['file_id'] or not re.fullmatch(r'[0-9A-F]{32}\.chk', audio['chunk']):
        raise ValueError('Invalid Endfield original voice binding.')
    return reader(install, executable, 'voice', {**audio, 'language': VOICE_LOCALES[locale]})
