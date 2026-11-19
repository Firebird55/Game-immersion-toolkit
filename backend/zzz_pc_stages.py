"""Consented original text stages using the verified compiler-free ZZZ reader."""
from pathlib import Path
import base64
import hashlib
import json
import os
import shutil
import re
import tempfile
import time
from urllib.error import URLError

from . import sophon_assets, zzz_hotfix
from .atomic_files import write_bytes
from .zzz_dialogue_records import (
    LANGUAGE_INDEX_VERSION, SCOPE, TEXT_LOCALES, _dialogue_records, _group_links,
    _omit_requested_audio, voice_namespace,
)
from .zzz_scene_sources import stage_scenes
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage, SnapshotSource, SourceProof
from .languages import audio_locale, resolve_locale
from .language_snapshot import write_payload
from .private_data_paths import MAX_TEXT
from .publisher_transport import PublisherTransport
from .zzz_game_data import _safe
from .zzz_pc_sources import Sources, NeedsFiles, discover

SCHEMA = 'zzz-pc-official-text-v1'
MODES = ('scene-plan', 'presentation-config-plan', 'presentation-owners', 'comic-plan', 'catalogue')
FINAL_METADATA_BYTES = 24 * 1024**2
MAX_OPERATIONS = 32 * 1024**2


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _operation_path(ctx, digest):
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise GameDataError('zzz_stage_changed', 'The ZZZ preparation stage needs a new estimate.', 409)
    return _safe(Path(ctx.cache_directory) / 'zzz-operations' / (digest + '.json'))


def _load_operations(ctx, handle, revision, reader):
    if (not isinstance(handle, dict) or handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json()
            or handle.get('revision') != revision or handle.get('reader') != reader.identity
            or not handle.get('operations')):
        return {'operations': {}, 'source_files': []}
    path = _operation_path(ctx, handle['operations'])
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_OPERATIONS:
        raise GameDataError('zzz_stage_changed', 'The ZZZ preparation inputs are unavailable. Check the next size again.', 409)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != handle['operations']:
        raise GameDataError('zzz_stage_changed', 'The ZZZ preparation inputs failed their checksum.', 409)
    result = json.loads(raw)
    if (result.get('revision') != revision or result.get('reader') != reader.identity
            or result.get('request') != ctx.request.json() or not isinstance(result.get('operations'), dict)
            or set(result['operations']) - set(MODES)):
        raise GameDataError('zzz_stage_changed', 'The ZZZ preparation inputs belong to another selection.', 409)
    return result


def _metadata(sources, inventories):
    files, batches = {}, {'design': [], 'catalog': []}
    for category, pattern in (('design', r'Blocks/Data/(\d+)\.blk'), ('catalog', r'Blocks/(\d+)\.blk')):
        for row in inventories[category]:
            match = re.fullmatch(pattern, row['remoteName'])
            if category == 'catalog' and (row.get('tags') or not match):continue
            if not match:raise GameDataError('zzz_metadata_schema', 'The original ZZZ metadata selection changed.')
            name = category + '-' + match[1] + '.blk'
            if name in files:raise GameDataError('zzz_metadata_schema', 'The original ZZZ metadata has conflicting owners.')
            files[name] = sources.asset(row); batches[category].append(name)
        if not batches[category]:raise GameDataError('zzz_metadata_missing', 'The selected original ZZZ metadata is unavailable.')
    # Scene selectors refer to original resource containers, including packages
    # whose own catalog metadata is tagged as optional.
    blocks = {row['remoteName']: sources.asset(row) for row in inventories['catalog']
              if re.fullmatch(r'Blocks/\d+\.blk', row['remoteName'])}
    return files, batches, blocks


def _mode_inputs(operations):
    if 'scene-plan' not in operations:return 'scene-plan', []
    scene = operations['scene-plan']['output']
    if 'presentation-config-plan' not in operations:
        return 'presentation-config-plan', scene['presentationConfigRoots']
    if 'presentation-owners' not in operations:
        return 'presentation-owners', operations['presentation-config-plan']['output']['ranges']
    if 'comic-plan' not in operations:return 'comic-plan', scene['comics']['ranges']
    return 'catalogue', [*scene['ranges'], *operations['presentation-owners']['output']['cinemaRanges'],
                         *operations['comic-plan']['output']['ranges']]


def _selected(metadata_files, blocks, ranges):
    result = list(metadata_files.values())
    for row in ranges:
        if not isinstance(row, dict) or row.get('block') not in blocks:
            raise GameDataError('zzz_scene_owner', 'An original ZZZ scene has no selected container owner.')
        asset = blocks[row['block']]
        if (type(row.get('offset')) is not int or type(row.get('size')) is not int
                or not 0 < row['size'] <= 64 * 1024**2 or not 0 <= row['offset'] <= asset.size - row['size']):
            raise GameDataError('zzz_scene_owner', 'An original ZZZ scene range leaves its container.')
        result.append(asset)
    return Sources.unique(result)


def _scratch_bytes(files, ranges, locales):
    # The current owned reader emits bounded per-locale JSON. Reserve the
    # staged compressed inputs plus its output cap and atomic snapshot copies.
    return sum(asset.size for asset in files.values()) + sum(row['size'] + 4 for row in ranges) + (len(locales) + 3) * MAX_TEXT


class _BoundFile:
    def __init__(self, sources, asset):self.sources, self.asset, self.size = sources, asset, asset.size
    @property
    def chunks(self):return tuple((offset, min(8 * 1024**2, self.size - offset)) for offset in range(0, self.size, 8 * 1024**2))
    def read(self, _directory, offset, count):return self.sources.read(self.asset, offset, count)


def _query(reader, work, mode, inputs, ctx):
    portable = getattr(reader, 'run_operation', None)
    if portable is not None:
        portable(mode, inputs, work, ctx)
        return _read_operation_output(work, mode)
    import subprocess

    (work / (mode + '-input.json')).write_bytes(encoded(inputs))
    command = reader.publisher_command(mode, work)
    process = subprocess.Popen(command, cwd=work, env=reader.environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    started = time.monotonic()
    try:
        while True:
            ctx.check()
            if time.monotonic() - started > 1200:
                raise GameDataError('zzz_reader_timeout', 'Original ZZZ text preparation took too long. Previous data is kept.')
            try:
                _stdout, _stderr = process.communicate(timeout=.5)
                break
            except subprocess.TimeoutExpired:pass
        if process.returncode:
            raise GameDataError('zzz_reader_source_failed', 'The original ZZZ text could not be read. Previous data is kept.')
        return _read_operation_output(work, mode)
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.communicate(timeout=5)
            except subprocess.TimeoutExpired:process.kill(); process.communicate(timeout=5)


def _read_operation_output(work, mode):
    path = _safe(work / (mode + '-output.json'))
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_TEXT:
        raise GameDataError('zzz_reader_source_failed', 'The original ZZZ text could not be read. Previous data is kept.')
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def _execute(ctx, reader, mode, sources, files, batches, blocks, operation):
    operations = operation['operations']
    work_root = ctx.directory if getattr(reader, 'run_operation', None) is not None else reader.work_root
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='zzz-content-', dir=work_root) as temporary:
        work = Path(temporary).resolve()
        for name, asset in files.items():
            with (work / name).open('xb') as output:
                for offset in range(0, asset.size, 1024**2):
                    ctx.check(); output.write(sources.read(asset, offset, min(1024**2, asset.size - offset)))
        for previous, result in operations.items():
            for side in ('input', 'output'):(work / (previous + '-' + side + '.json')).write_bytes(encoded(result[side]))
        proxy = {zzz_hotfix.BASE + name: _BoundFile(sources, asset) for name, asset in blocks.items()}
        def frames(ranges, extension):return stage_scenes(work, None, proxy, ranges, extension=extension) if ranges else []
        if mode == 'scene-plan':inputs = {'design': batches['design'], 'catalogs': batches['catalog']}
        else:
            scene = operations['scene-plan']['output']
            if mode == 'presentation-config-plan':
                inputs = {'roots': frames(scene['presentationConfigRoots'], 'presentation-roots'), 'catalogs': batches['catalog']}
            elif mode == 'presentation-owners':
                config = operations['presentation-config-plan']['output']
                inputs = {'blocks': frames(config['ranges'], 'presentation-configs'), 'catalogs': batches['catalog'],
                    'keys': scene['timelineKeys'], 'timelineConfigs': config['timelineConfigs'], 'videoConfigs': config['videoConfigs']}
            elif mode == 'comic-plan':
                roots = scene['comics']['ranges']
                inputs = {'roots': frames(roots, 'comic-roots'), 'rootCount': len(roots), 'catalogs': batches['catalog']}
            else:
                owners = operations['presentation-owners']['output']
                selected = {ctx.request.source_locale, *(resolve_locale(locale, TEXT_LOCALES) for locale in ctx.request.target_locales)} - {None}
                inputs = {'design': batches['design'], 'locales': sorted(selected),
                    'namespace': voice_namespace(audio_locale(ctx.request.source_locale)),
                    'blocks': frames(scene['ranges'], 'scenes'), 'comics': frames(operations['comic-plan']['output']['ranges'], 'comics'),
                    'voiceDirectory': (frames(scene['voiceDirectory'], 'voice-directory') if ctx.request.content_mode == 'text-audio' else []),
                    'cinemaTimelines': frames(owners['cinemaRanges'], 'cinema-timelines'),
                    'knownTimelineKeys': [owner['key'] for owner in owners['owners']], 'includeAudio': ctx.request.content_mode == 'text-audio'}
        if mode == 'comic-plan' and not inputs['roots']:result = {'ranges': []}
        else:result = _query(reader, work, mode, inputs, ctx)
        if mode != 'catalogue':return {'input': inputs, 'output': result}
        links = json.loads((work / 'links.json').read_bytes())
        tables = {locale: json.loads((work / ('texts-' + locale + '.json')).read_bytes()) for locale in inputs['locales']}
        stamp = sophon_assets.descriptor(sources.build)[0]
        scene = operations['scene-plan']['output']
        owners = operations['presentation-owners']['output']
        result.update(scene_paths=scene['scenePaths'], comic_paths=scene['comics']['scenePaths'],
                      perform_presentations=scene['performPresentations'], presentation_owners=owners['coverage'])
        result['presentation_owners']['extra_config_references'] = operations['presentation-config-plan']['output']['extraConfigs']
        if ctx.request.content_mode == 'text-audio':
            occurrences = result.pop('cinema_occurrences', [])
            return {'links': links, 'tables': tables, 'coverage': result,
                'cinema_occurrences': occurrences,
                'voice_directory': json.loads((work / 'voice-directory.json').read_bytes()),
                'registry': base64.b64encode((work / 'audio-resource.flex').read_bytes()).decode('ascii')}
        expanded, channels, evidence, kinds = _group_links(links)
        rows = _dialogue_records(tables, ctx.request.source_locale, set(inputs['locales']), channels, evidence, kinds, {})
        _omit_requested_audio(rows, links, expanded, stamp, audio_locale(ctx.request.source_locale))
        result['presentation_owners']['subtitle_audio_acquisition'] = 'omitted-by-request'
        available = {locale for row in rows for locale in row['texts']}
        return {'format': 2, 'game': 'zzz', 'source_locale': ctx.request.source_locale, 'content_mode': 'text',
            'source_mode': 'publisher', 'publisher_region': ctx.request.region, 'install': None, 'fingerprint': stamp,
            'metadata_revision': sources.build['build'] + '/' + sources.build['hotfix']['revisions']['design'],
            'records': rows, 'coverage': result, 'missing_translation_locales': [locale for locale in ctx.request.target_locales
                if resolve_locale(locale, TEXT_LOCALES) not in available],
            'coverage_warnings': [SCOPE], 'message': 'Official ZZZ text prepared without audio acquisition.'}


def plan(ctx, launcher, bootstrap_cache, reader, *, transport_factory=PublisherTransport, codecs=None, crypto=None, verification=None):
    memo = getattr(ctx, 'preparation_memo', {})
    current = memo.get('zzz-current')
    if current is None:
        current = discover(ctx, launcher, bootstrap_cache, transport_factory=transport_factory, crypto=crypto)
        memo['zzz-current'] = current
    revision = sophon_assets.descriptor(current)[0]
    handle = {'schema': SCHEMA, 'game': 'zzz', 'request': ctx.request.json(), 'revision': revision,
              'build': current, 'reader': reader.identity}
    if ctx.request.content_mode == 'text-audio' and codecs is None:
        return GameDataPlan(revision, None, None, handle=handle, runtime_available=False, stage='audio-materialization',
            message='The verified original-audio decoder is unavailable on this device. Text-only preparation is available separately.')
    if ctx.request.source_locale not in ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'):
        return GameDataPlan(revision, None, None, handle=handle, runtime_available=False, stage='study-language',
            message='This ZZZ study language cannot be prepared on this device yet.')
    installed = _same_source(ctx, revision, reader, codecs)
    if installed is not None:
        return GameDataPlan(revision, 0, 0, installed['handle'], runtime_available=True, stage='current', reuse_installed=True)
    previous = getattr(ctx, 'stage_handle', None)
    if (ctx.request.content_mode == 'text' and previous and previous.get('mode') == 'text-confirmation'
            and previous.get('request') == ctx.request.json() and previous.get('revision') == revision
            and previous.get('reader') == reader.identity):
        confirmation = {**handle, 'mode': 'text-confirmation',
                        'candidate_directory': ctx.stage_directory.name, 'candidate': previous['candidate']}
        try:
            candidate = _text_candidate(ctx, confirmation)
            disk = sum(path.stat().st_size for path in (candidate.snapshot_path,
                       candidate.snapshot_path.parent / 'source-receipt.json')) + 1024**2
        except (OSError, ValueError, TypeError, KeyError, GameDataError):
            ctx.check()
        else:
            return GameDataPlan(revision, FINAL_METADATA_BYTES, disk, confirmation, runtime_available=True,
                                download_is_upper_bound=True, stage='zzz-text-confirmation', final_transfer=True,
                                message='Confirm the current publisher update for the saved ZZZ dialogue.')
    if ctx.request.content_mode == 'text-audio':
        from . import zzz_pc_audio
        initial = zzz_pc_audio.plan_inputs(ctx, current, handle, transport_factory=transport_factory, verification=verification)
        if initial is not None:return initial
        audio = zzz_pc_audio.plan_candidate(ctx, current, handle, reader,
            transport_factory=transport_factory, final_metadata_bytes=FINAL_METADATA_BYTES, verification=verification)
        if audio is not None:return audio
    sources = Sources(ctx, current, transport_factory=transport_factory)
    try:inventories = sources.indexes(('design', 'catalog'))
    except NeedsFiles as missing:
        selected, network, disk = sources.quote(missing.files)
        handle.update(mode='indexes', files=selected)
        return GameDataPlan(revision, network, disk, handle=handle, runtime_available=True, stage='publisher-indexes', download_is_upper_bound=True,
            message='Download the selected original ZZZ metadata indexes, then check the next source size.')
    files, batches, blocks = _metadata(sources, inventories)
    previous = getattr(ctx, 'stage_handle', None)
    operation = _load_operations(ctx, previous, revision, reader)
    mode, ranges = _mode_inputs(operation['operations'])
    if mode == 'catalogue' and ctx.request.content_mode == 'text-audio':
        ranges = [*ranges, *operation['operations']['scene-plan']['output']['voiceDirectory']]
    assets = _selected(files, blocks, ranges)
    locales = {ctx.request.source_locale, *(resolve_locale(locale, TEXT_LOCALES) for locale in ctx.request.target_locales)} - {None}
    selected, network, disk = sources.quote(assets, scratch_bytes=_scratch_bytes(files, ranges, locales))
    handle.update(mode=mode, files=selected, operations=previous.get('operations') if previous and operation.get('revision') else None)
    automatic = (getattr(ctx, 'job', None) or {}).get('automatic')
    allowance = FINAL_METADATA_BYTES if mode == 'catalogue' and ctx.request.content_mode == 'text' and not automatic else 0
    handle['source_network_bytes'] = network
    return GameDataPlan(revision, network + allowance, disk, handle=handle, runtime_available=True,
        stage='zzz-' + mode, download_is_upper_bound=True, final_transfer=bool(allowance),
        message=('Prepare the selected original ZZZ text sources. Audio is not included.' if ctx.request.content_mode == 'text'
                 else 'Verify the original dialogue and voice references, then check the selected audio size.'))


def download(ctx, planned, reader, *, transport_factory=PublisherTransport, codecs=None, verification=None, crypto=None):
    handle = planned.handle
    if (handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json()
            or handle.get('reader') != reader.identity or handle.get('revision') != planned.revision
            or sophon_assets.descriptor(handle['build'])[0] != planned.revision):
        raise GameDataError('zzz_stage_changed', 'Check the selected ZZZ text download again.', 409)
    if handle['mode'] == 'text-confirmation':
        candidate = _text_candidate(ctx, handle)
        _verify_current(ctx, handle['build'], planned.revision, transport_factory, crypto=crypto)
        for name in ('textmap.json', 'source-receipt.json'):
            original = _safe(candidate.snapshot_path.parent / name)
            target = _safe(ctx.directory / name)
            ctx.check()
            try:
                os.link(original, target)
            except OSError:
                shutil.copyfile(original, target)
        return restore(ctx, candidate.restore_handle)
    if ctx.request.content_mode == 'text-audio':
        if codecs is None:raise GameDataError('zzz_audio_runtime_missing', 'The verified original-audio decoder is unavailable. Repair the app runtime.', 409)
        if handle['mode'].startswith('audio-'):
            from . import zzz_pc_audio
            return zzz_pc_audio.download(ctx, planned, reader, codecs,
                transport_factory=transport_factory, verify_current=_verify_current, verification=verification, crypto=crypto)
    sources = Sources(ctx, handle['build'], transport_factory=transport_factory)
    if handle['mode'] == 'indexes':
        assets = [sources.index_file(name) for name in ('design', 'catalog')]
        assets = [asset for asset in assets if asset.json() in handle['files']]
        if [asset.json() for asset in Sources.unique(assets)] != handle['files']:
            raise GameDataError('zzz_stage_changed', 'The original ZZZ index selection changed.', 409)
        sources.download(assets)
        return PreparationStage(handle, 'Original ZZZ indexes verified. Check the next download size.')
    # Inputs consumed by the reader were already metadata-authenticated during
    # planning. Losing them cannot authorize a hidden repair connection here.
    index_assets = [sources.index_file(name) for name in ('design', 'catalog')]
    if not all(sources.available(asset) for asset in index_assets):
        raise GameDataError('zzz_stage_changed', 'Original ZZZ metadata is unavailable. Check its size again.', 409)
    inventories = {name: zzz_hotfix.inventory_rows(sources.read(asset, 0, asset.size))
                   for name, asset in zip(('design', 'catalog'), index_assets)}
    files, batches, blocks = _metadata(sources, inventories)
    operation = _load_operations(ctx, handle, planned.revision, reader)
    mode, ranges = _mode_inputs(operation['operations'])
    if mode == 'catalogue' and ctx.request.content_mode == 'text-audio':
        ranges = [*ranges, *operation['operations']['scene-plan']['output']['voiceDirectory']]
    assets = _selected(files, blocks, ranges)
    selected, network, _disk = sources.quote(assets)
    if mode != handle['mode'] or selected != handle['files'] or network > handle['source_network_bytes']:
        raise GameDataError('zzz_stage_changed', 'The selected ZZZ source changed. Check its size again.', 409)
    sources.download(assets, **({'kind': 'audio'} if ctx.request.content_mode == 'text-audio' else {}))
    progress = getattr(ctx, 'progress', None)
    if progress is not None:
        progress('preparing', ctx.consumed, ctx.budget, 'Preparing the downloaded ZZZ dialogue…')
    result = _execute(ctx, reader, mode, sources, files, batches, blocks, operation)
    if mode != 'catalogue':
        operation.update(revision=planned.revision, reader=reader.identity, request=ctx.request.json())
        operation['operations'][mode] = result
        operation['source_files'] = list({encoded(row): row for row in [*operation.get('source_files', []), *selected]}.values())
        raw = encoded(operation)
        if len(raw) > MAX_OPERATIONS:raise GameDataError('zzz_stage_bounds', 'The original ZZZ stage exceeds its supported metadata bound.')
        digest = hashlib.sha256(raw).hexdigest(); path = _operation_path(ctx, digest)
        path.parent.mkdir(parents=True, exist_ok=True); ctx.check(); write_bytes(path, raw, check=ctx.check)
        return PreparationStage({**handle, 'operations': digest}, 'Original ZZZ text stage verified. Check the remaining download size.')
    if ctx.request.content_mode == 'text-audio':
        from . import zzz_pc_audio
        return zzz_pc_audio.save_candidate(ctx, handle, result, reader)
    # Only the final source pointer check may spend the explicitly planned
    # metadata allowance. It has no permission to acquire a newer client key.
    automatic = (getattr(ctx, 'job', None) or {}).get('automatic')
    if not automatic:
        _verify_current(ctx, handle['build'], planned.revision, transport_factory, crypto=crypto)
    destination = _safe(ctx.directory / 'textmap.json')
    write_payload('zzz', result, ctx.request.source_locale, ctx.request.target_locales, destination, check=ctx.check, reader_revision=LANGUAGE_INDEX_VERSION)
    with destination.open('rb') as stream:
        snapshot_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    ctx.check()
    receipt = {'schema': SCHEMA, 'revision': planned.revision, 'build': handle['build'], 'reader': reader.identity,
               'request': ctx.request.json(), 'snapshot_sha256': snapshot_sha, 'reader_revision': LANGUAGE_INDEX_VERSION,
               'source_files': [*operation.get('source_files', []), *selected]}
    raw = encoded(receipt); digest = hashlib.sha256(raw).hexdigest()
    _safe(ctx.directory / 'source-receipt.json').write_bytes(raw)
    result_handle = {'schema': SCHEMA, 'game': 'zzz', 'request': ctx.request.json(), 'revision': planned.revision,
                     'receipt_sha256': digest, 'snapshot_sha256': snapshot_sha}
    if automatic:
        pending = {key: handle[key] for key in ('schema', 'request', 'reader', 'revision')}
        pending.update(mode='text-confirmation', candidate=result_handle)
        return PreparationStage(pending, 'ZZZ dialogue is saved. Confirm the current publisher update to finish.')
    return SnapshotSource(destination, result_handle, SourceProof('official', digest, True))


def _text_candidate(ctx, handle):
    from types import SimpleNamespace

    name = handle.get('candidate_directory')
    if not isinstance(name, str) or re.fullmatch('[a-f0-9]{64}', name) is None or ctx.request.content_mode != 'text':
        raise GameDataError('zzz_stage_changed', 'Check the saved ZZZ dialogue again.', 409)
    candidate = handle['candidate']
    if not isinstance(candidate, dict) or candidate.get('revision') != handle['revision']:
        raise GameDataError('zzz_stage_changed', 'The saved ZZZ dialogue belongs to another update.', 409)
    directory = _safe(Path(ctx.cache_directory) / 'sources' / name)
    return restore(SimpleNamespace(directory=directory, request=ctx.request, check=ctx.check), candidate)


def _same_source(ctx, revision, reader, codecs):
    installed = getattr(ctx, 'installed_source', lambda: None)()
    if installed is None or installed['revision'] != revision:
        return None
    try:
        path = _safe(Path(ctx.cache_directory) / 'sources' / installed['directory'] / 'source-receipt.json')
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_OPERATIONS:
            return None
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != installed['handle'].get('receipt_sha256'):
            return None
        receipt = json.loads(raw)
        if (not isinstance(receipt, dict) or receipt.get('reader') != reader.identity
                or receipt.get('reader_revision', 24) != LANGUAGE_INDEX_VERSION
                or codecs is not None and receipt.get('codecs') != codecs.identity):
            return None
        return installed
    except (OSError, ValueError, GameDataError):
        return None


def _verify_current(ctx, build, revision, transport_factory, *, crypto=None):
    channel = build['channel']
    def official_fetch(url, *, limit):
        (launcher, _, downloader), _, _, _ = sophon_assets.CHANNELS[channel]
        return transport_factory(ctx, hosts={launcher, downloader}).fetch_bytes(url, limit=limit, kind='metadata')[0]
    bootstrap_cache = Path(ctx.cache_directory) / 'zzz-original' / ctx.request.region
    for attempt in range(2):
        ctx.check()
        progress = getattr(ctx, 'progress', None)
        if progress is not None:
            progress('verifying', ctx.consumed, ctx.budget, 'Confirming the current ZZZ publisher update…')
        try:
            latest_launcher = sophon_assets.release(channel, fetch=official_fetch)
            latest = discover(ctx, latest_launcher, bootstrap_cache, transport_factory=transport_factory, crypto=crypto)
            break
        except (URLError, GameDataError) as error:
            if isinstance(error, GameDataError) and error.code != 'metadata_download_interrupted':
                raise
            if attempt:
                raise GameDataError('zzz_update_confirmation_interrupted',
                    'Game files are saved. Publisher confirmation could not finish. Continue to reuse the verified files.', 502) from error
    if sophon_assets.descriptor(latest)[0] != revision:
        raise GameDataError('zzz_publisher_changed', 'The original ZZZ update changed during preparation. Retry; previous data is kept.', 409)


def restore(ctx, handle):
    if (handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json() or ctx.request.content_mode != 'text'):
        raise GameDataError('zzz_restore_selection', 'The prepared ZZZ text belongs to another selection.', 409)
    receipt = _safe(ctx.directory / 'source-receipt.json')
    snapshot = _safe(ctx.directory / 'textmap.json')
    raw = receipt.read_bytes()
    if len(raw) > MAX_OPERATIONS or hashlib.sha256(raw).hexdigest() != handle.get('receipt_sha256'):
        raise GameDataError('zzz_restore_integrity', 'The retained ZZZ source receipt failed validation.')
    source = json.loads(raw)
    with snapshot.open('rb') as stream:digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if (source.get('request') != ctx.request.json() or source.get('revision') != handle.get('revision')
            or sophon_assets.descriptor(source['build'])[0] != handle['revision']
            or digest != source.get('snapshot_sha256') or digest != handle.get('snapshot_sha256')):
        raise GameDataError('zzz_restore_integrity', 'The retained ZZZ text failed validation.')
    ctx.check()
    return SnapshotSource(snapshot, handle, SourceProof('official', handle['receipt_sha256'], True))
