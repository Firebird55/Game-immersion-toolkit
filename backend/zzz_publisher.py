"""Prepare authored ZZZ dialogue from one released Global launcher build."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from tempfile import TemporaryDirectory

from . import game_tools, hoyo_publisher_voice as voice, sophon_assets as sophon, zzz_assets, zzz_hotfix
from .hoyo_dialogue import voice_namespace
from .languages import audio_locale, resolve_locale
from .prebuilt_node_reader import require_zzz_reader
from .publisher_regions import REGIONS, selected_region
from .runtime_bundle import discover_layout
from .runtime_paths import voice_work_root
from .zzz_source_bindings import VOICE_DIRECTORIES, _short_id, original_bindings, source_paths, voice_directory
from .zzz_dialogue_records import SCOPE, TEXT_LOCALES, _omit_requested_audio
from .zzz_scene_sources import stage_scenes
from . import zzz_publisher_cinematics as cinema

CHANNELS = {'global': 'zzz-global', 'cn': 'zzz-cn'}
BASE = 'ZenlessZoneZero_Data/StreamingAssets/'
@lru_cache(maxsize=2)
def _poll(region, _period):
    return voice.descriptor(zzz_hotfix.discover(sophon.release(CHANNELS[region])))[0]


def fingerprint(region='global'):
    return _poll(region, int(time.monotonic() // 30))


def _stage_metadata(build, cache, work):
    files = sophon.manifest(cache, build['channel'], tuple(build['manifests']['game']), ('revision', '/data_version', '/res_version', '.blk'))
    inventories = None
    if 'hotfix' in build:
        files, inventories = zzz_hotfix.metadata_files(cache, build, files)
    batches = {}
    for index, label, pattern in (('data_version', 'design', r'Blocks/Data/(\d+)\.blk'),
                                  ('res_version', 'catalog', r'Blocks/(\d+)\.blk')):
        if inventories is not None:
            rows = inventories[label]
        else:
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


def _read_catalogue(build, data_dir, locales, namespace, progress, *, include_audio=True):
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
        progress('Reading original ZZZ timeline and movie configuration ownership')
        presentation_roots = stage_scenes(work, cache, files, plan['presentationConfigRoots'], extension='presentation-roots')
        presentation_plan = query('presentation-config-plan', roots=presentation_roots, catalogs=batches['catalog'])
        presentation_blocks = stage_scenes(work, cache, files, presentation_plan['ranges'], extension='presentation-configs')
        presentation_owners = query('presentation-owners', blocks=presentation_blocks, catalogs=batches['catalog'],
                                    keys=plan['timelineKeys'], timelineConfigs=presentation_plan['timelineConfigs'],
                                    videoConfigs=presentation_plan['videoConfigs'])
        progress('Reading original ZZZ film subtitle tracks and whole-voice event ownership')
        cinema_timelines = stage_scenes(work, cache, files, presentation_owners['cinemaRanges'], extension='cinema-timelines')
        progress('Reading the released ZZZ scene ranges and their authored dialogue')
        comic_plan = plan['comics']
        comic_roots = comic_plan['ranges']
        selected = []
        if comic_roots:
            progress('Reading the released ZZZ motion-comic dictionary manifests')
            roots = stage_scenes(work, cache, files, comic_roots, extension='comic-roots')
            selected = query('comic-plan', roots=roots, rootCount=len(comic_roots), catalogs=batches['catalog'])['ranges']
        blocks = stage_scenes(work, cache, files, plan['ranges'])
        comics = stage_scenes(work, cache, files, selected, extension='comics')
        directory = (stage_scenes(work, cache, files, plan['voiceDirectory'], extension='voice-directory')
                     if include_audio else [])
        coverage = query('catalogue', design=batches['design'], locales=sorted(locales), namespace=namespace,
                         blocks=blocks, comics=comics, voiceDirectory=directory,
                         cinemaTimelines=cinema_timelines,
                         knownTimelineKeys=[owner['key'] for owner in presentation_owners['owners']],
                         includeAudio=include_audio)
        coverage['comic_paths'] = comic_plan['scenePaths']
        coverage['selected_comic_bytes'] = sum(item['size'] for item in [*comic_roots, *selected])
        coverage['scene_paths'] = plan['scenePaths']
        coverage['perform_presentations'] = plan['performPresentations']
        coverage['presentation_owners'] = presentation_owners['coverage']
        coverage['presentation_owners']['extra_config_references'] = presentation_plan['extraConfigs']
        coverage['presentation_owners']['subtitle_audio_acquisition'] = 'partial-subtitle-tracks; original audio unresolved'
        coverage['selected_cinema_timeline_bytes'] = sum(item['size'] for item in presentation_owners['cinemaRanges'])
        coverage['selected_scene_bytes'] = sum(item['size'] for item in plan['ranges'])
        if include_audio and 'hotfix' in build:
            coverage['auxiliary_update_resources'] = zzz_hotfix.silence_evidence(cache, build)
        return (json.loads((work / 'links.json').read_bytes()),
                {locale: json.loads((work / ('texts-' + locale + '.json')).read_bytes()) for locale in locales},
                coverage, json.loads((work / 'voice-directory.json').read_bytes()),
                cinema.audio_registry((work / 'audio-resource.flex').read_bytes()) if include_audio else {})


def build_language(data_dir, source_locale, target_locales, progress, *, content_mode='text-audio'):
    # The legacy language worker keeps its original audio behavior. The native
    # per-game provider passes its explicit request, whose default is text.
    if content_mode not in {'text', 'text-audio'}:
        raise ValueError('Choose ZZZ text or text and audio before preparation.')
    include_audio = content_mode == 'text-audio'
    region = selected_region(data_dir / 'tools', 'zzz')
    build = zzz_hotfix.discover(sophon.release(CHANNELS[region]))
    stamp, raw = voice.descriptor(build)
    game_tools._atomic_file(data_dir / 'tools/sophon/releases' / stamp, raw)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    progress('Reading ZZZ dialogue and translations from the ' + REGIONS[region] + ' PC publisher release')
    dub = audio_locale(source_locale)
    options = {} if include_audio else {'include_audio': False}
    links, tables, coverage, directory, registry = _read_catalogue(
        build, data_dir, selected, voice_namespace('zzz', dub), progress, **options)
    expanded, channels, evidence, kinds = zzz_assets._group_links(links)
    # One caption can be a silent/interactive choice in one scene and spoken in
    # another. This snapshot addresses text IDs, so avoid assigning that sound
    # unless all uses of the selected performance agree on a sentence source.
    bindings, contexts = {}, {}
    if include_audio:
        progress('Matching the selected original ZZZ dub to its released scene and message sources')
        entries = voice.inventory(data_dir, stamp, dub, 'zzz')
        consistent = [link for link in expanded if evidence[link['text_id']] == {'unavailable'}]
        bindings = original_bindings(consistent, entries, dub, build['version'], voice_directory(directory))
        progress('Resolving original ZZZ film events through the selected publisher voice banks')
        contexts = cinema.bindings(data_dir, stamp, dub, links, registry)
    for identity, binding in contexts.items():
        bindings.setdefault(identity, binding)
    coverage['cinema_context_recordings'] = len({audio['event'] for audio in contexts.values()})
    coverage['cinema_context_subtitle_bindings'] = len(contexts)
    if include_audio and 'presentation_owners' in coverage:
        coverage['presentation_owners']['subtitle_audio_acquisition'] = 'partial-subtitle-tracks-and-original-film-contexts'
    for link in links:
        if 'start_ms' in link and (binding := bindings.get(link['text_id'])):
            bindings[link['text_id']] = {**binding, 'start_ms': link['start_ms'], 'end_ms': link['end_ms']}
    rows = zzz_assets._dialogue_records(tables, source_locale, selected, channels, evidence, kinds, bindings)
    if not include_audio:
        _omit_requested_audio(rows, links, expanded, stamp, dub)
    if not rows or voice.descriptor(zzz_hotfix.discover(sophon.release(CHANNELS[region])))[0] != stamp:
        raise ValueError('No ZZZ dialogue was prepared or the launcher release changed. Retry preparation.')
    available = {locale for row in rows for locale in row['texts']}
    return {'format': 2, 'game': 'zzz', 'source_locale': source_locale, 'install': None, 'source_mode': 'publisher',
            'publisher_region': region, 'content_mode': content_mode,
            'fingerprint': stamp, 'metadata_revision': build['build'] +
                ('/' + build['hotfix']['revisions']['design'] if 'hotfix' in build else ''),
            'records': rows, 'coverage': coverage,
            'missing_translation_locales': [target for target, locale in targets.items() if locale not in available],
            'coverage_warnings': [SCOPE, 'Movie and timeline subtitle coverage is incomplete. '
                'Their configured references are inventoried separately from verified current dialogue.'],
            'message': f"{len(rows):,} {REGIONS[region]} ZZZ dialogue entries in {source_locale}. {SCOPE}"}
