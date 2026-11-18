"""Explicit original copyright-voice choices; no inferred playback locale."""
import re

from .game_data_protocol import GameDataError, VoiceChoiceSet, VoiceChoiceSelection, SHA256
from .hoyo_dialogue import audio_locale, voice_namespace
from .starrail_game_audio import identity
from .starrail_events import wwise_hash

TABLES = frozenset({'AvatarCobrand', 'AllowedAudioLanguage', 'VoiceAtlas'})
EXTRA_TABLES = TABLES - {'VoiceAtlas'}
SCHEMA = 'starrail-original-voice-choices-v1'
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,255}')
METADATA_MESSAGE = ('The original voice-choice metadata is not available from this reader yet. '
    'Text-only preparation and your existing text and recordings remain available.')
LOCALE_MESSAGE = ('Your original voice choices are retained, but their study, package and spoken-language '
    'bindings still need verification before audio preparation. Text-only preparation and your existing recordings remain available.')


def _check(value):
    if not value:
        raise GameDataError('starrail_voice_choices_changed', 'The original voice choices changed. Check the choices again; your existing library is retained.', 409)


def discover(catalog, generation, source_locale):
    """Require original-reader schemas, never private rows or inferred layouts.

    The current 21-table preparation may not supply the two extra tables. That
    is an explicit unavailable boundary, not permission to inject research rows.
    """
    descriptions = getattr(getattr(catalog, 'tables', None), 'descriptions', {})
    if not isinstance(descriptions, dict) or not TABLES <= descriptions.keys():
        return None
    _check(isinstance(generation, str) and SHA256.fullmatch(generation) is not None)
    rows = {name: catalog.file('ExcelOutput/' + name + '.json') for name in sorted(TABLES)}
    _check(all(isinstance(items, list) and len(items) <= 1024**2 and all(isinstance(row, dict) for row in items)
               for items in rows.values()))
    language_rows = {}
    for row in rows['AllowedAudioLanguage']:
        key, wwise = row.get('AudioLanguageKey'), row.get('WwiseLanguageKey')
        _check(isinstance(key, str) and 0 < len(key) <= 64 and key not in language_rows and isinstance(wwise, str))
        locales = [locale for locale in ('en', 'ja', 'ko', 'zh-Hans') if voice_namespace('starrail', locale) == wwise]
        _check(len(locales) == 1)
        language_rows[key] = locales[0]
    avatars, voices = set(), set()
    for row in rows['VoiceAtlas']:
        owner, voice = row.get('AvatarID'), row.get('VoiceID')
        _check(type(owner) is int and 0 < owner < 2**32 and type(voice) is int and 0 < voice < 2**32
               and (owner, voice) not in voices)
        voices.add((owner, voice))
        audio_id, event = row.get('AudioID', 0), row.get('AudioEvent')
        _check(type(audio_id) is int and 0 <= audio_id < 2**32
               and (event is None or isinstance(event, str) and len(event) <= 512))
        if audio_id or event:
            avatars.add(owner)
    groups, ids, states = [], set(), set()
    for row in rows['AvatarCobrand']:
        owner = row.get('ID')
        _check(type(owner) is int and 0 < owner < 2**32 and owner not in ids)
        ids.add(owner)
        _check(all(isinstance(row.get(key), str) and NAME.fullmatch(row[key])
                   for key in ('StateGroupName', 'OffStateName', 'OnStateName')))
        group = wwise_hash(row['StateGroupName'])
        _check(wwise_hash(row['OffStateName']) != wwise_hash(row['OnStateName']) and group not in states)
        states.add(group)
        _check(isinstance(row.get('AudioLanguage'), str) and row['AudioLanguage'] in language_rows)
        if owner in avatars:
            groups.append((f'starrail:copyright-avatar:{owner}', owner, audio_locale(source_locale), language_rows[row['AudioLanguage']]))
    if not groups:
        return None
    generation_sha = identity({'native_generation': generation, 'build': catalog.build, 'study_locale': source_locale})
    schema_sha = identity({name: descriptions[name] for name in sorted(TABLES)})
    rows_sha = identity({name: sorted(items, key=identity) for name, items in rows.items()})
    digest = identity({'schema': SCHEMA, 'generation': generation_sha, 'schemas': schema_sha,
                       'rows': rows_sha, 'groups': sorted(groups)})
    return VoiceChoiceSet(digest, generation_sha, schema_sha, rows_sha, tuple(groups))


def selection_receipt(available, selection):
    _check(isinstance(available, VoiceChoiceSet))
    groups = {row[0] for row in available.groups}
    if selection is not None:
        _check(isinstance(selection, VoiceChoiceSelection) and selection.choice_set_sha256 == available.choice_set_sha256
               and all(key in groups for key, _ in selection.choices))
    chosen = dict(selection.choices) if selection else {}
    return {'schema': SCHEMA, 'choice_set_sha256': available.choice_set_sha256,
            'selection_sha256': identity(selection.json()) if selection else None,
            'user_choices': [{'group_key': key, 'alternative': value} for key, value in sorted(chosen.items())],
            'unselected_groups': sorted(groups - chosen.keys()), 'publisher_default_status': 'unknown',
            'authored_locale_receipt_status': 'unproven'}
