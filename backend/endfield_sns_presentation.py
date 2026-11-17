"""Stateless admission of complete original Baker cells, shared by capture hosts."""
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from .endfield_presentation import _box
from .languages import normalize_text


SOURCE_ROLES = frozenset((
    'basic_ctrl', 'barker_ctrl', 'mission_ctrl', 'core_ctrl', 'cell_ctrl', 'system_ctrl', 'base_ctrl',
    'basic_layout', 'barker_layout', 'mission_layout', 'core_layout', 'cell_layout', 'system_layout',
    'chat_table', 'dialog_table', 'label_table'))


def validate_sns_dialogue_ui(value):
    """Canonical bounded provenance/IDs; original bodies remain in their own rows."""
    def check(condition):
        if not condition:
            raise ValueError('Invalid original Endfield Baker UI metadata')

    check(isinstance(value, dict) and set(value) == {'schema', 'revision', 'sources', 'locales', 'chains'})
    check(type(value['schema']) is int and value['schema'] == 1)
    check(isinstance(value['revision'], str) and re.fullmatch(r'endfield-[0-9a-f]{64}', value['revision']))
    check(isinstance(value['sources'], dict) and set(value['sources']) == SOURCE_ROLES)
    check(all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{32}', v) for v in value['sources'].values()))
    check(isinstance(value['locales'], dict) and 1 <= len(value['locales']) <= 64)

    def identity(text):
        check(isinstance(text, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,384}', text))
        return text

    def label(text, locale):
        check(isinstance(text, str) and text == text.strip() and 1 <= len(text) <= 128)
        check(not any(c in text for c in '\r\n\0{}') and bool(normalize_text(text, locale)))
        return text

    locales = {}
    for locale, row in value['locales'].items():
        check(isinstance(locale, str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}', locale))
        check(isinstance(row, dict) and set(row) == {'modes', 'friends', 'chats'})
        check(isinstance(row['modes'], list) and len(row['modes']) == 2)
        modes = [label(text, locale) for text in row['modes']]
        friends = label(row['friends'], locale)
        check(len({normalize_text(text, locale) for text in [*modes, friends]}) == 3)
        check(isinstance(row['chats'], dict) and 1 <= len(row['chats']) <= 4096)
        chats = {identity(key): label(text, locale) for key, text in row['chats'].items()}
        locales[locale] = {'modes': modes, 'friends': friends, 'chats': chats}
    chat_ids = {key for row in locales.values() for key in row['chats']}
    check(isinstance(value['chains'], list) and 1 <= len(value['chains']) <= 65536)
    chains = set()
    for chain in value['chains']:
        check(isinstance(chain, dict) and set(chain) == {'chat_id', 'text_ids'})
        chat = identity(chain['chat_id'])
        check(chat in chat_ids and isinstance(chain['text_ids'], list) and 2 <= len(chain['text_ids']) <= 4)
        ids = tuple(identity(text) for text in chain['text_ids'])
        check(len(set(ids)) == len(ids) and all(text.startswith('endfield:SNSDialogTable:') for text in ids))
        chains.add((chat, ids))
    result = {'schema': 1, 'revision': value['revision'], 'sources': dict(value['sources']), 'locales': locales,
              'chains': [{'chat_id': chat, 'text_ids': list(ids)} for chat, ids in sorted(chains)]}
    check(len(json.dumps(result, ensure_ascii=True)) <= 4 * 1024**2)
    return result


def sns_ui_signature(value):
    return sha256(json.dumps(validate_sns_dialogue_ui(value), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def sns_record_signature(row):
    """Retain translations, status, branch, scope, channels and ALL guards."""
    return json.dumps({key: value for key, value in row.items() if key != 'text_id'}, sort_keys=True)


@dataclass(frozen=True)
class SnsSourceChain:
    header: str
    bodies: tuple[str, ...]
    text_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompiledSnsDialogue:
    ui_signature: str
    locale: str
    config: dict
    chains: tuple[SnsSourceChain, ...]


@dataclass(frozen=True)
class SnsBodyObservation:
    text_id: str
    source_ocr: str
    line_range: tuple[int, int]


def compile_sns_chains(value, records, source_locale, player_voice='unconfigured', *, display_locale=None):
    """Compare every source-chain peer before admitting a written presentation."""
    descriptor = validate_sns_dialogue_ui(value)
    rows = {row['text_id']: row for row in records}
    if len(rows) != len(records):
        raise ValueError('Duplicate Endfield Baker source IDs')
    display_locale = display_locale or source_locale
    config = descriptor['locales'].get(display_locale)
    if config is None:
        return CompiledSnsDialogue(sns_ui_signature(descriptor), display_locale, {}, ())
    peers = defaultdict(list)
    for source in descriptor['chains']:
        if any(identity not in rows for identity in source['text_ids']):
            raise ValueError('Original Baker chain references an absent prepared row')
        header = config['chats'].get(source['chat_id'])
        if not header:
            continue
        chain = [rows[identity] for identity in source['text_ids']]
        bodies = tuple(row.get('texts', {}).get(display_locale) for row in chain)
        if any(not isinstance(text, str) or not text.strip() for text in bodies):
            continue  # Never mix selected-study bodies with another display language.
        key = (normalize_text(header, display_locale), *(normalize_text(text, display_locale) for text in bodies))
        peers[key].append((SnsSourceChain(header, bodies, tuple(source['text_ids'])), chain))
    admitted = []
    for choices in peers.values():
        signatures = {tuple(sns_record_signature(row) for row in rows) for _, rows in choices}
        if len(signatures) != 1:
            continue
        source, chain = min(choices, key=lambda choice: choice[0].text_ids)
        # Unavailable/unknown/voiced cells remain conflict peers, never an
        # unvoiced identity. This route does not satisfy temporal short guards.
        if (not any(row.get('dialogue_kind') == 'message_system' for row in chain)
                or any(row.get('dialogue_kind') not in {'message', 'message_system'}
                       or row.get('voice_status') != 'unvoiced' or row.get('audio') is not None
                       or row.get('text_capture_verified') is not True
                       or 'dialogue' not in row.get('channels', ())
                       or row.get('requires_previous') or row.get('previous_text_id')
                       or row.get('player_voice') not in (None, player_voice)
                       for row in chain)):
            continue
        admitted.append(source)
    return CompiledSnsDialogue(sns_ui_signature(descriptor), display_locale, config, tuple(admitted))


def observe_sns_dialogue(compiled, spans, image_size, *, dialogue_menu=False):
    """Require mode, active header and 2–4 complete adjacent authored cells.

    Every selected line needs genuine confidence/geometry. Body positions stay
    independent: a chain can establish several visible system messages. A
    partial paragraph, contact preview, menu or old temporal anchor cannot do so.
    """
    if dialogue_menu or not compiled.chains or not compiled.config:
        return []
    try:
        width, height = image_size
        if (any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in image_size)
                or not isinstance(spans, list) or len(spans) > 512):
            return []
        positioned = []
        for span in spans:
            if not isinstance(span, dict) or not isinstance(span.get('text'), str) or len(span['text']) > 2048:
                return []
            text = span['text'].strip()
            if not text:
                continue
            box = _box(span, width, height)
            if box is None:
                return []
            score = span.get('confidence')
            reliable = type(score) in (int, float) and math.isfinite(score) and .8 <= score <= 1
            positioned.append((normalize_text(text, compiled.locale), box, reliable, text))
    except (TypeError, ValueError, OverflowError):
        return []
    config = compiled.config
    modes = {normalize_text(text, compiled.locale) for text in config['modes']}
    friends = normalize_text(config['friends'], compiled.locale)
    if any(key == friends and box[1] < .15 and box[0] < .4 for key, box, _, _ in positioned):
        return []
    mode = [box for key, box, reliable, _ in positioned
            if reliable and key in modes and box[0] < .35 and box[3] < .12]
    if len(mode) != 1:
        return []
    headers = {normalize_text(chain.header, compiled.locale) for chain in compiled.chains}
    visible = [(key, box) for key, box, reliable, _ in positioned
               if reliable and key in headers and box[0] >= .25
               and mode[0][3] < box[1] < .25 and box[3] < .28]
    if len(visible) != 1:
        return []
    header, header_box = visible[0]
    body = [row for row in positioned if row[0] and row[1][0] >= .28 and row[1][2] <= .99
            and row[1][1] > header_box[3] + .005 and row[1][3] < .95]
    body.sort(key=lambda row: (row[1][1], row[1][0]))

    def consume(start, wanted):
        value, previous = '', None
        for end in range(start, min(len(body), start + 64)):
            text, box, reliable, _ = body[end]
            if (not reliable or previous is not None
                    and (box[1] < previous[1] - .002 or box[1] - previous[3] > .055)):
                return None
            value += text
            if not wanted.startswith(value):
                return None
            if value == wanted:
                if end + 1 < len(body) and body[end + 1][1][1] - box[3] < .012:
                    return None  # Embedded in a longer wrapped paragraph.
                return end + 1
            previous = box
        return None

    observations = []
    for chain in compiled.chains:
        if normalize_text(chain.header, compiled.locale) != header:
            continue
        wanted = [normalize_text(text, compiled.locale) for text in chain.bodies]
        minimum, one_body = (12, 6) if len(header) == 1 else (8, 4)
        if min(map(len, wanted)) < 2 or sum(map(len, wanted)) < minimum or max(map(len, wanted)) < one_body:
            continue
        for start in range(len(body)):
            if start and body[start][1][1] - body[start - 1][1][3] < .012:
                continue
            ranges, at = [], start
            for part in wanted:
                if at >= len(body) or ranges and not .012 <= body[at][1][1] - body[at - 1][1][3] <= .10:
                    break
                end = consume(at, part)
                if end is None:
                    break
                ranges.append((at, end))
                at = end
            else:
                observations.extend(SnsBodyObservation(identity, ' '.join(body[i][3] for i in range(a, b)), (a, b))
                                    for identity, (a, b) in zip(chain.text_ids, ranges))
    return observations


def merge_sns_observations(matches, observations):
    """Keep existing match objects/confirmation; place scoped bodies in visual order."""
    if not observations:
        return matches
    identities = {hit.text_id for hit in observations}
    result = {key: value for key, value in matches.items() if key not in identities}
    result.update((hit.text_id, matches.get(hit.text_id, hit)) for hit in observations)
    return result
