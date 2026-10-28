"""Portal 2: layered official subtitles, choreography, movies and credits."""
from collections import Counter
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import struct
import subprocess
import wave
import zlib

from .preparation_errors import PreparationFailure
from .portal_assets import TEXT_LOCALES
from .source_dialogue import (SourceFiles, caption_pages, clean_caption, decode_performance,
    mapping, pack_performance, reference_signature, resolve_sequence, sound_events,
    steam_language, text_table)
from .source_formats import compiled_captions, invalid, keyvalues
from .source_scene import binary_scene, caption_sequences

GAME = 'portal2'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'de', 'es-ES', 'ru')
MOUNTS = ('update', 'portal2_dlc2', 'portal2_dlc1', 'portal2')
MOVIES = ('coop_outro', 'sp_ending_callback', 'dlc1_endmovie')


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(p) for p in candidates if (Path(p) / 'portal2.exe').is_file()
                 and (Path(p) / 'portal2/gameinfo.txt').is_file()
                 and (Path(p) / 'portal2/pak01_dir.vpk').is_file()), None)


def archive_sources(install):
    install, result = Path(install), set()
    directories = list(MOUNTS) + [f'{mount}_{TEXT_LOCALES[locale]}'
        for mount in MOUNTS for locale in SUPPORTED_LOCALES]
    for directory in directories:
        root = install / directory
        for pattern in ('pak01*.vpk', 'gameinfo.txt', 'resource/subtitles_*.*',
                        'resource/closecaption_*.*', 'resource/portal2_*.txt',
                        'scripts/*.txt', 'scenes/*.image', 'media/*captions.txt',
                        'media/*.bik', 'sound/**/*.wav', 'sound/**/*.mp3'):
            result.update(p for p in root.glob(pattern) if p.is_file())
    manifest = install.parent.parent / 'appmanifest_620.acf'
    if manifest.is_file():
        result.add(manifest)
    return sorted(result)


def fingerprint(install):
    root = Path(install)
    return hashlib.sha256('|'.join(f'{p.relative_to(root) if p.is_relative_to(root) else p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in archive_sources(root)).encode()).hexdigest()


class PortalFiles(SourceFiles):
    """Preserve mount priority across both VPK and official loose resources."""
    def __init__(self, install, directories):
        super().__init__(install, [d + '/pak01_dir.vpk' for d in directories], directories)
        self.layers = [SourceFiles(install, [d + '/pak01_dir.vpk'], [d]) for d in directories]

    def locate(self, member):
        return next((ref for layer in self.layers if (ref := layer.locate(member))), None)


def _files(install):
    return PortalFiles(install, _mounts(install))


def _mounts(install):
    """Read the highest official DLC's SearchPaths without following mod paths."""
    install = Path(install)
    selected = next((name for name in MOUNTS[1:] if (install / name / 'gameinfo.txt').is_file()), None)
    if selected is None:
        raise invalid('Portal 2 gameinfo.txt is missing.')
    path = install / selected / 'gameinfo.txt'
    if not path.resolve().is_relative_to(install.resolve()) or path.stat().st_size > 1024 * 1024:
        raise invalid('Portal 2 gameinfo.txt exceeds its bounds.')
    info = mapping(mapping(keyvalues(path.read_bytes())).get('gameinfo', []))
    filesystem = mapping(info.get('filesystem', []))
    if filesystem.get('steamappid') != '620':
        raise invalid('Portal 2 gameinfo.txt has an unexpected application identity.')
    result = ['update']
    for kind, value in filesystem.get('searchpaths', []):
        if not isinstance(value, str) or kind.casefold() != 'game':
            continue
        value = value.replace('\\', '/').casefold()
        candidate = selected if value in {'|gameinfo_path|.', '|gameinfo_path|'} else value.rstrip('/')
        if candidate in MOUNTS[1:] and candidate not in result:
            result.append(candidate)
    if selected not in result or 'portal2' not in result:
        raise invalid('Unsupported Portal 2 official mount paths.')
    return result


def _voices(install, locale):
    native = TEXT_LOCALES[locale]
    # Localized mounts are independently identified. The common VPK/media
    # resources are English and cannot satisfy an absent dubbed pack.
    mounts = _mounts(install)
    directories = [f'{mount}_{native}' for mount in mounts]
    if locale == 'en' and steam_language(install, 620) == 'english':
        directories += mounts
    return PortalFiles(install, directories)


def _scene_image(data):
    """VSIF 3 adds a last-speech millisecond field to each scene summary."""
    if not 20 <= len(data) <= 256 * 1024 * 1024:
        raise invalid('Invalid Portal 2 scene image size.')
    magic, version, count, string_count, entries = struct.unpack_from('<4s4I', data)
    if (magic != b'VSIF' or version != 3 or count > 100000 or string_count > 32768
            or 20 + string_count * 4 > entries or entries + count * 16 > len(data)):
        raise invalid('Unsupported Portal 2 scene image layout.')
    strings = []
    for number in range(string_count):
        offset = struct.unpack_from('<I', data, 20 + 4 * number)[0]
        end = data.find(b'\0', offset, min(offset + 4096, entries))
        if offset < 20 + string_count * 4 or end < 0:
            raise invalid('Portal 2 scene string exceeds its pool.')
        try:
            strings.append(data[offset:end].decode('utf-8'))
        except UnicodeError:
            raise invalid('Invalid Portal 2 scene string encoding.') from None
    result = {}
    for number in range(count):
        identity, offset, size, summary = struct.unpack_from('<4I', data, entries + number * 16)
        if (identity in result or offset < entries + count * 16 or size < 10
                or offset + size > len(data) or summary < entries + count * 16 or summary + 12 > len(data)):
            raise invalid('Portal 2 scene entry exceeds its image.')
        _duration, _speech, sounds = struct.unpack_from('<III', data, summary)
        if sounds > 100000 or summary + 12 + sounds * 4 > len(data):
            raise invalid('Portal 2 scene summary exceeds its image.')
        result[identity] = binary_scene(data[offset:offset + size], strings)
    return result


def _localized_bytes(data, native):
    # The shipped Latin-American text sources have a byte-level CR insertion
    # before every LF in otherwise UTF-16LE data. Compiled captions are intact.
    # Undo only this evidenced, reversible signature; all other encoding
    # failures retain the normal unsupported-format error.
    if (native == 'latam' and data.startswith(b'\xff\xfe') and b'\r\0\r\n\0' in data
            and all(index and data[index - 1] == 13 for index, value in enumerate(data) if value == 10)):
        repaired = data.replace(b'\r\n', b'\n')
        try:
            repaired.decode('utf-16')
        except UnicodeError:
            pass
        else:
            return repaired
    return data


def _caption_table(files, native, stem):
    """Named source rows identify hashes; compiled rows own the displayed text.

    The official base closecaptions and DLC1 subtitles contain duplicate named
    rows. Their obsolete source wording must not override the compiled caption.
    """
    path = f'resource/{stem}_{native}'
    if not files.locate(path + '.txt') or not files.locate(path + '.dat'):
        return {}
    root = mapping(mapping(keyvalues(_localized_bytes(files.read(path + '.txt'), native))).get('lang', []))
    if str(root.get('language', '')).casefold() not in ({native, 'korean'} if native == 'koreana' else {native}):
        raise invalid('Portal 2 caption language does not match its filename.')
    compiled = compiled_captions(files.read(path + '.dat'))
    result, hashes = {}, {}
    for token, value in root.get('tokens', []):
        token = token.casefold()
        if token.startswith('[english]'):
            continue
        if not isinstance(value, str):
            raise invalid('Invalid Portal 2 caption token.')
        identity = zlib.crc32(token.encode('utf-8'))
        if identity in hashes and hashes[identity] != token:
            raise invalid('Ambiguous Portal 2 caption hash.')
        hashes[identity] = token
        if identity in compiled:
            result[token] = compiled[identity]
    return result


def _tables(files, locale):
    native, table, ui = TEXT_LOCALES[locale], {}, {}
    # Caption/UI resources are additive between DLCs, unlike sound-manifest
    # and scene-image replacements. Newer DLC tokens override older tokens.
    for layer in reversed(files.layers):
        for stem in ('closecaption', 'subtitles'):
            table.update(_caption_table(layer, native, stem))
        path = f'resource/portal2_{native}.txt'
        if layer.locate(path):
            ui.update(text_table(_localized_bytes(layer.read(path), native), native))
    return table, ui


def _binding(token, sequence, voices, locale, *, clip=None, origin='caption'):
    if not sequence or len(sequence) > 64 or token == 'music.sp_a5_credits' and locale != 'en':
        return None
    parts = []
    for member, at_ms in sequence:
        ref = voices.locate(member)
        if ref is None:
            return None
        if 'archive' in ref:
            archive = next(a for a in voices.archives if a.path == voices.install / ref['archive'])
            entry = archive.entries[member]
            if entry.length and entry.archive != 0x7FFF:
                chunk = archive.path.with_name(archive.path.name[:-8] + f'_{entry.archive:03d}.vpk')
                if not chunk.is_file() or chunk.stat().st_size < entry.offset + entry.length:
                    return None
        parts.append({'member': member, 'at_ms': at_ms, **ref})
    result = {'token': token, 'locale': locale, 'parts': parts, 'origin': origin}
    if clip:
        result['clip_ms'] = list(clip)
    if token == 'music.sp_a5_credits':
        result['playback_scope'] = 'full_track'
    result['binding_hash'] = reference_signature(result)
    return result


@lru_cache(maxsize=8)
def _probe(install, locale, _stamp):
    voices = _voices(install, locale)
    member = next((n for n in voices.entries if n.startswith('sound/vo/') and n.endswith('.wav')), None)
    if member is None:
        for directory in voices.directories:
            sample = next((voices.install / directory / 'sound/vo').glob('**/*.wav'), None)
            if sample is not None:
                member = sample.relative_to(voices.install / directory).as_posix()
                break
    return ('present' if _binding('probe', ((member, 0),), voices, locale) else 'incomplete') if member else 'missing'


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        return _probe(str(install), locale, fingerprint(install))
    except (OSError, ValueError):
        return 'incomplete'


def _movies(files):
    result = []
    for movie in MOVIES:
        path = f'media/{movie}_captions.txt'
        if not files.locate(path):
            continue
        lines = [line.strip() for line in files.read(path).decode('utf-8-sig').splitlines() if line.strip()]
        if len(lines) % 4:
            raise invalid('Invalid Portal 2 movie caption timeline.')
        for index in range(0, len(lines), 4):
            token, color, start, end = lines[index:index + 4]
            try:
                start, end = float(start), float(end)
            except ValueError:
                raise invalid('Invalid Portal 2 movie caption timing.') from None
            if (not token.startswith('#cheaptitles_') or not re.fullmatch('0x[0-9A-Fa-f]{8}', color)
                    or not all(math.isfinite(n) for n in (start, end)) or not 0 <= start < end <= 1800):
                raise invalid('Unsupported Portal 2 movie caption timing.')
            result.append((f'{movie}:{index // 4}', token[1:].casefold(), movie, round(start * 1000), round(end * 1000)))
    return result


def _movie_audio(identity, token, movie, start, end, voices, locale, events, sequences):
    # An explicit event identifies the dry recording even when repeated in a
    # movie. Otherwise the caption timeline licenses only its own movie clip.
    event = token.removeprefix('cheaptitles_')
    direct = _binding(event, resolve_sequence(event, events, sequences), voices, locale)
    return direct or _binding(identity, ((f'media/{movie}.bik', 0),), voices, locale,
                              clip=(start, end), origin='movie')


def _movie_layout(path):
    """Verify the installed Bink1 topology before mixing its original tracks.

    Four tracks (stereo, mono, mono, stereo), IDs 0..3, are the native Portal 2
    surround container. Preserve all tracks; track zero alone can omit speech.
    The Bink header layout is independently documented by FFmpeg's demuxer.
    """
    with Path(path).open('rb') as stream:
        header = stream.read(92)
    if (len(header) != 92 or header[:4] != b'BIKi'
            or struct.unpack_from('<I', header, 4)[0] + 8 != Path(path).stat().st_size
            or struct.unpack_from('<I', header, 40)[0] != 4):
        raise invalid('Unsupported Portal 2 movie audio layout.')
    channels, rates = [], []
    for index in range(4):
        rate, flags = struct.unpack_from('<HH', header, 60 + 4 * index)
        rates.append(rate)
        channels.append(2 if flags & 0x2000 else 1)
    if channels != [2, 1, 1, 2] or rates != [44100] * 4 or struct.unpack_from('<4I', header, 76) != (0, 1, 2, 3):
        raise invalid('Portal 2 movie audio tracks changed; refresh game data.')
    return 4


def _credits(files):
    if not files.locate('scripts/credits.txt'):
        return [], []
    groups = mapping(mapping(keyvalues(files.read('scripts/credits.txt'))).get('credits.txt', []))
    entries = groups.get('outrosonglyrics', [])
    clock, lyrics, report, pending, start = 0.0, [], [], [], 0.0
    def flush(end):
        nonlocal pending
        text = clean_caption(' '.join(pending))
        if text and end > start:
            lyrics.append((text, round(start * 1000), round(end * 1000)))
        pending = []
    for index, (value, _font) in enumerate(entries):
        match = re.fullmatch(r'\[(\d+(?:\.\d+)?)\](.*)', value, re.S)
        if not match:
            raise invalid('Unsupported Portal 2 credits display timeline.')
        duration, text = float(match[1]), match[2].lstrip('*').strip()
        if not math.isfinite(duration) or duration > 120 or clock + duration > 1800:
            raise invalid('Portal 2 credits duration exceeds its bounds.')
        if index < 2:
            if text:
                report.append(text)
        elif not text or text in {'&', '^'}:
            flush(clock)
        else:
            if not pending:
                start = clock
            pending.append(text)
        clock += duration
    flush(clock)
    return lyrics, report


def _row(identity, texts, locale, audio, kind, status=None, pages=None):
    return {'text_id': f'{GAME}:{identity}', 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', ''), 'source_locale': locale,
            'source_text': texts[locale], 'texts': texts, 'audio_locale': locale,
            'audio': audio, 'voice_status': status or ('voiced' if audio else 'unavailable'),
            'dialogue_kind': kind, 'ocr_texts': pages or {key: [value] for key, value in texts.items()}}


def _context(install, locale):
    files, voices = _files(install), _voices(install, locale)
    events, missing = sound_events(files)
    scenes = _scene_image(files.read('scenes/scenes.image')) if files.locate('scenes/scenes.image') else {}
    return files, voices, events, caption_sequences(scenes), len(scenes), missing


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Portal 2 spoken language')
    install, stamp = Path(install), fingerprint(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    files, voices, events, sequences, scene_count, missing = _context(install, source_locale)
    tables, ui = {}, {}
    for locale in sorted(selected):
        tables[locale], ui[locale] = _tables(files, locale)
    if not tables[source_locale]:
        raise PreparationFailure('missing_voice_pack', 'Portal 2 text resources are missing. Select the official language in Steam Properties → Language, finish the download and verify game files.')
    progress(f'Reading Portal 2 {source_locale} base/DLC dialogue and movie captions')
    records, diagnostics, matched = [], Counter(), set()
    diagnostics.update({'sound_events': len(events), 'scenes': scene_count, 'missing_sound_scripts': len(missing), 'caption_tokens': len(tables[source_locale])})
    for token, raw in tables[source_locale].items():
        if '<sfx>' in raw.casefold() or re.fullmatch(r'(?:\[[^\]]+\]|\*[^*]+\*)', clean_caption(raw)):
            diagnostics['excluded_sound_effect_captions'] += 1
            continue
        texts = {locale: clean_caption(table[token]) for locale, table in tables.items() if token in table and clean_caption(table[token])}
        if source_locale not in texts:
            continue
        title = token.startswith('commentary_title_')
        sequence = () if title else resolve_sequence(token, events, sequences)
        audio = _binding(token, sequence, voices, source_locale)
        matched.update(member for member, _time in sequence)
        kind = 'readable' if title else 'commentary' if token.startswith('#commentary') else 'ambient' if token.startswith(('turret.', 'npc_floorturret.')) else 'subtitle'
        records.append(_row('caption:' + token, texts, source_locale, audio, kind, 'unvoiced' if title else None,
                            {locale: caption_pages(table[token]) for locale, table in tables.items() if token in table}))
        if not sequence and not title:
            diagnostics['unresolved_caption_bindings'] += 1
        elif len(sequence) > 1:
            diagnostics['timed_composite_captions'] += 1
    for identity, token, movie, start, end in _movies(files):
        texts = {locale: clean_caption(table.get(token) or tables[locale].get(token.removeprefix('cheaptitles_'), ''))
                 for locale, table in ui.items()}
        texts = {locale: text for locale, text in texts.items() if text}
        if source_locale not in texts:
            diagnostics['missing_movie_caption_texts'] += 1
            continue
        audio = _movie_audio(identity, token, movie, start, end, voices, source_locale, events, sequences)
        records.append(_row('movie:' + identity, texts, source_locale, audio, 'cinematic'))
        diagnostics['movie_caption_segments'] += 1
    lyrics, report = _credits(files)
    if source_locale == 'en':
        sequence = resolve_sequence('music.sp_a5_credits', events, sequences)
        audio = _binding('music.sp_a5_credits', sequence, voices, source_locale)
        for number, (text, _start, _end) in enumerate(lyrics):
            records.append(_row(f'credits:lyric:{number}', {'en': text}, source_locale, audio, 'song_full_track'))
        for number, text in enumerate(report):
            records.append(_row(f'credits:report:{number}', {'en': text}, source_locale, None, 'readable', 'unvoiced'))
    diagnostics['credits_lyric_segments'], diagnostics['credits_report_headings'] = len(lyrics), len(report)
    diagnostics['voices_without_resolved_caption'] = sum(n.startswith(('sound/vo/', 'sound/commentary/')) and n.endswith(('.wav', '.mp3')) and n not in matched for n in voices.entries)
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'Portal 2 files changed during preparation. Finish the Steam update and retry.', game_files_changed=True)
    counts = Counter(row['voice_status'] for row in records)
    warnings = [
        'Official base game, Peer Review and Perpetual Testing Initiative resources are merged in mount order. Custom mounts, Workshop dialogue and mods are not read.',
        'Randomized or unresolved sound bindings remain unavailable; missing recordings and sound-effect captions are never labeled silent dialogue.',
        'Prerecorded ending captions use their own authored start/end times. Movie clips include the original mix, not an isolated speech stem.',
        'Credit lyrics are separate literal English display groups with complete original-song playback. Display timings do not establish exact sung-line cuts. Commentary titles and two credits report headings are confirmed text-only readables.',
        'Use full-frame capture or independent calibration for commentary, credit terminal and each split-screen viewport; bottom-only subtitle capture is incomplete.',
        'Texture-only signs, graffiti, the external Lab Rat comic, unsubtitled radio/turret music, and movies without authored caption timelines have no native text binding.']
    if probe_voice_pack(install, source_locale) != 'present':
        warnings.insert(0, f'Install the official Portal 2 {source_locale} voice pack in Steam Properties → Language, finish downloading and verify files. No shared English audio is substituted.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install), 'fingerprint': stamp,
            'reader_revision': LANGUAGE_INDEX_VERSION, 'records': records, 'diagnostics': dict(diagnostics), 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if not tables.get(locale)],
            'message': f"{counts['voiced']:,} original {source_locale} entries; {counts['unvoiced']:,} text-only readables; {counts['unavailable']:,} unavailable voices"}


def index_install(install, data_dir, progress=lambda _: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, destination):
    locale, token, origin = audio.get('locale'), audio.get('token'), audio.get('origin')
    if locale not in SUPPORTED_LOCALES or not isinstance(token, str):
        raise invalid('Invalid Portal 2 original voice reference.')
    files, voices, events, sequences, _count, _missing = _context(install, locale)
    expected = None
    if origin == 'caption':
        expected = _binding(token, resolve_sequence(token, events, sequences), voices, locale)
    elif origin == 'movie':
        for identity, caption, movie, start, end in _movies(files):
            if identity == token:
                expected = _movie_audio(identity, caption, movie, start, end, voices, locale, events, sequences)
    if expected is None or expected != audio:
        raise invalid('Portal 2 original voice binding changed; refresh game data.')
    if 'clip_ms' not in expected:
        return pack_performance([voices.read_ref(part) for part in expected['parts']])
    from .media_tools import ffmpeg_executable
    executable = ffmpeg_executable()
    if executable is None:
        raise invalid('The installed media decoder is unavailable.')
    part, scratch = expected['parts'][0], Path(destination)
    if 'file' in part:
        source = voices.install / part['file']
    else:
        source = scratch / ('portal2-original' + Path(part['member']).suffix)
        source.write_bytes(voices.read_ref(part))
    output = scratch / 'portal2-segment.wav'
    start, end = expected['clip_ms']
    output_args = ['-map', '0:a:0']
    if origin == 'movie':
        tracks = _movie_layout(source)
        # amix promotes mono tracks to stereo and retains all authored audio.
        # Normalization prevents clipping from the combined original mix.
        output_args = ['-filter_complex', ''.join(f'[0:a:{i}]' for i in range(tracks)) +
                       f'amix=inputs={tracks}:normalize=1[out]', '-map', '[out]']
    subprocess.run([str(executable), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-ss', str(start / 1000), '-i', str(source), '-t', str((end - start) / 1000),
                    *output_args, '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', str(output)],
                   check=True, capture_output=True, timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    with wave.open(str(output)) as stream:
        if abs(stream.getnframes() / stream.getframerate() * 1000 - (end - start)) > 100:
            raise invalid('Portal 2 movie or credits segment exceeds its recording.')
    return pack_performance([output.read_bytes()])


decode_voice_source = decode_performance
