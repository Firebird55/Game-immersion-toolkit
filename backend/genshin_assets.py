"""Genshin Impact authored dialogue hashes and original locale voice paths."""
from collections import defaultdict
import re

from . import hoyo_dialogue as common
from .dialogue_catalog import DialogueCatalog, selected_tables

LANGUAGE_INDEX_VERSION = 1
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


def dialogue_hashes(talks):
    values = defaultdict(set)
    for talk in talks:
        for array, identity, text in DIALOG_SCHEMAS:
            for row in talk.get(array, []):
                if row.get(identity) and row.get(text):
                    values[str(row[identity])].add(str(row[text]))
    # Conflicting upstream records cannot silently select a translation.
    return {identity: next(iter(hashes)) for identity, hashes in values.items() if len(hashes) == 1}


def dialogue_links(voice_maps, hashes, locale, reminders=None):
    reminders = reminders or {}
    values = defaultdict(set)
    for mapping in voice_maps:
        for voice in mapping.values():
            if not isinstance(voice, dict):
                continue
            for array, filename, trigger, argument in VOICE_SCHEMAS:
                kind = voice.get(trigger)
                if kind not in {'Dialog', 'DungeonReminder'}:
                    continue
                identity = str(voice.get(argument, ''))
                table = hashes if kind == 'Dialog' else reminders
                if identity not in table:
                    continue
                for source in voice.get(array, []):
                    path = source.get(filename, '')
                    if isinstance(path, str) and path.casefold().endswith('.wem'):
                        values[(kind, identity)].add(common.VOICE_NAMES[locale] + '\\' + path)
    links = []
    for (kind, identity), sources in values.items():
        # A dialogue may explicitly have player variants. Unrelated multiple
        # performances are excluded instead of choosing the first source.
        for source in sorted(sources):
            gender = ('female' if re.search(r'(?:girl|female|lumine)', source, re.I) else
                      'male' if re.search(r'(?:boy|male|aether)', source, re.I) else None)
            if len(sources) > 1 and (not gender or len(sources) != 2):
                continue
            suffix = ':' + gender if len(sources) > 1 else ''
            table = hashes if kind == 'Dialog' else reminders
            row_id = identity if kind == 'Dialog' else 'reminder-' + identity
            links.append({'id': row_id + suffix, 'hash': table[identity], 'source': source,
                          'player_voice': gender if len(sources) > 1 else None})
    return links


def reminder_hashes(rows):
    fields = ('contentTextMapHash', 'BPKEKEBFEIG', 'HNDLKHJFLNF')
    return {str(row['id']): str(value) for row in rows if row.get('hasAudio')
            for field in fields if (value := row.get(field))}


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Genshin study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('genshin', data_dir)
    progress('Reading official Genshin subtitle tables and authored dialogue bindings')
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales, medium=True)
    hashes = dialogue_hashes(catalog.directory_json('BinOutput/Talk'))
    reminders = reminder_hashes(catalog.file('ExcelBinOutput/ReminderExcelConfigData.json'))
    links = dialogue_links(catalog.directory_json('BinOutput/Voice'), hashes, source_locale, reminders)
    entries = common.inventory(install, 'genshin', source_locale)
    rows = common.records('genshin', links, tables, source_locale, entries)
    return common.snapshot('genshin', install, stamp, catalog, rows, source_locale, target_locales, TEXT_LOCALES)


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, _executable, _destination):
    return common.extract_voice(install, 'genshin', audio)
