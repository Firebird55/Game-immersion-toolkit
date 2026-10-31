"""Shared Source caption/sound bindings without cross-language voice fallback."""
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import wave
import zlib

from .source_formats import VpkArchive, compiled_captions, invalid, keyvalues, safe_name


def mapping(pairs):
    return {key.casefold(): value for key, value in pairs}


def steam_language(install, appid):
    """Return only the mounted language of a completed matching Steam install.

    Never persist or expose other appmanifest fields (including account IDs).
    UserConfig alone describes a requested language, not a completed download.
    """
    install = Path(install)
    manifest = install.parent.parent / f'appmanifest_{appid}.acf'
    if not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
        return None
    try:
        state = mapping(mapping(keyvalues(manifest.read_bytes()))['appstate'])
        if state.get('appid') != str(appid) or state.get('installdir', '').casefold() != install.name.casefold() or state.get('stateflags') != '4':
            return None
        mounted = mapping(state.get('mountedconfig', []))
        selected = mapping(state.get('userconfig', []))
        language = mounted.get('language', '').casefold()
        if selected.get('language', language).casefold() != language:
            return None
        return language or None
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        return None


class SourceFiles:
    """Explicit official mounts in priority order; no custom/mod search paths."""
    def __init__(self, install, archives, directories=()):
        self.install = Path(install).resolve()
        self.archives = []
        self.entries = {}
        for relative in archives:
            path = self.install / safe_name(relative)
            if not path.resolve().is_relative_to(self.install):
                raise invalid('Source archive escaped its install folder.')
            if path.is_file():
                archive = VpkArchive(path)
                self.archives.append(archive)
                for name in archive.entries:
                    self.entries.setdefault(name, {'archive': relative, 'member': name})
        self.directories = [safe_name(value) for value in directories]

    def locate(self, member):
        member = safe_name(member)
        if member in self.entries:
            return dict(self.entries[member])
        for directory in self.directories:
            relative = directory + '/' + member
            path = self.install / relative
            if path.resolve().is_relative_to(self.install) and path.is_file() and path.stat().st_size:
                return {'file': relative}
        return None

    def read(self, member, maximum=64 * 1024 * 1024):
        ref = self.locate(member)
        if not ref:
            raise FileNotFoundError('The requested Source game resource is not installed.')
        return self.read_ref(ref, maximum)

    def read_ref(self, ref, maximum=64 * 1024 * 1024):
        if 'archive' in ref:
            for archive in self.archives:
                if archive.path == self.install / ref['archive']:
                    return archive.read(ref['member'], maximum)
            raise invalid('Source voice archive is not an approved mount.')
        relative = safe_name(ref.get('file'))
        path = self.install / relative
        if not path.resolve().is_relative_to(self.install) or not any(relative.startswith(value + '/') for value in self.directories) or path.stat().st_size > maximum:
            raise invalid('Source loose file exceeds its bounds.')
        return path.read_bytes()


def text_table(data, native):
    root = mapping(mapping(keyvalues(data)).get('lang', []))
    # Localized files include [english] reference rows. They must never be
    # substituted for an untranslated selected-language token.
    aliases = {native, 'korean'} if native == 'koreana' else {native}
    language = root.get('language', '')
    if not isinstance(language, str) or language.casefold() not in aliases:
        raise invalid('Source text resource language does not match its filename.')
    result = {}
    for token, value in root.get('tokens', []):
        if token.casefold().startswith('[english]'):
            continue
        if not isinstance(value, str):
            raise invalid('Invalid Source localized text token.')
        token = token.casefold()
        if token in result and result[token] != value:
            raise invalid('Conflicting Source localized token.')
        result[token] = value
    return result


def captions(files, native):
    path = f'resource/closecaption_{native}'
    named = text_table(files.read(path + '.txt'), native)
    compiled = compiled_captions(files.read(path + '.dat'))
    result = {}
    hashes = {}
    for token in named:
        identity = zlib.crc32(token.encode('utf-8'))
        if identity in hashes and hashes[identity] != token:
            raise invalid('Ambiguous Source caption hash.')
        hashes[identity] = token
        if identity in compiled:
            result[token] = compiled[identity]
    return result


def sound_path(value):
    if not isinstance(value, str) or value.startswith(('!', '?')):
        return None
    value = value.lstrip('*#@><^)}').replace('\\', '/')
    if not value.casefold().endswith(('.wav', '.mp3')):
        return None
    return safe_name('sound/' + value)


def sound_events(files):
    root = mapping(keyvalues(files.read('scripts/game_sounds_manifest.txt')))
    events, conflicting, missing = {}, set(), []
    for key, path in root.get('game_sounds_manifest', []):
        if key.casefold() not in {'precache_file', 'preload_file'} or not isinstance(path, str):
            continue
        path = safe_name(path.replace('\\', '/'))
        if not files.locate(path):
            missing.append(path)
            continue
        for name, pairs in keyvalues(files.read(path)):
            if not isinstance(pairs, list):
                continue
            options = mapping(pairs)
            direct = [sound_path(value) for key, value in pairs if key.casefold() == 'wave']
            random = [sound_path(value) for key, value in options.get('rndwave', []) if key.casefold() == 'wave']
            waves = tuple(dict.fromkeys(value for value in direct + random if value))
            record = {'waves': waves, 'random': bool(random), 'channel': options.get('channel', '')}
            name = name.casefold()
            if name in events and events[name] != record:
                conflicting.add(name)
            events[name] = record
    for name in conflicting:
        events[name] = {'waves': (), 'random': False, 'channel': ''}
    return events, missing


def clean_caption(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', value.replace('\\n', '\n'))).strip()


def caption_pages(value):
    return list(dict.fromkeys(clean_caption(part) for part in re.split(r'<delay:[^>]+>', value, flags=re.I) if clean_caption(part)))


def resolve_sequence(token, events, sequences):
    """Resolve explicit event waves, then authored scene overrides.

    Randomized sound scripts are unresolved: a generic turret caption does not
    identify which differently worded recording the engine selected.
    """
    if token in events:
        event = events[token]
        if len(event['waves']) == 1:
            return ((event['waves'][0], 0),)
        return ()
    sequence = sequences.get(token, ())
    result = []
    for sound, at in sequence:
        event = events.get(sound)
        if event:
            if len(event['waves']) != 1:
                return ()
            path = event['waves'][0]
        else:
            path = sound_path(sound)
        if not path:
            return ()
        result.append((path, at))
    if result:
        return tuple(result)
    # Commentary caption keys are original dry-mix filenames. Require the
    # authored extension, and restrict direct file keys to that namespace.
    if token.startswith('#commentary\\') or token.startswith('#commentary/'):
        path = sound_path(token)
        return ((path, 0),) if path else ()
    return ()


def pack_performance(blobs):
    if not 1 <= len(blobs) <= 64 or sum(len(data) for data in blobs) > 256 * 1024 * 1024:
        raise invalid('Source performance exceeds its size limit.')
    return b'SRCVOIC1' + struct.pack('<I', len(blobs)) + b''.join(struct.pack('<I', len(data)) + data for data in blobs)


def unpack_performance(data):
    if len(data) < 12 or len(data) > 256 * 1024 * 1024 or data[:8] != b'SRCVOIC1':
        raise invalid('Invalid Source performance container.')
    count = struct.unpack_from('<I', data, 8)[0]
    if not 1 <= count <= 64:
        raise invalid('Invalid Source performance count.')
    cursor, blobs = 12, []
    for _ in range(count):
        if cursor + 4 > len(data):
            raise invalid('Truncated Source performance.')
        size = struct.unpack_from('<I', data, cursor)[0]
        cursor += 4
        if not 0 < size <= 64 * 1024 * 1024 or cursor + size > len(data):
            raise invalid('Source recording exceeds its performance.')
        blobs.append(data[cursor:cursor + size]); cursor += size
    if cursor != len(data):
        raise invalid('Unexpected Source performance bytes.')
    return blobs


def _complete_pcm_wave(data):
    """Validate actual PCM bytes, rather than trusting a WAV's declared frames.

    Structurally valid non-PCM WAVE stays eligible for the source codec path.
    Damaged containers fail before any decoder or output publication.
    """
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise invalid('Invalid Source original WAVE container.')
    if struct.unpack_from('<I', data, 4)[0] + 8 != len(data):
        raise invalid('Source original WAVE container length changed.')
    cursor, chunks, fmt = 12, defaultdict(list), None
    while cursor < len(data):
        if cursor + 8 > len(data):
            raise invalid('Truncated Source original WAVE chunk.')
        name, size = struct.unpack_from('<4sI', data, cursor)
        start, end = cursor + 8, cursor + 8 + size
        if end > len(data):
            raise invalid('Truncated Source original WAVE data.')
        chunks[name].append(size)
        if name == b'fmt ':
            fmt = data[start:end]
        # Some original PCM writers omit the final odd-byte padding. There is
        # no following chunk to misalign in that case; retain those valid bytes.
        cursor = end if end == len(data) else end + (size & 1)
    if cursor != len(data) or len(chunks[b'fmt ']) != 1 or len(chunks[b'data']) != 1:
        raise invalid('Unsupported Source original WAVE chunk layout.')
    if len(fmt) < 16:
        raise invalid('Truncated Source original WAVE format.')
    tag, channels, rate, byte_rate, alignment, bits = struct.unpack_from('<HHIIHH', fmt)
    if not tag or not channels or not rate or not byte_rate or not alignment:
        raise invalid('Invalid Source original WAVE format fields.')
    is_pcm = tag == 1
    if tag == 0xfffe:
        if len(fmt) < 40 or struct.unpack_from('<H', fmt, 16)[0] < 22:
            raise invalid('Truncated Source original extensible WAVE format.')
        if 18 + struct.unpack_from('<H', fmt, 16)[0] > len(fmt):
            raise invalid('Truncated Source original WAVE format extension.')
        is_pcm = fmt[24:40] == bytes.fromhex('0100000000001000800000aa00389b71')
        if is_pcm and not 0 < struct.unpack_from('<H', fmt, 18)[0] <= bits:
            raise invalid('Invalid Source original PCM valid-bit count.')
    if not is_pcm:
        return False
    if (bits not in {8, 16, 24, 32} or alignment != channels * (bits // 8)
            or byte_rate != rate * alignment):
        raise invalid('Invalid Source original PCM frame format.')
    try:
        stream = wave.open(io.BytesIO(data))
    except wave.Error:
        raise invalid('Invalid Source original PCM format.') from None
    except EOFError:
        raise invalid('Truncated Source original WAVE format.') from None
    with stream:
        if stream.getcomptype() != 'NONE':
            return False
        frames, rate = stream.getnframes(), stream.getframerate()
        frame_bytes = stream.getnchannels() * stream.getsampwidth()
        if not rate or not frame_bytes or not 0 < frames <= rate * 1800:
            raise invalid('Source original audio duration exceeds its limit.')
        expected = frames * frame_bytes
        if chunks[b'data'][0] != expected:
            raise invalid('Source original PCM data is not aligned to complete frames.')
        remaining = expected
        while remaining:
            block = stream.readframes(min(65536, (remaining + frame_bytes - 1) // frame_bytes))
            if not block or len(block) > remaining:
                raise invalid('Truncated Source original PCM frames.')
            remaining -= len(block)
        return True


def decode_performance(data, audio, output, decoder, scratch):
    # Both the unchanged-PCM path and the source codec path publish only after
    # validation. A malformed stream or failed decoder retains prior output.
    output = Path(output)
    with tempfile.TemporaryDirectory(prefix='source-pcm-', dir=output.parent) as temporary:
        pending = Path(temporary) / 'performance.wav'
        _decode_performance(data, audio, pending, decoder, scratch)
        pending.replace(output)


def _decode_performance(data, audio, output, decoder, scratch):
    from .media_tools import ffmpeg_executable
    blobs = unpack_performance(data)
    parts = audio.get('parts', [])
    if len(blobs) != len(parts):
        raise invalid('Source performance no longer matches its timing.')
    options = {'check': True, 'capture_output': True, 'timeout': 90,
               'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
    if len(blobs) == 1 and blobs[0][:4] == b'RIFF' and parts[0].get('at_ms') == 0:
        if _complete_pcm_wave(blobs[0]):
            Path(output).write_bytes(blobs[0])
            return
    executable = ffmpeg_executable()
    if not executable:
        raise invalid('The installed media decoder is unavailable.')
    command = [str(executable), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    for index, blob in enumerate(blobs):
        if blob[:4] == b'RIFF' and blob[8:12] == b'WAVE':
            suffix = '.wav'
        elif blob[:3] == b'ID3' or len(blob) > 1 and blob[0] == 255 and blob[1] & 0xE0 == 0xE0:
            suffix = '.mp3'
        else:
            raise invalid('Unsupported Source original audio encoding.')
        path = Path(scratch) / f'source-{index}{suffix}'
        path.write_bytes(blob)
        command += ['-i', str(path)]
    filters = []
    for index, part in enumerate(parts):
        delay = part.get('at_ms')
        if type(delay) is not int or not 0 <= delay <= 1800000:
            raise invalid('Invalid Source performance offset.')
        filters.append(f'[{index}:a]adelay={delay}:all=1[a{index}]')
    filters.append(''.join(f'[a{i}]' for i in range(len(parts))) + f'amix=inputs={len(parts)}:normalize=0[out]')
    # Decode one second beyond the supported bound so long input is rejected,
    # never silently exported as a truncated original performance.
    command += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-t', '1801', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', str(output)]
    subprocess.run(command, **options)
    with wave.open(str(output)) as stream:
        if not 0 < stream.getnframes() <= stream.getframerate() * 1800:
            raise invalid('Source original audio duration exceeds its limit.')


def reference_signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
