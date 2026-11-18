"""Immutable authored ZZZ cinema occurrences; shared base rows stay ambiguous."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
import math
import re

from .languages import audio_locale, normalize_text
from .local_game import LocalDialogue, dialogue_capture_channels

SCHEMA = 'zzz-cinema-occurrences-v1'
FIELD = 'publisher_cinema_occurrences'
LOCALES = frozenset(('en', 'zh-Hans', 'ja', 'ko'))
# C055's two original movie events and their distinct performer captions.
# Match both identifiers so an event reused by another timeline cannot opt in.
_C055_PLAYERS = {
    ('Play_vo_C055_EP020B', 'CS_05.5_02_060'): 'male',
    ('Play_vo_C055_EP020G', 'CS_05.5_02_070'): 'female',
}


def presentation_player(presentation, records):
    anchor = records[presentation['audio_anchor']]
    if not any(caption['text_id'] == anchor['text_id'] for caption in presentation['captions']):
        return None
    player = _C055_PLAYERS.get((presentation['event'], anchor['text_id']), anchor.get('player_voice'))
    return player if player in {'male', 'female'} else None


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _pointer(value):
    return (isinstance(value, str) and re.fullmatch(r'-?[1-9][0-9]{0,18}', value)
            and -(2**63) <= int(value) < 2**63)


def build(payload, occurrences, request):
    """Keep only original occurrences backed by an already admitted performance.

    This never asks for another bank/media body. A context-only performance must
    already be selected by an unconditional caption in the same prepared source.
    """
    if not occurrences:
        return None
    if not isinstance(occurrences, list) or len(occurrences) > 5_000_000:
        raise ValueError('Invalid ZZZ cinema occurrences')
    records = {row['text_id']: row for row in payload['records']}
    by_event = defaultdict(list)
    for row in records.values():
        audio = row.get('audio') or {}
        if (row.get('voice_status') == 'voiced' and row.get('audio_scope') == 'context'
                and audio.get('audio_scope') == 'context' and audio.get('event')):
            by_event[audio['event']].append(row)
    grouped = defaultdict(dict)
    for row in occurrences:
        if not isinstance(row, dict) or set(row) != {
                'text_id', 'locale', 'start', 'duration', 'track', 'clip',
                'subtitle_position', 'resource', 'timeline', 'event'}:
            raise ValueError('Changed ZZZ cinema occurrence fields')
        resource, timeline, event = row['resource'], row['timeline'], row['event']
        if (not isinstance(resource, str) or not re.fullmatch('[a-f0-9]{64}', resource)
                or not _pointer(timeline) or not _pointer(row['track']) or not _pointer(row['clip'])
                or not isinstance(event, str) or not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I)
                or row['locale'] not in LOCALES or not isinstance(row['text_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,2047}', row['text_id'])
                or any(type(row[name]) not in (int, float) or not math.isfinite(row[name]) for name in ('start', 'duration'))
                or not 0 <= row['start'] <= 1_000_000 or not 0 < row['duration'] <= 1_000_000
                or type(row['subtitle_position']) is not int):
            raise ValueError('Invalid original ZZZ cinema occurrence')
        # The existing capture lane has evidence only for the ordinary bottom
        # subtitle position. Other positions keep their existing guarded state.
        if row['subtitle_position'] == 0 and row['text_id'] in records:
            caption = {key: row[key] for key in ('text_id', 'locale', 'start', 'duration', 'track', 'clip')}
            previous = grouped[resource, timeline, event].get(row['clip'])
            if previous is not None and previous != caption:
                raise ValueError('Conflicting original ZZZ clip occurrence')
            grouped[resource, timeline, event][row['clip']] = caption
    presentations = []
    for (resource, timeline, event), captions in sorted(grouped.items()):
        anchors = by_event.get(event, [])
        if not anchors or len({digest(row['audio']) for row in anchors}) != 1:
            continue
        presentations.append({'resource': resource, 'timeline': timeline, 'event': event,
            'audio_anchor': min(row['text_id'] for row in anchors), 'captions': list(captions.values())})
    result = {'schema': SCHEMA, 'generation': payload['fingerprint'],
        'region': payload['publisher_region'], 'dub': audio_locale(payload['source_locale']),
        'request': request, 'presentations': presentations}
    validate(payload, result)
    return result


def validate(payload, metadata=None):
    metadata = payload.get(FIELD) if metadata is None else metadata
    if metadata is None:
        return None
    if (not isinstance(metadata, dict) or set(metadata) != {
            'schema', 'generation', 'region', 'dub', 'request', 'presentations'}
            or metadata['schema'] != SCHEMA or payload.get('game') != 'zzz'
            or payload.get('content_mode') != 'text-audio'
            or metadata['generation'] != payload.get('fingerprint')
            or metadata['region'] != payload.get('publisher_region')
            or metadata['region'] not in ('global', 'cn')
            or metadata['dub'] != audio_locale(payload['source_locale'])):
        raise ValueError('ZZZ occurrence source identity changed')
    request = metadata['request']
    if (not isinstance(request, dict) or set(request) != {'region', 'source_locale', 'target_locales', 'content_mode'}
            or request['region'] != metadata['region'] or request['source_locale'] != payload['source_locale']
            or request['content_mode'] != 'text-audio' or not isinstance(request['target_locales'], list)
            or len(request['target_locales']) > 32
            or any(not isinstance(value, str) or not 0 < len(value) <= 64 for value in request['target_locales'])):
        raise ValueError('ZZZ occurrence request changed')
    presentations = metadata['presentations']
    if not isinstance(presentations, list) or len(presentations) > 100_000:
        raise ValueError('Invalid ZZZ occurrence inventory')
    records = {row['text_id']: row for row in payload['records']}
    seen, total = set(), 0
    for presentation in presentations:
        if not isinstance(presentation, dict) or set(presentation) != {'resource', 'timeline', 'event', 'audio_anchor', 'captions'}:
            raise ValueError('Invalid ZZZ presentation owner')
        resource, timeline, event = (presentation[name] for name in ('resource', 'timeline', 'event'))
        identity = resource, timeline
        if (not isinstance(resource, str) or not re.fullmatch('[a-f0-9]{64}', resource)
                or not _pointer(timeline) or identity in seen or not isinstance(event, str)
                or not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I)):
            raise ValueError('Ambiguous ZZZ resource occurrence')
        seen.add(identity)
        anchor = records.get(presentation['audio_anchor'], {})
        audio = anchor.get('audio') or {}
        if (anchor.get('voice_status') != 'voiced' or anchor.get('audio_omitted_by_request')
                or anchor.get('audio_scope') != 'context' or audio.get('audio_scope') != 'context'
                or audio.get('event') != event or audio.get('publisher') != metadata['generation']
                or audio.get('locale') != metadata['dub']):
            raise ValueError('ZZZ context has no original event/media performance')
        clips = set()
        if not isinstance(presentation['captions'], list):
            raise ValueError('Invalid ZZZ subtitle sequence')
        for caption in presentation['captions']:
            total += 1
            if (total > 5_000_000 or not isinstance(caption, dict)
                    or set(caption) != {'text_id', 'locale', 'start', 'duration', 'track', 'clip'}
                    or caption['text_id'] not in records or caption['locale'] not in LOCALES
                    or not _pointer(caption['clip']) or not _pointer(caption['track'])
                    or caption['clip'] in clips
                    or any(type(caption[name]) not in (int, float) or not math.isfinite(caption[name]) for name in ('start', 'duration'))
                    or not 0 <= caption['start'] <= 1_000_000 or not 0 < caption['duration'] <= 1_000_000):
                raise ValueError('Invalid authored ZZZ subtitle occurrence')
            clips.add(caption['clip'])
    return metadata


def compile_occurrences(payload, index=None):
    """Produce conditional rows separately from the ordinary capture lookups."""
    metadata = validate(payload)
    if metadata is None:
        return None
    records = {row['text_id']: row for row in payload['records']}
    wanted = defaultdict(set)
    variants = []
    for presentation in metadata['presentations']:
        for locale in LOCALES:
            captions = sorted((row for row in presentation['captions'] if row['locale'] == locale),
                key=lambda row: (row['start'], row['clip']))
            # An omitted/blank translation, overlapping captions or reused ID
            # does not establish a linear, complete observation sequence.
            if (not captions or len({row['text_id'] for row in captions}) != len(captions)
                    or any(not records[row['text_id']].get('texts', {}).get(locale, '').strip() for row in captions)
                    or any(a['start'] + a['duration'] > b['start'] + 1e-6 for a, b in zip(captions, captions[1:]))):
                continue
            variant = {**presentation, 'locale': locale, 'captions': captions,
                'player': presentation_player(presentation, records),
                'key': digest([metadata['generation'], metadata['request'], metadata['region'], metadata['dub'],
                    presentation['resource'], presentation['timeline'], locale])}
            variants.append(variant)
            for caption in captions:
                wanted[locale].add(normalize_text(records[caption['text_id']]['texts'][locale], locale))
    # Scan the actual full inventory, including non-voiced rows and OCR aliases.
    # A selected protagonist or a duplicate translated string cannot certify an
    # otherwise ambiguous whole-text anchor.
    global_ids = defaultdict(lambda: defaultdict(set))
    for row in payload['records']:
        for locale, keys in wanted.items():
            values = [row.get('texts', {}).get(locale, ''), *row.get('ocr_texts', {}).get(locale, [])]
            for text in values:
                key = normalize_text(text, locale)
                if key in keys:
                    global_ids[locale][key].add(row['text_id'])
    occurrences = defaultdict(list)
    for variant in variants:
        for ordinal, caption in enumerate(variant['captions']):
            key = normalize_text(records[caption['text_id']]['texts'][variant['locale']], variant['locale'])
            occurrences[variant['locale'], key].append((variant, ordinal, caption))
    player_anchors, shared_rows = {}, set()
    for (locale, key), hits in occurrences.items():
        if not key or len(hits) != 2 or {variant['player'] for variant, _, _ in hits} != {'female', 'male'}:
            continue
        cue_ids = {caption['text_id'] for _, _, caption in hits}
        if (len(cue_ids) != 1 or global_ids[locale][key] != cue_ids
                or len({variant['event'] for variant, _, _ in hits}) != 2):
            continue
        player_anchors[locale, key] = {variant['player']: (variant['key'], ordinal)
            for variant, ordinal, _ in hits}
        shared_rows.update(player_anchors[locale, key].values())
    rows, anchors = {}, defaultdict(list)
    for variant in variants:
        locale, eligible = variant['locale'], []
        anchor_audio = records[variant['audio_anchor']]['audio']
        for ordinal, caption in enumerate(variant['captions']):
            base = records[caption['text_id']]
            text = base['texts'][locale]
            key = normalize_text(text, locale)
            if (key and global_ids[locale][key] == {caption['text_id']}
                    and len(occurrences[locale, key]) == 1
                    and base.get('audio') == anchor_audio and base.get('voice_status') == 'voiced'):
                # When compiling for capture, additionally require the actual
                # full multilingual matcher to agree, without a context hint.
                hit = index.match_lines([text], threshold=100, exact_only=True, channel='cinematic') if index is not None else None
                if index is None or hit and hit.text_id == caption['text_id'] and not hit.ambiguous:
                    eligible.append(ordinal)
                    anchors[locale, key].append((variant['key'], ordinal))
        variant['anchors'] = eligible
        variant['rows'] = {}
        for ordinal, caption in enumerate(variant['captions']):
            base = records[caption['text_id']]
            if ((variant['key'], ordinal) not in shared_rows and not any(anchor < ordinal for anchor in eligible)
                    or base.get('audio') or base.get('voice_status') not in ('unknown', 'unavailable')
                    or base.get('text_binding_unresolved') or base.get('audio_omitted_by_request')):
                continue
            scope = [metadata['generation'], metadata['request'], metadata['region'], metadata['dub'],
                variant['resource'], variant['timeline'], locale, caption['track'], caption['clip'], caption['text_id']]
            row = {**base, 'text_id': 'zzz-cinema:' + digest(scope), 'member_text_ids': [caption['text_id']],
                'audio': dict(anchor_audio), 'audio_locale': metadata['dub'], 'audio_scope': 'context',
                'voice_status': 'voiced', 'player_voice': None, 'source_voice_binding': None,
                'dialogue_kind': 'cutscene', 'text_capture_verified': True}
            # The ordinary index adds defaults while loading. Canonicalize the
            # authoritative occurrence here as well, so its provenance survives
            # worker publication and a fresh index/recording-service restart.
            row = asdict(LocalDialogue(**row))
            row['channels'] = sorted(dialogue_capture_channels(row['channels']))
            variant['rows'][ordinal] = row
            rows[row['text_id']] = row
    return {'metadata': metadata, 'request_sha256': digest(metadata['request']),
        'player_anchors': player_anchors,
        'variants': {variant['key']: variant for variant in variants}, 'anchors': dict(anchors), 'rows': rows,
        'texts': {caption['text_id']: records[caption['text_id']]['texts']
            for variant in variants for caption in variant['captions']}}


def recording_rows(payload):
    compiled = compile_occurrences(payload)
    return tuple(compiled['rows'].values()) if compiled else ()
