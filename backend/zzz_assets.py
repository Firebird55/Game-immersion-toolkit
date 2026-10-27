"""Selected official TextMaps joined to installed authored scene/voice bindings."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import game_tools
from .honkai_assets import package_tables
from .languages import audio_locale, resolve_locale
from .models import is_comic_text_id
from .textmaps import display_text
from .voice_assets import VoiceEntry, read_external_table, resolve_links, voice_hash
from .zzz_cinematics import resolve_cinematic_links
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 4
SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
VOICE_FOLDERS = {'en': 'En', 'zh-Hans': 'Cn', 'zh-Hant': 'Cn', 'ja': 'Jp', 'ko': 'Kr'}
VOICE_FAMILIES = {'en': 'english', 'zh-Hans': 'chinese', 'zh-Hant': 'chinese', 'ja': 'japanese', 'ko': 'korean'}
TEXT_LOCALES = {'en': 'EN', 'zh-Hans': '', 'zh-Hant': 'CHT', 'ja': 'JA', 'ko': 'KO',
    'fr': 'FR', 'de': 'DE', 'es-ES': 'ES', 'pt-BR': 'PT', 'ru': 'RU', 'th': 'TH', 'vi': 'VI', 'id': 'ID'}
GENDER = re.compile(r'\{([MF])#([^{}]*)\}')
# Authored TextMap ID, male alternative, female/default source fields. Unknown
# schemas must fail instead of silently removing all free-roam dialogue.
ONGOING_SCHEMAS = (
    ('PMNJCMFLJIL', 'EODLJIEIIGJ', 'DGFCDOGFFGP'),
    ('FGAHJLHNEDB', 'CIBKAFBOGCI', 'PFOBGIIIICG'),
)
# Observed together in the pinned 3.3 configuration revision. These schemas are
# explicit: renamed/new fields must be reviewed before certifying silence.
MESSAGE_FIELDS = frozenset(('EGBBBFIINLO', 'PFOAJKNPCHL', 'NMIFFJEFBJI', 'BKAEOOPMGNC',
    'HPKJODNLJOA', 'GJNMPOBFICI', 'LDHNMACDKLH', 'MFHGKPHENGE', 'HBPLELJNAEA', 'FMOFACKFIMM',
    'ONEHPCHLKMM', 'FNOKFPDDECI', 'NAPGHEGEOOC', 'HFEPEHJGIAN', 'GGHOAADLHCF', 'EEJNOOGPFND',
    'BKABBJFGMNK', 'LDOINOBMLGN', 'EEDAJDFAKEN', 'JAEBGEAAPNB'))
TIP_FIELDS = frozenset(('KEGKBLHLMBF', 'BHLFCEAPFIG', 'NCDPMAKENFG', 'EFDGGDAACEO', 'KDPLFOOHOAA',
    'MCILFMGEHFE', 'NACIONHDABL', 'ICMKKEADFDE', 'FDCIOBOBHIE', 'NMMACKNBLKO', 'MILOEOOHMLN',
    'GCHFKNAENPG', 'FNHBBPCONOL', 'FFNNCACHDLN', 'NPDBBLABDAK', 'IOBBCFLDLOE'))
MESSAGE_CHOICES = ('FNOKFPDDECI', 'NAPGHEGEOOC', 'GGHOAADLHCF', 'EEJNOOGPFND')
TEXT_ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_-]*')
MESSAGE_SOURCE = re.compile(r'VO_Message/[A-Za-z0-9_-]+/Message_[A-Za-z0-9_-]+', re.I)
TIP_SOURCE = re.compile(r'(?:VO_(?:Tips|Chessboard|Level|Monthlycard)/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+|'
                        r'(?:Accompany|Level|Chessboard|Tips|OngoingMainCity)_[A-Za-z0-9_-]+)', re.I)


def ongoing_links(config):
    rows = next((value for value in config.values() if isinstance(value, list)), [])
    schema = next((fields for fields in ONGOING_SCHEMAS if rows and all(field in rows[0] for field in fields)), None)
    if schema is None:
        raise ValueError('Unsupported ZZZ ongoing dialogue schema; previous complete table retained.')
    text_field, male_field, female_field = schema
    links = []
    for item in rows:
        if not isinstance(item, dict) or not all(field in item for field in schema):
            raise ValueError('Unsupported ZZZ ongoing dialogue schema; previous complete table retained.')
        identity = str(item.get(text_field) or '')
        if not identity:
            continue
        male, female = str(item.get(male_field) or ''), str(item.get(female_field) or '')
        channel = 'gameplay' if 'ongoinglevel' in identity.casefold() else 'tip'
        if not male and not female:
            links.append({'text_id': identity, 'source': '', 'gender': None,
                'channels': [channel], 'dialogue_kind': 'ambient', 'voice_status': 'unvoiced'})
        for gender, source in (('M', male), ('F', female)):
            if source:
                links.append({'text_id': identity, 'source': source,
                    'gender': gender if male and female and male != female else None,
                    'channels': [channel], 'dialogue_kind': 'ambient', 'voice_status': 'unavailable'})
    return links


def _config_rows(config, fields, strings, name):
    lists = [value for value in config.values() if isinstance(value, list)] if isinstance(config, dict) else []
    if len(lists) != 1 or not lists[0] or any(not isinstance(row, dict) or set(row) != fields or
            any(not isinstance(row[key], str) for key in strings) for row in lists[0]):
        raise PreparationFailure('zzz_dialogue_schema',
            f'ZZZ {name} uses an unsupported table format. Update the toolkit for this game version and retry preparation; the previous index is retained.')
    return lists[0]


def message_links(config, textmap):
    rows = _config_rows(config, MESSAGE_FIELDS, ('LDHNMACDKLH', 'BKAEOOPMGNC', 'GJNMPOBFICI', *MESSAGE_CHOICES), 'message dialogue')
    links, unresolved = [], 0
    for row in rows:
        identity = row['LDHNMACDKLH']
        if TEXT_ID.fullmatch(identity) and identity in textmap:
            sources = {row[key] for key in ('BKAEOOPMGNC', 'GJNMPOBFICI') if row[key]}
            # The observed source columns agree. Do not guess gender or choose
            # whichever asset happens to be installed when future variants differ.
            source = next(iter(sources)) if len(sources) == 1 else ''
            source = source if MESSAGE_SOURCE.fullmatch(source) else ''
            unresolved += bool(sources and not source)
            links.append({'text_id': identity, 'source': source, 'dialogue_kind': 'message',
                          'voice_status': 'unavailable' if sources else 'unvoiced',
                          'channels': ['dialogue', 'cinematic']})
        for key in MESSAGE_CHOICES:
            if TEXT_ID.fullmatch(row[key]) and row[key] in textmap:
                # The message's own recording is not the selectable response.
                links.append({'text_id': row[key], 'source': '', 'dialogue_kind': 'choice',
                              'voice_status': 'unknown', 'channels': ['dialogue', 'cinematic']})
    return links, {'rows': len(rows), 'text_references': len(links), 'unresolved_voice_variants': unresolved}


def tip_links(config, textmap):
    rows = _config_rows(config, TIP_FIELDS, ('BHLFCEAPFIG', 'NMMACKNBLKO', 'FNHBBPCONOL',
        'NPDBBLABDAK', 'KDPLFOOHOAA', 'GCHFKNAENPG'), 'gameplay tips')
    links, unresolved = [], 0
    for row in rows:
        if not isinstance(row['FFNNCACHDLN'], list) or not all(isinstance(event, str) for event in row['FFNNCACHDLN']):
            raise PreparationFailure('zzz_dialogue_schema', 'ZZZ gameplay tip audio events use an unsupported format. Update the toolkit and retry; the previous index is retained.')
        identity = row['BHLFCEAPFIG']
        if not TEXT_ID.fullmatch(identity) or identity not in textmap:
            continue
        primary, alternate, reaction = (row[key] for key in ('NMMACKNBLKO', 'NPDBBLABDAK', 'FNHBBPCONOL'))
        source = primary if (not alternate or alternate == primary) and TIP_SOURCE.fullmatch(primary) else ''
        unresolved += bool((primary or alternate) and not source)
        # A reaction pool or a sound event never substitutes for sentence audio.
        status = 'unavailable' if primary or alternate else 'unknown' if reaction or row['FFNNCACHDLN'] or row['KDPLFOOHOAA'] else 'unvoiced'
        links.append({'text_id': identity, 'source': source, 'dialogue_kind': 'gameplay_tip',
                      'voice_status': status, 'channels': ['tip', 'gameplay']})
    return links, {'rows': len(rows), 'text_references': len(links), 'unresolved_voice_variants': unresolved}


def supplemental_links(revision, textmap):
    links, diagnostics = [], {}
    for name, reader in (('MessageConfigTemplateTb', message_links), ('TipsConfigTemplateTb', tip_links)):
        data = json.loads(game_tools.download(f'https://git.mero.moe/dimbreath/ZenlessData/raw/commit/{revision}/FileCfg/{name}.json'))
        current, diagnostics[name] = reader(data, textmap)
        links.extend(current)
    return links, diagnostics


def game_data(install):
    path = install if install.name.endswith('_Data') else install / 'ZenlessZoneZero_Data'
    if not path.is_dir():
        raise ValueError('Choose the installed Zenless Zone Zero game folder.')
    return path


def fingerprint(install):
    root = game_data(install)
    files = []
    for layer in ('StreamingAssets', 'Persistent'):
        directory = root / layer
        files.extend(p for name in ('res_version', 'res_version_persist') if (p := directory / name).is_file())
        files.extend((directory / 'Audio/Windows/Full').glob('*/*.pck'))
        files.extend((directory / 'Blocks').glob('*.blk'))
    values = [f'{p.relative_to(root).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}' for p in sorted(set(files))]
    return hashlib.sha256('\n'.join(values).encode()).hexdigest()


def localized_inventory(root, locale):
    namespace_names, entries = set(), {}
    for layer in ('StreamingAssets', 'Persistent'):
        current, ambiguous = {}, set()
        for package in sorted((root / layer / 'Audio/Windows/Full' / VOICE_FOLDERS[locale]).glob('*.pck')):
            languages, _, _ = package_tables(package)
            namespace_names.update(name.casefold() for name in languages.values() if name.casefold() != 'sfx')
            for entry in read_external_table(package):
                if entry.file_id in current and current[entry.file_id] != entry:
                    ambiguous.add(entry.file_id)
                current[entry.file_id] = entry
        for identity in ambiguous:
            current.pop(identity, None)
            entries.pop(identity, None)
        # Persistent resources explicitly replace the corresponding base ID.
        entries.update(current)
    if not namespace_names:
        return None, {}
    if len(namespace_names) != 1:
        raise ValueError('The selected ZZZ voice pack has ambiguous language metadata.')
    namespace, = namespace_names
    if not re.fullmatch(re.escape(VOICE_FAMILIES[locale]) + r'(?:\([a-z]+\))?', namespace):
        raise ValueError('The installed ZZZ voice pack does not match its selected language.')
    return namespace, entries


def _variants(text):
    return {gender: display_text(value) for gender, value in GENDER.findall(str(text))}


def _text(text, gender):
    variants = _variants(text)
    return variants.get(gender, '') if variants else display_text(text)


def build_records(tables, source_locale, selected, links, prefixes, entries, cinematic, namespace):
    expanded, channels, evidence, kinds = [], {}, {}, {}
    for link in links:
        identity = link['text_id']
        channels.setdefault(identity, set()).update(link.get('channels', ['dialogue', 'cinematic']))
        kinds.setdefault(identity, set()).add(link.get('dialogue_kind') or
            ('comic' if is_comic_text_id(identity) else 'cutscene' if identity.startswith('CS_') else 'conversation'))
        status = link.get('voice_status') or ('unavailable' if link.get('source') else 'unknown')
        sources = _variants(link['source'])
        if sources:
            expanded.extend({'text_id': identity + ':' + gender, 'source': source} for gender, source in sources.items() if source)
            for gender, source in sources.items():
                evidence.setdefault(identity + ':' + gender, set()).add(status if source else 'unknown')
        elif link.get('gender'):
            expanded.append({'text_id': identity + ':' + link['gender'], 'source': link['source']})
            evidence.setdefault(identity + ':' + link['gender'], set()).add(status)
        else:
            if link['source']:
                expanded.append({'text_id': identity, 'source': link['source']})
            evidence.setdefault(identity, set()).add(status)
    bindings = resolve_links(expanded, prefixes, entries, namespace=namespace) if namespace else {}
    bindings.update(cinematic)
    identities = set(channels) | set(cinematic) | {key for key in tables[source_locale] if is_comic_text_id(key)}
    rows = []
    for identity in sorted(identities):
        values = {locale: table.get(identity, '') for locale, table in tables.items()}
        gendered = any(_variants(values.get(locale, '')) for locale in selected) or any(identity + ':' + gender in bindings for gender in ('M', 'F'))
        for gender in ('M', 'F') if gendered else (None,):
            text = _text(values.get(source_locale, ''), gender)
            if not text:
                continue
            texts = {locale: value for locale in selected if (value := _text(values.get(locale, ''), gender))}
            binding = bindings.get(identity + ':' + gender, bindings.get(identity)) if gender else bindings.get(identity)
            audio = None
            if binding:
                stat = Path(binding['package']).stat()
                audio = {**binding, 'locale': audio_locale(source_locale), 'namespace': namespace,
                         'package_size': stat.st_size, 'package_mtime_ns': stat.st_mtime_ns}
            row_id = identity + ':' + gender if gender else identity
            states = evidence.get(row_id, evidence.get(identity, {'unknown'}))
            voice_status = 'voiced' if audio else 'unavailable' if 'unavailable' in states else 'unvoiced' if states == {'unvoiced'} else 'unknown'
            kind = next((kind for kind in ('comic', 'cutscene', 'conversation', 'message', 'choice', 'narration', 'ambient', 'gameplay_tip') if kind in kinds.get(identity, set())),
                'comic' if is_comic_text_id(identity) else 'cutscene' if identity.startswith('CS_') else 'conversation')
            rows.append({'text_id': row_id, 'source_locale': source_locale, 'source_text': text,
                'texts': texts, 'english': _text(values.get('en', ''), gender), 'chinese': texts.get('zh-Hans', ''),
                'audio_locale': audio_locale(source_locale), 'audio': audio,
                'player_voice': {'M': 'male', 'F': 'female'}.get(gender),
                'member_text_ids': [identity] if gender else None,
                'voice_status': voice_status, 'dialogue_kind': kind,
                'channels': sorted(channels.get(identity, {'cinematic'}))})
    return rows


def _tables(directory, revision, locales):
    result = {}
    for locale in locales:
        merged = {}
        prefix = '_' + TEXT_LOCALES[locale] if TEXT_LOCALES[locale] else ''
        for suffix in ('TemplateTb', 'OverwriteTemplateTb'):
            name = 'TextMap' + prefix + suffix + '.json'
            data = game_tools.download(f'https://git.mero.moe/dimbreath/ZenlessData/raw/commit/{revision}/TextMap/{name}')
            values = json.loads(data)
            if not isinstance(values, dict) or (suffix == 'TemplateTb' and not values) or not all(isinstance(value, str) for value in values.values()):
                raise ValueError('The requested official ZZZ TextMap is empty or unsupported.')
            merged.update(values)
        result[locale] = merged
    return result


def _links(root, directory, revision, progress):
    project = directory.parent.parent
    tools = project / 'work/voice-assets'
    reader = tools / 'galgame-perform.ts'
    if not reader.is_file() or not shutil.which('node'):
        raise ValueError('Install the ZZZ scene tools in Setup before preparing a language.')
    game_tools.refresh_zzz_metadata(project, revision=revision)
    code = Path(__file__).resolve().parents[1]
    signature = hashlib.sha256(b''.join([fingerprint(root).encode(), reader.read_bytes(),
        *((code / 'scripts' / name).read_bytes() for name in ('extract_voice_links.mjs', 'extract_cinematic_links.mjs',
            'scene-catalog.mjs', 'cinematic-links.mjs', 'comic-links.mjs', 'zzz-dialogue.mjs')),
        *( (tools / name).read_bytes() for name in game_tools.METADATA_FILES)])).hexdigest()
    cache = directory / 'scene-links.json'
    try:
        old = json.loads(cache.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        old = {}
    if old.get('signature') != signature:
        links = []
        diagnostics = []
        for category in ('dialogue', 'comic'):
            progress('Reading installed ZZZ ' + category + ' subtitle/voice bindings')
            name = 'language-links-' + category + '.json'
            result = subprocess.run(['node', str(code / 'scripts/extract_voice_links.mjs'), str(root), str(tools), category, name],
                cwd=code, capture_output=True, timeout=1200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise PreparationFailure('zzz_scene_catalog', 'ZZZ subtitle/voice links could not be read from the installed resource catalog. Update the toolkit and verify game files in the launcher, then retry preparation.')
            links.extend({**link, 'channels': ['cinematic'] if category == 'comic' else link.get('channels', ['dialogue', 'cinematic'])}
                         for link in json.loads((tools / name).read_text(encoding='utf-8')))
            diagnostics.append(json.loads((tools / (name + '.diagnostics.json')).read_text(encoding='utf-8')))
        progress('Reading installed ZZZ cinematic timelines and their original voice events')
        result = subprocess.run(['node', str(code / 'scripts/extract_cinematic_links.mjs'), str(root), str(tools)],
            cwd=code, capture_output=True, timeout=1200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise PreparationFailure('zzz_cinematic_catalog', 'ZZZ cinematic voice links could not be read from the installed resource catalog. Update the toolkit and verify game files in the launcher, then retry preparation.')
        old = {'signature': signature, 'links': links, 'diagnostics': diagnostics,
               'cinematic': json.loads((tools / 'scene-links-cinematic.json').read_text(encoding='utf-8'))}
        cache.parent.mkdir(parents=True, exist_ok=True)
        pending = cache.with_suffix('.pending'); pending.write_text(json.dumps(old), encoding='utf-8'); pending.replace(cache)
    return old['links'], old['cinematic'], tools, old['diagnostics']


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported ZZZ study/audio language.')
    root, stamp = game_data(install), fingerprint(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    revision = json.loads(game_tools.download('https://git.mero.moe/api/v1/repos/dimbreath/ZenlessData/branches/master'))['commit']['id']
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('ZZZ official text revision is unavailable.')
    tables = _tables(data_dir, revision, selected)
    links, cinematic_links, tools, scene_diagnostics = _links(root, data_dir, revision, progress)
    ongoing = json.loads((tools / 'OngoingTipsConfigTemplateTb.json').read_text(encoding='utf-8'))
    links.extend(ongoing_links(ongoing))
    progress('Reading official ZZZ messages, reply choices and gameplay tip bindings')
    supplemental, table_diagnostics = supplemental_links(revision, tables[source_locale])
    links.extend(supplemental)
    namespace, inventory = localized_inventory(root, source_locale)
    cinematic = resolve_cinematic_links(cinematic_links, root,
        json.loads((tools / 'AudioResourceData.json').read_text(encoding='utf-8')),
        folder=VOICE_FOLDERS[source_locale], namespace=namespace) if namespace else {}
    links.extend({'text_id': link['text_id'], 'source': '', 'channels': ['cinematic'],
                  'dialogue_kind': 'cutscene', 'voice_status': 'unavailable' if link.get('event') else 'unknown'}
                 for link in cinematic_links if re.fullmatch(r'CS_[A-Za-z0-9_]+', link.get('text_id', '')))
    prefixes = json.loads((tools / 'VoiceData.json').read_text(encoding='utf-8'))['allPrefixes']
    rows = build_records(tables, source_locale, selected, links, prefixes, inventory, cinematic, namespace)
    if not rows or fingerprint(install) != stamp:
        raise ValueError('ZZZ files changed or selected text is incomplete; previous table retained.')
    mapped = sum(bool(row['audio']) for row in rows)
    silent = sum(row['voice_status'] == 'unvoiced' for row in rows)
    unresolved = sum(item['unresolved_scenes'] for item in scene_diagnostics)
    unsupported = sum(sum(item.get('unsupported_dialogue_nodes', {}).values()) for item in scene_diagnostics)
    available = {locale for row in rows for locale in row['texts']}
    missing = [target for target, locale in targets.items() if locale not in available]
    return {'format': 2, 'game': 'zzz', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'metadata_revision': revision, 'records': rows, 'missing_translation_locales': missing,
        'coverage_warnings': [
            *([f'{unresolved:,} referenced scenes are absent from the installed catalog.'] if unresolved else []),
            *([f'{unsupported:,} dialogue objects use an unsupported format; update the toolkit for this game version.'] if unsupported else []),
            'Message reply choices without explicit silence and ambiguous tip voice variants remain unresolved. Clue recordings and additional event-specific tables are not comprehensively imported. Unknown or missing voices are not treated as silent dialogue.'],
        'coverage': {'scene_catalogs': scene_diagnostics, 'dialogue_tables': table_diagnostics, 'verified_unvoiced': silent,
                     'unknown_voice_status': sum(row['voice_status'] == 'unknown' for row in rows)},
        'message': f'{len(rows):,} official {source_locale} entries; {mapped:,} original voices; {silent:,} authored unvoiced entries' +
        (f'; {unresolved:,} metadata scenes are not in the installed catalog' if unresolved else '') +
        (f'; {unsupported:,} dialogue objects use a new format: update the toolkit for full coverage' if unsupported else '') +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; selected voice pack is missing or incomplete' if not mapped and namespace is None else
         '; no verified original bindings; check the installed game version and scene metadata' if not mapped else '')}


def _validate_audio(install, audio):
    locale = audio.get('locale')
    if locale not in SUPPORTED_LOCALES:
        raise ValueError('Invalid ZZZ original voice locale.')
    root, path = game_data(install).resolve(), Path(audio['package']).resolve()
    allowed = [root / layer / 'Audio/Windows/Full' / VOICE_FOLDERS[locale] for layer in ('StreamingAssets', 'Persistent')]
    namespace = audio.get('namespace', '')
    if path.parent not in allowed or path.suffix.casefold() != '.pck' or not re.fullmatch(re.escape(VOICE_FAMILIES[locale]) + r'(?:\([a-z]+\))?', namespace):
        raise ValueError('ZZZ original voice package does not match its selected locale.')
    stat = path.stat()
    if stat.st_size != audio['package_size'] or stat.st_mtime_ns != audio['package_mtime_ns']:
        raise ValueError('ZZZ voice package changed; refresh the prepared language.')
    if audio.get('source'):
        if not audio['source'].startswith(namespace + '/ex/') or voice_hash(audio['source']) != int(audio['file_id'], 16):
            raise ValueError('ZZZ authored original voice source does not match its locale or identity.')
    elif audio.get('matched_by') != 'authored_cinematic_event' or not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', audio.get('event', ''), re.I):
        raise ValueError('ZZZ original voice has no authored subtitle binding.')
    entry = VoiceEntry(path, int(audio['offset']), int(audio['size']), int(audio['file_id'], 16))
    if entry.offset < 28 or not 0 < entry.size <= 64 * 1024 * 1024 or entry.offset + entry.size > stat.st_size:
        raise ValueError('Invalid ZZZ original voice bounds.')
    return entry


def extract_voice(install, audio, _executable, _destination):
    entry = _validate_audio(install, audio)
    data = entry.read()
    _validate_audio(install, audio)
    return data


def extract_voices(install, audios, executable, destination):
    if len({audio.get('locale') for audio in audios}) > 1:
        raise ValueError('Original voice batch crosses study/audio locales.')
    return [extract_voice(install, audio, executable, destination) for audio in audios]
