"""Star Rail authored dialogue, messages and exact locale PCK bindings."""
import re

from . import hoyo_dialogue as common
from .dialogue_catalog import DialogueCatalog, selected_tables
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 18
SUPPORTED_LOCALES = common.SUPPORTED_LOCALES
TEXT_LOCALES = {locale: ('Main' + code, *((code + '_0', code + '_1') if code in {'KR', 'RU', 'TH'} else (code,)))
                for locale, code in common.TEXT_LOCALES.items()}


def archive_sources(install):
    return common.archive_sources(install, 'starrail')


def fingerprint(install):
    if install is None:
        from .starrail_publisher import fingerprint as publisher_fingerprint
        return publisher_fingerprint()
    return common.fingerprint(install, 'starrail')


def publisher_fingerprint(tools):
    from .publisher_regions import selected_region
    from .starrail_publisher import fingerprint as publisher_stamp
    return publisher_stamp(selected_region(tools, 'starrail'))


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


def _voice_links(identity, text_hash, voice_id, voices, locale, kind='dialogue', *, multiple=False, individual_cutscene=False):
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
        if not individual_cutscene:
            return [_text_link(identity, text_hash, 'cutscene_caption', 'unavailable')]
        kind = 'cutscene_caption'
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
    # Companion cutscenes include per-line external media. Whole-film events
    # use a separate naming family. A path reused for distinct captions is
    # insufficient to assign either sentence to the recording.
    cutscene_texts = {}
    for row in sentences:
        voice = voices.get(row.get('VoiceID'), {})
        path = voice.get('VoicePath', '')
        if voice.get('VoiceType') == 'Cutscene' and isinstance(path, str) and re.fullmatch(
                r'companion(?:[0-9]+|x)_[a-z0-9]+_[0-9]+', path, re.IGNORECASE):
            cutscene_texts.setdefault(path.lower(), set()).add(_hash(row.get('TalkSentenceText')))
    alternatives = {}
    for row in multi_voices:
        candidates = row.get('VoiceIDList')
        if candidates:
            if not isinstance(candidates, list) or not all(type(v) is int and v > 0 for v in candidates):
                raise PreparationFailure('unsupported_game_format', 'Unsupported Star Rail multi-voice IDs. Refresh after updating the reader.')
            alternatives.setdefault(row.get('TalkSentenceID'), set()).update(candidates)
    links = []
    for row in sentences:
        identity, primary = row.get('TalkSentenceID'), row.get('VoiceID')
        candidates = alternatives.get(identity)
        if candidates and primary:
            candidates = candidates | {primary}
        # A singleton names the only authored performance. More than one
        # remains ambiguous, including a primary that conflicts with the list.
        ambiguous = bool(candidates and len(candidates) > 1)
        voice_id = next(iter(candidates)) if candidates and not ambiguous else primary
        path = voices.get(voice_id, {}).get('VoicePath')
        individual = isinstance(path, str) and len(cutscene_texts.get(path.lower(), ())) == 1
        links.extend(_voice_links(identity, _hash(row.get('TalkSentenceText')), voice_id, voices, locale,
                                  multiple=ambiguous, individual_cutscene=individual))
    return links


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


def _presentation_links(catalog):
    links = []
    families = (
        ('ActivityHipplenSentence', ('ID',), 'SentenceDesc', 'hipplen', 'event_dialogue'),
        ('ClockParkTalkText', ('TalkID',), 'TalkText', 'clock-park', 'event_dialogue'),
        ('IdleLiveEventSentence', ('SectionID', 'Index'), 'Sentence', 'idle-story', 'event_dialogue'),
        ('ChimeraTalk', ('TalkID',), 'TalkContent', 'chimera', 'event_dialogue'),
        ('RogueDialogueOptionDisplay', ('OptionDisplayID',), 'OptionTitle', 'rogue-option', 'choice'))
    for table, ids, field, prefix, kind in families:
        seen = set()
        for row in _table(catalog, table, (*ids, field)):
            text_hash = _hash(row.get(field))
            if not text_hash:
                continue
            values = tuple(row[key] for key in ids)
            if any(type(v) is not int or v < 0 for v in values) or values in seen:
                raise ValueError('Ambiguous Star Rail presentation identity in ' + table)
            seen.add(values)
            identity = prefix + '-' + '-'.join(map(str, values))
            status = 'unavailable' if row.get('EvPath') else 'unknown'
            links.append(_text_link(identity, text_hash, kind, status))
    return links


def _readable_records(catalog, tables, locale):
    books = _table(catalog, 'LocalbookConfig', ('BookID', 'BookContent'))
    audio = {row['BookID'] for row in _table(catalog, 'AudioBookData', ('BookID', 'AudioEvent'))
             if row.get('AudioEvent')}
    result, seen = [], set()
    for book in books:
        book_id, text_hash = book['BookID'], _hash(book.get('BookContent'))
        if type(book_id) is not int or book_id in seen:
            raise ValueError('Ambiguous Star Rail readable identity')
        seen.add(book_id)
        if not text_hash:
            continue
        parts = {lang: [common.display_text(t) for t in table.get(str(text_hash), '').replace('\\n', '\n').splitlines()]
                 for lang, table in tables.items()}
        for number, para in enumerate(parts[locale]):
            if not para:
                continue
            texts = {lang: values[number] for lang, values in parts.items()
                     if len(values) == len(parts[locale]) and values[number]}
            result.append({'text_id': f'starrail:book-{book_id}-{number}', 'source_locale': locale,
                           'source_text': para, 'texts': texts, 'english': texts.get('en', ''),
                           'chinese': texts.get('zh-Hans', ''), 'audio_locale': common.audio_locale(locale),
                           'audio': None, 'channels': ['dialogue'], 'dialogue_kind': 'readable',
                           'voice_status': 'unavailable' if book_id in audio else 'unvoiced'})
    return result


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
            link = _text_link(identity, text_hash, kind, 'unavailable' if row.get('AudioEvent') else 'unknown')
            if row.get('AudioEvent'):
                link['audio_event'] = row['AudioEvent']
                link['avatar_id'] = row['AvatarID']
            links.append(link)
    links.extend(message_links(
        _table(catalog, 'MessageItemConfig', ('ID', 'ItemType')),
        _table(catalog, 'MessageItemTextOverride', ('ItemID', 'MainText'))))
    links.extend(message_links(_table(catalog, 'RestaurantMessageConfig', ('ID', 'ItemType')),
        prefix='restaurant-message'))
    for row in _table(catalog, 'IdleLiveMessageContent', ('ContentID', 'ContentType')):
        if row.get('ContentType') in {'DisplayText', 'Reply'} and (text_hash := _hash(row.get('MainText'))):
            links.append(_text_link('idle-message-' + str(row['ContentID']), text_hash, 'message', 'unvoiced'))
    links.extend(_presentation_links(catalog))
    return links


def _speaker_lines(text, count):
    raw_lines = text.replace('\\n', '\n').splitlines()
    if len(raw_lines) != count:
        return ()
    parts = []
    for line in raw_lines:
        if line.count(':') + line.count('：') > 1 and '「' not in line:
            # A colon can also be part of a character name or their sentence.
            parts.append(common.display_text(line))
            continue
        match = re.fullmatch(r'\s*([^「」:：]{1,80}?)(?:\s*[:：]\s*(.+)|「(.+)」)\s*', line)
        if not match:
            return ()
        parts.append(common.display_text(match[2] or match[3]))
    return parts if all(parts) else ()


def _player_row(row, gender):
    from .textmaps import GENDER_VARIANT_RE
    tag = gender[0].upper()
    texts = {lang: common.display_text(GENDER_VARIANT_RE.sub(
        lambda match: match[2] if match[1] == tag else '', text)) for lang, text in row['texts'].items()}
    return row | {'player_voice': gender, 'texts': texts, 'source_text': texts[row['source_locale']],
                  'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', '')}


def _archive_rows(rows, links, bindings, credits, locale, tables=None):
    cv = {'en': 'CV_EN', 'zh-Hans': 'CV_CN', 'zh-Hant': 'CV_CN', 'ja': 'CV_JP', 'ko': 'CV_KR'}[locale]
    result = []
    for row in rows:
        item = links.get(row['text_id'], {})
        options = bindings.get(item.get('audio_event'), {})
        if any((key or '').startswith('localized') for key in options) and not _hash(credits.get(item.get('avatar_id'), {}).get(cv)):
            options = {}
        parts = {}
        if any('part-' in (key or '') for key in options):
            for lang, table in (tables or {}).items():
                lines = _speaker_lines(table.get(str(item['hash']), ''), len(options))
                if lines:
                    parts[lang] = lines
            if locale not in parts:
                options = {}
        if not options:
            result.append(row)
            continue
        for variant, binding in options.items():
            updated = row | {'audio': binding, 'voice_status': 'voiced'}
            if variant in ('male', 'female'):
                updated = _player_row(updated, variant)
                updated['text_id'] = row['text_id'] + '_' + variant[0]
            elif parts:
                number = int(variant.rsplit('-', 1)[1])
                texts = {lang: lines[number - 1] for lang, lines in parts.items()}
                updated.update(text_id=f"{row['text_id']}-part-{number}", texts=texts, source_text=texts[locale],
                               english=texts.get('en', ''), chinese=texts.get('zh-Hans', ''))
            result.append(updated)
    return result


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Star Rail study/audio language.')
    if install is None:
        from . import starrail_publisher, hoyo_publisher_voice
        from .publisher_regions import selected_region
        region = selected_region(data_dir / 'tools', 'starrail')
        stamp, catalog = starrail_publisher.prepare(data_dir, region)
    else:
        stamp = fingerprint(install)
        catalog = DialogueCatalog('starrail', data_dir)
    progress('Reading Star Rail dialogue, messages and authored voice IDs')
    tables = selected_tables(catalog, TEXT_LOCALES, source_locale, target_locales)
    links = authored_links(catalog, source_locale)
    entries = (common.inventory(install, 'starrail', source_locale) if install is not None else
               hoyo_publisher_voice.inventory(data_dir, stamp, source_locale, 'starrail'))
    rows = common.records('starrail', links, tables, source_locale, entries)
    rows = [_player_row(row, row['player_voice']) if row['player_voice'] else row for row in rows]
    rows.extend(_readable_records(catalog, tables, source_locale))
    if install is None:
        from . import starrail_films, starrail_events
        events = {'starrail:' + link['id']: link for link in links if 'audio_event' in link}
        audio = starrail_events.bindings(data_dir / 'tools', stamp, source_locale,
                                        {link['audio_event'] for link in events.values()})
        credits = {}
        if any((key or '').startswith('localized') for options in audio.values() for key in options):
            credits = {row['AvatarID']: row for row in _table(catalog, 'AvatarAtlas', ('AvatarID', 'CV_JP'))}
        rows = _archive_rows(rows, events, audio, credits, source_locale, tables)
        rows.extend(starrail_films.caption_rows(data_dir / 'tools', catalog, tables, source_locale, entries, rows))
    result = common.snapshot('starrail', install, stamp, catalog, rows, source_locale, target_locales, TEXT_LOCALES)
    result['coverage_warnings'] = [
        'Multi-voice and event-only performances without an exact original media binding remain unavailable.',
        'Captions without a timed localized recording, image-only messages and event-only formats have incomplete coverage. Missing voice metadata is not proof of silence.']
    if install is None:
        if not any(row['audio'] for row in rows) or not starrail_publisher.current(stamp, region):
            raise ValueError('The Star Rail publisher release changed or its voice data is incomplete. Retry preparation.')
        result['metadata_revision_title'] = catalog.revision_title
        result['publisher_region'] = region
        result['source_mode'] = 'publisher'
        result['message'] += ' using the selected regional HoYoPlay release and verified in-game hotfix indexes.'
    return result


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ('en',), progress)


def extract_voice(install, audio, _executable, _destination):
    if install is None and 'audio_event' in audio:
        from .starrail_events import extract as extract_event
        return extract_event(audio, _executable)
    if install is None:
        from .hoyo_publisher_voice import extract
        return extract(audio, _executable, 'starrail')
    return common.extract_voice(install, 'starrail', audio)


def publisher_snapshot_available(tools, stamp):
    from .hoyo_publisher_voice import snapshot_available
    return snapshot_available(tools, stamp, 'starrail')
