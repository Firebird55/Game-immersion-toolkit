"""Star Rail authored dialogue, messages and exact locale PCK bindings."""
from . import hoyo_dialogue as common
from .dialogue_catalog import DialogueCatalog, selected_tables
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = common.SUPPORTED_LOCALES
TEXT_LOCALES = {locale: ('Main' + code, *((code + '_0', code + '_1') if code in {'KR', 'RU', 'TH'} else (code,)))
                for locale, code in common.TEXT_LOCALES.items()}


def archive_sources(install):
    return common.archive_sources(install, 'starrail')


def fingerprint(install):
    return common.fingerprint(install, 'starrail')


def _hash(value):
    return value.get('Hash') if isinstance(value, dict) else None


def _table(catalog, name, fields):
    rows = catalog.file('ExcelOutput/' + name + '.json')
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or rows and not any(all(field in row for field in fields) for row in rows)):
        raise PreparationFailure('unsupported_game_format', 'Unsupported Star Rail ' + name + ' schema. Update the toolkit after this game update; the previous table is retained.')
    return rows


def _text_link(identity, text_hash, kind, status):
    return {'id': str(identity), 'hash': text_hash, 'source': None,
        'player_voice': None, 'voice_status': status, 'dialogue_kind': kind}


def _voice_links(identity, text_hash, voice_id, voices, locale, kind='dialogue', *, multiple=False):
    if not identity or not text_hash:
        return []
    voice = voices.get(voice_id)
    # MultiVoice lists do not establish which performance was heard. In
    # particular, a missing primary VoiceID is not proof that a line is silent.
    if multiple:
        return [_text_link(identity, text_hash, kind, 'unavailable')]
    if voice and voice.get('VoiceType') == 'NoVoice':
        return [_text_link(identity, text_hash, kind, 'unvoiced')]
    if not voice_id:
        return [_text_link(identity, text_hash, kind, 'unknown')]
    if not voice:
        return [_text_link(identity, text_hash, kind, 'unavailable')]
    voice_type = voice.get('VoiceType', '')
    if voice_type == 'Cutscene':
        # Retain the subtitle without substituting a whole movie soundtrack.
        return [_text_link(identity, text_hash, 'cutscene_caption', 'unavailable')]
    if kind == 'dialogue':
        if voice_type.startswith('NPC_'):
            kind = 'ambient'
        elif voice_type.startswith('Broadcast'):
            kind = 'broadcast'
    path = voice.get('VoicePath', '')
    if not isinstance(path, str) or not path or '/' in path or '\\' in path:
        return [_text_link(identity, text_hash, kind, 'unavailable')]
    # Player variants are authored alternate paths. Keep their identities
    # separate even when the translated sentence is the same.
    variants = (('_m', 'male'), ('_f', 'female')) if voice.get('IsPlayerInvolved') else (('', None),)
    return [{'id': str(identity) + suffix, 'hash': text_hash, 'player_voice': gender,
        'source': common.voice_namespace('starrail', locale) + '/voice/' + path + suffix + '.wem',
        'dialogue_kind': kind} for suffix, gender in variants]


def sentence_links(sentences, voices, locale, multi_voices=()):
    voices = {row['VoiceID']: row for row in voices}
    multiple = {row.get('TalkSentenceID') for row in multi_voices if row.get('VoiceIDList')}
    return [link for row in sentences for link in _voice_links(
        row.get('TalkSentenceID'), _hash(row.get('TalkSentenceText')), row.get('VoiceID'), voices, locale,
        multiple=row.get('TalkSentenceID') in multiple)]


def message_links(messages, overrides=(), *, prefix='message'):
    links = []
    text_ids = set()
    for row in messages:
        identity = row.get('ID')
        if not identity:
            continue
        if row.get('ItemType') == 'Text':
            # MessageItemConfig discriminates Text from Video, Image, Sticker,
            # Link and Raid attachments. These are authored plain-text message
            # bodies/reply choices, not missing TalkSentence voice references.
            text_ids.add(identity)
            if text_hash := _hash(row.get('MainText')):
                links.append(_text_link(f'{prefix}-{identity}', text_hash, 'message', 'unvoiced'))
            if text_hash := _hash(row.get('OptionText')):
                links.append(_text_link(f'{prefix}-{identity}-option', text_hash, 'message_choice', 'unvoiced'))
    for row in overrides:
        identity, text_hash = row.get('ItemID'), _hash(row.get('MainText'))
        if identity in text_ids and text_hash:
            # Conditions can select different text for one item. The text hash
            # identifies a variant without choosing an account's current state.
            links.append(_text_link(f'{prefix}-{identity}-override-{text_hash}', text_hash, 'message', 'unvoiced'))
    return links


def authored_links(catalog, locale):
    sentences = _table(catalog, 'TalkSentenceConfig', ('TalkSentenceID', 'TalkSentenceText'))
    voices = _table(catalog, 'VoiceConfig', ('VoiceID', 'VoicePath'))
    if not sentences or not voices or not any('VoiceID' in row for row in sentences):
        raise ValueError('Star Rail sentence/voice metadata is incomplete; previous table retained.')
    links = sentence_links(sentences, voices, locale,
        _table(catalog, 'TalkSentenceMultiVoice', ('TalkSentenceID', 'VoiceIDList')))
    by_voice = {row['VoiceID']: row for row in voices}
    for row in _table(catalog, 'TarotBookSentence', ('ID', 'Sentence', 'VoiceID')):
        if not row.get('ID'):
            continue
        links.extend(_voice_links('narration-' + str(row.get('ID')), _hash(row.get('Sentence')),
            row.get('VoiceID'), by_voice, locale, 'narrated_story'))
    for row in _table(catalog, 'VoiceAtlas', ('AvatarID', 'VoiceID', 'Voice_M')):
        if not row.get('AvatarID') or not row.get('VoiceID'):
            continue
        identity = f"voice-atlas-{row.get('AvatarID')}-{row.get('VoiceID')}"
        text_hash = _hash(row.get('Voice_M'))
        kind = 'battle_voice' if row.get('IsBattleVoice') else 'character_voice'
        if row.get('AudioID'):
            links.extend(_voice_links(identity, text_hash, row['AudioID'], by_voice, locale, kind))
        elif text_hash:
            # AudioEvent is a Wwise event, not a VoiceConfig ID or media path.
            links.append(_text_link(identity, text_hash, kind, 'unavailable' if row.get('AudioEvent') else 'unknown'))
    links.extend(message_links(
        _table(catalog, 'MessageItemConfig', ('ID', 'ItemType')),
        _table(catalog, 'MessageItemTextOverride', ('ItemID', 'MainText'))))
    links.extend(message_links(_table(catalog, 'RestaurantMessageConfig', ('ID', 'ItemType')),
        prefix='restaurant-message'))
    for row in _table(catalog, 'IdleLiveMessageContent', ('ContentID', 'ContentType')):
        if row.get('ContentType') in {'DisplayText', 'Reply'} and (text_hash := _hash(row.get('MainText'))):
            links.append(_text_link('idle-message-' + str(row['ContentID']), text_hash, 'message', 'unvoiced'))
    return links


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Star Rail study/audio language.')
    stamp = fingerprint(install)
    catalog = DialogueCatalog('starrail', data_dir)
    progress('Reading Star Rail dialogue, messages and authored voice IDs')
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales)
    links = authored_links(catalog, source_locale)
    entries = common.inventory(install, 'starrail', source_locale)
    rows = common.records('starrail', links, tables, source_locale, entries)
    result = common.snapshot('starrail', install, stamp, catalog, rows, source_locale, target_locales, TEXT_LOCALES)
    result['coverage_warnings'] = [
        'Multi-voice and event-only performances without an exact original media binding remain unavailable.',
        'Movie captions, image-only messages and presentation-specific event formats are not comprehensively mapped. Missing voice metadata is not proof of silence.']
    return result


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, _executable, _destination):
    return common.extract_voice(install, 'starrail', audio)
