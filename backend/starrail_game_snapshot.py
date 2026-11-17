"""Render only complete original audio bindings and persist inert ownership."""
import re

from .game_data_protocol import GameDataError
from . import starrail_game_audio as audio
from .private_data_paths import MAX_ROWS

MEMBERS_SCHEMA = 'starrail-original-members-v1'


def _incomplete():
    raise GameDataError('starrail_audio_incomplete',
        'Some authored recordings or movie audio still need verified preparation. Your existing library is retained.', 409)


def _event_rows(row, options, raw_texts):
    from .starrail_assets import _player_row, _speaker_lines
    groups = {}
    for variant, binding in options.items():
        match = re.fullmatch(r'(?:(male|female)-)?part-([1-9][0-9]*)', variant or '')
        if variant is None or variant in ('male', 'female'):
            gender, part = variant, None
        elif match:
            gender, part = match[1], int(match[2])
        else:
            _incomplete()
        groups.setdefault(gender, []).append((part, binding))
    result = []
    for gender, choices in groups.items():
        if gender and row.get('player_voice') and gender != row['player_voice']:
            continue
        current = _player_row(row, gender) if gender else dict(row)
        if not current['source_text'].strip():
            continue
        if gender and not row.get('player_voice'):
            current['text_id'] += '_' + gender[0]
        if len(choices) == 1 and choices[0][0] is None:
            result.append(current | {'audio': choices[0][1], 'voice_status': 'voiced'})
            continue
        if any(part is None for part, _ in choices):
            _incomplete()
        choices.sort(key=lambda value: value[0])
        if [part for part, _ in choices] != list(range(1, len(choices)+1)):
            _incomplete()
        from .textmaps import GENDER_VARIANT_RE
        texts_for_group = raw_texts
        if selected := gender or row.get('player_voice'):
            texts_for_group = {locale: GENDER_VARIANT_RE.sub(
                lambda match: match[2] if match[1] == selected[0].upper() else '', text)
                for locale, text in raw_texts.items()}
        texts = {locale: lines for locale, text in texts_for_group.items()
                 if (lines := _speaker_lines(text, len(choices)))}
        if current['source_locale'] not in texts:
            _incomplete()
        for part, binding in choices:
            localized = {locale: lines[part-1] for locale, lines in texts.items()}
            result.append(current | {'text_id': current['text_id'] + '-part-' + str(part),
                'texts': localized, 'source_text': localized[current['source_locale']],
                'english': localized.get('en', ''), 'chinese': localized.get('zh-Hans', ''),
                'audio': binding, 'voice_status': 'voiced'})
    if not result:
        _incomplete()
    return result


def render(payload, external, events, *, sequence_texts=None):
    """Resolve all authored refs; preserve other unknown/unavailable records."""
    from .voice_assets import voice_hash
    rows, members = [], []
    for original in payload['records']:
        row = original | {'audio_omitted_by_request': False}
        source = row.get('source_voice_binding') or {}
        if (not isinstance(source, dict) or source.get('source') and source.get('audio_event')
                or source and source.get('locale') != row.get('audio_locale')):
            _incomplete()
        if source.get('film_caption', {}).get('movies'):
            _incomplete()
        if path := source.get('source'):
            if path not in external:
                _incomplete()
            span = external[path]
            row.update(audio={key: source[key] for key in ('publisher', 'locale', 'source')}
                | {'file_id': f'{voice_hash(path):016x}'}, voice_status='voiced')
            selected = [(row, span)]
        elif event := source.get('audio_event'):
            options, spans = {}, {}
            for variant, (mid, span) in events.get(event, {}).items():
                reference = {key: source[key] for key in ('publisher', 'locale', 'audio_event')}
                reference.update(event_media=mid, bank_package=span.owner.name, bank_digest=span.owner.md5,
                    bank_offset=span.start, bank_size=span.length)
                if variant:
                    reference['event_variant'] = variant
                options[variant], spans[audio.identity(reference)] = reference, span
            if not options:
                _incomplete()
            key = row['text_id']
            raw_texts = (sequence_texts or {}).get(key)
            if raw_texts is None and row.get('player_voice'):
                key = re.sub(r'-text-player-' + row['player_voice'][0] + '$', '', key)
                raw_texts = (sequence_texts or {}).get(key)
            selected = [(updated, spans[audio.identity(updated['audio'])])
                        for updated in _event_rows(row, options, raw_texts or row['texts'])]
        else:
            if row.get('audio') or row.get('voice_status') == 'voiced':
                _incomplete()
            selected = [(row, None)]
        for current, span in selected:
            rows.append(current)
            if span is not None:
                members.append(audio.OriginalMember(current['text_id'], current['audio'], span, current.get('player_voice')))
    if not rows or len(rows) > MAX_ROWS or len({row['text_id'] for row in rows}) != len(rows):
        _incomplete()
    return payload | {'records': rows, 'content_mode': 'text-audio',
        'message': f'{len(rows):,} official lines; {len(members):,} verified original recordings'}, members


def pack(members):
    owners = tuple(dict.fromkeys(member.span.owner for member in members))
    indexes = {owner: number for number, owner in enumerate(owners)}
    return {'schema': MEMBERS_SCHEMA, 'owners': [{'name': owner.name, 'bytes': owner.size, 'md5': owner.md5,
        'url': owner.url, 'generation': owner.generation} for owner in owners],
        'members': [[member.text_id, indexes[member.span.owner], member.span.start, member.span.length] for member in members]}


def unpack(value, payload):
    if (not isinstance(value, dict) or set(value) != {'schema', 'owners', 'members'}
            or value['schema'] != MEMBERS_SCHEMA or not isinstance(value['owners'], list)
            or not isinstance(value['members'], list) or len(value['owners']) > MAX_ROWS or len(value['members']) > MAX_ROWS):
        _incomplete()
    owners = []
    for owner in value['owners']:
        if not isinstance(owner, dict) or set(owner) != {'name', 'bytes', 'md5', 'url', 'generation'}:
            _incomplete()
        owners.append(audio.Owner(owner['name'], owner['bytes'], owner['md5'], owner['url'], owner['generation']))
    rows = {row['text_id']: row for row in payload['records'] if row.get('audio')}
    found, result = set(), []
    for item in value['members']:
        if (not isinstance(item, list) or len(item) != 4 or not isinstance(item[0], str)
                or item[0] not in rows or item[0] in found or type(item[1]) is not int or not 0 <= item[1] < len(owners)):
            _incomplete()
        text_id, owner, start, length = item; row = rows[text_id]; found.add(text_id)
        result.append(audio.OriginalMember(text_id, row['audio'], audio.Span(owners[owner], start, length), row.get('player_voice')))
    if found != set(rows):
        _incomplete()
    return result
