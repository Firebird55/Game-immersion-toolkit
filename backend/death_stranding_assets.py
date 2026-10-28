"""Death Stranding ORIGINAL PC: authored sentences, voices, mail and interviews."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import struct

from .decima_archive import Archive, PackSet, invalid, pack_name, sources
from .decima_dialogue import (SENTENCE, TEXT, SOUND, MAIL, INTERVIEW,
    core_objects, localized_sound, localized_text, readable, sentence)
from .decima_cinematics import SceneReader, scene_bindings
from .preparation_errors import PreparationFailure
from .textmaps import display_text

GAME = 'deathstranding'
LANGUAGE_INDEX_VERSION = 1
TEXT_LOCALES = {'en': 1, 'fr': 2, 'es-ES': 3, 'de': 4, 'it': 5, 'nl': 6,
    'pt-PT': 7, 'zh-Hant': 8, 'ko': 9, 'ru': 10, 'pl': 11, 'ja': 16,
    'es-419': 17, 'pt-BR': 18, 'tr': 19, 'ar': 20, 'zh-Hans': 21,
    'el': 23, 'cs': 24, 'hu': 25}
VOICE_LOCALES = {'en': 'english', 'fr': 'french', 'es-ES': 'spanish',
    'de': 'german', 'it': 'italian', 'pt-PT': 'portuguese', 'ru': 'russian',
    'pl': 'polish', 'ja': 'japanese', 'es-419': 'latamsp', 'pt-BR': 'latampor', 'el': 'greek'}
SUPPORTED_LOCALES = tuple(VOICE_LOCALES)


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    for candidate in candidates:
        path = Path(candidate)
        if (path / 'ds.exe').is_file() and (path / 'data' / pack_name('initial')).is_file():
            return path
    return None


def archive_sources(install):
    return [path for _category, _language, path in sources(install)]


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        for path in archive_sources(install)).encode()).hexdigest()


def probe_voice_pack(install, locale):
    if locale not in VOICE_LOCALES:
        return 'unknown'
    path = Path(install) / 'data' / pack_name('initial', VOICE_LOCALES[locale])
    if not path.is_file():
        return 'missing'
    try:
        return 'present' if Archive(path).entries else 'incomplete'
    except (OSError, ValueError):
        return 'incomplete'


@lru_cache(maxsize=1)
def _packs(install, _stamp):
    return PackSet(Path(install))


class Resources:
    def __init__(self, packs):
        self.packs, self.cache = packs, {}

    def load(self, path):
        if path not in self.cache:
            if len(self.cache) > 8:
                self.cache.clear()
            self.cache[path] = core_objects(self.packs.read(path + '.core'))[0]
        return self.cache[path]

    def get(self, current, reference, expected):
        if reference is None:
            return None
        path, identity = reference
        path = path or current
        if not self.packs.has(path + '.core'):
            return None
        obj = self.load(path).get(identity)
        if obj is None or obj[0] != expected:
            raise invalid('Death Stranding authored resource reference changed.')
        return obj[1]


def _category(path, row=None):
    if '/ds_lines_cutscene/' in path:
        return 'cinematic'
    if row and row['delivery'] == 2:
        return 'radio'
    if '/ds_lines_terminal/' in path:
        return 'terminal_hologram'
    if '/ds_lines_mission/' in path:
        return 'mission'
    if '/ds_lines_npc/' in path:
        return 'npc_dialogue'
    if '/ds_lines_sam/' in path or '/ds_lines_common/' in path:
        return 'ambient_bark'
    return 'dialogue'


def _texts(body, selected, counts):
    native = localized_text(body)
    raw = {locale: native[TEXT_LOCALES[locale]][0] for locale in selected if native[TEXT_LOCALES[locale]][0]}
    readable = {locale: value for locale, value in raw.items() if display_text(value)}
    counts['blank_or_markup_only_localized_fields'] += len(raw) - len(readable)
    return readable


def _record(identity, raw, source, kind, state, audio=None):
    texts = {locale: display_text(text) for locale, text in raw.items()}
    # Preserve authored line/paragraph breaks as additional OCR anchors. The
    # complete resource is retained as the study text and original performance.
    pages = {locale: list(dict.fromkeys(display_text(part) for part in re.split(r'\r?\n|\\n|<br\s*/?>', text)
                                      if display_text(part))) for locale, text in raw.items()}
    return {'text_id': f'{GAME}:{identity}', 'english': texts.get('en', ''), 'chinese': '',
        'source_locale': source, 'source_text': texts[source], 'texts': texts,
        'audio_locale': source, 'audio': audio, 'voice_status': state,
        'dialogue_kind': kind, 'ocr_texts': pages, 'ocr_english': pages.get('en')}


def _binding(resources, path, identity, row, locale):
    body = resources.get(path, row['sound'], SOUND)
    if body is None:
        return None
    source = localized_sound(body).get(VOICE_LOCALES[locale])
    if source is None or not resources.packs.has(source['stream']):
        return None
    return {'core': path, 'sentence': identity, 'locale': locale, **source}


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Death Stranding original study/audio locale')
    install = Path(install)
    stamp = fingerprint(install)
    progress('Reading original Death Stranding archive manifest')
    packs = _packs(str(install.resolve()), stamp)
    resources = Resources(packs)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    paths, links = packs.manifest(with_links=True)
    records, counts, used_texts = [], Counter(), set()
    dialogue_paths = [path for path in paths if path.endswith('/sentences') and (
        path.startswith('localized/sentences/ds_lines_') or path.startswith('localized/sentences/ds_radio_system/'))]
    for number, path in enumerate(dialogue_paths):
        if number % 20 == 0:
            progress(f'Reading Death Stranding sentence resources ({number}/{len(dialogue_paths)})')
        if not packs.has(path + '.core'):
            counts['manifest_sentence_resources_not_installed'] += 1
            continue
        objects = resources.load(path)
        counts['sentence_resources'] += 1
        for identity, (kind, body) in objects.items():
            if kind != SENTENCE:
                continue
            counts['authored_sentences'] += 1
            row = sentence(body)
            text = resources.get(path, row['text'], TEXT)
            if text is None:
                counts['sentences_without_text_reference'] += 1
                continue
            raw = _texts(text, selected, counts)
            if not raw.get(source_locale):
                counts['sentences_without_selected_text'] += 1
                continue
            used_texts.add((row['text'][0] or path, row['text'][1]))
            category = _category(path, row)
            audio = _binding(resources, path, identity, row, source_locale)
            # Cutscenes store speech on separate scene tracks. A null sentence
            # sound never establishes silence, including outside cutscenes.
            state = 'voiced' if audio else 'unavailable' if row['sound'] or category == 'cinematic' else 'unknown'
            if not row['show_subtitles']:
                counts['sentences_subtitles_disabled'] += 1
            records.append(_record('sentence:' + identity, raw, source_locale, category, state, audio))
    groups, cinematic_counts = scene_bindings(packs, links, source_locale, TEXT_LOCALES[source_locale], progress)
    counts.update(cinematic_counts)
    by_id = {row['text_id']: row for row in records if row['dialogue_kind'] == 'cinematic' and not row['audio']}
    grouped, scenes = set(), []
    for audio, sentences in groups:
        members = [by_id[f'{GAME}:sentence:{identity}'] for _path, identity in sentences
                   if f'{GAME}:sentence:{identity}' in by_id]
        if not members:
            continue
        identity = hashlib.sha256((audio['stream'] + audio['uuid']).encode()).hexdigest()[:24]
        raw = {locale: '\n'.join(member['texts'][locale] for member in members if member['texts'].get(locale))
               for locale in selected}
        scene = _record('scene:' + identity, raw, source_locale, 'cinematic', 'voiced', audio)
        scene['member_text_ids'] = [member['text_id'] for member in members]
        scene['ocr_texts'] = {locale: list(dict.fromkeys(page for member in members
            for page in member['ocr_texts'].get(locale, []))) for locale in selected}
        scene['ocr_english'] = scene['ocr_texts'].get('en')
        scenes.append(scene)
        grouped.update(scene['member_text_ids'])
    records = [row for row in records if row['text_id'] not in grouped] + scenes
    counts['cinematic_sentences_bound_to_complete_tracks'] = len(grouped)
    counts['cinematic_records_with_complete_tracks'] = len(scenes)
    for path, expected, category in [('ds/archives/mail_resource', MAIL, 'mail'),
                                     ('ds/archives/interviews_resource', INTERVIEW, 'interview')]:
        progress(f'Reading Death Stranding {category} resources')
        for identity, (kind, body) in resources.load(path).items():
            if kind != expected:
                continue
            counts[category + '_resources'] += 1
            for field, ref in readable(kind, body).items():
                if ref is None:
                    continue
                text = resources.get(path, ref, TEXT)
                if text is None:
                    counts['unresolved_readable_references'] += 1
                    continue
                raw = _texts(text, selected, counts)
                if not raw.get(source_locale):
                    continue
                used_texts.add((ref[0] or path, ref[1]))
                records.append(_record(f'{category}:{identity}:{field}', raw, source_locale, category, 'unvoiced'))
    for path in paths:
        if not (path.startswith('localized/sentences/ds_ui/') and path.endswith('/simpletext')):
            continue
        if not packs.has(path + '.core'):
            counts['manifest_ui_resources_not_installed'] += 1
            continue
        counts['ui_text_resources'] += 1
        for identity, (kind, body) in resources.load(path).items():
            if kind != TEXT or (path, identity) in used_texts:
                continue
            raw = _texts(body, selected, counts)
            if raw.get(source_locale):
                records.append(_record('local:' + identity, raw, source_locale, 'ui_localization', 'unknown'))
    if not records or len({row['text_id'] for row in records}) != len(records):
        raise invalid('Missing or duplicate Death Stranding dialogue identity.')
    if fingerprint(install) != stamp:
        raise PreparationFailure('deathstranding_files_changed',
            'Death Stranding files changed during preparation. Wait for Steam to finish, then retry.',
            game_files_changed=True, previous_snapshot_retained=True)
    counts['manifest_paths'] = len(paths)
    counts['installed_voice_languages'] = len({language for _category, language, _archive in packs.packs if language})
    counts['excluded_trial_sentence_resources'] = sum(path.endswith('/sentences') and path.startswith('localized/sentences/')
        and path not in dialogue_paths for path in paths)
    warnings = [
        'Original 2020 PC edition only. Director’s Cut has different sound resource schemas.',
        'Cinematic subtitle pages resolve through authored flattened sequence events to complete localized scene voice tracks. Playback is the complete original track; subtitle pause frames are not guessed audio cut points. Unresolved or conflicting scenes remain unavailable.',
        'Mail and interview text fields have authored readable-only schemas and use the capture-unvoiced toggle. Other UI localization stays unknown.',
        'Non-subtitled sentences are inventoried; OCR requires visible authored text. Full-frame capture covers subtitles, holograms, radio and scrollable readables; calibrate unusual layouts.',
        'Trial/development sentence resources are excluded. Pack presence is distinct from playback verification; missing recordings remain unavailable.'
    ]
    if probe_voice_pack(install, source_locale) != 'present':
        warnings.append('The selected original voice pack is missing or incomplete. Select the language in Steam, finish the download, verify game files, and prepare again.')
    voiced = sum(row['audio'] is not None for row in records)
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': records, 'narrative_inventory': dict(counts),
        'coverage_warnings': warnings,
        'missing_translation_locales': [target for target, locale in targets.items() if not any(locale in row['texts'] for row in records)],
        'message': f'{len(records):,} official {source_locale} entries; {voiced:,} original voices'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', [], progress)


def _original_wem(data):
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise invalid('Unsupported Death Stranding original voice media.')
    end = struct.unpack_from('<I', data, 4)[0] + 8
    if not 12 <= end <= len(data):
        raise invalid('Truncated Death Stranding original voice media.')
    # Decima stream extents can include a trailer after the authored RIFF.
    # Respect the container's exact length; never edit or trim audio packets.
    return data[:end]


def extract_voice(install, audio, _executable, _destination):
    locale, path, identity = audio.get('locale'), audio.get('core'), audio.get('sentence')
    if locale not in VOICE_LOCALES or not isinstance(path, str):
        raise invalid('Invalid Death Stranding original voice reference.')
    if audio.get('kind') == 'scene':
        if not path.startswith(('levels/', 'ds/')):
            raise invalid('Invalid Death Stranding cinematic sequence path.')
        packs = _packs(str(Path(install).resolve()), fingerprint(install))
        bindings = SceneReader(packs).groups(path, locale, TEXT_LOCALES[locale])
        if not any(binding == audio for binding, _sentences in bindings):
            raise invalid('Death Stranding cinematic binding changed. Refresh game data.')
        data = packs.read(audio['stream'], limit=256 * 1024 * 1024, offset=audio['offset'], length=audio['length'])
        return _original_wem(data)
    if not isinstance(identity, str):
        raise invalid('Invalid Death Stranding sentence identity.')
    if not (path.startswith('localized/sentences/ds_lines_') or path.startswith('localized/sentences/ds_radio_system/')) or not path.endswith('/sentences'):
        raise invalid('Invalid Death Stranding sentence path.')
    resources = Resources(_packs(str(Path(install).resolve()), fingerprint(install)))
    body = resources.get(path, (None, identity), SENTENCE)
    if body is None:
        raise invalid('Death Stranding sentence resource is missing.')
    current = _binding(resources, path, identity, sentence(body), locale)
    if current is None or current != audio:
        raise invalid('Death Stranding original voice binding changed. Refresh game data.')
    data = resources.packs.read(current['stream'], offset=current['offset'], length=current['length'])
    return _original_wem(data)
