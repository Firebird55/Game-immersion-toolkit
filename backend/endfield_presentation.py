"""Stateless original Endfield world-dialogue evidence from visible OCR spans."""
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from .languages import normalize_text


SOURCE_ROLES = frozenset(('dialog', 'top', 'profile', 'dialog_ctrl', 'dialog_base', 'profile_ctrl'))


def validate_world_dialogue_ui(value):
    """Canonical, bounded metadata shared by desktop and portable libraries."""
    if (not isinstance(value, dict) or set(value) != {'schema', 'revision', 'sources', 'locales'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['revision'], str)
            or re.fullmatch(r'endfield-[0-9a-f]{64}', value['revision']) is None
            or not isinstance(value['sources'], dict) or set(value['sources']) != SOURCE_ROLES
            or any(not isinstance(v, str) or re.fullmatch(r'[0-9a-f]{32}', v) is None
                   for v in value['sources'].values())
            or not isinstance(value['locales'], dict) or not 1 <= len(value['locales']) <= 64):
        raise ValueError('Invalid original Endfield dialogue UI metadata')

    def words(items, maximum):
        if (not isinstance(items, list) or not 1 <= len(items) <= maximum
                or any(not isinstance(t, str) or not t.strip() or t != t.strip()
                       or len(t) > 128 or any(c in t for c in '\r\n\0') for t in items)):
            raise ValueError('Invalid original Endfield dialogue UI label')
        return sorted(set(items))

    locales = {}
    for locale, row in value['locales'].items():
        if (not isinstance(locale, str) or re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}', locale) is None
                or not isinstance(row, dict) or set(row) != {'auto', 'skip', 'profile', 'speakers'}
                or not isinstance(row['speakers'], dict) or not 1 <= len(row['speakers']) <= 4096):
            raise ValueError('Invalid original Endfield dialogue UI locale')
        speakers = {}
        for identity, labels in row['speakers'].items():
            if not isinstance(identity, str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', identity) is None:
                raise ValueError('Invalid original Endfield dialogue UI speaker')
            speakers[identity] = words(labels, 8)
        locales[locale] = {'auto': words(row['auto'], 4), 'skip': words(row['skip'], 2),
                           'profile': words(row['profile'], 4), 'speakers': speakers}
        normalized = {key: {normalize_text(t, locale) for t in locales[locale][key]}
                      for key in ('auto', 'skip', 'profile')}
        if (any(not t for values in normalized.values() for t in values)
                or len(normalized['profile']) < 2 or normalized['auto'] & normalized['skip']
                or any(not normalize_text(t, locale) for values in speakers.values() for t in values)):
            raise ValueError('Incomplete original Endfield dialogue UI labels')
    result = {**value, 'sources': dict(value['sources']), 'locales': locales}
    if len(json.dumps(result, ensure_ascii=True)) > 256 * 1024:
        raise ValueError('Original Endfield dialogue UI metadata is too large')
    return result


def world_ui_signature(value):
    return sha256(json.dumps(validate_world_dialogue_ui(value), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class WorldCaptionEvidence:
    ui_signature: str
    locale: str
    original_speaker_id: str
    caption: str


def _box(span, width, height):
    try:
        raw = span['bounding_rect']
        xs = [float(raw['x' + str(i)]) / width for i in range(1, 5)]
        ys = [float(raw['y' + str(i)]) / height for i in range(1, 5)]
        left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
        if (all(math.isfinite(v) for v in xs + ys)
                and 0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            return left, top, right, bottom
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        pass
    return None


def observe_world_caption(value, spans, image_size):
    """Require complete controls and a separate, source-owned bottom caption.

    NPC response options may coexist elsewhere in the frame. They never enter
    this stateless caption and cannot establish or retain a predecessor.
    Unknown confidence, missing geometry and mixed/changed UI fail closed.
    """
    try:
        descriptor = validate_world_dialogue_ui(value)
        width, height = image_size
        if (type(width) not in (int, float) or type(height) not in (int, float)
                or not math.isfinite(width) or not math.isfinite(height) or min(width, height) <= 0
                or not isinstance(spans, list) or len(spans) > 4096):
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    positioned = []
    for span in spans:
        if not isinstance(span, dict) or not isinstance(span.get('text'), str):
            return None
        text = span['text'].strip()
        if not text:
            continue
        box = _box(span, width, height)
        if box is None:
            return None
        confidence = span.get('confidence')
        try:
            reliable = type(confidence) in (int, float) and math.isfinite(confidence) and .8 <= confidence <= 1
        except OverflowError:
            reliable = False
        positioned.append((text, box, reliable))
    # A profile can overlay an older world frame. Its own complete header
    # prevents background controls from identifying the visible recording.
    for locale, config in descriptor['locales'].items():
        profile = {normalize_text(t, locale) for t in config['profile']}
        if len({normalize_text(t, locale) for t, b, _ in positioned
                if b[1] < .5 and normalize_text(t, locale) in profile}) >= 2:
            return None
    observations = []
    for locale, config in descriptor['locales'].items():
        rows = [(text, box, normalize_text(text, locale), reliable) for text, box, reliable in positioned]
        auto = {normalize_text(t, locale) for t in config['auto']}
        skip = {normalize_text(t, locale) for t in config['skip']}
        autos = [b for _, b, t, reliable in rows if reliable and t in auto and b[0] > .65 and b[3] < .2]
        skips = [b for _, b, t, reliable in rows if reliable and t in skip and b[0] > .65 and b[3] < .2]
        if len(autos) != 1 or len(skips) != 1:
            continue
        a, s = autos[0], skips[0]
        if not a[2] < s[0] or s[0] - a[2] > .2 or abs((a[1] + a[3] - s[1] - s[3]) / 2) > .045:
            continue
        names = defaultdict(set)
        for identity, labels in config['speakers'].items():
            for text in labels:
                names[normalize_text(text, locale)].add(identity)
        speakers = [(b, names[t]) for _, b, t, reliable in rows if reliable and t in names and len(names[t]) == 1
                    and .76 < b[1] < .92 and .2 < (b[0] + b[2]) / 2 < .8]
        if len(speakers) != 1:
            continue
        actor_box, actors = speakers[0]
        body = [(t, b, reliable) for t, b, _, reliable in rows if b[1] >= actor_box[3] and b[1] > .82
                and .15 < (b[0] + b[2]) / 2 < .85 and b[2] - b[0] > .1]
        if not body or not all(reliable for _, _, reliable in body):
            continue
        body.sort(key=lambda row: (row[1][1], row[1][0]))
        center = (min(b[0] for _, b, _ in body) + max(b[2] for _, b, _ in body)) / 2
        if abs(center - (actor_box[0] + actor_box[2]) / 2) > .12:
            continue
        previous = actor_box[3]
        for _, box, _ in body:
            if box[1] - previous > .08:
                break
            previous = box[3]
        else:
            observations.append((locale, next(iter(actors)), ' '.join(t for t, _, _ in body)))
    if not observations or len({(actor, text) for _, actor, text in observations}) != 1:
        return None
    locale, actor, text = observations[0]
    return WorldCaptionEvidence(world_ui_signature(descriptor), locale, actor, text)
