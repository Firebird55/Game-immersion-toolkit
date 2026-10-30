"""Original-PC Decima sentence, localized sound, and readable resource schemas.

Field layout corroborated against original-PC RTTI metadata and binary handlers
in ShadelessFox/decima-workshop, then validated against installed resources.
Only explicit UUID references establish text/audio associations.
"""
from __future__ import annotations

import math

from .decima_archive import AUDIO_NAMES, Cursor, invalid, safe_path

SENTENCE = 0xAD7F486B5DD745A4
TEXT = 0x31BE502435317445
SOUND = 0xC726DF870437D774  # Original PC; Director's Cut has a different schema.
GROUP = 0xC144982A3EE1E95D
MAIL = 0x8AE41F7BC588FD6D
INTERVIEW = 0x3A91CD86B3B5CB20
TYPES = {SENTENCE, TEXT, SOUND, GROUP, MAIL, INTERVIEW}


def reference(cursor, allow_empty=False):
    kind, = cursor.unpack('B')
    if kind not in (0, 1, 2, 3, 5):
        raise invalid('Unsupported Decima reference type.')
    if not kind:
        return None
    identity = cursor.take(16).hex()
    path = cursor.string() if kind in (2, 3) else None
    if path is not None and (path or not allow_empty):
        safe_path(path)
    return (path, identity)


def core_objects(data):
    cursor, result, counts = Cursor(data), {}, {}
    while cursor.pos < len(data):
        kind, size = cursor.unpack('QI')
        body = cursor.take(size)
        counts[kind] = counts.get(kind, 0) + 1
        if sum(counts.values()) > 200_000:
            raise invalid('Too many Decima resource objects.')
        if kind not in TYPES:
            continue
        if len(body) < 16:
            raise invalid('Truncated Decima resource identity.')
        identity = body[:16].hex()
        if identity in result:
            raise invalid('Duplicate Decima resource identity.')
        result[identity] = (kind, body)
    return result, counts


def sentence(body):
    cursor = Cursor(body)
    cursor.take(16)
    delivery, delay, show = cursor.unpack('BfB')
    if delivery not in (0, 1, 2) or not math.isfinite(delay) or show not in (0, 1):
        raise invalid('Unsupported Death Stranding sentence fields.')
    sound, animation, text, voice = [reference(cursor) for _ in range(4)]
    cursor.finish()
    return {'sound': sound, 'animation': animation, 'text': text, 'voice': voice,
            'delivery': delivery, 'show_subtitles': bool(show)}


def localized_text(body):
    cursor = Cursor(body)
    cursor.take(16)
    result = {}
    # ELanguage IDs 1..25, including the engine's unused locale slots. Never
    # collapse empty entries, which would shift later languages into English.
    for language in range(1, 26):
        length, = cursor.unpack('H')
        try:
            text = cursor.take(length).decode('utf-8')
            length, = cursor.unpack('H')
            cursor.take(length).decode('utf-8')  # translator notes
        except UnicodeDecodeError as error:
            raise invalid('Invalid Death Stranding localized text.') from error
        mode, = cursor.unpack('B')
        if mode not in (0, 1, 2):
            raise invalid('Unsupported Death Stranding subtitle visibility mode.')
        result[language] = (text, mode)
    cursor.finish()
    return result


def localized_sound(body):
    cursor = Cursor(body)
    cursor.take(16)
    cursor.string()  # ResourceWithName.Name
    reference(cursor)  # SoundResource.Group
    # Serialized SoundResource scalars (including SoundShape), WwiseName.Id,
    # WwiseSimpleSoundResource.Flags. This is the original-PC C726... schema.
    cursor.take(137)
    reference(cursor)  # SoundMixState
    reference(cursor)  # Preset
    durations = cursor.count(26)
    cursor.take(4 * durations)
    identifiers = cursor.count(26)
    cursor.take(4 * identifiers)
    cursor.take(4)  # VolumeCorrectionRTPCValue
    mask, streaming, vbr, quality, frame, encoding, channels, rate, bits, bitrate, alignment, tag = cursor.unpack('HBBB HBB IHIHH'.replace(' ', ''))
    if (mask & ~0xfff or streaming != 1 or vbr not in (0, 1)
            or not 1 <= channels <= 8 or rate not in (22050, 24000, 32000, 44100, 48000)
            or not 0 < bits <= 32 or encoding != 4 or tag != 1):
        raise invalid('Unsupported Death Stranding localized voice encoding.')
    result = {}
    for i, language in enumerate(AUDIO_NAMES):
        if not mask & (1 << i):
            continue
        length, = cursor.unpack('B')
        end = cursor.pos + length
        path = safe_path(cursor.string(hashed=False))
        identity = cursor.take(16).hex()
        channel, offset, size = cursor.unpack('III')
        if (cursor.pos != end or not path.startswith('localized/')
                or not path.endswith('.wem.' + language) or not 0 < size <= 64 * 1024 * 1024):
            raise invalid('Invalid Death Stranding authored voice source.')
        result[language] = {'stream': path + '.core.stream', 'uuid': identity,
                            'channel': channel, 'offset': offset, 'length': size}
    cursor.finish()
    return result


def readable(kind, body):
    """Read explicit text fields in resources with no audio member."""
    cursor = Cursor(body)
    cursor.take(16)
    if kind == MAIL:
        reference(cursor)  # household sender
        refs = {field: reference(cursor) for field in ('title', 'body', 'sender')}
        flags = cursor.take(4)
        if any(flag not in (0, 1) for flag in flags):
            raise invalid('Unsupported Death Stranding mail flags.')
        cursor.take(10)  # gift likes, receive delay, internal name
    elif kind == INTERVIEW:
        cursor.take(5)  # menu order + flags
        refs = {field: reference(cursor) for field in ('title', 'body', 'description')}
        group, = cursor.unpack('B')
        if group > 12:
            raise invalid('Unsupported Death Stranding interview group.')
        refs.update({field: reference(cursor) for field in ('who', 'when', 'where')})
        reference(cursor, allow_empty=True)  # an optional streaming image may have an empty path
        cursor.take(8)  # mission gate
        deferred, = cursor.unpack('B')
        if deferred not in (0, 1):
            raise invalid('Unsupported Death Stranding interview flags.')
    else:
        raise invalid('Unknown Death Stranding readable type.')
    cursor.finish()
    return refs
