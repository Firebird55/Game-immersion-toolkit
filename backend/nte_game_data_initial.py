"""Explicit immutable initial format descriptions, never a current-data feed."""
from pathlib import Path
import hashlib

from . import nte_game_data_content as content
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .game_tools import _atomic_file
from .private_data_paths import _no_links

STAGE = 'nte-initial-descriptions-v1'
HOSTS = frozenset(('raw.githubusercontent.com',))


def descriptions():
    from .nte_publisher import NATIVE_ARCHIVE, NATIVE_LOCALIZATION
    from . import nte_assets as assets, nte_archive_metadata as archive
    return {
        'archive': {'url': f'https://raw.githubusercontent.com/{archive.REPOSITORY}/{NATIVE_ARCHIVE[0]}/{archive.SOURCE_PATH}',
            'sha256': NATIVE_ARCHIVE[1], 'bytes': 78835,
            'target': 'tools/nte-publisher/format/'+NATIVE_ARCHIVE[0]+'-'+NATIVE_ARCHIVE[1]+'.txt'},
        'localization': {'url': f'https://raw.githubusercontent.com/{archive.LOCALIZATION_REPOSITORY}/{NATIVE_LOCALIZATION[0]}/{archive.LOCALIZATION_PATH}',
            'sha256': NATIVE_LOCALIZATION[1], 'bytes': 1544,
            'target': 'tools/nte-publisher/format/'+NATIVE_LOCALIZATION[0]+'-'+NATIVE_LOCALIZATION[1]+'.txt'},
        'seed': {'url': assets.TABLE_SCHEMA_URL, 'sha256': assets.TABLE_SCHEMA_SHA256, 'bytes': 1252093,
            'target': 'tools/nte-publisher/native-seed/'+assets.TABLE_SCHEMA_SHA256+'.usmap'}}


def _retained(cache, spec):
    path = Path(cache)/spec['target']; _no_links(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 8*1024**2:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == spec['sha256']


def _verify(name, row, raw):
    from . import nte_archive_metadata as archive
    from .nte_publisher import NATIVE_ARCHIVE, NATIVE_LOCALIZATION
    if name == 'seed':
        from .nte_native_schema import _seed
        _seed(raw)
    else:
        revision = (NATIVE_ARCHIVE if name == 'archive' else NATIVE_LOCALIZATION)[0]
        load = archive.load if name == 'archive' else archive.load_localization
        load(revision=revision, digest=row['sha256'], fetch=lambda *_a, **_k: raw)


def plan(indices, names, ctx, reader):
    specs = descriptions()
    missing = [name for name in names if not _retained(ctx.cache_directory, specs[name])]
    if not missing:
        return None
    packet = {'schema': STAGE, 'indices': indices, 'descriptions': {name: specs[name] for name in missing}}
    size = sum(row['bytes'] for row in packet['descriptions'].values())
    guards = 2*sum(row['bytes'] for row in indices['verification'].values())
    return GameDataPlan('nte-initial-descriptions-'+content._identity(packet), size+guards, size+128*1024,
        handle=packet, runtime_available=True, download_is_upper_bound=True, stage='initial-descriptions',
        message='Download the fixed initial NTE compatibility information before local preparation.')


def download(plan, ctx, reader, transport):
    packet = plan.handle
    def invalid():
        return GameDataError('nte_initial_description_changed',
            'The initial NTE compatibility information changed. Check the download size again.', 409)
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'indices', 'descriptions'}
            or packet['schema'] != STAGE or plan.stage != 'initial-descriptions'
            or plan.revision != 'nte-initial-descriptions-'+content._identity(packet)):
        raise invalid()
    indices, selected = packet['indices'], packet['descriptions']
    cache, _ = content.validate_handle(indices, ctx, reader)
    specs = descriptions()
    if (not isinstance(selected, dict) or not selected or set(selected)-set(specs)
            or any(row != specs[name] for name, row in selected.items())):
        raise invalid()
    guards = indices['verification']
    total = sum(row['bytes'] for row in selected.values())+2*sum(row['bytes'] for row in guards.values())
    if total != plan.download_bytes:
        raise invalid()
    transferred = 0
    def recheck():
        nonlocal transferred
        for url, row in guards.items():
            ctx.check()
            _, receipt = transport.fetch_bytes(url, kind='metadata', limit=row['bytes'], expected_size=row['bytes'],
                digests={'sha256': row['sha256']})
            transferred += receipt.bytes
    recheck()
    for name, row in selected.items():
        ctx.check()
        data, receipt = transport.fetch_bytes(row['url'], kind='asset', limit=row['bytes'],
            expected_size=row['bytes'], digests={'sha256': row['sha256']})
        _verify(name, row, data)
        with ctx.transfer_lock:
            ctx.check(); target = cache/row['target']; _no_links(target); _atomic_file(target, data); ctx.check()
        transferred += receipt.bytes
    recheck()
    if not all(_retained(cache, row) for row in selected.values()):
        raise invalid()
    ctx.progress('verifying', transferred, total, 'Initial NTE compatibility information verified.')
    return PreparationStage({'schema': STAGE, 'plan_sha256': content._identity(packet),
        'descriptions': {name: row['sha256'] for name, row in selected.items()}, 'transferred_bytes': transferred},
        'Initial NTE compatibility information is downloaded. Check the remaining preparation.')
