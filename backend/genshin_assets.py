"""Genshin Impact authored dialogue hashes and original locale voice paths."""
from collections import defaultdict
import configparser
from pathlib import PurePosixPath
import re

from . import hoyo_dialogue as common
from .dialogue_catalog import DialogueCatalog, selected_tables
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = common.SUPPORTED_LOCALES
TEXT_LOCALES = {**common.TEXT_LOCALES, 'it': 'IT', 'tr': 'TR',
                'ru': ('RU_0', 'RU_1'), 'th': ('TH_0', 'TH_1')}
# Reviewed schemas describe the same authored fields across client versions.
DIALOG_SCHEMAS = (
    ('dialogList', 'id', 'talkContentTextMapHash'),
    ('PCIAMAFDDAA', 'id', 'LKECPJIFFEE'),
    ('PFALHAKIILD', 'OIFGMOHKPOI', 'OACNIBLFFDI'),
    ('GDDPNNHLGBL', 'ANKFNLMKOII', 'DMIFDJDEFAL'),
)
VOICE_SCHEMAS = (
    ('sourceNames', 'sourceFileName', 'gameTrigger', 'gameTriggerArgs'),
    ('SourceNames', 'sourceFileName', 'GameTrigger', 'GameTriggerArgs'),
    ('SourceNames', 'sourceFileName', 'GameTrigger', 'gameTriggerArgs'),
    ('GLDBLKKLJHP', 'CFIKOCLOKGH', 'NLGBEEIGDJP', 'BMPENHIILJG'),
    ('BCNMCOBNGJB', 'KFPDDPCDHJO', 'IEIJJNGJDID', 'BNCPBCFLDNL'),
    ('JKDJFGBGOEB', 'DCIHFJLBLAP', 'BHOKINENJBN', 'MEDGFBMLDDK'),
    ('NEJBKIJIBHJ', 'NKPOOPONEHG', 'JOMDCMBGNMB', 'BKGHEBIGJNC'),
    ('JKHGLBHOKIC', 'BJDAJEKPCFP', 'HPIPCKOOMLL', 'HEKJMGHIJBM'),
    ('LANPKDLFAEG', 'CGDCGMHJCIF', 'KICAJHAAJMH', 'BBHPPDMPJFF'),
)


def archive_sources(install):
    return common.archive_sources(install, 'genshin')


def fingerprint(install):
    return common.fingerprint(install, 'genshin')


def _identity(value):
    return str(value) if (isinstance(value, int) and not isinstance(value, bool) and value > 0
                          or isinstance(value, str) and value.isdecimal() and int(value) > 0) else None


def _unique(values):
    return {identity: next(iter(hashes)) for identity, hashes in values.items() if len(hashes) == 1}


def _warn(warnings, message):
    if warnings is not None and message not in warnings:
        warnings.append(message)


def dialogue_hashes(talks, fallback=(), warnings=None, annotations=None):
    values = defaultdict(set)
    for talk in talks:
        if not isinstance(talk, dict):
            _warn(warnings, 'Some Genshin Talk records use an unsupported structure.')
            continue
        recognized = False
        for array, identity, text in DIALOG_SCHEMAS:
            if array not in talk:
                continue
            recognized = True
            if not isinstance(talk[array], list):
                _warn(warnings, 'Some Genshin Talk records use an unsupported structure.')
                continue
            for row in talk[array]:
                if not isinstance(row, dict):
                    _warn(warnings, 'Some Genshin Talk records use an unsupported structure.')
                    continue
                key, content = _identity(row.get(identity)), _identity(row.get(text))
                if key and content:
                    values[key].add(content)
                    if annotations is not None:
                        kind = {'ACTIVITY': 'event_dialogue', 'GADGET': 'interaction',
                                'NARRATOR': 'narration', 'STORYBOARD': 'storyboard'}.get(talk.get('type'))
                        if kind:
                            annotations[key] = {'dialogue_kind': kind, 'channels':
                                ['dialogue', 'cinematic'] if kind in {'narration', 'storyboard'} else ['dialogue']}
                elif text not in row and row.get(identity):
                    # Empty routing nodes are valid; unfamiliar nonempty text
                    # fields still need to be visible during compatibility review.
                    _warn(warnings, 'Some Genshin Talk nodes have no recognized subtitle field.')
        if not recognized and talk:
            _warn(warnings, 'Some Genshin Talk records use an unsupported structure.')
    # Global dialogue IDs cover ambient/optional entries absent from Talk assets.
    # Runtime Talk content wins, including conflicts (which must stay excluded).
    runtime_ids = set(values)
    for row in fallback:
        if not isinstance(row, dict):
            _warn(warnings, 'Some Genshin global dialogue records use an unsupported structure.')
            continue
        key = _identity(row.get('id')) or _identity(row.get('GFLDJMJKIKE'))
        content = _identity(row.get('talkContentTextMapHash'))
        if key and content and key not in runtime_ids:
            values[key].add(content)
        elif not key or 'talkContentTextMapHash' not in row:
            _warn(warnings, 'Some Genshin global dialogue records use an unsupported structure.')
        if annotations is not None and key and content in values.get(key, ()):
            role = row.get('talkRole')
            role_type = role.get('type', '') if isinstance(role, dict) else ''
            if row.get('talkShowType') == 'TALK_SHOW_FORCE_SELECT':
                annotations[key] = {'dialogue_kind': 'choice', 'channels': ['dialogue']}
            elif isinstance(role_type, str) and 'BLACK_SCREEN' in role_type:
                annotations[key] = {'dialogue_kind': 'narration', 'channels': ['dialogue', 'cinematic']}
    # Conflicting upstream records cannot silently select a translation.
    if any(len(hashes) != 1 for hashes in values.values()):
        _warn(warnings, 'Conflicting Genshin dialogue identities were excluded.')
    return _unique(values)


def dialogue_links(voice_maps, hashes, locale, reminders=None, *, cards=None, warnings=None, authored=None):
    reminders = reminders or {}
    tables = {'Dialog': hashes, 'DungeonReminder': reminders, 'Card': cards or {}}
    values = defaultdict(set)
    known_structures, unknown_structures = 0, 0
    for mapping in voice_maps:
        if not isinstance(mapping, dict):
            _warn(warnings, 'Some Genshin voice records use an unsupported structure.')
            continue
        for voice in mapping.values():
            if not isinstance(voice, dict):
                continue
            recognized = False
            for array, filename, trigger, argument in VOICE_SCHEMAS:
                if array not in voice:
                    continue
                recognized = True
                known_structures += 1
                kind = voice.get(trigger)
                if not isinstance(kind, str) or kind not in tables:
                    continue
                identity = _identity(voice.get(argument))
                table = tables[kind]
                if identity not in table:
                    continue
                if authored is not None:
                    authored.add((kind, identity))
                if not isinstance(voice[array], list):
                    _warn(warnings, 'Some Genshin voice records use an unsupported structure.')
                    continue
                for source in voice[array]:
                    if not isinstance(source, dict):
                        _warn(warnings, 'Some Genshin voice records use an unsupported structure.')
                        continue
                    path = source.get(filename, '')
                    if (isinstance(path, str) and path.casefold().endswith('.wem')
                            and not path.startswith(('\\', '/')) and ':' not in path
                            and '..' not in re.split(r'[/\\]', path)):
                        values[(kind, identity)].add(common.VOICE_NAMES[locale] + '\\' + path)
                    else:
                        _warn(warnings, 'Some Genshin voice sources could not be resolved safely.')
            if not recognized and voice:
                unknown_structures += 1
                _warn(warnings, 'Some Genshin voice records use an unsupported structure.')
    if unknown_structures and not known_structures:
        raise PreparationFailure('unsupported_game_format',
            'Genshin voice metadata uses an unrecognized schema. Update the toolkit and refresh game data; the previous index is retained.')
    links = []
    for (kind, identity), sources in values.items():
        # A dialogue may explicitly have player variants. Unrelated multiple
        # performances are excluded instead of choosing the first source.
        genders = {source: ('female' if re.search(r'(?:^|[/\\_])(?:girl|female|lumine)(?:[/\\_.]|$)', source, re.I) else
                           'male' if re.search(r'(?:^|[/\\_])(?:boy|male|aether)(?:[/\\_.]|$)', source, re.I) else None)
                   for source in sources}
        if len(sources) > 1 and (len(sources) != 2 or set(genders.values()) != {'male', 'female'}):
            _warn(warnings, 'Ambiguous Genshin voice performances were left unavailable.')
            continue
        for source in sorted(sources):
            gender = genders[source]
            suffix = ':' + gender if len(sources) > 1 else ''
            table = tables[kind]
            row_id = {'Dialog': '', 'DungeonReminder': 'reminder-', 'Card': 'card-'}[kind] + identity
            links.append({'id': row_id + suffix, 'hash': table[identity], 'source': source,
                          'player_voice': gender if len(sources) > 1 else None})
    return links


def reminder_hashes(rows):
    fields = ('contentTextMapHash', 'BPKEKEBFEIG', 'HNDLKHJFLNF')
    values = defaultdict(set)
    for row in rows:
        if isinstance(row, dict) and (identity := _identity(row.get('id'))):
            for field in fields:
                if value := _identity(row.get(field)):
                    values[identity].add(value)
    return _unique(values)


def card_hashes(rows, tutorials=(), warnings=None):
    values = defaultdict(set)
    for row in rows:
        if not isinstance(row, dict):
            _warn(warnings, 'Some Genshin card dialogue records use an unsupported structure.')
            continue
        voices, texts = row.get('talkVoiceId'), row.get('talkContent')
        if not isinstance(voices, list) or not isinstance(texts, list) or len(voices) != len(texts):
            _warn(warnings, 'Some Genshin card dialogue arrays are incompatible.')
            continue
        # Preserve array positions: filtering zero IDs before pairing shifts text.
        for identity, content in zip(voices, texts):
            if (key := _identity(identity)) and (value := _identity(content)):
                values[key].add(value)
    for row in tutorials:
        if isinstance(row, dict) and (key := _identity(row.get('voiceTriggerId'))):
            if value := _identity(row.get('commentTextMapHash')):
                values[key].add(value)
    if any(len(hashes) != 1 for hashes in values.values()):
        _warn(warnings, 'Conflicting Genshin card voice identities were excluded.')
    return _unique(values)


def _table(catalog, name, warnings):
    value = catalog.file('ExcelBinOutput/' + name + '.json', optional=True)
    if value == {} or value == []:
        _warn(warnings, 'Some Genshin narrative tables are unavailable in the metadata snapshot.')
        return []
    if not isinstance(value, list):
        raise PreparationFailure('unsupported_game_format',
            'Genshin narrative tables use an unsupported structure. Update the toolkit and refresh game data; the previous index is retained.')
    return value


def _metadata_version(install, catalog, warnings):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(install / 'config.ini', encoding='utf-8-sig')
    versions = {parser.get(section, 'game_version') for section in parser.sections()
                if parser.has_option(section, 'game_version')}
    title = getattr(catalog, 'revision_title', '')
    match = re.search(r'(?:CN|OS)RELWin(\d+\.\d+\.\d+)(?:_|$)', title)
    if len(versions) == 1 and match:
        if next(iter(versions)) != match[1]:
            raise PreparationFailure('unsupported_game_format',
                'The Genshin metadata version does not match the installed game. Finish the launcher update or retry after matching metadata is available; the previous index is retained.')
        return True
    else:
        _warn(warnings, 'The Genshin metadata version could not be matched to the installed client.')
        return False


def readable_records(catalog, locales, source_locale, existing, warnings):
    if not hasattr(catalog, 'directory_text'):
        _warn(warnings, 'Genshin readable text is unavailable in this metadata snapshot.')
        return []
    localized = {}
    for locale in locales:
        code = {'ru': 'RU', 'th': 'TH'}.get(locale, TEXT_LOCALES[locale])
        files = {}
        for name, text in catalog.directory_text('Readable/' + code):
            path = PurePosixPath(name)
            ending = '' if code == 'CHS' else '_' + code
            if len(path.parts) != 1 or (ending and not path.stem.endswith(ending)):
                _warn(warnings, 'Some Genshin readable identities use an unsupported format.')
                continue
            identity = path.stem[:-len(ending)] if ending else path.stem
            if identity in files:
                raise PreparationFailure('unsupported_game_format',
                    'Genshin readable identities are ambiguous. Update the toolkit and refresh game data; the previous index is retained.')
            paragraphs = re.split(r'\n[ \t]*\n+', text.replace('\r\n', '\n').replace('\r', '\n').strip())
            files[identity] = [common.display_text(paragraph) for paragraph in paragraphs]
        localized[locale] = files
    authored_audio_text = {row['source_text'] for row in existing
                           if row['voice_status'] in {'voiced', 'unavailable'}}
    records = []
    for identity, paragraphs in localized[source_locale].items():
        translations = {}
        for locale, files in localized.items():
            target = files.get(identity)
            if target is not None and len(target) == len(paragraphs):
                translations[locale] = target
            elif locale != source_locale:
                _warn(warnings, 'Some Genshin readable translations have missing or incompatible paragraph boundaries.')
        for index, text in enumerate(paragraphs):
            if not text:
                continue
            texts = {locale: values[index] for locale, values in translations.items() if values[index]}
            # Book assets are the text-only Books/Inventory presentation. Other
            # readable assets may also participate in voiced quest/cinematic UI.
            silent = bool(re.fullmatch(r'Book\d+', identity)) and text not in authored_audio_text
            records.append({'text_id': f'genshin:readable:{identity}:{index}', 'source_locale': source_locale,
                'source_text': text, 'texts': texts, 'english': texts.get('en', ''),
                'chinese': texts.get('zh-Hans', ''), 'audio_locale': common.audio_locale(source_locale),
                'audio': None, 'player_voice': None, 'channels': ['dialogue', 'tip'],
                'voice_status': 'unvoiced' if silent else 'unknown', 'dialogue_kind': 'readable'})
    return records


def _complete_links(links, tables, authored, reminder_rows):
    present = {link['id'].split(':')[0] for link in links}
    silent_reminders = {str(row['id']) for row in reminder_rows
                        if isinstance(row, dict) and row.get('hasAudio') is False and _identity(row.get('id'))}
    voiced_reminders = {str(row['id']) for row in reminder_rows
                        if isinstance(row, dict) and row.get('hasAudio') is True and _identity(row.get('id'))}
    for kind, hashes in tables.items():
        prefix = {'Dialog': '', 'DungeonReminder': 'reminder-', 'Card': 'card-'}[kind]
        for identity, content in hashes.items():
            row_id = prefix + identity
            if row_id not in present:
                status = ('unavailable' if (kind, identity) in authored or
                          kind == 'DungeonReminder' and identity in voiced_reminders else
                          'unvoiced' if kind == 'DungeonReminder' and identity in silent_reminders else 'unknown')
                links.append({'id': row_id, 'hash': content, 'source': None, 'voice_status': status})
    for link in links:
        if link['id'].startswith('reminder-'):
            link.update(channels=['dialogue', 'tip', 'gameplay'], dialogue_kind='reminder')
        elif link['id'].startswith('card-'):
            link.update(channels=['dialogue', 'gameplay'], dialogue_kind='card_dialogue')
        else:
            link['dialogue_kind'] = 'conversation'
    return links


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Genshin study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('genshin', data_dir)
    warnings = []
    version_matches = _metadata_version(install, catalog, warnings)
    progress('Reading Genshin metadata and validating original installed voice bindings')
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales, medium=True)
    dialog_rows = _table(catalog, 'DialogExcelConfigData', warnings)
    annotations = {}
    hashes = dialogue_hashes(catalog.directory_json('BinOutput/Talk'), dialog_rows, warnings, annotations)
    if not hashes:
        raise PreparationFailure('unsupported_game_format',
            'No supported Genshin dialogue identities were found. Update the toolkit and refresh game data; the previous index is retained.')
    reminder_rows = _table(catalog, 'ReminderExcelConfigData', warnings)
    reminders = reminder_hashes(reminder_rows)
    cards = card_hashes(_table(catalog, 'GCGTalkDetailExcelConfigData', warnings),
                        _table(catalog, 'GCGTutorialTextExcelConfigData', warnings), warnings)
    authored = set()
    links = dialogue_links(catalog.directory_json('BinOutput/Voice'), hashes, source_locale,
                           reminders, cards=cards, warnings=warnings, authored=authored)
    links = _complete_links(links, {'Dialog': hashes, 'DungeonReminder': reminders, 'Card': cards},
                            authored, reminder_rows)
    for link in links:
        if annotation := annotations.get(link['id'].split(':', 1)[0]):
            link.update(annotation)
    entries = common.inventory(install, 'genshin', source_locale)
    # Reminders use a distinct hash namespace. In this modality Medium takes
    # priority; ordinary dialogue keeps the full TextMap's canonical values.
    reminder_tables = {}
    for locale, values in tables.items():
        medium = {}
        codes = TEXT_LOCALES[locale]
        for code in (codes,) if isinstance(codes, str) else codes:
            data = catalog.file('TextMap/TextMap_Medium' + code + '.json', optional=True)
            if not isinstance(data, dict) or not all(isinstance(value, str) for value in data.values()):
                raise PreparationFailure('unsupported_game_format',
                    'The Genshin reminder text format is unsupported. Update the toolkit and refresh game data; the previous index is retained.')
            medium.update(data)
        reminder_tables[locale] = {**values, **medium}
    ordinary = [link for link in links if not link['id'].startswith('reminder-')]
    reminder_links = [link for link in links if link['id'].startswith('reminder-')]
    rows = common.records('genshin', ordinary, tables, source_locale, entries)
    rows += common.records('genshin', reminder_links, reminder_tables, source_locale, entries)
    if len(rows) < len(links):
        _warn(warnings, 'Some Genshin authored lines have no text in the selected locale.')
    if version_matches:
        rows += readable_records(catalog, tables, source_locale, rows, warnings)
    else:
        _warn(warnings, 'Genshin readables require metadata matching the installed client version.')
    if any(row['voice_status'] == 'unknown' for row in rows):
        _warn(warnings, 'Some Genshin lines have unknown voice status and are excluded from unvoiced capture.')
    _warn(warnings, 'Genshin coverage is partial: profile and combat voices, messages, and movie subtitle timing are not fully indexed.')
    result = common.snapshot('genshin', install, stamp, catalog, rows, source_locale, target_locales, TEXT_LOCALES)
    count = sum(bool(row['audio']) for row in rows)
    result['message'] = f'{len(rows):,} {source_locale} lines from versioned community metadata; {count:,} verified installed voices'
    result['coverage_warnings'] = warnings
    return result


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, _executable, _destination):
    return common.extract_voice(install, 'genshin', audio)
