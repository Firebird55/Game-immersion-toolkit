"""Prepare authored ZZZ dialogue from one released Global launcher build."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from . import game_tools, hoyo_publisher_voice as voice, sophon_assets as sophon, zzz_assets
from .hoyo_dialogue import voice_namespace
from .languages import audio_locale, resolve_locale
from .prebuilt_node_reader import require_zzz_reader
from .runtime_bundle import discover_layout
from .runtime_paths import voice_work_root
from .voice_assets import voice_hash
from .zzz_assets import TEXT_LOCALES

CHANNEL = 'zzz-global'
BASE = 'ZenlessZoneZero_Data/StreamingAssets/'
SCOPE = ('Publisher preparation covers catalogue-matched dialogue scenes, phone messages, replies, gameplay tips, ongoing dialogue and timed clue recordings. '
         'Other presentations and later in-version overrides have partial coverage.')


def fingerprint():
    return voice.descriptor(sophon.release(CHANNEL))[0]


def stage_scenes(work, cache, files, ranges):
    grouped = defaultdict(list)
    for row in ranges:
        name = row['block']
        if not re.fullmatch(r'Blocks/\d+\.blk', name):
            raise ValueError('Invalid scene block identity.')
        grouped[name].append((row['offset'], row['size']))

    def stage(item):
        name, ranges = item
        asset = files[BASE + name]

        @lru_cache(maxsize=3)
        def chunk(position, length):
            return asset.read(cache, position, length)

        out = work / (name.split('/')[-1] + '.scenes')
        with out.open('xb') as handle:
            for start, length in sorted(ranges):
                if not 0 < length <= 64 * 1024**2 or not 0 <= start <= asset.size - length:
                    raise ValueError('Scene exceeds its released package.')
                end = start + length
                handle.write(struct.pack('<I', length))
                begin = handle.tell()
                for offset, size, *_ in asset.chunks:
                    if offset >= end:
                        break
                    if offset + size > start:
                        handle.write(chunk(offset, size)[max(0, start - offset):min(size, end - offset)])
                if handle.tell() - begin != length:
                    raise ValueError('Incomplete staged scene.')
        return out.name

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(stage, sorted(grouped.items())))


def source_paths(source, version):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', source) or '..' in source:
        return set()
    if '/' in source:
        return {source}
    family = {'galgame': 'VO_GalGame', 'ongoinglevel': 'VO_Ongoing', 'ongoingmaincity': 'VO_Ongoing',
              'ongoing': 'VO_Ongoing', 'level': 'VO_Level', 'accompany': 'VO_Accompany',
              'chessboard': 'VO_Chessboard', 'tips': 'VO_Tips', 'maincity': 'VO_MainCity', 'chat': 'VO_Chat',
              'chatplus': 'VO_ChatPlus', 'chatplustimeline': 'VO_Timeline', 'timeline': 'VO_Timeline',
              'ongoingantique': 'VO_Ongoing'}.get(source.split('_', 1)[0].lower())
    if not family:
        return set()
    # Index membership decides among candidates, including unversioned launch files.
    major, minor, _ = map(int, version.split('.'))
    versions = [f'Ver{i}_{j}/' for i in range(1, major + 1)
                for j in range(1 + minor if i == major else 10)]
    speakers = {s for s in source.split('_')[1:] if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9]+', s)}
    return {f'{family}/{v}VO_{s}/{source}' for v in ['', *versions] for s in speakers}


def _stage_metadata(build, cache, work):
    files = sophon.manifest(cache, CHANNEL, tuple(build['manifests']['game']), ('/data_version', '/res_version', '.blk'))
    batches = {}
    for index, label, pattern in (('data_version', 'design', r'Blocks/Data/(\d+)\.blk'),
                                  ('res_version', 'catalog', r'Blocks/(\d+)\.blk')):
        asset = files[BASE + index]
        rows = json.loads(asset.read(cache, 0, asset.size))['files']
        if not isinstance(rows, list) or not rows:
            raise ValueError('Unsupported ZZZ launcher resource list.')
        selected = {}
        for row in rows:
            name = row['remoteName']
            match = re.fullmatch(pattern, name)
            if label == 'catalog' and (row.get('tags') or not match):
                continue
            if not match:
                raise ValueError('Unknown ZZZ launcher design directory structure.')
            resource = files[BASE + name]
            local = f'{label}-{match[1]}.blk'
            if local in selected or row['fileSize'] != resource.size:
                raise ValueError('ZZZ resource inventory differs from the selected manifest.')
            selected[local] = resource
        if not 0 < len(selected) <= 4096:
            raise ValueError('Unsupported ZZZ launcher catalogue or design selection.')

        def stage(item):
            local, resource = item
            (work / local).write_bytes(resource.read(cache, 0, resource.size))
            return local

        with ThreadPoolExecutor(max_workers=4) as pool:
            batches[label] = list(pool.map(stage, selected.items()))
    return files, batches


def _read_catalogue(build, data_dir, locales, namespace, progress):
    packaged = require_zzz_reader()
    cache = data_dir / 'tools/sophon'
    parent = packaged.work_root if packaged else cache
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='zzz-dialogue-', dir=parent) as tmp:
        work = Path(tmp).resolve()
        files, batches = _stage_metadata(build, cache, work)
        options = {'cwd': work, 'timeout': 1200, 'check': True, 'capture_output': True,
                   'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        script = game_tools.CODE_ROOT / 'scripts/zzz-publisher-dialogue.mjs'
        if packaged:
            options['env'] = packaged.environment()
        else:
            layout = discover_layout()
            project = layout.legacy_project_root if os.environ.get('PROXY_TRANSCRIPT_PROJECT_ROOT') else data_dir.parent.parent
            source = voice_work_root(project) / 'galgame-perform.ts'
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != game_tools.READER_SHA:
                raise ValueError('Prepare the ZZZ reader in Setup before preparing a language.')
            subprocess.run(['node', str(script), 'compile', str(work), str(source)], **options)

        def query(mode, **inputs):
            (work / (mode + '-input.json')).write_text(json.dumps(inputs), encoding='utf-8')
            command = (packaged.publisher_command(mode, work) if packaged else
                       ['node', str(script), mode, str(work), str(work / 'galgame-perform.mjs')])
            subprocess.run(command, **options)
            return json.loads((work / (mode + '-output.json')).read_bytes())

        plan = query('scene-plan', design=batches['design'], catalogs=batches['catalog'])
        progress('Reading the released ZZZ scene ranges and their authored dialogue')
        blocks = stage_scenes(work, cache, files, plan['ranges'])
        coverage = query('catalogue', design=batches['design'], locales=sorted(locales), namespace=namespace, blocks=blocks)
        coverage['scene_paths'] = plan['scenePaths']
        coverage['selected_scene_bytes'] = sum(item['size'] for item in plan['ranges'])
        return (json.loads((work / 'links.json').read_bytes()),
                {locale: json.loads((work / ('texts-' + locale + '.json')).read_bytes()) for locale in locales},
                coverage)


def original_bindings(links, entries, dub, version):
    namespace = voice_namespace('zzz', dub)
    candidates = defaultdict(set)
    for link in links:
        candidates[link['text_id']].add(link['source'])
    result = {}
    by_source = {}
    for identity, sources in candidates.items():
        # Different authored sentence takes under one identity require a selection rule.
        if len(sources) != 1:
            continue
        source, = sources
        if source not in by_source:
            matches = []
            for path in source_paths(source, version):
                full = f'{namespace}/ex/{path}.wem'
                file_id = voice_hash(full)
                if file_id in entries:
                    matches.append({**entries[file_id], 'source': full, 'file_id': f'{file_id:016x}', 'locale': dub})
            by_source[source] = matches[0] if len(matches) == 1 else None
        if by_source[source]:
            result[identity] = by_source[source]
    return result


def build_language(data_dir, source_locale, target_locales, progress):
    build = sophon.release(CHANNEL)
    stamp, raw = voice.descriptor(build)
    game_tools._atomic_file(data_dir / 'tools/sophon/releases' / stamp, raw)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    progress('Reading ZZZ dialogue and translations from the Global PC launcher release')
    dub = audio_locale(source_locale)
    links, tables, coverage = _read_catalogue(build, data_dir, selected, voice_namespace('zzz', dub), progress)
    progress('Matching the selected original ZZZ dub to its released scene and message sources')
    entries = voice.inventory(data_dir, stamp, dub, 'zzz')
    expanded, channels, evidence, kinds = zzz_assets._group_links(links)
    # One caption can be a silent/interactive choice in one scene and spoken in
    # another. This snapshot addresses text IDs, so avoid assigning that sound
    # unless all uses of the selected performance agree on a sentence source.
    consistent = [link for link in expanded if evidence[link['text_id']] == {'unavailable'}]
    bindings = original_bindings(consistent, entries, dub, build['version'])
    for link in links:
        if 'start_ms' in link and (binding := bindings.get(link['text_id'])):
            bindings[link['text_id']] = {**binding, 'start_ms': link['start_ms'], 'end_ms': link['end_ms']}
    rows = zzz_assets._dialogue_records(tables, source_locale, selected, channels, evidence, kinds, bindings)
    if not rows or fingerprint() != stamp:
        raise ValueError('No ZZZ dialogue was prepared or the launcher release changed. Retry preparation.')
    available = {locale for row in rows for locale in row['texts']}
    return {'format': 2, 'game': 'zzz', 'source_locale': source_locale, 'install': None, 'source_mode': 'publisher',
            'fingerprint': stamp, 'metadata_revision': build['build'], 'records': rows, 'coverage': coverage,
            'missing_translation_locales': [target for target, locale in targets.items() if locale not in available],
            'coverage_warnings': [SCOPE], 'message': f"{len(rows):,} Global ZZZ dialogue entries in {source_locale}. {SCOPE}"}
