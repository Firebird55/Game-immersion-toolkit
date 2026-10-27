"""Official BEYOND PC localization and explicitly bound original performances."""
from __future__ import annotations

import hashlib
import re
import struct
import subprocess
from pathlib import Path

from . import quantic_assets as q
from .quantic_audio import decode_blocks, mp3_format, mp3_samples
from .languages import GAME_LOCALES, normalize_text, resolve_locale
from .media_tools import ffmpeg_executable
from .preparation_errors import PreparationFailure

LANGUAGE_INDEX_VERSION = 3
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


def standalone_localization(data):
    """Standalone resources retain section lengths stripped in DATA_CONT."""
    position, flattened = 0, bytearray()
    for tag, expected in ((b'COM_CONT', 4), (b'LOADCONT', 2), (b'LOCALIZ_', 5)):
        if len(data) > q.METADATA_LIMIT or position + 16 > len(data) or data[position:position+8] != tag:
            raise ValueError('Unsupported standalone BEYOND localization sections')
        version, size = struct.unpack_from('<II', data, position + 8)
        end = position + 16 + size
        if version != expected or end > len(data) or (tag == b'LOADCONT' and size):
            raise ValueError('Unsupported standalone BEYOND localization bounds')
        flattened.extend(data[position:position+12])
        flattened.extend(data[position+16:end])
        position = end
    if position != len(data):
        raise ValueError('Trailing standalone BEYOND localization data')
    return q.localization(bytes(flattened))


def unbound_status(key, paragraph, source):
    """Only authored chapter text labels are silent, never missing speech.

    Type 2 is the observed localized text-only field; type 1 carries FlowDialog
    aliases and type 4 texture aliases. Global UI and shared controller prompts
    deliberately remain outside the narrative catalog.
    """
    flag = source.get('text_flags', {}).get(key)
    pointer = source.get('binding_states', {}).get(key, 'absent')
    if flag == 4:
        return 'unknown', 'localized_texture'
    scene_label = re.fullmatch(r'IW_(?:0[1-9]|[1-3]\d|40)\d{2}_[A-Z0-9_]+_K\d+', key)
    if flag == 2 and pointer in {'absent', 'none'} and scene_label and not re.search(r'\{(?:S|\*)', paragraph):
        return 'unvoiced', 'choice'
    if flag == 1 or pointer in {'unresolved', 'internal', 'resolved'}:
        return 'unavailable', 'subtitle'
    return 'unknown', 'unclassified_text'


def unbound_paragraph(text):
    # Unresolved speech cannot use its cue labels as validated audio anchors.
    # Some unused shipped paragraphs repeat cue numbers; retain their complete
    # text for inventory without relaxing the bound-performance cue parser.
    return re.sub(r'\s+', ' ', re.sub(r'\{[^}]*\}', '', text)).strip()


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
        if audio and paragraph and type(audio.get('start_ms')) is int and type(audio.get('end_ms')) is int:
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
    try:
        return _index_language(install, data_dir, source_locale, target_locales, progress)
    except PreparationFailure:
        raise
    except (ValueError, struct.error, UnicodeError) as error:
        raise PreparationFailure('unsupported_game_format',
            'BEYOND game archives or dialogue metadata no longer match this reader. '
            'Finish any game update, verify its files and update the toolkit before retrying.') from error


def _index_language(install, data_dir, source_locale, target_locales, progress):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported BEYOND study/audio language')
    stamp = fingerprint(install)
    code, language_id = TEXT_LOCALES[source_locale], LANGUAGE_IDS[TEXT_LOCALES[source_locale]]
    available = set(TEXT_LOCALES)
    targets = {target: resolve_locale(target, available) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    voices, containers, authored, offset_owners = {}, [], set(), {}
    standalone = []
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
            elif entry.kind == 1016:
                standalone.append(entry)
    records, diagnostics, seen = [], {}, {}
    performance_cache = {}
    # These resources include console/system messages and localized textures.
    # Count and validate them, without treating an image alias as readable text.
    for entry in standalone:
        if entry.size > q.METADATA_LIMIT:
            raise ValueError('Standalone BEYOND localization exceeds the metadata limit')
        table = standalone_localization(q.metadata(entry)).get(code, {})
        diagnostics['standalone_localized_entries'] = diagnostics.get('standalone_localized_entries', 0) + len(table.get('texts', {}))
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
                if source.get('text_flags', {}).get(key) == 2 and key.startswith(('IW_5000_', 'IW_6000_', 'IW_6001_')):
                    diagnostics['excluded_system_or_shared_prompts'] = diagnostics.get('excluded_system_or_shared_prompts', 0) + 1
                    continue
                reference = source['bindings'].get(key)
                voice = voices.get(reference[1]) if reference and reference[0] == 4091 and reference[1] in authored else None
                if voice is None:
                    diagnostics['unbound_paragraphs'] = diagnostics.get('unbound_paragraphs', 0) + 1
                    status, kind = unbound_status(key, paragraph, source)
                    if reference and reference[0] == 4091:
                        status, kind = 'unavailable', 'subtitle'
                    cue = 'complete' if status == 'unvoiced' else 'unresolved'
                    source_text = unbound_paragraph(paragraph)
                    source_cues = {cue: source_text} if source_text else {}
                    translated = {locale: {cue: text} for locale in selected
                        if (text := unbound_paragraph(tables.get(TEXT_LOCALES[locale], {}).get('texts', {}).get(key, '')))}
                    for cue, text in source_cues.items():
                        texts = {locale: values[cue] for locale, values in translated.items() if cue in values}
                        row = {'text_id': f'beyond:{key}:{cue}', 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                               'source_locale': source_locale, 'source_text': text, 'texts': texts, 'audio_locale': source_locale,
                               'audio': None, 'voice_status': status, 'dialogue_kind': kind}
                        if row['text_id'] in seen and seen[row['text_id']] != row:
                            raise ValueError('Conflicting unbound narrative identities')
                        if row['text_id'] not in seen:
                            records.append(row); seen[row['text_id']] = row
                    continue
                performance = performance_cache.get(voice.identity)
                if performance is None:
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
                    performance = (offset_id, times, offset_table, len(blocks))
                    performance_cache[voice.identity] = performance
                offset_id, times, offset_table, block_count = performance
                if offset_id in offsets and offsets[offset_id] != offset_table:
                    raise ValueError('Conflicting original dialogue chunk tables')
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
                           'audio_locale': source_locale, 'voice_status': 'voiced', 'dialogue_kind': 'subtitle',
                           'ocr_texts': {locale: list(values.values()) for locale, values in translated.items()},
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
                    if not 0 <= start < end <= block_count * 1000:
                        raise ValueError('Official subtitle timing exceeds its original performance')
                    texts = {locale: values[cue] for locale, values in translated.items() if cue in values}
                    text_id = f'beyond:{key}:{cue}'
                    audio = {'index': voice.index.name, 'identity': voice.identity, 'locale': source_locale,
                             'offsets': offset_table.hex(), 'start_ms': start, 'end_ms': end}
                    row = {'text_id': text_id, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                           'source_locale': source_locale, 'source_text': text, 'texts': texts,
                           'audio_locale': source_locale, 'audio': audio, 'voice_status': 'voiced', 'dialogue_kind': 'subtitle'}
                    if text_id in seen and seen[text_id] != row:
                        raise ValueError('Conflicting official subtitle or performance identities')
                    if text_id not in seen:
                        records.append(row); seen[text_id] = row
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'BEYOND game files changed during preparation. Finish the game update and retry; the previous table was kept.', game_files_changed=True)
    if not records:
        raise ValueError('BEYOND dialogue metadata is empty')
    # Preserve existing authored voice/context identities when a text-only
    # choice happens to have the same short wording as a spoken cue.
    records = group_short_cues([row for row in records if row['audio']]) + [row for row in records if not row['audio']]
    diagnostics['validated_performances'] = len(performance_cache)
    diagnostics['context_groups'] = sum(bool(row.get('member_text_ids')) for row in records)
    counts = {state: sum(row['voice_status'] == state for row in records) for state in ('voiced', 'unvoiced', 'unavailable', 'unknown')}
    warnings = [f"{counts['unavailable']:,} subtitle records lack a verified installed original performance; these are not unvoiced dialogue.",
                'Chapter-scoped text-only choices are inventoried separately. Repeated short choices can remain ambiguous during OCR.',
                'Localized textures, writing rendered only in scene images, system prompts and bonus videos do not have per-line text/audio coverage.']
    if counts['unknown']:
        warnings.append(f"{counts['unknown']:,} localized records have an unclassified text/audio format and remain excluded from capture.")
    if not voices:
        warnings.insert(0, f'Install the official {source_locale} voice pack through Steam for spoken dialogue. Text-only choices remain available with the unvoiced toggle.')
    return {'format': 2, 'game': 'beyond', 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'reader_revision': LANGUAGE_INDEX_VERSION, 'records': records, 'diagnostics': diagnostics, 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if locale is None],
            'message': f"{counts['voiced']:,} official {source_locale} subtitles with original audio; {counts['unvoiced']:,} text-only choices; {counts['unavailable']:,} unresolved voices"}


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
    return decode_blocks(blocks, destination, executable=ffmpeg_executable(), decode=subprocess.run)
