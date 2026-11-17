"""Context-owned original IoStore metadata; no implicit source acquisition."""
import hashlib
from pathlib import Path

from . import nte_game_data_content as content, nte_game_data_ranges as ranges
from . import nte_publisher_pak as pak, nte_publisher_iostore as io, nte_release as release
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links

STAGE = 'nte-original-global-import-metadata-v1'
MAX_GLOBAL = 16*1024**2


def _failure():
    return GameDataError('nte_import_metadata_unavailable',
        'The original NTE import information could not be verified. Your previous library is retained.', 409)


def _offline(*_args):
    raise GameDataError('nte_original_bytes_missing',
        'Required original NTE data is missing. Check the download size again.', 409)


def containers(handle, ctx, reader, *, inventory_only=False, range_reader=None):
    """Build checked directory metadata without UCAS or PAK source lookups."""
    from .nte_publisher import ROOT, container_context
    sources = ranges._sources(handle, ctx, _offline)
    description = ranges._format(ctx)
    archives = {name: pak.Archive(source, description, oodle=reader.oodle) for name, source in sources.items()}
    current = handle['inventory']
    files = {name: release.File(**row) for name, row in current['files'].items()}
    selected = [name for name in files if name.startswith(ROOT) and name.endswith('.utoc')]
    if not 0 < len(selected) <= 128:
        raise _failure()
    result = {}
    for name in sorted(selected):
        ctx.check()
        if name[:-5]+'.ucas' not in files:
            raise _failure()
        result[name] = io.Container(current['region'], current['branch'], files[name], files[name[:-5]+'.ucas'],
            tuple(archives.values()), Path(ctx.cache_directory)/'tools/nte-publisher/iostore',
            oodle=reader.oodle, range_reader=range_reader or _offline)
    selected = container_context(result)
    if inventory_only:
        for name, source in selected.items():
            if not name.endswith('/global.utoc'):
                source.inventory_metadata_only = True
    return selected


def _global(values):
    chosen = [(name, item) for name, item in values.items() if name.endswith('/global.utoc')]
    if len(chosen) != 1:
        raise _failure()
    name, source = chosen[0]
    if source.paths or not 0 < source.ucas.size <= MAX_GLOBAL:
        raise _failure()
    return name, source


def retained(source):
    path = source.root/'complete.ucas'
    _no_links(path)
    if not path.is_file() or path.stat().st_size != source.ucas.size:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'md5').hexdigest() == source.ucas.digest


def plan(handle, selection, ctx, reader):
    values = containers(handle, ctx, reader)
    name, source = _global(values)
    packet = {'schema': STAGE, 'indices': handle, 'pak_selection': selection, 'global': name}
    identity = content._identity(packet)
    if retained(source):
        from . import nte_game_data_prepare as processing
        return processing.plan(packet, values, ctx, reader)
    guards = 2*sum(row['bytes'] for row in handle['verification'].values())
    return GameDataPlan('nte-global-metadata-'+identity, source.ucas.size+guards, source.ucas.size+128*1024,
        handle=packet, download_is_upper_bound=True, runtime_available=True, stage='global-import-metadata',
        message='Download original NTE import metadata before processing the selected dialogue.')


def download(plan, ctx, reader, transport):
    packet = plan.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'indices', 'pak_selection', 'global'}
            or packet['schema'] != STAGE or plan.stage != 'global-import-metadata'
            or plan.revision != 'nte-global-metadata-'+content._identity(packet)):
        raise _failure()
    handle = packet['indices']; cache, host = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']):
        raise _failure()
    _, pending, selection = ranges._pending(handle, ctx, reader)
    if pending or selection != packet['pak_selection']:
        raise _failure()
    values = containers(handle, ctx, reader)
    name, source = _global(values)
    guards = handle['verification']
    if (name != packet['global'] or retained(source) or
            plan.download_bytes != source.ucas.size+2*sum(row['bytes'] for row in guards.values())):
        raise _failure()
    transferred = 0
    def recheck():
        nonlocal transferred
        for url, row in guards.items():
            ctx.check()
            _, receipt = transport.fetch_bytes(url, kind='metadata', limit=row['bytes'], expected_size=row['bytes'],
                digests={'sha256': row['sha256']})
            transferred += receipt.bytes
    recheck()
    item = source.ucas; owner = item.object_digest+'.'+str(item.object_size)
    url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner[0]+'/'+owner
    with ctx.transfer_lock:
        ctx.check()
        receipt = transport.download_to(url, source.root/'complete.ucas', limit=item.size, expected_size=item.size,
            digests={'md5': item.digest}, kind='asset', original_range=(item.offset, item.size, item.object_size))
        ctx.check()
    transferred += receipt.bytes
    recheck()
    if not retained(source):
        raise _failure()
    ctx.check()
    ctx.progress('verifying', transferred, plan.download_bytes, 'Original NTE import metadata verified.')
    return PreparationStage({'schema': STAGE, 'plan_sha256': content._identity(packet), 'reader': reader.identity,
        'inventory_sha256': content._identity(handle['inventory']), 'pak_selection': selection,
        'toc_md5': source.toc.digest, 'global_md5': source.ucas.digest, 'transferred_bytes': transferred},
        'Original NTE import metadata is downloaded. Check the remaining local processing.')
