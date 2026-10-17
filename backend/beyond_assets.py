"""Official BEYOND PC localization and explicitly bound original performances."""
from __future__ import annotations

import hashlib
import io
import re
import struct
import subprocess
import wave
from pathlib import Path

from . import quantic_assets as q
from .languages import GAME_LOCALES, normalize_text, resolve_locale
from .media_tools import ffmpeg_executable

LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = GAME_LOCALES['beyond']
TEXT_LOCALES = dict(zip(('fr','en','de','it','es-ES','nl','pt-PT','sv','da','no','fi','ru','pl','ja','ko','zh-Hant','el','cs','hu','hr','es-419','pt-BR','tr','zh-Hans'),
                       ('FRE','ENG','GER','ITA','SPA','DUT','POR','SWE','DAN','NOR','FIN','RUS','POL','JAP','KOR','CHI','GRE','CZE','HUN','CRO','MEX','BRA','TUR','CHS')))
LANGUAGE_IDS = {code: index for index, code in enumerate(TEXT_LOCALES.values())}


def archive_sources(install):
    return sorted(p for p in install.glob('BigFile_PC*') if p.is_file() and re.fullmatch(r'.*\.(?:idx|dat|d\d\d)', p.name, re.I))


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}' for p in archive_sources(install)).encode()).hexdigest()


def cues(text):
    """Preserve authored cue identities; never align translated text by position."""
    matches = list(re.finditer(r'\{\*(?:(\d+)|TC:(\d+)\|(\d+))\}', text))
    if not matches:
        value = re.sub(r'\s+', ' ', re.sub(r'\{[^}]*\}', '', text)).strip()
        return {'complete': value} if value else {}
    result = {}
    for i, match in enumerate(matches):
        identity = match[1] or f'TC:{match[2]}|{match[3]}'
        value = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
        value = re.sub(r'\{[^}]*\}', '', value).strip()
        value = re.sub(r'\s+', ' ', value)
        if value:
            if identity in result and result[identity] != value:
                raise ValueError('Ambiguous official subtitle cue identity')
            result[identity] = value
    return result


def group_short_cues(records):
    """Collect ambiguous fragments with a following, uniquely authored cue.

    Both cues must use one paragraph and one original performance. Only the
    final cue is an OCR anchor: the earlier fragment alone cannot select a
    performance, and cannot publish speech that has not appeared yet.
    """
    import json
    choices, anchors, paragraphs, global_rows, global_choices = {}, {}, {}, {}, {}
    for row in records:
        values = {(locale, normalize_text(text, locale)) for locale, text in row['texts'].items()}
        values.update((locale, normalize_text(text, locale))
                      for locale, texts in row.get('ocr_texts', {}).items() for text in texts)
        values = {(locale, text) for locale, text in values if len(text) >= 2}
        anchors[row['text_id']] = values
        for key in values:
            identity = (json.dumps(row['audio'], sort_keys=True), row['source_text'])
            choices.setdefault(key, set()).add(identity)
            global_rows.setdefault(key[1], set()).add(row['text_id'])
            global_choices.setdefault(key[1], set()).add(identity)
        audio = row['audio']
        paragraph = re.fullmatch(r'beyond:([A-Za-z0-9_]+):(?:\d+|TC:\d+\|\d+)', row['text_id'])
        if paragraph and type(audio.get('start_ms')) is int and type(audio.get('end_ms')) is int:
            performance = {key: value for key, value in audio.items() if key not in {'start_ms', 'end_ms'}}
            key = (paragraph[1], json.dumps(performance, sort_keys=True), row.get('player_voice'))
            paragraphs.setdefault(key, []).append(row)
    replaced, used = {}, set()
    for (paragraph, _, _), rows in paragraphs.items():
        rows.sort(key=lambda row: row['audio']['start_ms'])
        for first, following in zip(rows, rows[1:]):
            if first['text_id'] in used or following['text_id'] in used:
                continue
            values = anchors[first['text_id']]
            # Keep fragments that can already identify their own performance
            # separate. Otherwise a later context record would repeat them.
            if not values or any(len(text) > 24 or len(choices[(locale, text)]) == 1 for locale, text in values):
                continue
            ambiguous = {locale for locale, _ in values}
            if any(len(global_choices[text]) == 1 and len(global_rows[text]) > 1
                   for _, text in anchors[following['text_id']]):
                continue
            if not any(locale in ambiguous and len(choices[(locale, text)]) == 1
                       for locale, text in anchors[following['text_id']]):
                continue
            start, end = first['audio']['start_ms'], following['audio']['end_ms']
            if not first['audio']['end_ms'] <= following['audio']['start_ms'] <= first['audio']['end_ms'] + 12000:
                continue
            if first.get('channels') != following.get('channels') or first['source_locale'] != following['source_locale']:
                continue
            if not following['texts'].keys() <= first['texts'].keys():
                continue
            locales = first['texts'].keys() & following['texts'].keys()
            texts = {locale: first['texts'][locale] + ' ' + following['texts'][locale] for locale in locales}
            source = first['source_locale']
            if source not in texts or len(texts[source]) > 2000:
                continue
            if any(normalize_text(text, locale) in global_rows for locale, text in texts.items()):
                continue
            row = {**first, 'text_id': f'beyond:{paragraph}:context-{start}-{end}',
                   'source_text': texts[source], 'texts': texts,
                   'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                   'audio': {**first['audio'], 'start_ms': start, 'end_ms': end},
                   'member_text_ids': [first['text_id'], following['text_id']],
                   'ocr_texts': {locale: list(dict.fromkeys([following['texts'][locale],
                       *following.get('ocr_texts', {}).get(locale, [])])) for locale in locales}}
            replaced[following['text_id']] = row
            used.update((first['text_id'], following['text_id']))
    # Retain the original short cues in the lookup. Removing them would make
    # an identical fragment in a different performance falsely look unique.
    return [replaced.get(row['text_id'], row) for row in records]


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported BEYOND study/audio language')
    stamp = fingerprint(install)
    code, language_id = TEXT_LOCALES[source_locale], LANGUAGE_IDS[TEXT_LOCALES[source_locale]]
    available = set(TEXT_LOCALES)
    targets = {target: resolve_locale(target, available) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    voices, containers, authored, offset_owners = {}, [], set(), {}
    for path in sorted(install.glob('BigFile_PC*.idx')):
        entries = q.read_index(path)
        # English is in the base archives; other packs contain only FlowDialog.
        is_source = path.stem.endswith('_' + code) or (code == 'ENG' and not re.search(r'_[A-Z]{3}$', path.stem))
        for entry in entries:
            if entry.kind == 4091 and is_source:
                if entry.identity in voices:
                    if hashlib.sha256(voices[entry.identity].read()).digest() != hashlib.sha256(entry.read()).digest():
                        raise ValueError('Ambiguous installed original dialogue identity')
                else:
                    voices[entry.identity] = entry
            elif entry.kind == 29:
                refs = q.container_references(q.metadata(entry, first_only=True))
                authored.update(identity for kind, identity, lang in refs if kind == 4091 and lang == language_id)
                for kind, identity, _ in refs:
                    if kind == 4092:
                        offset_owners.setdefault(identity, entry)
                if any(kind == 1016 for kind, _, _ in refs):
                    containers.append(entry)
    if not voices:
        raise ValueError(f'Install the official {source_locale} voice pack through Steam before preparing BEYOND.')
    records, diagnostics, seen = [], {}, {}
    for number, entry in enumerate(containers):
        progress(f'Reading BEYOND {source_locale} dialogue container {number+1}/{len(containers)}')
        parts = q.components(q.metadata(entry))
        offsets = {identity: body for kind, identity, lang, body in parts if kind == 4092 and lang == language_id}
        for kind, identity, _, body in parts:
            if kind != 1016:
                continue
            tables = q.localization(body)
            source = tables.get(code, {})
            for key, paragraph in source.get('texts', {}).items():
                reference = source['bindings'].get(key)
                if not reference or reference[0] != 4091 or reference[1] not in authored:
                    diagnostics['unbound_paragraphs'] = diagnostics.get('unbound_paragraphs', 0) + 1
                    continue
                voice = voices.get(reference[1])
                if voice is None:
                    diagnostics['missing_performances'] = diagnostics.get('missing_performances', 0) + 1
                    continue
                raw = voice.read()
                offset_id, times, _ = q.partition(raw)
                offset_table = offsets.get(offset_id)
                if offset_table is None and offset_id in offset_owners:
                    owner_parts = q.components(q.metadata(offset_owners[offset_id]))
                    offset_table = next((body for kind, identity, lang, body in owner_parts if kind == 4092 and identity == offset_id and lang == language_id), None)
                if offset_table is None:
                    raise ValueError('Authored original dialogue chunk reference is unavailable')
                try:
                    blocks = q.partition_blocks(raw, offset_table)
                except ValueError as error:
                    raise ValueError(f'Original dialogue {voice.identity}: {error}') from error
                translated = {locale: cues(tables.get(TEXT_LOCALES[locale], {}).get('texts', {}).get(key, '')) for locale in selected}
                source_cues = cues(paragraph)
                numbered = [int(cue) for cue in source_cues if cue.isdigit()]
                if 'complete' in source_cues or numbered and (set(numbered) != set(range(1, len(times)+1))):
                    # Some shipped dub paragraphs have fewer timing pairs than
                    # text pages. Retain their exact complete performance and
                    # authored OCR pages instead of inventing per-page cuts.
                    diagnostics['complete_performance_paragraphs'] = diagnostics.get('complete_performance_paragraphs', 0) + 1
                    texts = {locale: ' '.join(values.values()) for locale, values in translated.items() if values}
                    text_id = f'beyond:{key}:complete'
                    row = {'text_id': text_id, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                           'source_locale': source_locale, 'source_text': ' '.join(source_cues.values()), 'texts': texts,
                           'audio_locale': source_locale, 'ocr_texts': {locale: list(values.values()) for locale, values in translated.items()},
                           'audio': {'index': voice.index.name, 'identity': voice.identity, 'locale': source_locale,
                                     'offsets': offset_table.hex()}}
                    if text_id in seen and seen[text_id] != row:
                        raise ValueError('Conflicting complete original performance identities')
                    if text_id not in seen:
                        records.append(row); seen[text_id] = row
                    continue
                for cue, text in source_cues.items():
                    if cue.startswith('TC:'):
                        start, end = map(int, cue[3:].split('|'))
                    elif 1 <= int(cue) <= len(times):
                        start, end = (round(value * 1000) for value in times[int(cue)-1])
                    else:
                        raise ValueError(f'Official subtitle cue {cue} has no authored audio timing: {voice.identity}, {len(times)} times')
                    if not 0 <= start < end <= len(blocks) * 1000:
                        raise ValueError('Official subtitle timing exceeds its original performance')
                    texts = {locale: values[cue] for locale, values in translated.items() if cue in values}
                    text_id = f'beyond:{key}:{cue}'
                    audio = {'index': voice.index.name, 'identity': voice.identity, 'locale': source_locale,
                             'offsets': offset_table.hex(), 'start_ms': start, 'end_ms': end}
                    row = {'text_id': text_id, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                           'source_locale': source_locale, 'source_text': text, 'texts': texts,
                           'audio_locale': source_locale, 'audio': audio}
                    if text_id in seen and seen[text_id] != row:
                        raise ValueError('Conflicting official subtitle or performance identities')
                    if text_id not in seen:
                        records.append(row); seen[text_id] = row
    if not records or fingerprint(install) != stamp:
        raise ValueError('BEYOND game files changed or dialogue was incomplete; previous table retained.')
    records = group_short_cues(records)
    diagnostics['context_groups'] = sum(bool(row.get('member_text_ids')) for row in records)
    return {'format': 2, 'game': 'beyond', 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'records': records, 'diagnostics': diagnostics,
            'missing_translation_locales': [target for target, locale in targets.items() if locale is None],
            'message': f'{len(records):,} official {source_locale} subtitles with original audio; {len(containers):,} authored containers'}


def extract_voice(install, audio, _executable, destination):
    locale, name = audio['locale'], audio['index']
    if locale not in SUPPORTED_LOCALES or Path(name).name != name or not re.fullmatch(r'BigFile_PC.*\.idx', name):
        raise ValueError('Invalid BEYOND original voice reference')
    code = TEXT_LOCALES[locale]
    if not (Path(name).stem.endswith('_' + code) or code == 'ENG' and not re.search(r'_[A-Z]{3}$', Path(name).stem)):
        raise ValueError('BEYOND original voice locale disagrees with its pack')
    entry = next((entry for entry in q.read_index(install / name) if entry.kind == 4091 and entry.identity == audio['identity']), None)
    if entry is None:
        raise ValueError('Original BEYOND performance is no longer installed')
    blocks = q.partition_blocks(entry.read(), bytes.fromhex(audio['offsets']))
    # Decode contiguous MP3 runs together to preserve their frame reservoir.
    # NULL partitions retain their authored position as PCM silence.
    rate = 44100
    pcm = bytearray(len(blocks) * rate * 2)
    index = 0
    while index < len(blocks):
        if blocks[index] is None:
            index += 1; continue
        start = index
        run = []
        while index < len(blocks) and blocks[index] is not None:
            run.append(blocks[index]); index += 1
        encoded = b''.join(run)
        samples, encoded_rate = mp3_format(encoded)
        # FFmpeg's demuxer needs two consecutive frames to identify a stream.
        # A shipped single-frame tail is decoded with a duplicate probe frame;
        # discard the probe's PCM, retaining only the original frame's samples.
        probe = samples == 1152
        path = destination / f'run-{start}.mp3'; path.write_bytes(encoded * (2 if probe else 1))
        result = subprocess.run([str(ffmpeg_executable()), '-v', 'error', '-nostdin', '-i', str(path),
                                 '-f', 's16le', '-ac', '1', '-ar', str(rate), 'pipe:1'],
                                check=True, capture_output=True, timeout=90,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        decoded = result.stdout
        expected = (samples * rate + encoded_rate - 1) // encoded_rate
        if probe:
            decoded = decoded[:expected*2]
        # FFmpeg resamples original 32/48 kHz performances to the shared WAV
        # rate. Its final sample may round either way; larger differences
        # indicate a truncated stream rather than normal resampler rounding.
        if len(decoded) % 2 or abs(len(decoded)//2 - samples*rate/encoded_rate) > 1 or samples/encoded_rate > index-start+.1:
            raise ValueError('Original BEYOND MP3 duration disagrees with authored partitions')
        length = min(len(decoded), (index-start)*rate*2)
        pcm[start*rate*2:start*rate*2+length] = decoded[:length]
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(pcm)
    return output.getvalue()


def mp3_samples(data):
    return mp3_format(data)[0]


def mp3_format(data):
    """Validate contiguous MPEG-1 Layer III frames and their common sample rate."""
    position, samples, rate = 0, 0, None
    bitrates = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
    while position < len(data):
        if position + 4 > len(data):
            raise ValueError('Incomplete original MPEG audio frame')
        header = int.from_bytes(data[position:position+4], 'big')
        bitrate, frequency = (header >> 12) & 15, (header >> 10) & 3
        if header >> 21 != 0x7ff or (header >> 19) & 3 != 3 or (header >> 17) & 3 != 1 or not bitrates[bitrate] or frequency == 3:
            raise ValueError('Unsupported original MPEG dialogue frame')
        frame_rate = (44100, 48000, 32000)[frequency]
        if rate is not None and rate != frame_rate:
            raise ValueError('Original MPEG dialogue sample rate changed within a stream')
        rate = frame_rate
        length = 144000 * bitrates[bitrate] // rate + ((header >> 9) & 1)
        if position + length > len(data):
            raise ValueError('Original MPEG dialogue frame exceeds its block')
        position += length
        samples += 1152
    if not samples:
        raise ValueError('Original MPEG dialogue is empty')
    return samples, rate
