"""Read-only Shadow TIGER localization and authored Wwise subtitle bindings.

Archive/locals/WEM structures reviewed against TrRebootModTools commit
a79c48b75f1ffaaf623dc73a625211bf98ff0504 and a native Windows installation.
No external filename list, game text or third-party voice mapping is bundled.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
import struct

from .preparation_errors import PreparationFailure
from .textmaps import display_text
from .tiger_archive import TigerEntry, TigerSet, fingerprint

LANGUAGE_INDEX_VERSION = 1
GAME = 'shadowofthetombraider'
TEXT_LOCALES = {'en': 'english', 'fr': 'french', 'de': 'german', 'it': 'italian',
    'es-419': 'latamspanish', 'es-ES': 'iberspanish', 'ja': 'japanese',
    'pt-BR': 'portuguese', 'pl': 'polish', 'ru': 'russian', 'ko': 'korean',
    'zh-Hant': 'chinese', 'zh-Hans': 'simplechinese', 'ar': 'arabic'}
SUPPORTED_LOCALES = tuple(locale for locale in TEXT_LOCALES if locale != 'ko')
_BITS = dict(zip(('en', 'fr', 'de', 'it', 'es-419', 'es-ES', 'ja', 'pt-BR',
                  'pl', 'ru', 'ko', 'zh-Hant', 'zh-Hans', 'ar'),
                 (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 2048, 4096, 8192, 32768)))
_LANGUAGE_IDS = dict(zip(TEXT_LOCALES, (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)))
TEXT_MASKS = {locale: 0xFFFFFFFFFFFF0400 | bit for locale, bit in _BITS.items()}
VOICE_MASKS = {locale: 0x0FFFFF1C00FFFFFFF | (bit << 28) for locale, bit in _BITS.items()}
LOCALS_HASH = 0x331F339BC3DB8E80  # FNV-1a64 of pcx64-w\local\locals.bin
_MAX_METADATA = 1024 * 1024
_MAX_VOICE = 128 * 1024 * 1024
_GUID = re.compile(r'([0-9a-f]{8})[-_]([0-9a-f]{4})[-_]([0-9a-f]{4})[-_]([0-9a-f]{4})[-_]([0-9a-f]{12})$', re.I)


def _format(message='Unsupported Shadow dialogue format.'):
    return PreparationFailure('shadow_dialogue_format', message +
        ' Verify the installed game files and update the toolkit before retrying.')


def discover_install():
    from .game_paths import discover_install as discover
    return discover(GAME)


def read_locals(data: bytes, locale: str) -> dict[str, str]:
    """Read the keyed UTF-8 table, rejecting aliases and out-of-table pointers."""
    if len(data) < 8 or len(data) > 32 * 1024 * 1024:
        raise _format('Shadow localization is incomplete or exceeds its bound.')
    language, count = struct.unpack_from('<II', data)
    boundary = 8 + count * 8
    if language != _LANGUAGE_IDS[locale] or count > 500_000 or boundary > len(data):
        raise _format('Shadow localization language or table header is invalid.')
    result = {}
    for index in range(count):
        offset = struct.unpack_from('<Q', data, 8 + index * 8)[0]
        if not offset:
            continue
        if not boundary <= offset < len(data):
            raise _format('Shadow localization string bounds are invalid.')
        end = data.find(b'\0', offset, min(len(data), offset + 128 * 1024))
        if end < 0:
            raise _format('Shadow localization contains an unterminated string.')
        try:
            key, text = data[offset:end].decode('utf-8').split(' ', 1)
        except (UnicodeError, ValueError):
            raise _format('Shadow localization encoding is invalid.') from None
        key = key.casefold()
        if not key or len(key) > 4096 or key in result:
            raise _format('Shadow localization contains ambiguous keys.')
        result[key] = display_text(text)
    return result


def wem_bindings(data: bytes, total_size: int) -> list[dict]:
    """Read labels and paired sample cues; never estimate a subtitle boundary.

Metadata is before the data chunk in reviewed WEMs. A bounded prefix is enough;
an unrecognized late-metadata layout fails instead of guessing or decoding it.
"""
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        return []  # Wwise bank/control files are not individual speech files.
    riff_size = struct.unpack_from('<I', data, 4)[0] + 8
    if riff_size != total_size or total_size > _MAX_VOICE:
        raise _format('Shadow Wwise sound length is invalid.')
    cues, labels, sample_rate, position, reached_audio = {}, {}, None, 12, False
    while position + 8 <= min(len(data), total_size):
        kind, size = struct.unpack_from('<4sI', data, position)
        start, end = position + 8, position + 8 + size
        if end > total_size:
            raise _format('Shadow Wwise chunk exceeds its source.')
        if kind == b'data':
            reached_audio = True
            break
        if end > len(data):
            raise _format('Shadow Wwise metadata exceeds the supported prefix bound.')
        if kind == b'fmt ':
            if size < 16 or sample_rate is not None:
                raise _format()
            sample_rate = struct.unpack_from('<I', data, start + 4)[0]
            if not 8000 <= sample_rate <= 192000:
                raise _format('Shadow Wwise sample rate is invalid.')
        elif kind == b'cue ':
            if size < 4:
                raise _format()
            count = struct.unpack_from('<I', data, start)[0]
            if count > 8192 or size != 4 + count * 24:
                raise _format('Shadow Wwise cue table is invalid.')
            for index in range(count):
                identity, sample, chunk, chunk_start, block, sample_offset = struct.unpack_from('<II4sIII', data, start + 4 + index * 24)
                if identity in cues or chunk != b'data' or chunk_start or block or sample_offset:
                    raise _format('Shadow Wwise cue representation is unsupported.')
                cues[identity] = sample
        elif kind == b'LIST' and data[start:start + 4] == b'adtl':
            sub = start + 4
            while sub < end:
                if sub + 8 > end:
                    raise _format()
                child, length = struct.unpack_from('<4sI', data, sub)
                child_end = sub + 8 + length
                if child_end > end:
                    raise _format('Shadow Wwise label is incomplete.')
                if child == b'labl':
                    if length < 5:
                        raise _format()
                    identity = struct.unpack_from('<I', data, sub + 8)[0]
                    raw = data[sub + 12:child_end]
                    terminator = raw.find(b'\0')
                    if identity in labels or terminator < 0 or any(raw[terminator:]):
                        raise _format('Shadow Wwise labels are ambiguous or malformed.')
                    try:
                        labels[identity] = raw[:terminator].decode('utf-8').casefold()
                    except UnicodeError:
                        raise _format() from None
                sub = child_end + (length & 1)
        position = end + (size & 1)
    if not reached_audio or sample_rate is None:
        raise _format('Shadow Wwise audio or format metadata is incomplete.')
    if any(identity not in cues for identity in labels):
        raise _format('Shadow Wwise labels have no matching authored cue.')
    if len(labels) == 1:
        identity, label = next(iter(labels.items()))
        if label and not label.startswith('subtitle-') and cues[identity] == 0:
            return [{'label': label}]
    pairs = defaultdict(lambda: defaultdict(list))
    for identity, label in labels.items():
        match = re.fullmatch(r'subtitle-(start|end):(.+)', label)
        if match:
            pairs[match[2]][match[1]].append(cues[identity])
    result = []
    for label, sides in pairs.items():
        if len(sides['start']) != 1 or len(sides['end']) != 1:
            continue  # Repeated or unfinished cue pairs are not a unique clip.
        start, end = sides['start'][0], sides['end'][0]
        if not 0 <= start < end:
            continue
        start_ms, end_ms = round(start * 1000 / sample_rate), round(end * 1000 / sample_rate)
        if start_ms < end_ms:
            result.append({'label': label, 'start_ms': start_ms, 'end_ms': end_ms})
    return result


def _guid(key):
    match = _GUID.search(key)
    return ''.join(match.groups()).lower() if match else None


def _guid_keys(table):
    values = defaultdict(list)
    for key in table:
        if identity := _guid(key):
            values[identity].append(key)
    return {identity: keys[0] for identity, keys in values.items() if len(keys) == 1}


def _kind(key, cue=False):
    if cue or '_cine_' in key or '_igc_' in key:
        return 'cinematic'
    if any(value in key for value in ('_document_', '_mural_', '_relic_', 'collect_story_')):
        return 'narrated_collectible'
    if key.startswith(('ene_', 'civ_', 'npc_', 'lar_')) or '_walla_' in key:
        return 'ambient'
    if re.match(r'^\d{3}_', key):
        return 'dialogue'
    return 'unclassified'


def _select_voice(candidates):
    # Cinematics ship both isolated line WEMs and timed scene-mix WEMs with
    # the same authored key. Prefer the one unambiguous isolated recording;
    # distinct isolated performances must still remain unavailable.
    isolated = [candidate for candidate in candidates if 'start_ms' not in candidate]
    choices = isolated or candidates
    return choices[0] if len(choices) == 1 else None


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales,
                   progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Shadow study/audio locale; Korean has official text only.')
    stamp = fingerprint(install)
    archives = TigerSet(install, version=5)
    available = {locale for locale, mask in TEXT_MASKS.items() if (LOCALS_HASH, mask) in archives.files}
    if source_locale not in available:
        raise PreparationFailure('shadow_text_pack_missing',
            'The selected Shadow text pack is not installed. Select its official launcher language, finish downloading, and retry. Regional packs may require the matching edition.')
    targets = {target: resolve_locale(target, available) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    tables = {}
    for locale in sorted(selected):
        progress(f'Reading official Shadow {locale} localization')
        tables[locale] = read_locals(archives.read(archives.files[LOCALS_HASH, TEXT_MASKS[locale]],
                                                   max_bytes=32 * 1024 * 1024), locale)
    source = tables[source_locale]
    guid_keys = _guid_keys(source)
    voices, inventory = defaultdict(list), Counter()
    voice_entries = sorted((entry for entry in archives.entries() if entry.locale == VOICE_MASKS[source_locale]),
                           key=lambda entry: (entry.archive, entry.offset))
    progress(f'Checking exact original Shadow {source_locale} subtitle/voice bindings')
    for index, entry in enumerate(voice_entries):
        if index and index % 4000 == 0:
            progress(f'Checked {index:,} original Shadow voice entries')
        prefix = archives.prefix(entry, min(entry.size, 16384))
        if prefix[:4] != b'RIFF':
            inventory['non_speech_assets'] += 1
            continue
        # Large cinematic metadata is still bounded independently of audio.
        if len(prefix) < min(entry.size, _MAX_METADATA):
            try:
                bindings = wem_bindings(prefix, entry.size)
            except PreparationFailure as error:
                if 'prefix bound' not in str(error):
                    raise
                bindings = wem_bindings(archives.prefix(entry, min(entry.size, _MAX_METADATA)), entry.size)
        else:
            bindings = wem_bindings(prefix, entry.size)
        inventory['wem_files'] += 1
        if not bindings:
            inventory['wem_without_unique_subtitle'] += 1
        for binding in bindings:
            label = binding['label']
            key = label if label in source else guid_keys.get(_guid(label))
            if key is None:
                inventory['labels_without_localization'] += 1
                continue
            if label != key:
                inventory['unique_guid_bindings'] += 1
            voices[key].append({'entry': entry.reference(), 'locale': source_locale, **binding})
    rows = []
    for key, text in source.items():
        if not text:
            continue
        candidates = voices.get(key, [])
        audio = _select_voice(candidates)
        kind = _kind(key, bool(audio and 'start_ms' in audio))
        if kind == 'unclassified' and audio:
            kind = _kind(audio['label'])
        # Authored voice metadata proves unavailable speech; missing metadata
        # proves neither silence nor a spoken line. UI and choices stay unknown.
        state = 'voiced' if audio else 'unavailable' if candidates or kind != 'unclassified' else 'unknown'
        texts = {locale: table[key] for locale, table in tables.items() if table.get(key)}
        rows.append({'text_id': GAME + ':' + key, 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', texts.get('zh-Hant', '')), 'source_locale': source_locale,
            'source_text': text, 'texts': texts, 'audio_locale': source_locale,
            'audio': audio, 'voice_status': state, 'dialogue_kind': kind})
    if not rows:
        raise _format('No official Shadow localization rows were found.')
    if fingerprint(install) != stamp:
        raise PreparationFailure('shadow_files_changed', 'Shadow files changed during preparation. Finish the launcher update and retry; the previous snapshot was retained.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    missing = [target for target, locale in targets.items() if not locale or not any(locale in row['texts'] for row in rows)]
    counts = Counter(row['voice_status'] for row in rows)
    warnings = ['Unbound localization, UI and choice prompts are not proven silent; automatic silent capture remains disabled for these rows.',
        'Immersion-mode neutral/indigenous recordings are not substituted for the selected dubbed language. Region-specific and uninstalled packs have not received native playback verification.',
        'Cinematic clips use authored start/end cues; clips can include the original scene mix. Repeated performances without a unique binding remain unavailable.']
    if not voice_entries:
        warnings.append('The selected original voice pack is missing. Select its official language in the launcher and finish downloading; another language is never substituted.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows, 'missing_translation_locales': missing,
        'coverage_warnings': warnings, 'narrative_inventory': {**inventory, 'archive_files': len(archives.archives),
            'voice_entries': len(voice_entries), 'ambiguous_subtitle_bindings': sum(_select_voice(v) is None for v in voices.values()),
            'isolated_over_scene_mix': sum(bool(_select_voice(v)) and any('start_ms' in c for c in v) and
                                          any('start_ms' not in c for c in v) for v in voices.values()),
            'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in rows)), 'voice_counts': dict(counts)},
        'message': f"{len(rows):,} official {source_locale} text entries; {counts['voiced']:,} verified original voice bindings" +
            ('; install the selected original voice pack' if not voice_entries else '')}


def index_install(install: Path, data_dir: Path, progress=lambda _message: None):
    return index_language(install, data_dir, 'zh-Hans', ['en'], progress)


def _voice_entry(audio):
    locale = audio.get('locale')
    if locale not in SUPPORTED_LOCALES:
        raise ValueError('Invalid original Shadow voice locale')
    try:
        entry = TigerEntry(**audio['entry'])
    except (TypeError, KeyError):
        raise ValueError('Invalid original Shadow voice reference') from None
    if entry.locale != VOICE_MASKS[locale]:
        raise ValueError('Original Shadow voice reference crosses study/audio locales')
    return entry


def _extract(archives, audio, entry):
    data = archives.read(entry, max_bytes=_MAX_VOICE)
    expected = {key: audio[key] for key in ('label', 'start_ms', 'end_ms') if key in audio}
    if not expected.get('label') or expected not in wem_bindings(data, len(data)):
        raise ValueError('Original Shadow subtitle/voice binding changed; refresh game data')
    return data


def extract_voice(install: Path, audio: dict, _executable: Path, _destination: Path) -> bytes:
    entry = _voice_entry(audio)
    return _extract(TigerSet(install, version=5), audio, entry)


def extract_voices(install: Path, audios: list[dict], _executable: Path, _destination: Path) -> list[bytes]:
    if not 1 <= len(audios) <= 8:
        raise ValueError('Original Shadow voice batches require one to eight clips')
    entries = [_voice_entry(audio) for audio in audios]
    if len({audio['locale'] for audio in audios}) != 1:
        raise ValueError('Original Shadow voice batch crosses study/audio locales')
    archives = TigerSet(install, version=5)
    return [_extract(archives, audio, entry) for audio, entry in zip(audios, entries)]
