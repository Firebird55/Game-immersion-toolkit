"""Authored Director's Cut movie timelines and original CRI audio tracks."""
from pathlib import PureWindowsPath
import re
import struct

from . import deusex_hr_formats as fmt
from .persona_cri import utf

LOCALE_CODES = {'en': 0, 'fr': 1, 'it': 2, 'de': 3, 'es-ES': 4}
_NAMES = {'eng': 'en', 'fra': 'fr', 'fr': 'fr', 'ger': 'de', 'ita': 'it', 'it': 'it', 'spa': 'es-ES'}
_LANGUAGE = re.compile(r'(?<=_)(eng|fra|fr|ger|ita|it|spa|rus|ru|jap)(?=_|\.)')


def movie_binding(section):
    if section.kind != 7 or section.subtype != 0 or section.data[:16] != b'\xeb\xbe\xeb\xbe' * 4:
        return None
    data, refs = section.data, fmt.local_references(section)
    if not all(offset in refs for offset in (0, 4, 8, 12, 20)) or len(data) < 24:
        return None

    def string(offset):
        end = data.find(b'\0', offset)
        if end < 0 or end-offset > 2048:
            raise ValueError('Invalid Deus Ex cinematic path')
        return data[offset:end].decode('ascii').lower()

    path = string(refs[4])
    if not path.startswith('cinematics\\') or not path.endswith('.avi'):
        return None
    if any(part in {'', '.', '..'} for part in path.split('\\')) or ':' in path:
        raise ValueError('Unsafe Deus Ex movie resource path')
    count, table = struct.unpack_from('<I', data, 16)[0], refs[12]
    if not 0 <= count <= 32 or table + count * 40 > len(data):
        raise ValueError('Invalid Deus Ex movie audio-track table')
    variants, unbound = {}, set()
    for index in range(count):
        at = table + index * 40
        kind, language = struct.unpack_from('<II', data, at+16)
        samples = struct.unpack_from('<I', data, at+36)[0]
        cues = set()
        if samples:
            cue_at = refs.get(at+32)
            if cue_at is None or samples > 10000 or cue_at + samples * 12 > len(data):
                raise ValueError('Invalid Deus Ex cinematic subtitle timeline')
            for start, end, text in struct.iter_unpack('<III', data[cue_at:cue_at+samples*12]):
                if not 0 <= start < end <= 4 * 3600 * 1000 or not text:
                    raise ValueError('Invalid Deus Ex cinematic subtitle cue')
                cues.add((start, end, text))
        if kind != 1:
            continue
        resource = refs.get(at+12)
        name_at = refs.get(resource)
        if name_at is None:
            unbound.update(cues)
            continue
        name = string(name_at)
        name = PureWindowsPath(name).name
        codes = {match[1] for match in _LANGUAGE.finditer(name)}
        if not name.endswith('.wav') or len(codes) != 1:
            raise ValueError('Ambiguous Deus Ex cinematic voice filename')
        code = next(iter(codes))
        # Several shipped records exchange German/Italian numeric values.
        # The authored filename and CRI directory agree on the actual voice.
        variant = _LANGUAGE.sub('{locale}', name)
        group = variants.setdefault(variant, {'voices': {}, 'cues': set()})
        group['cues'].update(cues)
        if code in _NAMES:
            locale = _NAMES[code]
            if locale in group['voices'] and group['voices'][locale] != name:
                raise ValueError('Ambiguous Deus Ex cinematic voice locale')
            group['voices'][locale] = name
    # A normal movie authors one voice per locale, even when translators used
    # a different WAV basename. Its one subtitle timeline belongs to that
    # movie. Multiple ending performances per locale retain distinct variants.
    by_locale = {}
    for group in variants.values():
        for locale, name in group['voices'].items():
            by_locale.setdefault(locale, set()).add(name)
    if len(variants) > 1 and all(len(names) == 1 for names in by_locale.values()):
        primary = next((key for key, group in variants.items() if 'en' in group['voices']), next(iter(variants)))
        variants = {primary: {'voices': {locale: next(iter(names)) for locale, names in by_locale.items()},
                              'cues': set().union(*(group['cues'] for group in variants.values()))}}
    return {'media': fmt.filename_hash('pc-w\\design_database\\videos\\' + path[:-4] + '.usm'),
            'variants': {key: {'voices': value['voices'], 'cues': sorted(value['cues'])} for key, value in variants.items()},
            'unbound_cues': sorted(unbound), 'making_of': path == 'cinematics\\final_cinematics\\cut_23_makingof\\makingof.avi'}


def packet(archive, entry, position):
    header = archive.read(entry, position, 32)
    tag, size = struct.unpack_from('>4sI', header)
    offset, padding, channel, kind = header[9], struct.unpack_from('>H', header, 10)[0], header[12], header[15]
    if offset < 24 or size < offset + padding or position + 8 + size > entry.size:
        raise ValueError('Invalid CRI movie packet range')
    return tag, kind, channel, position+8+offset, size-offset-padding, position+8+size


def movie_tracks(archive, entry):
    tracks, audio = None, {}
    position = 0
    while position < min(entry.size, 4 * 1024 * 1024):
        tag, kind, channel, start, size, next_position = packet(archive, entry, position)
        if kind == 0:
            break
        if tag == b'CRID' or tag == b'@SFA' and kind == 1:
            if size > 256 * 1024:
                raise ValueError('CRI movie audio metadata exceeds the supported bound')
            rows = utf(archive.read(entry, start, size))
            if tag == b'CRID':
                if tracks is not None:
                    raise ValueError('Duplicate CRI movie stream directory')
                tracks = rows
            elif len(rows) != 1 or channel in audio:
                raise ValueError('Invalid CRI movie audio description')
            else:
                audio[channel] = rows[0]
        position = next_position
    if tracks is None:
        raise ValueError('Missing CRI movie stream directory')
    result = {}
    for row in tracks:
        if row.get('stmid') != int.from_bytes(b'@SFA', 'big'):
            continue
        name, channel = row.get('filename'), row.get('chno')
        metadata = audio.get(channel)
        if not isinstance(name, str) or not metadata:
            raise ValueError('Invalid CRI original voice track directory')
        rate, samples, channels = (metadata.get(key) for key in ('sampling_rate', 'total_samples', 'num_channels'))
        if type(channel) is not int or not 0 <= channel <= 255 or type(rate) is not int or rate not in {22050, 32000, 44100, 48000} or type(samples) is not int or samples <= 0 or channels not in {1, 2, 6}:
            raise ValueError('Unsupported CRI original voice track')
        info = {'track': channel, 'rate': rate, 'samples': samples, 'channels': channels}
        if name.casefold() in result:
            previous = result[name.casefold()]
            if any(previous[key] != info[key] for key in ('rate', 'samples', 'channels')):
                raise ValueError('Conflicting CRI duplicate voice metadata')
            previous.setdefault('duplicate_tracks', []).append(channel)
        else:
            result[name.casefold()] = info
    return result


def demux_adx(archive, entry, track):
    position, output = 0, bytearray()
    while position < entry.size:
        tag, kind, channel, start, size, position = packet(archive, entry, position)
        if tag == b'@SFA' and kind == 0 and channel == track:
            if len(output) + size > 128 * 1024 * 1024:
                raise ValueError('CRI original voice exceeds the supported bound')
            output.extend(archive.read(entry, start, size))
    adx_header(output)
    return bytes(output)


def adx_header(data):
    if len(data) < 24 or data[:2] != b'\x80\0' or data[4:7] != b'\x03\x12\x04':
        raise ValueError('Invalid original CRI ADX header')
    header_size = int.from_bytes(data[2:4], 'big') + 4
    if not 24 <= header_size <= len(data) or data[header_size-6:header_size] != b'(c)CRI' or data[18] not in {3, 4} or data[19]:
        raise ValueError('Unsupported or encrypted original CRI ADX header')
    channels, rate, samples = data[7], *struct.unpack_from('>II', data, 8)
    if channels not in {1, 2, 6} or rate not in {22050, 32000, 44100, 48000} or not samples:
        raise ValueError('Unsupported original CRI ADX waveform')
    return {'channels': channels, 'rate': rate, 'samples': samples}
