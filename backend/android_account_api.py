"""Native HTTP transport adapter for the maintained account/reading services."""
import json
import re
from urllib.parse import parse_qs

from .android_accounts import AndroidAccountConflict
from .lexirise_settings import account_settings


def _object(raw, allowed, required=()):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('Invalid account action')
    return value


def _integer(value, *, maximum=2**31 - 1, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid account action index')
    return value


def dispatch(host, method, path, query, headers, read_body):
    """Return (payload,status,pinned owner), or None for unrelated endpoints."""
    line_route = re.fullmatch(r'/api/lines/([1-9][0-9]*)/(reading(?:/[a-z]+(?:/[0-9]+/save)?)?|lexirise)', path)
    if path not in {'/api/lexirise/settings', '/api/lexirise/decks'} and not line_route:
        return None
    if method not in {'GET', 'POST', 'PATCH'}:
        return {'detail': 'Method unavailable'}, 405, None
    raw = read_body(16384) if method != 'GET' else b''
    if method != 'GET' and headers.get('X-Proxy-Transcript') != 'lexirise':
        return {'detail': 'Use the explicit account controls.'}, 403, None
    values = parse_qs(query, keep_blank_values=True, max_num_fields=4)
    if any(len(value) != 1 for value in values.values()):
        raise ValueError('Invalid account query')
    with host.session.lock:
        header = headers.get('X-Toolkit-Account-Generation')
        generation = host.guard_account(header) if method != 'GET' or header is not None else host.account_generation
        active = host.account_sessions.status()['active']
        if headers.get('X-Proxy-Transcript-Account', active) != active:
            raise AndroidAccountConflict('account_generation_changed', 'The selected account changed.')
        try:
            scope = host.account_sessions.pin(generation,
                line_id=int(line_route[1]) if line_route else None,
                language=values.get('language', [None])[0], remote=True)
        except LookupError:
            return {'detail': 'Transcript line not found'}, 404, None
    if path == '/api/lexirise/settings':
        if method not in {'GET', 'PATCH'} or values:
            return {'detail': 'Use the account settings controls.'}, 405, scope
        result = account_settings(scope.service, None if method == 'GET' else json.loads(raw))
    elif path == '/api/lexirise/decks':
        if set(values) - {'language'}:
            raise ValueError('Invalid destination query')
        if method == 'GET':
            result = {'decks': scope.service.available_decks()}
        elif method == 'POST':
            value = _object(raw, {'game', 'deck_id', 'create', 'language'}, {'game'})
            if not isinstance(value['game'], str) or (value.get('create') is not True and type(value.get('deck_id')) is not int):
                raise ValueError('Select a destination or explicitly create one')
            if value.get('create') is True and 'deck_id' in value:
                raise ValueError('Choose destination selection or creation')
            service = scope.service.pin(value.get('language', scope.service.source_language))
            service.configure_game_deck(value['game'], None if value.get('create') is True else value['deck_id'])
            result = service.status()
        else:
            return {'detail': 'Method unavailable'}, 405, scope
    elif line_route[2] == 'lexirise':
        if method != 'POST' or values:
            return {'detail': 'Use the sentence export button.'}, 405, scope
        line = scope.presented_line()
        if not line.voiced and line.voice_status != 'unvoiced' and not line.is_verified_missing_audio and not line.is_requested_text_only:
            return {'detail': 'This line requires verified dialogue or original audio.'}, 409, scope
        include_audio = line.voice_status != 'unvoiced' and not line.is_verified_missing_audio and not line.is_requested_text_only and line.audio_scope != 'paragraph'
        audio = scope.session.audio_path(line.id) if include_audio else None
        if include_audio and audio is None:
            return {'detail': 'The prepared original recording is unavailable.'}, 409, scope
        scope.check()
        result = scope.service.send(ref=f'line:{line.id}', game=line.game, chinese=line.source_text,
            english=line.translation_text, speaker=' / '.join(filter(None, [line.speaker_english, line.speaker_chinese])),
            audio=audio, audio_source=line.audio_source, audio_scope=line.audio_scope,
            voice_status='voiced' if line.voiced and not line.is_verified_missing_audio else line.voice_status)
        result = {**result, 'audio_included': include_audio}
    else:
        if set(values) - {'start'}:
            raise ValueError('Invalid reading query')
        operation = line_route[2].removeprefix('reading').strip('/')
        reader = scope.reader()
        text = scope.line.source_text
        if method == 'GET' and not operation:
            result = reader.analyze(text)
        elif method == 'GET' and operation in {'lookup', 'context', 'notes', 'examples', 'similar', 'characters'}:
            start = values.get('start', [''])[0]
            if not start.isascii() or not start.isdigit() or len(start) > 10:
                raise ValueError('A valid word position is required')
            result = getattr(reader, operation)(text, _integer(int(start)))
        elif method == 'POST' and operation == 'grammar':
            value = _object(raw, {'slug', 'known'}, {'slug', 'known'})
            if not isinstance(value['slug'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}', value['slug']) or type(value['known']) is not bool:
                raise ValueError('Invalid explicit grammar choice')
            result = reader.set_grammar_known(text, value['slug'], value['known'])
        elif method == 'POST' and operation == 'proficiency':
            value = _object(raw, {'start', 'proficiency'}, {'start', 'proficiency'})
            result = reader.set_proficiency(text, _integer(value['start']), _integer(value['proficiency'], minimum=1, maximum=4))
        elif method == 'POST' and operation == 'context':
            value = _object(raw, {'start', 'question'}, {'start', 'question'})
            if not isinstance(value['question'], str) or not 0 < len(value['question'].strip()) <= 500:
                raise ValueError('Enter a bounded context question')
            result = reader.context(text, _integer(value['start']), value['question'].strip())
        elif method == 'POST' and re.fullmatch(r'examples/[0-9]+/save', operation):
            start = values.get('start', [''])[0]
            if not start.isascii() or not start.isdigit() or len(start) > 10:
                raise ValueError('A valid word position is required')
            result = reader.save_example(text, _integer(int(start)), _integer(int(operation.split('/')[1])))
        else:
            return {'detail': 'Reading action unavailable'}, 405, scope
        if result is None:
            return {'detail': 'This word or rule is unavailable in the original line.'}, 404, scope
    scope.check()
    return result, 200, scope
