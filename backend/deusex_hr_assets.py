"""Authored PC dialogue from Deus Ex: Human Revolution Director's Cut."""
from collections import Counter, defaultdict
from array import array
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import wave

from . import deusex_hr_formats as fmt
from . import deusex_hr_cinematics as movies
from .preparation_errors import PreparationFailure

GAME = 'deusexhrdc'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'fr', 'it', 'de', 'es-ES')
TEXT_LOCALES = {'en': 0, 'fr': 1, 'it': 2, 'de': 3, 'es-ES': 4}
_LOCALS = fmt.filename_hash('pc-w\\local\\locals.bin')
_CUE = re.compile(r'//\((\d+(?:\.\d+)?)\)\\')


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(path) for path in candidates if (Path(path) / 'DXHRDC.exe').is_file()
                 and (Path(path) / 'BIGFILE.000').is_file()), None)


def archive_sources(install):
    return sorted(path for path in Path(install).glob('BIGFILE.*')
                  if path.is_file() and re.fullmatch(r'BIGFILE\.\d{3}', path.name))


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        for path in archive_sources(install)).encode()).hexdigest()


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        archive = fmt.Archive(install)
        if archive.select(_LOCALS, locale) is None:
            return 'missing'
        localized = [entry for entry in archive.entries if entry.locale != 0xffffffff
                     and entry.locale & fmt.LOCALE_BITS[locale] and entry.identity != _LOCALS]
        if not localized:
            return 'missing'
        # Directory evidence only: do not scan/decode thousands of voices here.
        for entry in localized:
            part = entry.offset * 2048 // archive.alignment
            if not (Path(install) / ('BIGFILE.%03d' % part)).is_file():
                return 'incomplete'
        return 'present'
    except (OSError, ValueError, struct.error):
        return 'incomplete'


def _invalid(error):
    return PreparationFailure('unsupported_game_format',
        "Deus Ex: Human Revolution Director's Cut resources no longer match this reader. "
        'Finish the Steam download, verify game files and update the toolkit before preparing again.')


def clean_text(text):
    # Localized color/style markup is not prose. Preserve authored punctuation.
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', text)).strip()


def captions(text):
    """Each authored page retains its own identity and text, including fallbacks."""
    matches = list(_CUE.finditer(text))
    starts = [0, *(match.end() for match in matches)]
    ends = [*(match.start() for match in matches), len(text)]
    return [(index, clean_text(text[start:end]), 0 if index == 0 else round(float(matches[index-1][1]) * 1000))
            for index, (start, end) in enumerate(zip(starts, ends))]


def _sound_inventory(archive, progress):
    candidates, seen, sounds, cinematics, choices, counts = [], set(), {}, {}, set(), Counter()
    entries = sorted((entry for entry in archive.entries if entry.locale == 0xffffffff), key=lambda entry: entry.offset)
    for index, entry in enumerate(entries):
        if index % 1000 == 0:
            progress(f'Reading Deus Ex resource directory {index+1:,}/{len(entries):,}')
        headers = fmt.section_directory(archive, entry)
        identities = {(kind, subtype, identity) for identity, kind, subtype, _locale in headers if kind == 7 and subtype in {0, 13, 42}}
        counts['drm_archives'] += bool(headers)
        if identities:
            candidates.append((entry, identities))
    # Resource IDs are reused by dependent scene bundles. Read the smallest
    # available owner first instead of repeatedly unpacking model textures.
    for index, (entry, identities) in enumerate(sorted(candidates, key=lambda item: item[0].size)):
        if identities <= seen:
            continue
        if index % 50 == 0:
            progress(f'Reading Deus Ex original sound definitions ({len(sounds):,} voice bindings)')
        counts['sound_archives_read'] += 1
        for section in fmt.selected_sections(archive, entry, identities-seen):
            key = section.kind, section.subtype, section.identity
            if key in seen:
                continue
            seen.add(key)
            if section.subtype == 13:
                binding = fmt.stream_binding(section)
                if binding:
                    sounds[section.identity] = (entry.identity, *binding)
                else:
                    counts['other_sound_graphs'] += 1
            elif section.subtype == 42:
                choices.update(fmt.choice_text_ids(section))
                counts['conversation_graphs'] += 1
            elif (binding := movies.movie_binding(section)):
                cinematics[section.identity] = (entry.identity, binding)
    counts['sound_definitions'] = sum(key[1] == 13 for key in seen)
    counts['voice_stream_bindings'] = len(sounds)
    counts['cinematic_definitions'] = len(cinematics)
    counts['choice_text_fields'] = len(choices)
    return sounds, cinematics, choices, counts


def _readables(archive):
    result = {}
    for name, kind, offsets in [('email_database', 'email', (0, 2, 4, 6)),
                                ('ireader_database', 'readable', (2, 8)),
                                ('objective_database', 'mission_log', (0, 2))]:
        entry = archive.select(fmt.filename_hash('pc-w\\' + name + '.drm'), 'en')
        if entry is None:
            continue
        data = fmt.decompress(archive.read(entry))
        sections = fmt.sections(data)
        root = struct.unpack_from('<I', data, 28)[0]
        if root >= len(sections):
            raise ValueError('Missing Deus Ex narrative database root')
        database = sections[root]
        if database.kind != 0 or len(database.data) < 4:
            raise ValueError('Unsupported Deus Ex narrative database')
        count = struct.unpack_from('<I', database.data)[0]
        if count * 4 + 4 != len(database.data):
            raise ValueError('Invalid Deus Ex narrative database count')
        by_id = {section.identity: section for section in sections if section.kind == 7}
        for (identity,) in struct.iter_unpack('<I', database.data[4:]):
            section = by_id.get(identity)
            if section is None or section.subtype != 0 or len(section.data) < max(offsets) + 2:
                raise ValueError('Missing Deus Ex narrative database record')
            # These database fields are text IDs (sender/recipient/subject/body,
            # iReader title/body and mission title/description), never VO slots.
            if name == 'ireader_database' and len(section.data) != 32:
                raise ValueError('Unsupported Deus Ex iReader record')
            for offset in offsets:
                text_id = struct.unpack_from('<H', section.data, offset)[0]
                if text_id:
                    result[text_id] = kind
    return result


def _kind(path):
    if '_rad_' in path:
        return 'infolink_radio'
    if '\\public_address\\' in path:
        return 'public_address'
    if '_3tr_' in path or '\\occupations\\' in path or '\\overheard\\' in path:
        return 'ambient_dialogue'
    if '\\commentary\\' in path:
        return 'developer_commentary'
    return 'dialogue'


def _movie_track(tracks, name):
    if name in tracks:
        return name, tracks[name]
    # The shipped PC menu tutorial retains _pc in its DTP WAV reference while
    # its CRI directory uses the same exact source basename without _pc.
    if name and re.fullmatch(r'dx3_menustutorial_vo_(?:eng|fra|ger|ita|spa)_pc\.wav', name):
        canonical = name[:-7] + '.wav'
        if canonical in tracks:
            return canonical, tracks[canonical]
    return name, None


def _cinematic_records(archive, cinematics, tables, source_locale, counts):
    records, caption_ids, validated_duplicates = [], set(), set()
    for identity, (owner, binding) in cinematics.items():
        entry = archive.select(binding['media'], source_locale)
        tracks = movies.movie_tracks(archive, entry) if entry else {}
        variants = dict(binding['variants'])
        if binding['making_of'] and binding['unbound_cues']:
            # Publisher marks the original making-of as an English extra;
            # the shipped multiplex has exactly one named original AVI track.
            name = 'makingof2.avi'
            if set(tracks) == {name}:
                variants['making_of'] = {'voices': {'en': name}, 'cues': binding['unbound_cues']}
            else:
                counts['unresolved_movie_cues'] += len(binding['unbound_cues'])
        else:
            counts['unresolved_movie_cues'] += len(binding['unbound_cues'])
        for variant, group in variants.items():
            caption_ids.update(cue[2] for cue in group['cues'])
            counts['cinematic_cues'] += len(group['cues'])
            name, track = _movie_track(tracks, group['voices'].get(source_locale))
            if track and track.get('duplicate_tracks'):
                duplicate_key = binding['media'], name
                if duplicate_key not in validated_duplicates:
                    original = movies.demux_adx(archive, entry, track['track'])
                    if any(movies.demux_adx(archive, entry, channel) != original for channel in track['duplicate_tracks']):
                        raise ValueError('Conflicting CRI original voice tracks')
                    validated_duplicates.add(duplicate_key)
            duration = round(track['samples'] / track['rate'] * 1000) if track else None
            variant_id = hashlib.sha256(variant.encode()).hexdigest()[:16]
            for cue_index, (cue_start, cue_end, text_id) in enumerate(group['cues']):
                if text_id not in tables[source_locale]:
                    counts['movie_cues_without_selected_text'] += 1
                    continue
                pages = captions(tables[source_locale][text_id])
                translations = {locale: captions(table[text_id]) for locale, table in tables.items() if text_id in table}
                # The movie timeline is authoritative. An endpoint extending
                # beyond the recording can only play through its actual EOF.
                end = min(cue_end, duration) if duration else cue_end
                timed = cue_start < end and all(a[2] < b[2] for a, b in zip(pages, pages[1:])) and all(cue_start + page[2] < end for page in pages if page[1])
                for page, text, relative_start in pages:
                    if not text:
                        continue
                    texts = {locale: values[page][1] for locale, values in translations.items()
                             if len(values) == len(pages) and values[page][1]}
                    audio = None
                    if track:
                        audio = {'locale': source_locale, 'owner': owner, 'movie': identity,
                                 'media': binding['media'], 'variant': variant_id, 'cue': cue_index,
                                 'caption': text_id, 'track': track['track'], 'decoder_format': 'adx',
                                 **{key: track[key] for key in ('rate', 'samples', 'channels')}}
                        if timed:
                            audio.update(start_ms=cue_start + relative_start,
                                end_ms=min(cue_start + pages[page+1][2], end) if page+1 < len(pages) else end)
                        else:
                            audio['playback_scope'] = 'full_track'
                    kind = 'making_of' if binding['making_of'] else 'cinematic'
                    if audio and not timed:
                        kind += '_full_track'
                    records.append({'text_id': f'{GAME}:movie:{identity}:{variant_id}:{cue_index}:{page}',
                        'english': texts.get('en', ''), 'chinese': '', 'source_locale': source_locale,
                        'source_text': text, 'texts': texts, 'audio_locale': source_locale, 'audio': audio,
                        'voice_status': 'voiced' if audio else 'unavailable', 'dialogue_kind': kind})
    return records, caption_ids


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported original Deus Ex Director\'s Cut spoken language')
    try:
        return _index_language(Path(install), source_locale, target_locales, progress)
    except PreparationFailure:
        raise
    except (ValueError, struct.error, UnicodeError) as error:
        raise _invalid(error) from error


def _index_language(install, source_locale, target_locales, progress):
    from .languages import resolve_locale
    if not discover_install([install]):
        raise PreparationFailure('deusexhrdc_missing_install', 'Choose the Deus Ex Director\'s Cut folder containing DXHRDC.exe and BIGFILE.000.')
    stamp, archive = fingerprint(install), fmt.Archive(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    tables = {}
    for locale in {source_locale, 'en', *(value for value in targets.values() if value)}:
        entry = archive.select(_LOCALS, locale)
        if entry:
            code, table = fmt.locals_table(archive.read(entry))
            if code != TEXT_LOCALES[locale]:
                raise ValueError('Deus Ex text locale disagrees with archive locale')
            tables[locale] = table
    if source_locale not in tables:
        raise PreparationFailure('deusexhrdc_missing_pack',
            'The selected Deus Ex language pack is missing. Choose that language in Steam Properties → Language, finish the download and verify game files, then prepare again.')
    sounds, cinematics, choices, counts = _sound_inventory(archive, progress)
    narrative = _readables(archive)
    narrative.update({identity: 'choice' for identity in choices})
    voices = defaultdict(list)
    for identity, (owner, text_id, path, media) in sounds.items():
        if not text_id:
            counts['voice_streams_without_caption'] += 1
            counts['english_only_commentary_streams'] += '\\commentary\\' in path
            continue
        voices[text_id].append((identity, owner, path, media))
    records, cinematic_ids = _cinematic_records(archive, cinematics, tables, source_locale, counts)
    for text_id, paragraph in tables[source_locale].items():
        if text_id in cinematic_ids and text_id not in voices:
            continue
        source_pages = captions(paragraph)
        translated = {locale: captions(table[text_id]) for locale, table in tables.items() if text_id in table}
        bindings = voices.get(text_id, [])
        unique_media = {binding[3] for binding in bindings}
        binding = bindings[0] if len(unique_media) == 1 else None
        if len(unique_media) > 1:
            counts['ambiguous_caption_voice_bindings'] += 1
        audio, duration = None, None
        if binding:
            identity, owner, path, media = binding
            entry = archive.select(media, source_locale)
            if entry:
                rate, samples, channels = fmt.mul_header(archive.read(entry, 0, 2048))
                if channels in {1, 2}:
                    duration = round(samples / rate * 1000)
                    audio = {'locale': source_locale, 'owner': owner, 'sound': identity,
                             'media': media, 'caption': text_id}
                    if channels == 2:
                        audio.update(decoder_format='mul', rate=rate, samples=samples, channels=channels)
                else:
                    counts['unsupported_multichannel_voices'] += 1
        timed = len(source_pages) > 1 and duration is not None and all(
            first[2] < second[2] for first, second in zip(source_pages, source_pages[1:])) and source_pages[-1][2] < duration
        state = 'voiced' if audio else 'unavailable' if bindings else 'unvoiced' if text_id in narrative else 'unknown'
        kind = _kind(binding[2]) if binding else 'unresolved_dialogue' if bindings else narrative.get(text_id, 'unclassified_localization')
        for page, text, start in source_pages:
            if not text:
                continue
            # Only corresponding authored page ordinals are aligned. Never put
            # a translation's complete future paragraph in a current caption.
            texts = {locale: pages[page][1] for locale, pages in translated.items()
                     if len(pages) == len(source_pages) and pages[page][1]}
            reference = dict(audio) if audio else None
            category = kind
            if reference:
                if timed:
                    reference.update(start_ms=start, end_ms=source_pages[page+1][2] if page+1 < len(source_pages) else duration)
                else:
                    reference['playback_scope'] = 'full_track'
                    category += '_full_track'
            records.append({'text_id': f'{GAME}:{text_id}:{page}', 'english': texts.get('en', ''), 'chinese': '',
                'source_locale': source_locale, 'source_text': text, 'texts': texts, 'audio_locale': source_locale,
                'audio': reference, 'voice_status': state, 'dialogue_kind': category})
    if fingerprint(install) != stamp:
        raise PreparationFailure('deusexhrdc_files_changed', 'Deus Ex game files changed during preparation. Finish the Steam download and prepare again.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    counts.update({'caption_voice_identifiers': len(voices), 'readable_text_fields': len(narrative),
                   'timed_caption_records': sum(bool(row['audio'] and 'start_ms' in row['audio']) for row in records)})
    voiced = sum(bool(row['audio']) for row in records)
    warnings = [
        'Each authored subtitle page is a separate current line. Valid authored page times trim the original recording; other pages explicitly play the full bound recording.',
        'Email, iReader and mission-log text is available through the unvoiced capture toggle. Use full-frame matching or independent regions for dialogue choices, terminal panels and readables.',
        'Pre-rendered CRI cinematics use authored subtitle timelines and exact named original voice tracks; ending variants retain their own caption and recording identities. Conversation-wheel labels and previews are text-only choices; the selected response retains its separate original voice.',
        'Non-subtitled barks and English-only developer commentary have no OCR caption binding. They are inventoried but are not inferred from nearby text.',
        'Caption IDs assigned to multiple different recordings remain unavailable until the scene can disambiguate them.']
    if not voiced:
        warnings.append('The selected voice pack is missing or incomplete. Select the language in Steam Properties → Language, finish the download and verify game files.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install), 'fingerprint': stamp,
            'records': records, 'narrative_inventory': dict(counts), 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if not any(locale in row['texts'] for row in records)],
            'message': f'{len(records):,} official {source_locale} entries; {voiced:,} original voice captions'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, _destination):
    try:
        if audio.get('decoder_format') == 'adx':
            return _extract_movie(install, audio)
        locale = audio.get('locale')
        if locale not in SUPPORTED_LOCALES or any(type(audio.get(key)) is not int or not 0 <= audio[key] <= 0xffffffff
                                               for key in ('owner', 'sound', 'media', 'caption')):
            raise ValueError('Invalid Deus Ex original voice reference')
        archive = fmt.Archive(install)
        owner = archive.select(audio['owner'], locale)
        if owner is None:
            raise ValueError('Missing Deus Ex sound owner')
        sections = [section for section in fmt.sections(archive.read(owner))
                    if section.kind == 7 and section.subtype == 13 and section.identity == audio['sound']]
        if len(sections) != 1:
            raise ValueError('Ambiguous Deus Ex sound owner')
        binding = fmt.stream_binding(sections[0])
        if not binding or binding[0] != audio['caption'] or binding[2] != audio['media']:
            raise ValueError('Deus Ex original voice binding changed; refresh game data')
        entry = archive.select(audio['media'], locale)
        if entry is None:
            raise ValueError('Missing selected Deus Ex original voice pack')
        data = archive.read(entry)
        if audio.get('decoder_format') == 'mul':
            rate, samples, channels = fmt.mul_header(data)
            if channels != 2 or (rate, samples, channels) != (audio.get('rate'), audio.get('samples'), audio.get('channels')):
                raise ValueError('Changed Deus Ex original stereo voice metadata')
            fmt.demux_streams(data)
            return data
        return fmt.demux_voice(data)
    except (ValueError, struct.error, UnicodeError) as error:
        raise _invalid(error) from error


def _extract_movie(install, audio):
    locale = audio.get('locale')
    if locale not in SUPPORTED_LOCALES or any(type(audio.get(key)) is not int or not 0 <= audio[key] <= 0xffffffff
        for key in ('owner', 'movie', 'media', 'caption', 'track', 'cue')):
        raise ValueError('Invalid Deus Ex movie voice reference')
    archive = fmt.Archive(install)
    owner = archive.select(audio['owner'], locale)
    if owner is None:
        raise ValueError('Missing Deus Ex movie owner')
    sections = fmt.selected_sections(archive, owner, {(7, 0, audio['movie'])})
    if len(sections) != 1:
        raise ValueError('Missing Deus Ex authored movie definition')
    binding = movies.movie_binding(sections[0])
    if not binding or binding['media'] != audio['media']:
        raise ValueError('Changed Deus Ex authored movie binding')
    entry = archive.select(audio['media'], locale)
    if entry is None:
        raise ValueError('Missing Deus Ex cinematic pack')
    tracks = movies.movie_tracks(archive, entry)
    variants = dict(binding['variants'])
    if binding['making_of'] and set(tracks) == {'makingof2.avi'}:
        variants['making_of'] = {'voices': {'en': 'makingof2.avi'}, 'cues': binding['unbound_cues']}
    groups = [group for variant, group in variants.items() if hashlib.sha256(variant.encode()).hexdigest()[:16] == audio.get('variant')]
    if len(groups) != 1 or audio['cue'] >= len(groups[0]['cues']) or groups[0]['cues'][audio['cue']][2] != audio['caption']:
        raise ValueError('Changed Deus Ex movie caption binding')
    _name, track = _movie_track(tracks, groups[0]['voices'].get(locale))
    if not track or any(audio.get(key) != track[key] for key in ('track', 'rate', 'samples', 'channels')):
        raise ValueError('Changed Deus Ex movie voice locale')
    result = movies.demux_adx(archive, entry, track['track'])
    if any(result != movies.demux_adx(archive, entry, channel) for channel in track.get('duplicate_tracks', [])):
        raise ValueError('Conflicting Deus Ex original movie tracks')
    if movies.adx_header(result) != {key: track[key] for key in ('rate', 'samples', 'channels')}:
        raise ValueError('Deus Ex original movie waveform changed')
    return result


def decode_voice_source(data, audio, output, decoder, scratch):
    """Use the verified local decoder with an explicit validated container."""
    is_adx = audio.get('decoder_format') == 'adx'
    if audio.get('decoder_format') == 'mul':
        return _decode_stereo_mul(data, audio, output, decoder, scratch)
    if is_adx:
        metadata = movies.adx_header(data)
        if metadata != {key: audio.get(key) for key in ('rate', 'samples', 'channels')}:
            raise ValueError('Deus Ex movie waveform disagrees with its original track')
    elif len(data) < 48 or data[:4] != b'FSB4' or struct.unpack_from('<I', data, 4)[0] != 1:
        raise ValueError('Invalid original Deus Ex dialogue waveform')
    scratch, output = Path(scratch), Path(output)
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / ('deusex-original.adx' if is_adx else 'deusex-original.fsb')
    source.write_bytes(data)
    try:
        process = subprocess.run([str(decoder), '-i', '-o', str(output), str(source)], capture_output=True, timeout=90,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if process.returncode or not output.is_file() or output.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('Deus Ex original voice decoding failed')
        with wave.open(str(output)) as decoded:
            if is_adx and (decoded.getnchannels(), decoded.getframerate(), decoded.getnframes()) != (metadata['channels'], metadata['rate'], metadata['samples']):
                raise ValueError('Deus Ex decoded movie waveform disagrees with its original track')
    finally:
        source.unlink(missing_ok=True)


def _decode_stereo_mul(data, audio, output, decoder, scratch):
    rate, samples, channels = fmt.mul_header(data)
    if channels != 2 or (rate, samples, channels) != (audio.get('rate'), audio.get('samples'), audio.get('channels')):
        raise ValueError('Invalid original Deus Ex stereo voice metadata')
    streams = fmt.demux_streams(data)
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    decoded, paths = [], []
    try:
        for index, stream in enumerate(streams):
            source, target = scratch / f'deusex-channel-{index}.fsb', scratch / f'deusex-channel-{index}.wav'
            paths.extend((source, target))
            source.write_bytes(stream)
            process = subprocess.run([str(decoder), '-i', '-o', str(target), str(source)], capture_output=True, timeout=90,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process.returncode or not target.is_file() or target.stat().st_size > 256 * 1024 * 1024:
                raise ValueError('Deus Ex original stereo voice decoding failed')
            with wave.open(str(target)) as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != rate:
                    raise ValueError('Unsupported decoded Deus Ex original channel')
                decoded.append(array('h', wav.readframes(wav.getnframes())))
        if len(decoded[0]) != len(decoded[1]) or len(decoded[0]) < samples:
            raise ValueError('Deus Ex original stereo channels have inconsistent lengths')
        # Interleave the original left/right PCM channels without resampling,
        # summing, inventing channel gains or discarding a performance.
        result = array('h', [0]) * (len(decoded[0]) * 2)
        result[0::2], result[1::2] = decoded
        with wave.open(str(output), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(result.tobytes())
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
