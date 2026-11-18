"""Explicit DEBUG-only account UI fixture: no outbound network or real keys.

Native startup must authorize this mode before constructing the transport. Its
two synthetic owners and remote mutations exist only in this process. Normal
account services and their ownership, storage and scope checks remain unchanged.
"""
from copy import deepcopy
import json
import re
import threading

import httpx

KEYS = ('lx_first_authored_account_fixture_only', 'lx_second_authored_account_fixture_only')


def transport():
    lock = threading.RLock()
    owners = {}
    for number, key in enumerate(KEYS, 1):
        owners['Bearer ' + key] = {
            'user': {'id': 'authored-owner-' + str(number), 'name': 'Authored account ' + str(number)},
            'settings': {'languages': ['zh', 'en', 'ja', 'ko'],
                'global': {'translationLanguage': 'en', 'effectiveTranslationLanguage': 'en'},
                'languageSettings': {}},
            'decks': {}, 'items': {}, 'members': {},
        }

    def response(request):
        # A MockTransport never falls back to the HTTP stack. Reject a changed
        # endpoint as well as unknown keys instead of imitating a real account.
        if request.url.scheme != 'https' or request.url.host != 'api.lexirise.app':
            return httpx.Response(403, json={'detail': 'Authored endpoint only'})
        with lock:
            state = owners.get(request.headers.get('authorization'))
            if state is None:
                return httpx.Response(401, json={'detail': 'Only authored fixture keys are accepted'})
            method, path = request.method, request.url.path
            payload = {}
            if request.content and 'application/json' in request.headers.get('content-type', ''):
                if len(request.content) > 65536:
                    return httpx.Response(413, json={})
                payload = json.loads(request.content)
            result = None
            if path == '/v1/me' and method == 'GET':
                result = {'user': state['user']}
            elif path == '/v1/settings' and method in {'GET', 'PATCH'}:
                if method == 'PATCH':
                    from .lexirise_settings import validate_patch
                    validate_patch(payload)
                    for key, value in payload.items():
                        if key == 'languages':
                            state['settings'][key] = value
                        elif key == 'languageSettings':
                            for locale, settings in value.items():
                                state['settings'][key].setdefault(locale, {}).update(settings)
                        else:
                            state['settings'][key].update(value)
                    state['settings']['global']['effectiveTranslationLanguage'] = state['settings']['global']['translationLanguage']
                result = state['settings']
            elif path == '/v1/decks' and method == 'GET':
                language = request.url.params.get('language', 'zh')
                result = {'decks': [value for value in state['decks'].values() if value['language'] == language]}
            elif path == '/v1/decks' and method == 'POST' and len(state['decks']) < 32:
                identity = len(state['decks']) + 1
                state['decks'][identity] = {'id': identity, 'owner_user_id': state['user']['id'],
                    'title': payload['title'], 'language': payload['language'],
                    'unit_type': payload['unit_type'], 'deck_type': payload['deck_type']}
                state['members'][identity] = []
                result = {'deck': state['decks'][identity]}
            elif (match := re.fullmatch(r'/v1/decks/([1-9][0-9]*)(/items)?', path)):
                identity = int(match[1])
                if identity in state['decks']:
                    if method == 'GET' and not match[2]:
                        result = {'deck': state['decks'][identity],
                            'items': [state['items'][item] for item in state['members'][identity]]}
                    elif method == 'POST' and match[2]:
                        ids = payload.get('saved_expression_selection', {}).get('ids', [])
                        if len(ids) <= 256 and all(type(item) is int and item in state['items'] for item in ids):
                            before = len(state['members'][identity])
                            state['members'][identity] = list(dict.fromkeys([*state['members'][identity], *ids]))
                            result = {'added_count': len(state['members'][identity]) - before}
            elif path == '/v1/vocabulary/audio' and method == 'POST':
                if len(request.content) <= 25 * 1024**2:
                    # This reserved domain is never fetched by this fixture.
                    result = {'publicUrl': 'https://audio.invalid/authored-original.wav'}
            elif path == '/v1/vocabulary' and method == 'GET':
                result = {'items': [item for item in state['items'].values()
                    if item['expression_text'] == request.url.params.get('search', '')]}
            elif path == '/v1/vocabulary' and method == 'POST' and len(state['items']) < 256:
                identity = len(state['items']) + 1
                state['items'][identity] = {'id': identity, 'expression_text': payload['text'],
                    'audio_urls': payload.get('audioUrls', []), 'proficiency': payload.get('proficiency', 1)}
                result = {'item': state['items'][identity]}
            elif (match := re.fullmatch(r'/v1/vocabulary/([1-9][0-9]*)', path)):
                identity = int(match[1])
                if identity in state['items'] and method in {'GET', 'PATCH'}:
                    if method == 'PATCH':
                        state['items'][identity].update(payload)
                    result = {'item': state['items'][identity]}
            elif path == '/v1/analyze/text' and method == 'POST':
                text = payload.get('text', '')
                if isinstance(text, str) and 0 < len(text) <= 1600:
                    # Authored tokens expose the real reader lifecycle without
                    # claiming a linguistic analysis from the service.
                    occurrences, metadata = [], {}
                    for identity, match in enumerate(re.finditer(r'\w+', text), 1):
                        occurrences.append({'charStart': len(text[:match.start()].encode('utf-16-le')) // 2,
                            'charEnd': len(text[:match.end()].encode('utf-16-le')) // 2,
                            'word': match[0], 'isWordLike': True, 'entryId': identity})
                        metadata[str(identity)] = {'gloss': 'Authored fixture definition'}
                    result = {'occurrences': occurrences, 'entryMetaById': metadata, 'stateByEntryId': {}}
            return httpx.Response(200 if result is not None else 404, json=deepcopy(result or {}))

    return httpx.MockTransport(response)
