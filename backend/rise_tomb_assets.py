"""Official Rise of the Tomb Raider subtitles bound to their original MUL audio."""
from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import struct
import subprocess
import time
import wave

from .preparation_errors import PreparationFailure
from .textmaps import display_text
from .tiger_archive import TigerSet, TigerEntry, fingerprint as archive_fingerprint, name_hash32

LANGUAGE_INDEX_VERSION = 1
GAME = 'riseofthetombraider'
# Authored language IDs, not launcher ordinals. Separate Chinese recordings are
# retained. Arabic and Latin American Spanish are also present in official DLC.
TEXT_LOCALES = {'en': 0, 'fr': 1, 'de': 2, 'it': 3, 'es-419': 4,
    'es-ES': 5, 'ja': 6, 'pt-BR': 7, 'pl': 8, 'ru': 9, 'nl': 10,
    'ko': 11, 'zh-Hant': 12, 'zh-Hans': 13, 'ar': 15}
PACK_NAMES = {'en': 'ENGLISH', 'fr': 'FRENCH', 'de': 'GERMAN', 'it': 'ITALIAN',
    'es-419': 'LATAMSPANISH', 'es-ES': 'IBERSPANISH', 'ja': 'JAPANESE',
    'pt-BR': 'PORTUGUESE', 'pl': 'POLISH', 'ru': 'RUSSIAN', 'ko': 'KOREAN',
    'zh-Hant': 'CHINESE', 'zh-Hans': 'SIMPLECHINESE', 'ar': 'ARABIC'}
SUPPORTED_LOCALES = tuple(PACK_NAMES)
_LOCALES = {str(value): key for key, value in TEXT_LOCALES.items()}
_LOCALS_HASH = name_hash32(r'pcx64-w\local\locals.bin')


def _movies(install):
    return sorted((path for path in (install / 'movies').rglob('*.bik') if path.is_file()),
                  key=lambda path: path.relative_to(install).as_posix())


def fingerprint(install):
    stamps = [archive_fingerprint(install), *(f'{path.relative_to(install).as_posix()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
              for path in _movies(install))]
    return hashlib.sha256('|'.join(stamps).encode()).hexdigest()


def _invalid(message='Unsupported or incomplete Rise dialogue stream.'):
    return PreparationFailure('rise_dialogue_format', message +
        ' Verify game files in the launcher, then update the toolkit and retry preparation.')


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for candidate in candidates:
        path = Path(candidate)
        if (path / 'ROTTR.exe').is_file() and (path / 'bigfile.000.tiger').is_file():
            return path
    return None


def probe_voice_pack(install: Path, locale: str):
    """Cheap launcher-pack presence check; full binding checks happen on Prepare."""
    if locale not in PACK_NAMES:
        return 'unknown'
    suffix = f'_{PACK_NAMES[locale]}.000.tiger'.casefold()
    candidates = [path for path in install.glob('*.000.tiger') if path.name.casefold().endswith(suffix)]
    if not candidates:
        return 'missing'
    present = []
    for path in candidates:
        try:
            with path.open('rb') as stream:
                header = stream.read(52)
            magic, version, parts, count, _identity = struct.unpack_from('<4s4I', header)
            if magic != b'TAFS' or version != 4 or not 1 <= parts <= 256 or count > 2_000_000 or 52 + count * 24 > path.stat().st_size:
                return 'incomplete'
            if count:
                present.append(path.name.casefold())
        except (OSError, struct.error):
            return 'incomplete'
    return 'present' if f'bigfile{suffix}' in present else 'incomplete'


class _Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise _invalid()
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def integer(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self, limit=100000):
        value = self.integer()
        if not 0 <= value <= limit:
            raise _invalid()
        return value


def _cine_header(cursor):
    if cursor.take(4) != b'ENIC':
        raise _invalid()
    version, size = cursor.integer(), cursor.count(16 * 1024 * 1024)
    if version != 14:
        raise _invalid('This Rise cinematic version is not supported.')
    cursor.take(4 + 0x40 + 4)
    anchors = cursor.count(); cursor.take(12 * anchors)
    channels = 9 * anchors
    skeletons = cursor.count()
    for _ in range(skeletons):
        cursor.take(4)
        bones = cursor.count(); cursor.take(4 + 64 * bones)
        channels += 3 + 14 * bones
        lights = cursor.count(); cursor.take(4 + 24 * lights)
        channels += lights * 10
        channels += cursor.count(); cursor.take(4)
        channels += cursor.count(); cursor.take(4)
    cameras = cursor.count(); cursor.take(4 * cameras + 4)
    triggers = cursor.count(); cursor.take(8 * triggers + 4)
    channels += cameras * 16 + triggers
    cursor.take(28 * skeletons + 28 * cameras)
    if cameras:
        cursor.take(4 * cursor.count())
    if cursor.pos != size + 8 or channels > 100000:
        raise _invalid()
    return [[0, False] for _ in range(channels)]


def _clean(value):
    # MUL captions have authored style/duration controls, e.g. [c4i1b1d1.5].
    return display_text(re.sub(r'\[(?:[cibd][-+\d.]+)+\]', '', value).replace('\n', ' '))


def is_mul(data):
    return (len(data) >= 60 and struct.unpack_from('<I', data)[0] in (22050, 32000, 44100, 48000)
            and 0 <= struct.unpack_from('<i', data, 12)[0] <= 12
            and struct.unpack_from('<I', data, 32)[0] in (0, 1)
            and struct.unpack_from('<I', data, 36)[0] in (0, 1))


def read_mul(data: bytes, *, audio=False):
    """Read bounded packets; retain full performances and authored OCR pages.

    A subtitle frame can be only one page of a longer utterance. The adapter
    groups the complete stream and never guesses cuts from text duration tags.
    """
    if not is_mul(data) or len(data) < 8192:
        raise _invalid()
    channels = struct.unpack_from('<i', data, 12)[0]
    animation, subtitle_flag = struct.unpack_from('<II', data, 32)
    mix = [[struct.unpack_from('<f', data, 60 + channel * 4)[0],
            struct.unpack_from('<f', data, 108 + channel * 4)[0]] for channel in range(channels)]
    if any(not math.isfinite(value) or abs(value) > 16 for pair in mix for value in pair):
        raise _invalid('Unsupported Rise authored channel mix.')
    chunks, prefixes, channel_lengths = [bytearray() for _ in range(channels)], [b''] * channels, [0] * channels
    pages, cine_channels, pos, previous_frame = [], None, 8192, -1
    packet_count = 0
    while pos < len(data):
        if len(data) - pos < 16:
            if any(data[pos:]):
                raise _invalid()
            break
        kind, size = struct.unpack_from('<II', data, pos)
        end = pos + 16 + size
        if end > len(data) or kind > 3 or size > 128 * 1024 * 1024:
            raise _invalid()
        cursor = _Cursor(data[pos + 16:end])
        if kind == 0:
            for channel in range(channels):
                length, actual = cursor.count(32 * 1024 * 1024), cursor.integer()
                if actual != channel:
                    raise _invalid()
                cursor.take(8); payload = cursor.take(length)
                if not prefixes[channel]:
                    prefixes[channel] = payload[:128]
                channel_lengths[channel] += len(payload)
                if audio:
                    chunks[channel].extend(payload)
        elif kind == 1:
            if cine_channels is None:
                cine_channels = _cine_header(cursor)
            frame_size, frame = cursor.count(128 * 1024 * 1024), cursor.integer()
            if frame >= 0:
                if frame < previous_frame:
                    raise _invalid()
                previous_frame = frame
                for state in cine_channels:
                    if not state[0]:
                        run = cursor.integer()
                        state[:] = [run & 0xFFFFFF, bool((run >> 24) & 255)]
                        if not state[0]:
                            raise _invalid()
                        cursor.take(4)
                    elif state[1]:
                        cursor.take(4)
                    state[0] -= 1
                length = cursor.count(4 * 1024 * 1024)
                if length:
                    try:
                        lines = cursor.take(length).decode('utf-8').split('\r')
                    except UnicodeDecodeError:
                        raise _invalid() from None
                    if lines[-1] != '' or len(lines) % 2 != 1:
                        raise _invalid()
                    texts = {}
                    for language, value in zip(lines[::2], lines[1::2]):
                        if language in _LOCALES:
                            locale = _LOCALES[language]
                            text = _clean(value)
                            # Cinematics can author several simultaneous
                            # captions for one language in the same frame.
                            texts[locale] = ' '.join(v for v in (texts.get(locale), text) if v)
                    if any(texts.values()):
                        pages.append({'frame': frame, 'texts': texts})
            if frame_size > size:
                raise _invalid()
        pos = (end + 15) & ~15
        packet_count += 1
        if packet_count > 2_000_000:
            raise _invalid()
    valid_audio = channels > 0
    for prefix, length in zip(prefixes, channel_lengths):
        if len(prefix) < 48 or prefix[:4] != b'FSB4':
            valid_audio = False
            continue
        samples, headers, encoded_size = struct.unpack_from('<III', prefix, 4)
        if samples != 1 or not 80 <= headers <= 65536 or length < 48 + headers + encoded_size:
            valid_audio = False
    return {'channels': channels, 'has_animation': bool(animation), 'has_subtitles': bool(subtitle_flag),
            'pages': pages, 'valid_audio': valid_audio,
            'audio': [bytes(chunk) for chunk in chunks] if audio else [], 'channel_prefixes': prefixes,
            'channel_mix': mix,
            'duration_ms': struct.unpack_from('<I', data, 8)[0] * 1000 // struct.unpack_from('<I', data)[0]}


def read_locals(data):
    cursor = _Cursor(data)
    language, inputs, count = cursor.integer(), cursor.count(100000), cursor.count(2_000_000)
    cursor.take(inputs * 4)
    offsets = [struct.unpack('<Q', cursor.take(8))[0] for _ in range(count)]
    result = {}
    for key, offset in enumerate(offsets):
        if not offset:
            continue
        if offset < cursor.pos or offset >= len(data):
            raise _invalid('Invalid Rise localization string bounds.')
        end = data.find(b'\0', offset, min(len(data), offset + 1_000_000))
        if end < 0:
            raise _invalid()
        try:
            text = _clean(data[offset:end].decode('utf-8'))
        except UnicodeDecodeError:
            raise _invalid() from None
        if text:
            result[key] = text
    return _LOCALES.get(str(language)), result


def _pack(entry):
    match = re.search(r'_([A-Z_]+)\.\d{3}\.tiger$', entry.archive, re.I)
    return match[1].upper() if match else None


def _selected(entries, archives):
    result = {}
    for entry in entries:
        previous = result.get(entry.name_hash)
        if previous is None or archives.priorities[entry.name_hash, entry.locale] > archives.priorities[previous.name_hash, previous.locale]:
            result[entry.name_hash] = entry
    return result


def _subtitle_groups(stream, locales, source_locale):
    """Cut only at shared authored frame boundaries, never translation order.

    Individual languages can paginate the same performance at different times.
    Their shared frame boundaries delimit safe bilingual performance groups;
    unmatched pages remain together until the next boundary shared by every
    available requested language. MUL cinematic frames are authored at 30 Hz.
    """
    frames = {locale: {page['frame'] for page in stream['pages'] if page['texts'].get(locale)}
              for locale in locales}
    available = [values for values in frames.values() if values]
    shared = set.intersection(*available) if available else set()
    duration = stream['duration_ms']
    boundaries = sorted({0, *(frame for frame in shared if 0 < frame * 1000 // 30 < duration)})
    for index, start in enumerate(boundaries):
        end = boundaries[index + 1] if index + 1 < len(boundaries) else None
        pages = {}
        for locale in locales:
            values = []
            for page in stream['pages']:
                if page['frame'] < start or end is not None and page['frame'] >= end:
                    continue
                value = page['texts'].get(locale)
                if value and (not values or values[-1] != value):
                    values.append(value)
            if values:
                pages[locale] = values
        if source_locale in pages:
            yield start, end * 1000 // 30 if end is not None else duration, pages, len(boundaries) > 1


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Rise of the Tomb Raider study/audio locale')
    stamp = fingerprint(install)
    archives = TigerSet(install, 4)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected_locales = {source_locale, *(locale for locale in targets.values() if locale)}
    pack = PACK_NAMES[source_locale]
    # Use exact archive language names, never broad locale bitmasks (English
    # assets can also carry Dutch text flags). Missing recordings stay absent.
    source_entries = _selected((e for e in archives.entries() if _pack(e) == pack), archives)
    fallback_entries = _selected((e for e in archives.entries() if _pack(e) == 'ENGLISH'), archives)
    candidates = {**fallback_entries, **source_entries}
    records, counts = [], Counter()
    progress(f'Reading Rise {source_locale} original dialogue and embedded subtitle pages')
    for number, (identity, entry) in enumerate(sorted(candidates.items(), key=lambda item: (item[1].archive, item[1].offset))):
        if number % 500 == 0:
            progress(f'Checking Rise dialogue streams: {number:,}/{len(candidates):,}')
        if not is_mul(archives.prefix(entry, 64)):
            continue
        stream = read_mul(archives.read(entry))
        counts['streams'] += 1
        if not stream['pages']:
            counts['streams_without_subtitles'] += 1
            continue
        if not any(page['texts'].get(source_locale) for page in stream['pages']):
            counts['streams_without_source_text'] += 1
            continue
        # Cinematics retain every original channel and the authored stereo
        # gains. Selecting a presumed voice stem would discard source content.
        playable = identity in source_entries and stream['valid_audio'] and 1 <= stream['channels'] <= 12
        state = 'voiced' if playable else 'unvoiced' if stream['channels'] == 0 else 'unavailable'
        if stream['channels'] > 1:
            counts['multichannel_streams'] += 1
        audio = {**entry.reference(), 'locale_name': source_locale, 'channel': 0} if playable else None
        if playable and stream['channels'] > 1:
            audio.update(decoder_format='mul', channel_mix=stream['channel_mix'])
        for start_frame, end_ms, pages, timed in _subtitle_groups(stream, selected_locales, source_locale):
            texts = {locale: ' '.join(values) for locale, values in pages.items()}
            reference = dict(audio) if audio else None
            if reference and timed:
                reference.update(start_ms=start_frame * 1000 // 30, end_ms=end_ms)
                reference['caption_locales'] = sorted(selected_locales)
                counts['timed_groups'] += 1
            records.append({'text_id': f'{GAME}:mul:{identity:08x}:frame:{start_frame}', 'english': texts.get('en', ''),
                'chinese': texts.get('zh-Hans', ''), 'source_locale': source_locale,
                'source_text': texts[source_locale], 'texts': texts, 'audio_locale': source_locale,
                'audio': reference, 'voice_status': state,
                'dialogue_kind': 'cinematic' if stream['has_animation'] or stream['channels'] > 1 else 'dialogue',
                'ocr_texts': pages,
                'ocr_english': pages.get('en') or None, 'ocr_chinese': pages.get('zh-Hans') or None})
    # UI/readable localization has no authored voice/silence relationship in
    # this format. Inventory it honestly instead of labelling absent audio mute.
    tables = {}
    for entry in sorted((e for e in archives.entries() if e.name_hash == _LOCALS_HASH),
                        key=lambda e: archives.priorities[e.name_hash, e.locale]):
        locale, table = read_locals(archives.read(entry, max_bytes=16 * 1024 * 1024))
        if locale in selected_locales:
            tables[locale] = table
    for identity, text in tables.get(source_locale, {}).items():
        texts = {locale: table[identity] for locale, table in tables.items() if identity in table}
        records.append({'text_id': f'{GAME}:local:{identity}', 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', ''), 'source_locale': source_locale, 'source_text': text,
            'texts': texts, 'audio_locale': source_locale, 'audio': None,
            'voice_status': 'unknown', 'dialogue_kind': 'unclassified_localization'})
    if not records:
        raise PreparationFailure('rise_language_missing',
            'No selected Rise text was found. Install the official language content through Steam Properties → Language and verify game files.')
    if fingerprint(install) != stamp:
        raise PreparationFailure('rise_files_changed', 'Rise game files changed during preparation. Wait for the launcher update to finish and retry.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    mapped = sum(record['audio'] is not None for record in records)
    missing = [target for target, locale in targets.items() if not any(locale in row['texts'] for row in records)]
    warnings = ['Audio cuts use shared authored subtitle-frame boundaries. Languages with different page timings remain grouped until the next shared boundary; translations are never paired by ordinal position.',
        'Localization-only UI/readables remain unknown; missing recordings never establish silence.',
        'Dialogue includes installed DLC streams, but filenames do not establish individual radio/document/bark categories.']
    if counts['multichannel_streams']:
        warnings.append('Cinematics preserve the complete original performance with its authored stereo channel mix, including music and effects.')
    for movie in _movies(install):
        with movie.open('rb') as handle:
            header = handle.read(44)
        counts['movie_files'] += 1
        if len(header) == 44 and header[:3] in (b'BIK', b'KB2'):
            tracks = struct.unpack_from('<I', header, 40)[0]
            if tracks <= 64:
                counts['movie_audio_tracks'] += tracks
    if counts['movie_files']:
        warnings.append('Bink movies are inventoried separately. Their audio-track language order and subtitle bindings are unverified, so movie tracks are not guessed.')
    base_pack = any(e.archive.casefold() == f'bigfile_{pack}.000.tiger'.casefold() for e in source_entries.values())
    if not base_pack:
        warnings.append('The selected base-game voice pack is absent. Select the language in Steam Properties → Language and let its download finish; installed DLC recordings remain usable.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': records, 'missing_translation_locales': missing,
        'coverage_warnings': warnings, 'narrative_inventory': dict(counts),
        'message': f'{len(records):,} official {source_locale} entries; {mapped:,} original voices' +
                   ('; selected base-game voice pack missing' if not base_pack else '')}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ['en'], progress)


def extract_voice(install: Path, audio: dict, _executable: Path, _destination: Path):
    locale = audio.get('locale_name')
    if locale not in SUPPORTED_LOCALES or audio.get('channel') != 0:
        raise _invalid('Invalid Rise original voice reference.')
    archives = TigerSet(install, 4)
    try:
        entry = TigerEntry(**{key: audio[key] for key in TigerEntry.__dataclass_fields__})
    except (KeyError, TypeError):
        raise _invalid('Invalid Rise original voice reference.') from None
    if _pack(entry) != PACK_NAMES[locale]:
        raise _invalid('Rise voice reference does not match the selected language.')
    data = archives.read(entry)
    stream = read_mul(data, audio=True)
    if not 1 <= stream['channels'] <= 12 or not stream['valid_audio']:
        raise _invalid('Original Rise voice channel is unavailable or changed.')
    if 'start_ms' in audio or 'end_ms' in audio:
        locales = audio.get('caption_locales')
        if (not isinstance(locales, list) or not 1 <= len(locales) <= len(TEXT_LOCALES)
                or any(not isinstance(value, str) or value not in TEXT_LOCALES for value in locales)
                or len(set(locales)) != len(locales) or locale not in locales):
            raise _invalid('Invalid Rise subtitle timing languages.')
        boundaries = {(start * 1000 // 30, end) for start, end, _pages, timed in _subtitle_groups(stream, locales, locale) if timed}
        if (audio.get('start_ms'), audio.get('end_ms')) not in boundaries:
            raise _invalid('Original Rise subtitle timing is unavailable or changed.')
    if stream['channels'] > 1:
        if audio.get('decoder_format') != 'mul' or audio.get('channel_mix') != stream['channel_mix']:
            raise _invalid('Original Rise cinematic channel mix is unavailable or changed.')
        return data
    if audio.get('decoder_format') or audio.get('channel_mix'):
        raise _invalid('Invalid Rise mono voice reference.')
    return stream['audio'][0]


def decode_voice_source(data: bytes, audio: dict, wav_path: Path, decoder_path: Path, scratch: Path):
    """Decode original channels; larger MULs exceed vgmstream's eight-track cap.

    Original FSB streams are decoded independently and interleaved without
    padding, resampling or stem selection. The caller applies the validated
    authored stereo gains and subtitle timing to this PCM source.
    """
    deadline = time.monotonic() + 90
    options = {'check': True, 'capture_output': True,
               'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}

    def decode(source, destination):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _invalid('Original Rise audio decoding exceeded its time bound.')
        try:
            subprocess.run([str(decoder_path), '-i', '-o', str(destination), str(source)],
                           timeout=remaining, **options)
        except (subprocess.SubprocessError, OSError):
            raise _invalid('Original Rise audio decoding failed or exceeded its time bound.') from None

    multiplexed = audio.get('decoder_format') == 'mul'
    stream = read_mul(data, audio=True) if multiplexed else None
    if not multiplexed or stream['channels'] <= 8:
        source = scratch / ('rise-original.mul' if multiplexed else 'rise-original.fsb')
        source.write_bytes(data)
        decode(source, wav_path)
        return
    channels = stream['channels']
    if not stream['valid_audio'] or not 9 <= channels <= 12 or audio.get('channel_mix') != stream['channel_mix']:
        raise _invalid('Unsupported Rise multichannel source.')
    declared_rate, _, declared_samples = struct.unpack_from('<III', data)
    # Bound disk use before decoding too: FSB sample headers record frame count
    # and rate. Each mono decode writes PCM16 in the pinned vgmstream CLI.
    expected = []
    for payload in stream['audio']:
        if len(payload) < 128:
            raise _invalid()
        sample_count = struct.unpack_from('<I', payload, 80)[0]
        sample_rate = struct.unpack_from('<I', payload, 100)[0]
        mono_channels = struct.unpack_from('<H', payload, 110)[0]
        if mono_channels != 1 or sample_rate != declared_rate or not 0 < declared_samples <= sample_count:
            raise _invalid('Rise original channels do not share the declared sample format.')
        expected.append((sample_count, sample_rate))
    if len(set(expected)) != 1 or expected[0][0] * channels * 2 > 256 * 1024 * 1024:
        raise _invalid('Rise original channels differ in duration or exceed the PCM size bound.')
    paths, signature = [], None
    for index, payload in enumerate(stream['audio']):
        source, destination = scratch / f'rise-channel-{index}.fsb', scratch / f'rise-channel-{index}.wav'
        source.write_bytes(payload)
        decode(source, destination)
        if destination.stat().st_size > expected[0][0] * 2 + 65536:
            raise _invalid('Rise decoded audio exceeds its PCM size bound.')
        try:
            with wave.open(str(destination), 'rb') as handle:
                current = (handle.getnchannels(), handle.getsampwidth(), handle.getframerate(),
                           handle.getnframes(), handle.getcomptype())
        except (wave.Error, EOFError):
            raise _invalid('Rise decoder did not produce supported PCM audio.') from None
        if current != (1, 2, declared_rate, expected[0][0], 'NONE') or signature is not None and current != signature:
            raise _invalid('Rise decoded channels differ in rate, width or duration.')
        signature = current
        paths.append(destination)
    from contextlib import ExitStack
    with ExitStack() as stack:
        inputs = [stack.enter_context(wave.open(str(path), 'rb')) for path in paths]
        output = stack.enter_context(wave.open(str(wav_path), 'wb'))
        output.setparams((channels, 2, declared_rate, declared_samples, 'NONE', 'not compressed'))
        remaining = declared_samples
        while remaining:
            if time.monotonic() >= deadline:
                raise _invalid('Original Rise audio decoding exceeded its time bound.')
            count = min(4096, remaining)
            interleaved = bytearray(count * channels * 2)
            for channel, handle in enumerate(inputs):
                block = handle.readframes(count)
                if len(block) != count * 2:
                    raise _invalid('Rise decoded channel ended before its authored duration.')
                interleaved[2 * channel::2 * channels] = block[::2]
                interleaved[2 * channel + 1::2 * channels] = block[1::2]
            output.writeframesraw(interleaved)
            remaining -= count
