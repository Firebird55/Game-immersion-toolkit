"""Half-Life 2 anniversary campaigns: official captions and Source performances.

The base game and episodes retain separate caption namespaces and voice mounts.
Shared English archives never satisfy a selected localized voice request.
"""
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct

from .preparation_errors import PreparationFailure
from .source_formats import invalid, keyvalues
from .source_dialogue import (SourceFiles, caption_pages, captions, clean_caption,
    decode_performance, pack_performance, reference_signature, resolve_sequence,
    sound_events, steam_language, text_table)
from .source_scene import caption_sequences, scene_image
# Source retained this exact HUD-message grammar and entity KeyValues syntax.
# Only Source BSP v19/v20 files from the explicit HL2 mounts are read below.
from .goldsrc_formats import entities, titles

GAME = 'halflife2'
LANGUAGE_INDEX_VERSION = 1
BASE_VOICE_LOCALES = ('en', 'fr', 'de', 'it', 'ko', 'es-ES', 'ru')
SUPPORTED_LOCALES = (*BASE_VOICE_LOCALES, 'zh-Hans', 'zh-Hant', 'th')
TEXT_LOCALES = dict(zip(
    ('en', 'fr', 'de', 'it', 'ko', 'es-ES', 'ru', 'zh-Hans', 'zh-Hant', 'nl',
     'da', 'fi', 'ja', 'no', 'pl', 'pt-PT', 'sv', 'th', 'bg', 'cs', 'el', 'hu',
     'pt-BR', 'ro', 'es-419', 'tr', 'uk'),
    ('english', 'french', 'german', 'italian', 'koreana', 'spanish', 'russian',
     'schinese', 'tchinese', 'dutch', 'danish', 'finnish', 'japanese', 'norwegian',
     'polish', 'portuguese', 'swedish', 'thai', 'bulgarian', 'czech', 'greek',
     'hungarian', 'brazilian', 'romanian', 'latam', 'turkish', 'ukrainian')))
CAMPAIGNS = {
    'hl2': {'stem': 'hl2', 'parents': (), 'voices': BASE_VOICE_LOCALES, 'appid': 220},
    'episodic': {'stem': 'ep1', 'parents': ('hl2',), 'voices': SUPPORTED_LOCALES, 'appid': 380},
    'ep2': {'stem': 'ep2', 'parents': ('episodic', 'hl2'),
            'voices': ('en', 'fr', 'de', 'es-ES', 'ru'), 'appid': 420},
}


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(value) for value in candidates if (Path(value) / 'hl2.exe').is_file()
                 and (Path(value) / 'hl2/gameinfo.txt').is_file()
                 and (Path(value) / 'hl2/hl2_pak_dir.vpk').is_file()), None)


def _campaigns(install):
    return [mount for mount, spec in CAMPAIGNS.items()
            if (Path(install) / mount / (spec['stem'] + '_pak_dir.vpk')).is_file()]


def archive_sources(install):
    install, result = Path(install), set()
    for mount, spec in CAMPAIGNS.items():
        for directory in (mount, *(mount + '_' + name for name in (*TEXT_LOCALES.values(), 'korean'))):
            root = install / directory
            for path in root.glob('*.vpk'):
                if path.name.startswith((spec['stem'] + '_pak', spec['stem'] + '_sound_vo_',
                                         'hl2_misc', 'hl2_sound_misc')) and path.is_file():
                    result.add(path)
        root = install / mount
        for pattern in ('resource/closecaption_*.txt', 'resource/closecaption_*.dat',
                        f'resource/{mount}_*.txt', 'scripts/*.txt', 'scenes/*.image', 'maps/*.bsp'):
            result.update(path for path in root.glob(pattern) if path.is_file())
        if (root / 'gameinfo.txt').is_file():
            result.add(root / 'gameinfo.txt')
        manifest = install.parent.parent / f"appmanifest_{spec['appid']}.acf"
        if manifest.is_file():
            result.add(manifest)
    return sorted(result)


def fingerprint(install):
    install = Path(install)
    return hashlib.sha256('|'.join(
        f'{path.relative_to(install).as_posix() if path.is_relative_to(install) else path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
        for path in archive_sources(install)).encode()).hexdigest()


def _files(install, campaign):
    mounts = (campaign, *CAMPAIGNS[campaign]['parents'])
    return SourceFiles(install, [f"{mount}/{CAMPAIGNS[mount]['stem']}_pak_dir.vpk" for mount in mounts]
                       + ['hl2/hl2_misc_dir.vpk'], mounts)


def _voices(install, campaign, locale):
    if locale not in CAMPAIGNS[campaign]['voices']:
        return SourceFiles(install, [])
    native, archives = TEXT_LOCALES[locale], []
    shared_english = locale == 'en' and any(steam_language(install, appid) == 'english'
        for appid in (220, CAMPAIGNS[campaign]['appid']))
    for mount in (campaign, *CAMPAIGNS[campaign]['parents']):
        if locale not in CAMPAIGNS[mount]['voices']:
            continue
        stem = CAMPAIGNS[mount]['stem']
        for language in ((native, 'korean') if locale == 'ko' else (native,)):
            archives += [f'{mount}/{stem}_sound_vo_{language}_dir.vpk',
                         f'{mount}_{language}/{stem}_sound_vo_{language}_dir.vpk',
                         f'{mount}_{language}/{stem}_pak_dir.vpk']
        if shared_english:
            archives.append(f'{mount}/{stem}_pak_dir.vpk')
    if shared_english:
        archives.append('hl2/hl2_sound_misc_dir.vpk')
    return SourceFiles(install, archives)


def _binding(campaign, token, sequence, voices, locale, full_track=False):
    if not sequence or len(sequence) > 64:
        return None
    parts = []
    for member, at_ms in sequence:
        ref = voices.locate(member)
        if not ref:
            return None
        archive = next((item for item in voices.archives if item.path == voices.install / ref['archive']), None)
        entry = archive.entries[member] if archive else None
        if entry is None:
            return None
        if entry.length and entry.archive != 0x7FFF:
            chunk = archive.path.with_name(archive.path.name[:-8] + f'_{entry.archive:03d}.vpk')
            if not chunk.is_file() or chunk.stat().st_size < entry.offset + entry.length:
                return None
        parts.append({'member': member, 'at_ms': at_ms, **ref})
    result = {'campaign': campaign, 'token': token, 'locale': locale, 'parts': parts}
    if full_track:
        result['playback_scope'] = 'full_track'
    result['binding_hash'] = reference_signature(result)
    return result


@lru_cache(maxsize=10)
def _probe(install, locale, _stamp):
    incomplete = False
    for campaign in _campaigns(install):
        voices = _voices(install, campaign, locale)
        sample = next((name for name in voices.entries if name.startswith('sound/vo/')
                       and name.endswith(('.wav', '.mp3'))), None)
        if sample:
            if _binding(campaign, 'probe', ((sample, 0),), voices, locale):
                return 'present'
            incomplete = True
    return 'incomplete' if incomplete else 'missing'


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    try:
        return _probe(str(install), locale, fingerprint(install))
    except (OSError, ValueError):
        return 'incomplete'


def _context(files):
    events, missing = sound_events(files)
    scenes = scene_image(files.read('scenes/scenes.image'), string_encoding='cp1252') if files.locate('scenes/scenes.image') else {}
    return events, caption_sequences(scenes), len(scenes), missing


def _nonverbal(raw):
    return '<sfx>' in raw.casefold() or bool(re.fullmatch(r'(?:\[[^\]]+\]|\*[^*]+\*)', clean_caption(raw)))


def _kind(token):
    if token.startswith('#commentary'):
        return 'commentary'
    if token.startswith(('breencast.', 'npc_metropolice.', 'npc_combine.', 'overwatch.', 'hev')):
        return 'radio'
    if token.startswith(('npc_', 'ep_01.alyx_npc_', 'ep_02.al_npc_')):
        return 'ambient'
    return 'subtitle'


def _row(identity, texts, locale, audio, kind, status=None):
    return {'text_id': f'{GAME}:{identity}', 'english': texts.get('en', ''),
            'chinese': texts.get('zh-Hans', ''), 'source_locale': locale,
            'source_text': texts[locale], 'texts': texts, 'audio_locale': locale,
            'audio': audio, 'voice_status': status or ('voiced' if audio else 'unavailable'),
            'dialogue_kind': kind}


def _map_entities(path):
    with Path(path).open('rb') as stream:
        header = stream.read(1036)
        if len(header) != 1036 or header[:4] != b'VBSP' or struct.unpack_from('<I', header, 4)[0] not in (19, 20):
            raise invalid('Unsupported Half-Life 2 BSP header.')
        offset, size, version, compressed = struct.unpack_from('<4I', header, 8)
        if offset < 1036 or not 0 < size <= 16 * 1024 * 1024 or offset + size > Path(path).stat().st_size or version or compressed:
            raise invalid('Half-Life 2 map entity lump exceeds its bounds or uses an unsupported encoding.')
        stream.seek(offset)
        return entities(stream.read(size))


def _readables(install, campaign, files, ui, locale, diagnostics):
    """Authored HUD titles/map text, never texture OCR or spoken-text inference."""
    records, seen = [], set()
    authored = titles(files.read('scripts/titles.txt')) if files.locate('scripts/titles.txt') else {}
    # Chapter and game-over blocks have explicit text-only HUD behavior. Ignore
    # unused testing/credit placeholders in the same legacy title resource.
    items = [('title:' + token, value['text']) for token, value in authored.items()
             if re.fullmatch(r'(?:ep[12]_)?chapter\d+_title|gameover_[a-z_]+', token)]
    pattern = {'hl2': r'd[123]_[a-z0-9_]+', 'episodic': r'ep1_[a-z0-9_]+', 'ep2': r'ep2_[a-z0-9_]+'}[campaign]
    for path in sorted((Path(install) / campaign / 'maps').glob('*.bsp')):
        if not path.stat().st_size or not re.fullmatch(pattern, path.stem):
            continue
        if not path.resolve().is_relative_to(Path(install).resolve()):
            raise invalid('Half-Life 2 map escaped the installation.')
        try:
            rows = _map_entities(path)
        except PreparationFailure:
            diagnostics['unsupported_map_readables'] += 1
            continue
        diagnostics['maps_inspected'] += 1
        for number, entity in enumerate(rows):
            kind, message = entity.get('classname'), entity.get('message', '')
            if kind in {'game_text', 'point_message'} and message:
                # A direct localized token may omit # in old maps.
                token = message.lstrip('#').casefold()
                if any(token in table for table in ui.values()):
                    message = '#' + token
                items.append((f'map:{path.stem}:{number}', message))
            elif kind == 'env_message' and message.casefold() not in authored:
                diagnostics['unresolved_hud_messages'] += 1
    for identity, raw in items:
        if raw.startswith('#'):
            token = raw[1:].casefold()
            texts = {language: clean_caption(table[token]) for language, table in ui.items()
                     if table.get(token) and clean_caption(table[token])}
        else:
            texts = {'en': clean_caption(raw)} if clean_caption(raw) else {}
        if locale not in texts:
            continue
        signature = json.dumps(texts, sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        records.append(_row(f'{campaign}:{identity}', texts, locale, None, 'readable', 'unvoiced'))
    diagnostics['text_only_hud_entries'] += len(records)
    return records


def _coalesce(records):
    """Inherited identical performances share one OCR identity across campaigns."""
    result, seen = [], {}
    for row in records:
        audio = row.get('audio')
        signature = json.dumps([row['voice_status'], row['texts'], row['dialogue_kind'],
                                audio and [audio['locale'], audio['parts'], audio.get('playback_scope')]], sort_keys=True)
        if signature in seen:
            seen[signature].setdefault('member_text_ids', []).append(row['text_id'])
        else:
            seen[signature] = row
            result.append(row)
    return result


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Half-Life 2 spoken language')
    install, records, diagnostics, coverage = Path(install), [], Counter(), {}
    stamp = fingerprint(install)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {'en', source_locale, *(locale for locale in targets.values() if locale)}
    available_text, warnings = set(), []
    for campaign in _campaigns(install):
        files, voices = _files(install, campaign), _voices(install, campaign, source_locale)
        tables, ui, counts, matched = {}, {}, Counter(), set()
        for locale in sorted(selected):
            native = TEXT_LOCALES[locale]
            if files.locate(f'resource/closecaption_{native}.txt') and files.locate(f'resource/closecaption_{native}.dat'):
                tables[locale] = captions(files, native)
            # Engine UI tables inherit base, then the active campaign.
            for mount in reversed((campaign, *CAMPAIGNS[campaign]['parents'])):
                path = f'resource/{mount}_{native}.txt'
                if files.locate(path):
                    ui.setdefault(locale, {}).update(text_table(files.read(path), native))
        available_text.update(tables)
        if source_locale not in tables:
            warnings.append(f'{campaign}: selected-language captions are missing; finish the official Steam language download and verify files.')
            continue
        progress(f'Reading Half-Life 2 {campaign} {source_locale} captions and original scenes')
        events, sequences, scene_count, missing = _context(files)
        counts.update({'caption_tokens': len(tables[source_locale]), 'sound_events': len(events),
                       'scenes': scene_count, 'missing_sound_scripts': len(missing)})
        start = len(records)
        for token, raw in tables[source_locale].items():
            if _nonverbal(raw):
                counts['excluded_sound_effect_captions'] += 1
                continue
            pages = {locale: caption_pages(table[token]) for locale, table in tables.items() if token in table}
            if not pages.get(source_locale):
                continue
            sequence = resolve_sequence(token, events, sequences)
            full_track = len(pages[source_locale]) > 1
            audio = _binding(campaign, token, sequence, voices, source_locale, full_track)
            matched.update(member for member, _time in sequence)
            if not sequence:
                counts['unresolved_caption_bindings'] += 1
            elif len(sequence) > 1:
                counts['timed_composite_captions'] += 1
            for page, text in enumerate(pages[source_locale]):
                texts = {locale: values[page] for locale, values in pages.items()
                         if len(values) == len(pages[source_locale])}
                kind = _kind(token) + ('_full_track' if full_track else '')
                identity = f'{campaign}:caption:{token}' + (f':page:{page}' if full_track else '')
                records.append(_row(identity, texts, source_locale, audio, kind))
        records.extend(_readables(install, campaign, files, ui, source_locale, counts))
        counts.update(Counter(row['voice_status'] for row in records[start:]))
        counts['voices_without_resolved_caption'] = sum(
            member.startswith(('sound/vo/', 'sound/commentary/', 'sound/npc/metropolice/vo/',
                               'sound/npc/combine_soldier/vo/', 'sound/npc/overwatch/', 'sound/hl1/fvox/'))
            and member.endswith(('.wav', '.mp3')) and member not in matched for member in voices.entries)
        if files.locate('scripts/sentences.txt'):
            # Runtime sentence words, pitch controls and virtual random tokens
            # are not prose and do not establish an exact recorded utterance.
            counts['sentence_definitions'] = sum(bool(re.match(rb'[A-Za-z][A-Za-z0-9_]*\s+', line))
                for line in files.read('scripts/sentences.txt').splitlines())
        coverage[campaign] = dict(counts)
        diagnostics.update(counts)
        if counts['unsupported_map_readables']:
            warnings.append(f"{campaign}: {counts['unsupported_map_readables']} map entity resources could not be decoded; their HUD/readable text is not covered. Verify game files in Steam.")
    if source_locale not in available_text:
        raise PreparationFailure('missing_voice_pack', 'Half-Life 2 captions are missing. Select the official language in Steam Properties → Language, finish the download and verify game files.')
    records = _coalesce(records)
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'Half-Life 2 files changed during preparation. Finish the Steam update and retry.', game_files_changed=True)
    states = Counter(row['voice_status'] for row in records)
    warnings += [
        'Coverage is Half-Life 2 plus installed Episode One and Episode Two anniversary campaigns. Lost Coast, Half-Life: Source, Deathmatch, mods and custom overrides are separate products and are not silently indexed as Half-Life 2.',
        'Base-game voices: English, French, German, Italian, Korean, Spanish (Spain), Russian. Episode One additionally advertises Simplified/Traditional Chinese and Thai; Episode Two advertises English, French, German, Russian and Spanish (Spain). Regional episode packs require their own official files.',
        'Localized captions alone never establish a dub. Shared English commentary and episode recordings are bound only for English with a completed Steam language manifest; other languages need independently identified localized archives.',
        'Randomized barks, dynamic Combine/Overwatch radio sentences, HEV sample assemblies and obsolete captions without a unique authored recording remain unavailable, never unvoiced.',
        'Scripted conversations, in-engine cinematics, Breencast screens, recorded radio and ambient speech share caption/sound/scene bindings. Source text retains each authored caption identity rather than joining future scene dialogue.',
        'Text-only HUD chapter/game-over titles and map messages use the unvoiced capture toggle. Some authored map messages may be dormant/debug content; file inspection does not prove in-game visibility.',
        'Use full-frame matching or independent calibration for the commentary panel, center-screen titles and movable HUD. Texture signs/posters, in-world documents, startup movies and unsubtitled speech have no resolved native text/audio binding here.']
    if not states['voiced']:
        warnings.insert(0, f'Install the official {source_locale} voice pack for its supported Half-Life 2 campaign in Steam Properties → Language, finish the download and verify files. English audio is never substituted.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
            'fingerprint': stamp, 'reader_revision': LANGUAGE_INDEX_VERSION, 'records': records,
            'diagnostics': dict(diagnostics), 'campaign_coverage': coverage, 'coverage_warnings': warnings,
            'missing_translation_locales': [target for target, locale in targets.items() if locale not in available_text],
            'message': f"{states['voiced']:,} official {source_locale} entries with original audio; {states['unvoiced']:,} text-only HUD entries; {states['unavailable']:,} unavailable voices"}


def index_install(install, data_dir, progress=lambda _: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, _destination):
    locale, campaign, token = audio.get('locale'), audio.get('campaign'), audio.get('token')
    if locale not in SUPPORTED_LOCALES or campaign not in CAMPAIGNS or not isinstance(token, str):
        raise invalid('Invalid Half-Life 2 original voice reference.')
    files, voices = _files(install, campaign), _voices(install, campaign, locale)
    events, sequences, _count, _missing = _context(files)
    table = captions(files, TEXT_LOCALES[locale])
    raw = table.get(token)
    expected = _binding(campaign, token, resolve_sequence(token, events, sequences), voices, locale,
                        bool(raw and len(caption_pages(raw)) > 1))
    if raw is None or expected is None or expected != audio:
        raise invalid('Half-Life 2 original voice binding changed; refresh game data.')
    return pack_performance([voices.read_ref(part) for part in expected['parts']])


decode_voice_source = decode_performance
