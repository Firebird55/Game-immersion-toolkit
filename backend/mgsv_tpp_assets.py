"""MGSV: The Phantom Pain's official subtitles and exact original Wwise media."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
import struct

from .fox_dialogue import (FoxArchive, QarEntry, bnk_entries, demo_bindings, fingerprint,
                          fpk_entries, fsm_audio, invalid, path_hash, read_lang, read_subp, sbp_entries,
                          stp_entries, strcode32, wem_labels)
from .preparation_errors import PreparationFailure
from .textmaps import display_text

GAME = 'mgsvtpp'
LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = ('en', 'ja')
TEXT_LOCALES = ('ja', 'en', 'fr', 'it', 'de', 'es-419', 'pt-BR', 'ru')
TEXT_NAMES = dict(zip(TEXT_LOCALES, ('Jpn', 'Eng', 'Fre', 'Ita', 'Ger', 'Spa', 'Por', 'Rus')))
VOICE_NAMES = {'en': 'Eng', 'ja': 'Jpn'}
# Official pack naming schema, from the public GzsTool path dictionary. This is
# metadata only; text/audio are always read from the user's installed files.
SCENARIOS = ('e20010 e20015 e20020 e20030 e20040 e20050 e20060 e20070 f30010 f30020 f30050 '
             'h40010 h40020 h40050 o50050 result reward s10010 s10020 s10030 s10033 s10036 '
             's10040 s10041 s10043 s10044 s10045 s10050 s10052 s10054 s10070 s10080 s10081 '
             's10082 s10085 s10086 s10090 s10091 s10093 s10100 s10110 s10115 s10120 s10121 '
             's10130 s10140 s10150 s10151 s10156 s10171 s10195 s10200 s10211 s10240 s10260 s10280').split()
RESIDENT_GROUPS = ('child_soldier common common_str enemy_af enemy_af_str enemy_en enemy_en_str '
                   'enemy_ru enemy_ru_str fob radio_cmn_t00 radio_cmn_t01 radio_cmn_t04 '
                   'radio_cmn_t07 radio_free snake tape').split()


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(p) for p in candidates if (Path(p) / 'mgsvtpp.exe').is_file()
                 and (Path(p) / 'master/data1.dat').is_file()), None)


def _subtitle_path(voice, text, group):
    return f'/Assets/tpp/ui/Subtitles/subp/{VOICE_NAMES[voice]}Voice/{TEXT_NAMES[text]}Text/{group}.subp'


def _has_pack(archives, locale):
    return path_hash(_subtitle_path(locale, locale, 'common')) in archives.entries


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        return 'present' if _has_pack(FoxArchive(install), locale) else 'missing'
    except (OSError, ValueError, PreparationFailure):
        return 'incomplete'


def _kind(group):
    if group.startswith('radio'):
        return 'radio'
    if group == 'tape':
        return 'cassette_tape'
    if re.match(r'p\d', group):
        return 'cinematic'
    if group.startswith(('enemy_', 'child_soldier', 'common', 'snake')):
        return 'bark_or_voiced_order'
    if group in ('result', 'reward', 'fob'):
        return 'mission_or_base_dialogue'
    return 'scripted_dialogue'


def _tables(archives, source_locale, selected, inventory, progress):
    tables, groups, conflicts = defaultdict(dict), defaultdict(set), set()
    localization, scene_names, scenes = defaultdict(dict), set(), []
    top_names = {path_hash(_subtitle_path(source_locale, locale, group)): (locale, group)
                 for locale in TEXT_LOCALES for group in (*SCENARIOS, *RESIDENT_GROUPS)}

    def consume(data, group, expected=None):
        legacy = data[:2] == b'\x01L' and expected is not None
        if len(data) < 4 or not legacy and data[1] >= len(TEXT_LOCALES):
            raise invalid('Unsupported TPP subtitle language tag.')
        locale = expected if legacy else TEXT_LOCALES[data[1]]
        if expected and locale != expected:
            raise invalid('TPP subtitle language tag disagrees with its pack.')
        inventory['subtitle_packages'] += 1
        if locale not in selected:
            return
        for key, row in read_subp(data, 'utf-8' if legacy and locale == 'ja' else None).items():
            pages = [display_text(page) for page in row['pages'] if display_text(page)]
            if not pages:
                continue
            text = ' '.join(pages)
            existing = tables[locale].setdefault(key, {'text': text, 'pages': pages, 'timings': row['timings'], 'variants': {}})
            if existing['pages'] != pages or existing['timings'] != row['timings']:
                existing['timings'] = []  # incompatible page layouts cannot align translations
            existing['variants'][text] = pages
            if len(existing['variants']) > 1:
                conflicts.add((locale, key))
            groups[key].add(group)

    for entry in archives.entries.values():
        if entry.extension == 'subp':
            expected, group = top_names.get(entry.name_hash, (None, 'unclassified_subtitle'))
            consume(archives.view(entry).read(), group, expected)
    language_codes = {value.lower(): key for key, value in TEXT_NAMES.items()}
    for number, entry in enumerate(archives.entries.values()):
        if entry.extension not in ('fpk', 'fpkd'):
            continue
        for name, _at, view in fpk_entries(archives.view(entry)):
            if name.endswith('.sand'):
                # SAND names supply the authored scene stem. Only an exact
                # existing FSM path AND exact subtitle ID can bind it later.
                stems = re.findall(r'p\d{2}_\d{6}(?:_\d{3})?', name)
                scene_names.update(stems)
                scene_names.update(stem[:10] for stem in stems)
            if name.endswith('.fox2'):
                for binding in demo_bindings(view):
                    inventory['authored_scene_relations'] += 1
                    scenes.append({**binding, 'archive': entry.reference(), 'member': name})
            if name.endswith('.subp'):
                match = re.search(r'/([A-Za-z]+)Voice/([A-Za-z]+)Text/([^/]+)\.subp$', name)
                if match and match[1] == VOICE_NAMES[source_locale]:
                    locale = language_codes.get(match[2].lower())
                    if locale in selected:
                        consume(view.read(), match[3], locale)
            elif name.endswith(('.lng', '.lng2')):
                match = re.search(r'\.([a-z]{3})\.lng2?$', name)
                locale = language_codes.get(match[1]) if match else None
                if locale in selected:
                    inventory['localization_tables'] += 1
                    localization[locale].update(read_lang(view.read()))
        if number % 3000 == 0:
            progress(f'Inspecting TPP dialogue and localization containers: {number:,}')
    return tables, groups, conflicts, localization, scene_names, scenes


def _tape_names():
    missions = {s[1:] for s in SCENARIOS if s.startswith('s')} | {'10160', '10190', '99060'}
    prefixes = [*(f'tp_m_{mission}' for mission in sorted(missions)), 'tp_c_00000', 'tp_c_00001',
                'tp_20010_01', 'tp_arch_diary_01', 'tp_chico_00', 'tp_pw_01', 'tp_sp_01']
    for prefix in prefixes:
        for number in range(100):
            yield f'{prefix}_{number:02}'
    yield 'tp_m_10115_0a'
    yield 'tp_it20030_01_01'
    yield 'tp_it20030_02_01'


def _named_performances(archives, source, scene_names, scenes, inventory):
    for name in _tape_names():
        key = strcode32(name)
        entry = archives.entries.get(path_hash(f'/Assets/tpp/sound/external/tape/{name}.wem'))
        if key in source and entry:
            inventory['bound_cassette_tracks'] += 1
            yield key, entry, name, 'cassette_tape', None
    bound = set()
    authored_movies = {path_hash(binding['movie']) for binding in scenes}
    for binding in scenes:
        entry = archives.entries.get(path_hash(binding['movie']))
        # audioPath is the authored original audio identifier in the same
        # DemoData entity as demoStreamPath, including renamed movie variants.
        name = binding['audio_name'] or binding['demo_name']
        key = strcode32(name)
        if key not in source or not entry or (key, entry.name_hash) in bound:
            continue
        if fsm_audio(archives.view(entry)) is not None:
            inventory['bound_cinematic_streams'] += 1
            inventory['bound_authored_scene_relations'] += 1
            bound.add((key, entry.name_hash))
            yield key, entry, Path(binding['movie']).stem, 'cinematic', {**binding, 'subtitle_name': name}
    for name in sorted(scene_names):
        key = strcode32(name)
        entry = archives.entries.get(path_hash(f'/Assets/tpp/demo/demo_stream/{name}.fsm'))
        if key in source and entry and entry.name_hash not in authored_movies:
            if fsm_audio(archives.view(entry)) is not None:
                inventory['bound_cinematic_streams'] += 1
                bound.add((key, entry.name_hash))
                yield key, entry, name, 'cinematic', None


def _media(archives, inventory):
    """Enumerate every installed SBP bank, streamed/embedded media and loose WEM."""
    for entry in archives.entries.values():
        if entry.extension not in ('sbp', 'wem', 'bnk'):
            continue
        root = archives.view(entry)
        if entry.extension == 'wem':
            inventory['loose_wem'] += 1
            yield entry, [], 0, root
            continue
        packages = [('bnk', 0, root)] if entry.extension == 'bnk' else sbp_entries(root)
        if entry.extension == 'sbp':
            inventory['soundbank_packages'] += 1
        for kind, package_offset, package in packages:
            if kind not in ('stp', 'bnk'):
                inventory[f'{kind}_packages'] += 1
                continue
            inventory[f'{kind}_packages'] += 1
            for media_id, offset, wem in (stp_entries(package) if kind == 'stp' else bnk_entries(package)):
                inventory['streamed_wem' if kind == 'stp' else 'embedded_wem'] += 1
                if kind == 'bnk':
                    header = wem.read(0, min(12, wem.size))
                    if len(header) < 12 or header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                        inventory['embedded_non_riff_media'] += 1
                        continue
                    if struct.unpack_from('<I', header, 4)[0] + 8 > wem.size:
                        # Wwise banks also hold prefetch fragments for external
                        # streams. These are not independently playable clips.
                        inventory['embedded_prefetch_fragments'] += 1
                        continue
                chain = [] if entry.extension == 'bnk' else [{'kind': kind, 'offset': package_offset, 'size': package.size}]
                chain.append({'kind': 'wem', 'id': media_id, 'offset': offset, 'size': wem.size})
                yield entry, chain, media_id, wem


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported The Phantom Pain study/audio locale')
    install = Path(install)
    stamp = fingerprint(install)
    archives = FoxArchive(install)
    if not _has_pack(archives, source_locale):
        raise PreparationFailure('mgsvtpp_voice_pack_missing',
            'The selected original voice edition is not installed. In Steam Properties → Language select English or Japanese, finish the download, and prepare again. Japanese subtitles in the English edition are not a Japanese voice pack.')
    if sum(_has_pack(archives, locale) for locale in SUPPORTED_LOCALES) != 1:
        raise invalid('TPP contains multiple voice-edition markers; the original audio edition is ambiguous.')
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    inventory = Counter()
    tables, groups, conflicts, localization, scene_names, scenes = _tables(archives, source_locale, selected, inventory, progress)
    voices = defaultdict(list)
    source = tables[source_locale]
    progress('Matching every installed TPP soundbank and standalone recording to official subtitle IDs')
    for number, (entry, chain, media_id, view) in enumerate(_media(archives, inventory)):
        if number % 1000 == 0:
            progress(f'Checking TPP original recordings: {number:,}')
        labels = wem_labels(view)
        if not labels:
            inventory['media_without_subtitle_label'] += 1
        for label in labels:
            candidates = {strcode32(value) for value in (label, label.lower())} & source.keys()
            if len(candidates) != 1:
                inventory['labels_without_source_subtitle'] += 1
                continue
            key, = candidates
            if key != strcode32(label):
                inventory['case_normalized_subtitle_labels'] += 1
            reference = {**entry.reference(), 'chain': chain, 'media_id': media_id,
                         'subtitle_label': label, 'subtitle_id': key, 'locale_name': source_locale}
            if entry.name_hash == path_hash('/Assets/tpp/sound/asset/radio_all.sbp'):
                reference['dialogue_kind'] = 'radio'
            voices[key].append(reference)
    for key, entry, name, kind, binding in _named_performances(archives, source, scene_names, scenes, inventory):
        voices[key].append({**entry.reference(), 'chain': [], 'media_id': 0,
                            'performance_name': name, 'subtitle_id': key,
                            **({'scene_binding': binding} if binding else {}),
                            'locale_name': source_locale, 'dialogue_kind': kind})
    inventory['cinematic_streams'] = sum(e.extension == 'fsm' for e in archives.entries.values())
    rows = []
    for key, row in sorted(source.items()):
        categories = sorted({_kind(group) for group in groups[key]})
        kind = categories[0] if len(categories) == 1 else 'multiple_dialogue_channels'
        if (source_locale, key) in conflicts:
            # Different authored text under one hash cannot establish either
            # audio or translation identity. Preserve every source variant.
            for text, pages in sorted(row['variants'].items()):
                identity = hashlib.sha256(text.encode()).hexdigest()[:16]
                rows.append({'text_id': f'{GAME}:sub:{key:08x}:conflict:{identity}',
                    'english': text if source_locale == 'en' else '', 'chinese': '',
                    'source_locale': source_locale, 'source_text': text, 'texts': {source_locale: text},
                    'ocr_texts': {source_locale: pages}, 'ocr_english': pages if source_locale == 'en' else None,
                    'audio_locale': source_locale, 'audio': None, 'voice_status': 'unavailable',
                    'dialogue_kind': kind, 'channels': categories})
            continue
        texts = {locale: table[key]['text'] for locale, table in tables.items()
                 if key in table and (locale, key) not in conflicts}
        texts[source_locale] = row['text']
        audios = voices.get(key, [])
        for ordinal, audio in enumerate(audios or [None]):
            full_track = bool(audio and (len(row['pages']) > 1 or audio.get('performance_name')))
            original = {**audio, 'playback_scope': 'full_track'} if full_track else audio
            for page_index, page in enumerate(row['pages']):
                localized = {source_locale: page}
                timings = row['timings']
                timing = timings[page_index] if len(timings) == len(row['pages']) else None
                for locale, table in tables.items():
                    target = table.get(key)
                    if locale == source_locale or locale not in texts or not target:
                        continue
                    if len(row['pages']) == len(target['pages']) == 1:
                        localized[locale] = target['pages'][0]
                    elif timing and timing[0] < timing[1] and len(target['timings']) == len(target['pages']):
                        # Match the exact authored subtitle interval, never guess
                        # translations by page number or language word count.
                        hits = [text for text, interval in zip(target['pages'], target['timings']) if interval == timing]
                        if len(hits) == 1:
                            localized[locale] = hits[0]
                category = audio.get('dialogue_kind', kind) if audio else kind
                rows.append({'text_id': f'{GAME}:sub:{key:08x}:{ordinal}:page:{page_index}', 'english': localized.get('en', ''),
                    'chinese': '', 'source_locale': source_locale, 'source_text': page, 'texts': localized,
                    'ocr_texts': {locale: [text] for locale, text in localized.items()}, 'ocr_english': [localized['en']] if 'en' in localized else None,
                    'audio_locale': source_locale, 'audio': original, 'voice_status': 'voiced' if audio else 'unavailable',
                    'dialogue_kind': category + '_full_track' if full_track else category, 'channels': categories})
    for key, text in sorted(localization[source_locale].items()):
        text = display_text(text)
        if text:
            texts = {locale: display_text(table[key]) for locale, table in localization.items() if key in table}
            rows.append({'text_id': f'{GAME}:local:{key:08x}', 'english': texts.get('en', ''), 'chinese': '',
                         'source_locale': source_locale, 'source_text': text, 'texts': texts,
                         'audio_locale': source_locale, 'audio': None, 'voice_status': 'unknown',
                         'dialogue_kind': 'unclassified_localization'})
    if not rows:
        raise invalid('No TPP subtitles were found for the selected original voice edition.')
    if fingerprint(install) != stamp:
        raise PreparationFailure('mgsvtpp_files_changed', 'TPP files changed during preparation. Finish Steam downloads and retry; the previous snapshot was retained.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    counts = Counter(row['voice_status'] for row in rows)
    inventory.update(conflicting_text_ids=len(conflicts), unique_subtitle_ids=len(source),
                     source_conflicting_subtitle_ids=sum(locale == source_locale for locale, _key in conflicts))
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows,
        'missing_translation_locales': [target for target, locale in targets.items() if not locale or not tables.get(locale)],
        'narrative_inventory': {**inventory, 'voice_counts': dict(counts),
                                'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in rows))},
        'coverage_warnings': [
            'Each authored subtitle page keeps its own current-line identity. Translations require matching authored intervals or a single-page performance. Full original performances are labelled; subtitle timing units are not guessed into audio cuts.',
            'Missing recordings, conflicting text IDs and unlabeled audio are not evidence of silence. No subtitle is marked confirmed unvoiced.',
            'Original audio uses authored Wwise labels (including lowercase subtitle-key normalization), exact cassette/cinematic identifiers, or the original audioPath and demoStreamPath in one FOX2 DemoData entity. Cinematics retain the original scene mix, including music and effects.',
            'Unbound scene mixes, recordings without official subtitles and localization-only UI/readables remain unavailable or unknown. Never treat these rows as confirmed silent.',
            'Scene variants bind through verified FOX2 movie/audio relations where available. Remaining movie streams without an established subtitle identity are inventoried; filenames and event hashes are never guessed into matches.',
            'The selected voice edition can intentionally contain Russian, Afrikaans and other character speech. This follows the original edition and does not imply a complete dub in those languages.',
            'Only the installed English edition has received native validation. Japanese uses evidenced JpnVoice paths and the same subtitle/audio schemas; install its official Steam edition before preparation.',
            'Metal Gear Online is a separate executable and content tree; its dialogue is not included in the TPP adapter.'],
        'message': f"{len(rows):,} official {source_locale} text entries; {counts['voiced']:,} original voice bindings"}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', ['ja'], progress)


def _extract(archives, audio):
    locale = audio.get('locale_name')
    if locale not in SUPPORTED_LOCALES or not _has_pack(archives, locale):
        raise invalid('The original TPP voice edition changed; prepare the selected language again.')
    try:
        entry = QarEntry(**{key: audio[key] for key in QarEntry.__dataclass_fields__})
    except (KeyError, TypeError):
        raise invalid('Invalid TPP original voice reference.') from None
    view = archives.view(entry)
    performance = audio.get('performance_name')
    if performance is not None:
        if not isinstance(performance, str) or not re.fullmatch(r'[a-z0-9_]+', performance):
            raise invalid('Invalid TPP performance name.')
        kind = audio.get('dialogue_kind')
        path = (f'/Assets/tpp/sound/external/tape/{performance}.wem' if kind == 'cassette_tape'
                else f'/Assets/tpp/demo/demo_stream/{performance}.fsm' if kind == 'cinematic' else '')
        subtitle_name = performance
        if 'scene_binding' in audio:
            binding = audio['scene_binding']
            if kind != 'cinematic' or not isinstance(binding, dict):
                raise invalid('Invalid TPP authored scene reference.')
            try:
                parent = QarEntry(**binding['archive'])
                member = next(child for name, _offset, child in fpk_entries(archives.view(parent)) if name == binding['member'])
                relation = next(item for item in demo_bindings(member) if item['entity'] == binding['entity'])
            except (KeyError, TypeError, StopIteration):
                raise invalid('The TPP authored scene relationship is missing.') from None
            subtitle_name = relation['audio_name'] or relation['demo_name']
            if relation['movie'] != path or subtitle_name != binding.get('subtitle_name'):
                raise invalid('The TPP scene movie and original audio relationship changed.')
        if not path or path_hash(path) != entry.name_hash or strcode32(subtitle_name) != audio.get('subtitle_id'):
            raise invalid('TPP named performance does not match its subtitle identity.')
        if kind == 'cinematic':
            view = fsm_audio(view)
        if view is None:
            raise invalid('TPP cinematic has no original audio stream.')
        return view.read()
    chain = audio.get('chain')
    if not isinstance(chain, list) or len(chain) > 2:
        raise invalid('Invalid TPP soundbank reference.')
    container_kind = entry.extension
    for step in chain:
        if container_kind == 'sbp':
            match = next((child for kind, offset, child in sbp_entries(view)
                          if kind == step.get('kind') and offset == step.get('offset') and child.size == step.get('size')), None)
            container_kind = step.get('kind')
        elif container_kind in ('bnk', 'stp'):
            match = next((child for media_id, offset, child in (bnk_entries(view) if container_kind == 'bnk' else stp_entries(view))
                          if media_id == step.get('id') and media_id == audio.get('media_id')
                          and offset == step.get('offset') and child.size == step.get('size')), None)
            container_kind = 'wem'
        else:
            raise invalid('Invalid TPP original media path.')
        if match is None:
            raise invalid('TPP original media changed; prepare its index again.')
        view = match
    label = audio.get('subtitle_label')
    if (container_kind != 'wem' or not isinstance(label, str) or label not in wem_labels(view)
            or audio.get('subtitle_id') not in {strcode32(label), strcode32(label.lower())}):
        raise invalid('TPP original audio no longer matches its subtitle identity.')
    return view.read()


def extract_voice(install, audio, _executable, _destination):
    archives = FoxArchive(install)
    try:
        return _extract(archives, audio)
    finally:
        archives.close()


def extract_voices(install, audios, _executable, _destination):
    archives = FoxArchive(install)
    try:
        return [_extract(archives, audio) for audio in audios]
    finally:
        archives.close()
