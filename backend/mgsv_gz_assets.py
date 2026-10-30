"""Ground Zeroes official text and exact original English/Japanese recordings."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

from .fox_dialogue import (bnk_entries, demo_bindings, fpk_entries, fsm_audio,
                          invalid, read_subp, sbp_entries, stp_entries,
                          strcode32, strcode48, wem_labels)
from .mgsv_gz_archive import (GzArchive, GzEntry, archive_paths, fingerprint,
                              fnv32, path_hash, quiz_items, radio_conditions, read_lang, sab_labels, subtitle_events,
                              ui_boot_bindings)
from .preparation_errors import PreparationFailure
from .textmaps import display_text

GAME = 'mgsvgz'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'ja')
TEXT_LOCALES = ('ja', 'en', 'fr', 'it', 'de', 'es-419', 'pt-BR', 'ru')
TEXT_NAMES = dict(zip(TEXT_LOCALES, ('Jpn', 'Eng', 'Fre', 'Ita', 'Ger', 'Spa', 'Por', 'Rus')))
VOICE_NAMES = {'en': 'Eng', 'ja': 'Jpn'}
LANG_NAMES = dict(zip(('jpn', 'eng', 'fra', 'ita', 'deu', 'spa', 'por', 'rus'), TEXT_LOCALES))


def archive_sources(install):
    return archive_paths(install)


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(p) for p in candidates if (Path(p) / 'MgsGroundZeroes.exe').is_file()
                 and (Path(p) / 'data_02.g0s').is_file()), None)


def _pack_path(locale):
    language = VOICE_NAMES[locale]
    return f'/Assets/tpp/pack/ui/subtitles/{language}Voice/{language}Text/e20010_subtitles.fpk'


def _has_pack(archives, locale):
    return path_hash(_pack_path(locale)) in archives.entries


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        archives = GzArchive(install)
        try:
            return 'present' if _has_pack(archives, locale) else 'missing'
        finally:
            archives.close()
    except (OSError, ValueError, PreparationFailure):
        return 'incomplete'


def _kind(group):
    if group == 'tape':
        return 'cassette_tape'
    if group == 'common':
        return 'bark_radio_or_scripted_dialogue'
    return 'mission_dialogue'


def _tables(archives, source_locale, selected, inventory):
    tables, groups, localization, scenes, animations = defaultdict(dict), defaultdict(set), defaultdict(dict), [], {}
    conflicts = set()
    readable_panel, quiz_panel, members = False, False, set()
    radio = set()
    interrogations = set()

    def read_radio(view):
        conditions, count = radio_conditions(view)
        radio.update(conditions)
        inventory['radio_data_files'] += 1
        inventory['radio_groups'] += count

    language_codes = {name: locale for locale, name in TEXT_NAMES.items()}
    for entry in archives.entries.values():
        if entry.extension == 'json' and entry.size <= 4 * 1024 * 1024:
            data = json.loads(archives.view(entry).read())
            if isinstance(data, dict):
                for result in data.get('interrogationResultTable', []):
                    if (isinstance(result, list) and len(result) >= 4
                            and isinstance(result[1], str) and re.fullmatch(r'[a-zA-Z0-9_]+', result[1])):
                        interrogations.add(strcode32(result[1]))
                        inventory['authored_interrogation_results'] += 1
        if entry.extension == 'rdf':
            read_radio(archives.view(entry))
        if entry.extension not in ('fpk', 'fpkd'):
            continue
        for name, _at, view in fpk_entries(archives.view(entry)):
            members.add(name)
            if name.endswith('.rdf'):
                read_radio(view)
            reference = {'archive': entry.reference(), 'member': name}
            if name == '/Assets/tpp/ui/GraphAsset/gz/uig_title_prestory_gz.fox2':
                ui = ui_boot_bindings(view)
                readable_panel = ({'langFile': '/Assets/tpp/lang/ui/gz/gz_backstory.lng'} in ui
                    and {'uiFile': '/Assets/tpp/ui/GraphAsset/gz/title_prestory.uigb', 'pauseFlag': 1} in ui)
            elif name == '/Assets/tpp/ui/GraphAsset/gz/uig_mgs_quiz.fox2':
                quiz_panel = {'uiFile': '/Assets/tpp/ui/GraphAsset/gz/mgs_quiz.uigb', 'pauseFlag': 0} in ui_boot_bindings(view)
            if name.endswith('.fox2'):
                for binding in demo_bindings(view, include_subtitles=True):
                    scenes.append({**binding, **reference})
                    inventory['authored_scene_relations'] += 1
            if name.endswith(('.sani#eng', '.sani#jpn')):
                # Authored localized animation suffix selects original voice timing.
                if name.endswith('#' + ('eng' if source_locale == 'en' else 'jpn')):
                    events = subtitle_events(view)
                    if name in animations and animations[name]['events'] != events:
                        raise invalid('Conflicting Ground Zeroes cinematic subtitle events.')
                    animations[name] = {**reference, 'events': events}
                    inventory['subtitle_event_streams'] += 1
            match = re.search(r'/([A-Za-z]+)Voice/([A-Za-z]+)Text/([^/]+)\.subp$', name)
            if match and match[1] == VOICE_NAMES[source_locale]:
                locale = language_codes.get(match[2])
                inventory['subtitle_packages'] += 1
                if locale not in selected:
                    continue
                encoding = {'ja': 'utf-8', 'pt-BR': 'utf-8', 'ru': 'iso8859-5'}.get(locale, 'latin1')
                for key, item in read_subp(view.read(), encoding).items():
                    pages = [display_text(page) for page in item['pages'] if display_text(page)]
                    if not pages:
                        continue
                    text = ' '.join(pages)
                    row = tables[locale].setdefault(key, {'text': text, 'pages': pages, 'variants': {}})
                    row['variants'][text] = pages
                    if len(row['variants']) > 1:
                        conflicts.add((locale, key))
                    groups[key].add(match[3])
            match = re.search(r'/([^/]+)\.lng#([a-z]{3})$', name)
            if match and (locale := LANG_NAMES.get(match[2])) in selected:
                inventory['localization_tables'] += 1
                for key, variants in read_lang(view.read()).items():
                    # Resource identity prevents collisions between UI tables.
                    identity = (match[1], key)
                    localization[locale].setdefault(identity, set()).update(display_text(text) for text in variants)
    quiz = archives.entries.get(path_hash('/Assets/tpp/level/mission/extra/e20060/e20060_sequence.lua'))
    ui_evidence = {
        'backstory': readable_panel and '/Assets/tpp/ui/GraphAsset/gz/title_prestory.uigb' in members,
        'quiz_choices': quiz_items(archives.view(quiz).read()) if quiz_panel and quiz
                       and '/Assets/tpp/ui/GraphAsset/gz/mgs_quiz.uigb' in members else set()}
    inventory['confirmed_readable_panels'] = int(ui_evidence['backstory'])
    inventory['confirmed_quiz_item_definitions'] = len(ui_evidence['quiz_choices'])
    inventory['authored_interrogation_subtitle_ids'] = len(interrogations)
    return tables, groups, conflicts, localization, scenes, animations, ui_evidence, radio, interrogations


def _media(archives, inventory):
    for entry in archives.entries.values():
        if entry.extension not in ('sbp', 'wem'):
            continue
        root = archives.view(entry)
        if entry.extension == 'wem':
            inventory['loose_wem'] += 1
            yield entry, [], 0, root
            continue
        inventory['soundbank_packages'] += 1
        for kind, package_offset, package in sbp_entries(root):
            inventory[kind + '_packages'] += 1
            if kind not in ('stp', 'bnk'):
                continue
            for media_id, offset, wem in (stp_entries(package) if kind == 'stp' else bnk_entries(package)):
                inventory['streamed_wem' if kind == 'stp' else 'embedded_wem'] += 1
                header = wem.read(0, min(12, wem.size))
                if len(header) < 12 or header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                    inventory['non_riff_media'] += 1
                    continue
                if struct.unpack_from('<I', header, 4)[0] + 8 > wem.size:
                    inventory['embedded_prefetch_fragments'] += 1
                    continue
                chain = [{'kind': kind, 'offset': package_offset, 'size': package.size},
                         {'kind': 'wem', 'id': media_id, 'offset': offset, 'size': wem.size}]
                yield entry, chain, media_id, wem


def _labels(archives, inventory):
    labels = defaultdict(dict)
    for entry in archives.entries.values():
        if entry.extension != 'sbp':
            continue
        for kind, offset, view in sbp_entries(archives.view(entry)):
            if kind != 'sab':
                continue
            for identity, label in sab_labels(view):
                inventory['sab_subtitle_relations'] += 1
                labels[identity][label] = {**entry.reference(), 'sab_offset': offset, 'sab_size': view.size}
    return labels


def _tape_names():
    # PreinstallTape.SetTrack also declares five Japanese-only archive-CD
    # tracks (positive dataTimeJp, zero dataTimeEn in the English edition).
    for prefix in ('tp_20010_01', 'tp_arch_diary_01', 'tp_arch_cd_01', 'tp_chico_00', 'tp_pw_01',
                   'tp_it20030_01', 'tp_it20030_02'):
        for number in range(100):
            yield f'{prefix}_{number:02}'


def _record(identity, texts, pages, locale, audio, kind, status=None):
    return {'text_id': f'{GAME}:{identity}', 'english': texts.get('en', ''), 'chinese': '',
            'source_locale': locale, 'source_text': texts[locale], 'texts': texts,
            'ocr_texts': pages, 'ocr_english': pages.get('en'), 'audio_locale': locale,
            'audio': audio, 'voice_status': status or ('voiced' if audio else 'unavailable'),
            'dialogue_kind': kind}


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Ground Zeroes study/audio locale')
    install = Path(install)
    stamp, inventory = fingerprint(install), Counter()
    archives = GzArchive(install)
    try:
        if not _has_pack(archives, source_locale):
            raise PreparationFailure('mgsvgz_voice_pack_missing',
                'The selected original Ground Zeroes voice edition is not installed. In Steam Properties → Language select English or Japanese, finish its download, then prepare again. Japanese text in the English edition does not supply Japanese audio.')
        if sum(_has_pack(archives, locale) for locale in SUPPORTED_LOCALES) != 1:
            raise invalid('Ground Zeroes contains ambiguous original voice edition markers.')
        targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
        selected = {source_locale, *(locale for locale in targets.values() if locale)}
        progress('Reading Ground Zeroes subtitles, narrative panels and authored cinematic events')
        tables, groups, conflicts, localization, scenes, animations, ui_evidence, radio, interrogations = _tables(archives, source_locale, selected, inventory)
        source, voices = tables[source_locale], defaultdict(list)
        labels = _labels(archives, inventory)
        for number, (entry, chain, media_id, view) in enumerate(_media(archives, inventory)):
            if number % 1000 == 0:
                progress(f'Matching original Ground Zeroes media: {number:,}')
            names = wem_labels(view)
            if not names:
                inventory['media_without_labels'] += 1
            for name in names:
                relations = labels.get(strcode48(name), {})
                if len(relations) != 1:
                    inventory['media_without_unique_sab_relation'] += 1
                    continue
                label, relation = next(iter(relations.items()))
                key = strcode32(label)
                if key not in source:
                    inventory['labels_without_source_subtitle'] += 1
                    continue
                voices[key].append({**entry.reference(), 'chain': chain, 'media_id': media_id,
                    'media_label': name, 'subtitle_label': label, 'subtitle_id': key,
                    'sab_relation': relation, 'locale_name': source_locale,
                    'dialogue_kind': 'interrogation' if key in interrogations else 'radio' if fnv32(label) in radio else _kind(next(iter(sorted(groups[key]))))})
        for name in _tape_names():
            key = strcode32(name)
            entry = archives.entries.get(path_hash(f'/Assets/tpp/sound/external/tape/{name}.wem'))
            if key in source and entry:
                inventory['bound_cassette_tracks'] += 1
                voices[key].append({**entry.reference(), 'performance_name': name,
                    'subtitle_id': key, 'locale_name': source_locale, 'dialogue_kind': 'cassette_tape_full_track',
                    'playback_scope': 'full_track'})
        rows, scene_keys, seen_movies = [], set(), set()
        for binding in scenes:
            entry = archives.entries.get(path_hash(binding['movie']))
            animation_name = binding['subtitle'] + '#' + ('eng' if source_locale == 'en' else 'jpn')
            animation = animations.get(animation_name)
            if not entry or entry.name_hash in seen_movies or not animation or not animation['events']:
                continue
            keys = [event['subtitle_id'] for event in animation['events']]
            if any(key not in source or (source_locale, key) in conflicts for key in keys):
                inventory['scenes_with_unresolved_text'] += 1
                continue
            if fsm_audio(archives.view(entry)) is None:
                inventory['scenes_without_original_audio'] += 1
                continue
            audio = {**entry.reference(), 'locale_name': source_locale, 'dialogue_kind': 'cinematic_full_track',
                     'scene_binding': binding, 'subtitle_events': animation, 'playback_scope': 'full_track'}
            for key in dict.fromkeys(keys):
                pages = {locale: table[key]['pages'] for locale, table in tables.items()
                         if key in table and (locale, key) not in conflicts}
                rows.append(_record(f'scene:{entry.name_hash:016x}:{key:08x}',
                                    {locale: ' '.join(p) for locale, p in pages.items()},
                                    pages, source_locale, audio, 'cinematic_full_track'))
            scene_keys.update(keys)
            seen_movies.add(entry.name_hash)
            inventory['bound_cinematic_streams'] += 1
            inventory['bound_cinematic_events'] += len(keys)
        for key, row in sorted(source.items()):
            kind = 'interrogation' if key in interrogations else _kind(next(iter(sorted(groups[key]))))
            if (source_locale, key) in conflicts:
                for text, pages in sorted(row['variants'].items()):
                    identity = hashlib.sha256(text.encode()).hexdigest()[:16]
                    rows.append(_record(f'sub:{key:08x}:conflict:{identity}', {source_locale: text},
                                        {source_locale: pages}, source_locale, None, kind))
                continue
            texts = {locale: table[key]['text'] for locale, table in tables.items()
                     if key in table and (locale, key) not in conflicts}
            pages = {locale: table[key]['pages'] for locale, table in tables.items() if locale in texts}
            audios = voices.get(key, [])
            if not audios and key in scene_keys:
                continue  # Every source page is already retained with its complete scene.
            for ordinal, audio in enumerate(audios or [None]):
                rows.append(_record(f'sub:{key:08x}:{ordinal}', texts, pages, source_locale, audio,
                                    audio['dialogue_kind'] if audio else kind))
        for (resource, key), variants in sorted(localization[source_locale].items()):
            kind = {'gz_backstory': 'backstory_readable', 'gz_quiz': 'quiz_choice_or_prompt',
                    'gz_end_roll': 'ending_chronology_or_credits'}.get(resource, 'unclassified_localization')
            for text in sorted(variants):
                if not text:
                    continue
                texts = {source_locale: text}
                if len(variants) == 1:
                    texts.update({locale: next(iter(table[(resource, key)])) for locale, table in localization.items()
                                  if len(table.get((resource, key), set())) == 1})
                identity = hashlib.sha256(text.encode()).hexdigest()[:16]
                # Typed UI routes, not failed media lookup, establish these
                # narrative labels. Quiz narration has separate radio events.
                choice = re.fullmatch(r'choice_(\d+)_([1-5])', key)
                unvoiced = (resource == 'gz_backstory' and ui_evidence['backstory']
                            and re.fullmatch(r'backstory_info_00_\d\d', key)) or (
                            resource == 'gz_quiz' and choice and int(choice[1]) in ui_evidence['quiz_choices'])
                rows.append(_record(f'local:{resource}:{key}:{identity}', texts, {}, source_locale, None,
                                    'quiz_choice' if unvoiced and choice else kind,
                                    'unvoiced' if unvoiced else 'unknown'))
        if not source:
            raise invalid('No Ground Zeroes subtitles found for the original voice edition.')
        if fingerprint(install) != stamp:
            raise PreparationFailure('mgsvgz_files_changed', 'Ground Zeroes files changed during preparation. Finish Steam downloads and retry; the previous snapshot was retained.',
                                     game_files_changed=True, previous_snapshot_retained=True)
        counts = Counter(row['voice_status'] for row in rows)
        inventory.update(unique_subtitle_ids=len(source), conflicting_text_ids=len(conflicts),
                         cinematic_streams=sum(e.extension == 'fsm' for e in archives.entries.values()),
                         selected_archive_entries=len(archives.entries),
                         source_conflicting_subtitle_ids=sum(locale == source_locale for locale, _key in conflicts))
        return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'records': rows,
            'missing_translation_locales': [target for target, locale in targets.items() if not locale or not tables.get(locale)],
            'narrative_inventory': {**inventory, 'voice_counts': dict(counts),
                                   'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in rows))},
            'coverage_warnings': [
                'Original bank recordings require both the embedded Wwise label and its exact SAB subtitle relation. Missing or ambiguous recordings are unavailable, never silent.',
                'Cassette tracks retain complete performances and authored OCR pages. Cinematic captions remain separate authored subtitle IDs with their corresponding locale text; their audio plays the complete original scene mix. Scene bindings require the same FOX2 movie/subtitle entity and structured SANI msgId events; no subtitle-length timing cuts are guessed.',
                'Backstory prose is confirmed unvoiced only through the typed paused reading-panel/language-resource relation. Quiz choices require the typed quiz UI and authored item declaration, whose radio prompts are separate. Other localization-only text, quiz questions, ending chronology and credits remain unknown.',
                'Cinematic streams without a resolved authored subtitle relation, unlabeled media and audio without official captions remain explicit gaps.',
                'Authored interrogation results name caption IDs and generic voice events separately. Those event-to-media paths are unresolved; their captions stay unavailable unless an independent exact original-media relation is present.',
                'English received installed-file and representative playback checks. Japanese voice is implemented from its JpnVoice and #jpn schema with synthetic fixtures; its absent voice edition has no native playback claim.',
                'The Japanese voice edition provides English/Japanese text; other translation targets may be missing. Arabic placeholder paths in the English archive do not establish an official PC Arabic localization.',
                'Full-frame matching covers moving caption/panel presentations. Native DPI, window/capture bounds and UI placement require calibration; parsed files do not validate capture geometry.'],
            'message': f"{len(rows):,} official {source_locale} text entries; {counts['voiced']:,} original voice bindings"}
    finally:
        archives.close()


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', ['ja'], progress)


def _member(archives, reference):
    try:
        parent = GzEntry(**reference['archive'])
        return next(child for name, _at, child in fpk_entries(archives.view(parent)) if name == reference['member'])
    except (KeyError, TypeError, StopIteration):
        raise invalid('Ground Zeroes authored metadata reference changed.') from None


def _extract(archives, audio):
    locale = audio.get('locale_name')
    if locale not in SUPPORTED_LOCALES or not _has_pack(archives, locale):
        raise invalid('The Ground Zeroes original voice edition changed; prepare again.')
    try:
        entry = GzEntry(**{key: audio[key] for key in GzEntry.__dataclass_fields__})
    except (KeyError, TypeError):
        raise invalid('Invalid Ground Zeroes original voice reference.') from None
    view = archives.view(entry)
    if 'scene_binding' in audio:
        binding, animation = audio['scene_binding'], audio.get('subtitle_events')
        if (not isinstance(binding, dict) or not isinstance(animation, dict)
                or audio.get('playback_scope') != 'full_track' or audio.get('dialogue_kind') != 'cinematic_full_track'):
            raise invalid('Invalid Ground Zeroes scene reference.')
        relations = demo_bindings(_member(archives, binding), include_subtitles=True)
        expected = {key: binding.get(key) for key in ('entity', 'movie', 'audio_name', 'demo_name', 'subtitle')}
        if (expected not in relations or path_hash(expected['movie']) != entry.name_hash
                or animation.get('member') != expected['subtitle'] + '#' + ('eng' if locale == 'en' else 'jpn')
                or subtitle_events(_member(archives, animation)) != animation.get('events')):
            raise invalid('Ground Zeroes authored scene/subtitle relationship changed.')
        result = fsm_audio(view)
        if result is None:
            raise invalid('Ground Zeroes scene has no original audio.')
        return result.read()
    if 'performance_name' in audio:
        name = audio['performance_name']
        if (name not in set(_tape_names()) or audio.get('dialogue_kind') != 'cassette_tape_full_track'
                or audio.get('playback_scope') != 'full_track'
                or path_hash(f'/Assets/tpp/sound/external/tape/{name}.wem') != entry.name_hash
                or strcode32(name) != audio.get('subtitle_id')):
            raise invalid('Ground Zeroes cassette identity changed.')
        return view.read()
    chain = audio.get('chain')
    if entry.extension == 'wem' and chain == [] and audio.get('media_id') == 0:
        pass  # Standalone media still requires the same exact SAB relation below.
    elif entry.extension == 'sbp' and isinstance(chain, list) and len(chain) == 2 and all(isinstance(step, dict) for step in chain):
        step, media = chain
        view = next((child for kind, offset, child in sbp_entries(view)
                     if kind == step.get('kind') and offset == step.get('offset') and child.size == step.get('size')), None)
        if view is None or step.get('kind') not in ('stp', 'bnk'):
            raise invalid('Ground Zeroes original soundbank package changed.')
        view = next((child for identity, offset, child in (stp_entries(view) if step['kind'] == 'stp' else bnk_entries(view))
                     if identity == audio.get('media_id') == media.get('id') and offset == media.get('offset')
                     and child.size == media.get('size')), None)
    else:
        raise invalid('Invalid Ground Zeroes soundbank reference.')
    if view is None or audio.get('media_label') not in wem_labels(view):
        raise invalid('Ground Zeroes original recording label changed.')
    relation = audio.get('sab_relation', {})
    try:
        parent = GzEntry(**{key: relation[key] for key in GzEntry.__dataclass_fields__})
        sab = next(child for kind, offset, child in sbp_entries(archives.view(parent))
                   if kind == 'sab' and offset == relation['sab_offset'] and child.size == relation['sab_size'])
        expected = (strcode48(audio['media_label']), audio['subtitle_label'])
        if expected not in set(sab_labels(sab)) or strcode32(expected[1]) != audio.get('subtitle_id'):
            raise invalid('Ground Zeroes original subtitle identity changed.')
    except (KeyError, TypeError, StopIteration):
        raise invalid('Ground Zeroes subtitle relation is incomplete.') from None
    return view.read()


def extract_voice(install, audio, _executable, _destination):
    archives = GzArchive(install)
    try:
        return _extract(archives, audio)
    finally:
        archives.close()


def extract_voices(install, audios, _executable, _destination):
    archives = GzArchive(install)
    try:
        return [_extract(archives, audio) for audio in audios]
    finally:
        archives.close()
