"""Public, authored Genshin mailbox, system notifications and Eye of Graeae chat."""
from collections import Counter

from . import hoyo_dialogue as common


def _fields(rows, anchors):
    """Recover renamed columns only when distinct retained records agree on every field."""
    possible = None
    for values in anchors:
        expected = set(values)
        matches = [row for row in rows if expected <= {v for v in row.values() if isinstance(v, (str, int))}]
        if len(matches) != 1:
            return ()
        fields = [{key for key, value in matches[0].items() if value == sample} for sample in values]
        possible = fields if possible is None else [left & right for left, right in zip(possible, fields)]
    if not all(len(keys) == 1 for keys in possible):
        return ()
    return tuple(next(iter(keys)) for keys in possible)


def _unique_rows(rows, field):
    counts = Counter(row[field] for row in rows if type(row.get(field)) is int and row[field] > 0)
    return (row for row in rows if type(row.get(field)) is int and counts[row[field]] == 1)


def message_records(catalog, tables, medium, locale, existing, warnings):
    from .genshin_assets import _table, _warn
    def load(name):
        return [row for row in _table(catalog, name + 'ExcelConfigData', warnings) if isinstance(row, dict)]

    occupied = {row['source_text'] for row in existing if row['voice_status'] in ('voiced', 'unavailable')}
    rows = []

    def add(identity, kind, content, names=None, *, medium_text=False, text_only=False):
        if type(content) is not int or content <= 0:
            return
        namespace = medium if medium_text else tables
        texts = {code: common.display_text(table[str(content)]) for code, table in namespace.items()
                 if table.get(str(content))}
        if not texts.get(locale):
            return
        row = {'text_id': 'genshin:' + identity, 'dialogue_kind': kind, 'source_locale': locale,
               'source_text': texts[locale], 'texts': texts, 'english': texts.get('en', ''),
               'chinese': texts.get('zh-Hans', ''), 'audio_locale': common.audio_locale(locale),
               'audio': None, 'player_voice': None, 'channels': ['dialogue', 'tip'],
               'voice_status': 'unvoiced' if text_only and texts[locale] not in occupied else 'unknown'}
        if names:
            for code, key in [('en', 'speaker_english'), ('zh-Hans', 'speaker_chinese')]:
                name = common.display_text(namespace.get(code, {}).get(str(names), ''))
                if name and '{' not in name:
                    row[key] = name
        rows.append(row)

    for letter in _unique_rows(load('Mail'), 'id'):
        for field, kind in [('contentTextMapHash', 'mail'), ('titleTextMapHash', 'mail_title')]:
            add(f"{kind}:{letter['id']}", kind, letter.get(field), letter.get('senderTextMapHash'),
                medium_text=True, text_only=True)
    for item in _unique_rows(load('ServerMessage'), 'id'):
        if item.get('showType') in ('SERVER_MESSAGE_SHOW_TYPE_INFO_MESSAGE', 'SERVER_MESSAGE_SHOW_TYPE_MESSAGE'):
            add(f"server_message:{item['id']}", 'server_message', item.get('contentTextMapHash'), text_only=True)

    # Anchor tuples identify original stable message/topic IDs, payload type and full text hash.
    # Two releases renamed every one of these fields without changing their contents.
    messages = load('TpsGlassesChatMessage')
    fields = _fields(messages, [(100101, 1001, 'TEXT', 3421014762), (100201, 1002, 'TEXT', 2109670066)])
    attachment_fields = _fields(messages, [(5008, 1008191327), (13004, 3590868607)])
    characters = load('TpsGlassesChatCharacter')
    name_fields = _fields(characters, [(1, 1264548403), (4, 405055187)])
    senders = {}
    if name_fields:
        actor, name = name_fields
        senders = {row[actor]: row.get(name) for row in _unique_rows(characters, actor)}
    if fields:
        identity, topic, payload, content = fields
        for item in _unique_rows(messages, identity):
            if type(item.get(topic)) is not int or item[topic] <= 0:
                continue
            match item.get(payload):
                case 'TEXT':
                    kind = 'chat_message'
                case 'IMAGE' | 'LOCATION' | 'HESPERIDES_MAP':
                    kind = 'chat_attachment'
                case _:
                    continue
            key = f"{item[topic]}:{item[identity]}"
            sender = senders.get(item.get('characterId'))
            add(f"{kind}:{key}", kind, item.get(content), sender)
            if item.get(payload) == 'LOCATION' and attachment_fields and attachment_fields[0] == identity:
                add(f'chat_location:{key}', 'chat_location', item.get(attachment_fields[1]), text_only=True)
    options = load('TpsGlassesChatOption')
    option_fields = _fields(options, [(1001011, 1001, 4069531165), (1002021, 1002, 1143764869)])
    if option_fields:
        identity, topic, content = option_fields
        for item in _unique_rows(options, identity):
            if type(item.get(topic)) is int and item[topic] > 0:
                add(f"chat_choice:{item[topic]}:{item[identity]}", 'chat_choice', item.get(content))
    topics = load('TpsGlassesChatTopic')
    topic_fields = _fields(topics, [(1001, 562223715), (1002, 118984643)])
    if topic_fields:
        identity, title = topic_fields
        for item in _unique_rows(topics, identity):
            add(f"chat_topic:{item[identity]}", 'chat_topic', item.get(title), text_only=True)
    unsupported = any(records and not columns for records, columns in (
        (messages, fields), (characters, name_fields), (options, option_fields), (topics, topic_fields)))
    if unsupported or (fields and any(row.get(fields[2]) == 'LOCATION' for row in messages) and not attachment_fields):
        _warn(warnings, 'Some Genshin message fields could not be identified from their retained authoring records.')
    return rows
