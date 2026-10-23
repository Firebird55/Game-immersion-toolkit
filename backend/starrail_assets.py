"""Honkai: Star Rail authored sentence → VoiceID → locale PCK bindings."""
from . import hoyo_dialogue as common
from .dialogue_catalog import DialogueCatalog, selected_tables

LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = common.SUPPORTED_LOCALES
TEXT_LOCALES = {locale: ('Main' + code, *((code + '_0', code + '_1') if code in {'KR', 'RU', 'TH'} else (code,)))
                for locale, code in common.TEXT_LOCALES.items()}


def archive_sources(install):
    return common.archive_sources(install, 'starrail')


def fingerprint(install):
    return common.fingerprint(install, 'starrail')


def sentence_links(sentences, voices, locale):
    voices = {row['VoiceID']: row for row in voices}
    links = []
    for row in sentences:
        voice = voices.get(row.get('VoiceID'))
        identity = row.get('TalkSentenceID')
        text_hash = row.get('TalkSentenceText', {}).get('Hash')
        if not voice or not identity or not text_hash or voice.get('VoiceType') == 'Cutscene':
            # A whole movie performance cannot be substituted for one subtitle.
            continue
        path = voice.get('VoicePath', '')
        if not path or '/' in path or '\\' in path:
            continue
        # Player variants are authored alternate paths. Keep their identities
        # separate even when the translated sentence is the same.
        variants = (('_m', 'male'), ('_f', 'female')) if voice.get('IsPlayerInvolved') else (('', None),)
        for suffix, gender in variants:
            links.append({'id': str(identity) + suffix, 'hash': text_hash, 'player_voice': gender,
                'source': common.voice_namespace('starrail', locale) + '/voice/' + path + suffix + '.wem'})
    return links


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Star Rail study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('starrail', data_dir)
    progress('Reading official Star Rail subtitles and authored voice IDs')
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales)
    links = sentence_links(catalog.file('ExcelOutput/TalkSentenceConfig.json'),
        catalog.file('ExcelOutput/VoiceConfig.json'), source_locale)
    entries = common.inventory(install, 'starrail', source_locale)
    rows = common.records('starrail', links, tables, source_locale, entries)
    return common.snapshot('starrail', install, stamp, catalog, rows, source_locale, target_locales, TEXT_LOCALES)


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, _executable, _destination):
    return common.extract_voice(install, 'starrail', audio)
