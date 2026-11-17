"""Context-owned original native/index stage, before any archive/media reads.

Complete files have manifest-owned ranges and full MD5 checks. This stage is
not a prepared library: authenticated archive block planning follows separately.
"""
from dataclasses import asdict
import hashlib
from pathlib import Path

from . import nte_release as release, nte_updater_source as updater
from . import nte_updater_baseline as initial, nte_native_baseline as baseline
from . import nte_native_metadata as metadata
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links


STAGE = 'nte-original-indices-v1'
MAX_NATIVE = 768*1024**2
MAX_INDEX = 64*1024**2


def _failure():
    return GameDataError('nte_original_indices_unavailable',
        'The original NTE download information is incomplete or incompatible. Your previous library is retained.', 409)


def _identity(value):
    return hashlib.sha256(updater._json(value)).hexdigest()


def _target(cache, spec):
    relative = spec['target']
    if not isinstance(relative, str) or not relative or '\\' in relative or '..' in Path(relative).parts:
        raise _failure()
    target = Path(cache)/relative
    _no_links(target)
    if not target.is_relative_to(cache) or target == Path(cache):
        raise _failure()
    return target


def _retained(cache, spec):
    path = _target(cache, spec)
    item = release.File(**spec['file'])
    if not path.is_file() or path.stat().st_size != item.size:
        return False
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'md5').hexdigest() != item.digest:
            return False
    if spec.get('sha256'):
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != spec['sha256']:
                return False
    return True


def _spec(region, branch, item, target, *, sha256=None, host=None):
    return {'region': region, 'branch': branch, 'file': asdict(item), 'target': target,
            **({'sha256': sha256} if sha256 else {}), **({'host': host} if host else {})}


def _selection(current, historical, host):
    from .nte_native_provider import _order
    old = [(name, item) for name, item in metadata.sources(historical).items()
           if item.digest == baseline.BASELINE['native_md5'] and item.size == baseline.BASELINE['native_size']]
    if len(old) != 1:
        raise _failure()
    lineage, old_native = old[0]
    candidates = metadata.sources(current)
    order = _order(candidates, lineage)
    if not order or candidates[order[0]].size > MAX_NATIVE:
        raise _failure()
    selected = candidates[order[0]]
    prefix = 'tools/nte-publisher/'
    result = [_spec(historical['region'], historical['branch'], old_native,
                    prefix+'native-baseline/originals/'+old_native.digest+'.native',
                    sha256=baseline.BASELINE['native_sha256'])]
    if (selected.digest, selected.size) != (old_native.digest, old_native.size):
        result.append(_spec(current['region'], current['branch'], selected,
                      prefix+'native-originals/'+selected.digest+'.native', host=host))
    files = {name: release.File(**row) for name, row in current['files'].items()}
    content = 'Client/WindowsNoEditor/HT/Content/'
    for name, item in sorted(files.items()):
        if not name.startswith(content):
            continue
        if name.endswith('.sig'):
            if not 0 < item.size <= MAX_INDEX:
                raise _failure()
            archive = files.get(name[:-4]+'.pak')
            if archive is None:
                raise _failure()
            target = prefix+'ranges/'+current['region']+'/'+archive.digest+'/'+item.digest+'/checksums.sig'
        elif name.endswith('.utoc'):
            if not 0 < item.size <= MAX_INDEX:
                raise _failure()
            archive = files.get(name[:-5]+'.ucas')
            if archive is None:
                raise _failure()
            folder = prefix+'iostore/'+current['region']+'/'+item.digest+'/'+archive.digest+'/'
            target = folder+'index.utoc'
        else:
            continue
        result.append(_spec(current['region'], current['branch'], item, target, host=host))
    if len(result) > 512 or len({item['target'] for item in result}) != len(result):
        raise _failure()
    return result


def plan(request, ctx, inputs, reader, transport):
    ctx.check()
    cache = Path(ctx.cache_directory)
    format_cache = cache/'tools/nte-publisher/format'
    verification = {}
    def fetch(url, *, limit):
        raw, _ = transport.fetch_bytes(url, limit=limit, kind='metadata')
        identity = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if url in verification and verification[url] != identity:
            raise _failure()
        verification[url] = identity
        return raw
    updater.recheck(inputs, fetch=fetch)
    host, branch = updater.release_origin(inputs, format_cache)
    approval = {}
    found_branch, version, files, sections = release.discover('nte-global', fetch=fetch,
        official_cache=format_cache, metadata_out=approval, initial_branch=branch, host=host)
    current = metadata.inventory({'region': 'nte-global', 'branch': found_branch, 'version': version,
                                  'files': files, 'sections': sections})
    historical = baseline.discover(cache/'tools/nte-publisher/native-baseline', fetch=fetch,
                                    parameters=initial.parameters(format_cache))
    specs = _selection(current, historical, host)
    missing = [spec for spec in specs if not _retained(cache, spec)]
    handle = {'schema': STAGE, 'request': request.json(), 'inputs': inputs.description(),
              'reader': reader.identity, 'inventory': current, 'updater': approval,
              'files': specs, 'verification': verification}
    identity = _identity(handle)
    if not missing:
        return GameDataPlan('nte-archive-blocks-'+identity, None, None, handle=handle, stage='content',
            message='Original NTE indexes are verified. A bounded archive-block preparation plan is still required.')
    payload = sum(spec['file']['size'] for spec in missing)
    checks = sum(item['bytes'] for item in verification.values())
    return GameDataPlan('nte-indices-'+identity, payload+2*checks, payload+128*1024,
        handle=handle, download_is_upper_bound=True, runtime_available=True, stage='original-indices',
        message='Download original NTE indexes and format metadata, then check the selected text and audio size.')


def download(plan, ctx, reader, transport):
    handle = plan.handle
    if (not isinstance(handle, dict) or handle.get('schema') != STAGE
            or set(handle) != {'schema', 'request', 'inputs', 'reader', 'inventory', 'updater', 'files', 'verification'}
            or plan.stage != 'original-indices' or plan.revision != 'nte-indices-'+_identity(handle)
            or handle['request'] != ctx.request.json() or handle['reader'] != reader.identity):
        raise _failure()
    inputs = updater._inputs(handle['inputs'])
    cache = Path(ctx.cache_directory)
    format_cache = cache/'tools/nte-publisher/format'
    current = metadata.inventory(handle['inventory'])
    receipt = updater.check_reference(handle['updater'], format_cache,
        original={**{key: current[key] for key in ('region', 'branch', 'version')},
                  'sha256': current['sections']['ResList.bin'][1]},
        result=({name: release.File(**row) for name, row in current['files'].items()}, current['sections']['ResList.bin']))
    if receipt['inputs_sha256'] != inputs.identity:
        raise _failure()
    historical = baseline.discover(cache/'tools/nte-publisher/native-baseline',
        fetch=lambda *_a, **_k: (_ for _ in ()).throw(_failure()), parameters=initial.parameters(format_cache))
    host, branch = updater.release_origin(inputs, format_cache)
    if branch != handle['inventory']['branch'] or _selection(handle['inventory'], historical, host) != handle['files']:
        raise _failure()
    missing = [spec for spec in handle['files'] if not _retained(cache, spec)]
    verification = handle['verification']
    if not isinstance(verification, dict) or not 0 < len(verification) <= 32:
        raise _failure()
    total = sum(spec['file']['size'] for spec in missing)+2*sum(item['bytes'] for item in verification.values())
    if total != plan.download_bytes:
        raise GameDataError('download_plan_changed', 'Check the NTE download size again.', 409)
    transferred = 0
    def recheck():
        nonlocal transferred
        for url, identity in verification.items():
            ctx.check()
            _, receipt = transport.fetch_bytes(url, limit=identity['bytes'], expected_size=identity['bytes'],
                digests={'sha256': identity['sha256']}, kind='metadata')
            transferred += receipt.bytes
    # A changed source is rejected before any large asset, and again after all
    # complete original files pass their checksum, before the stage marker.
    recheck()
    for spec in missing:
        ctx.check()
        item = release.File(**spec['file'])
        host = spec.get('host', release.HOSTS[spec['region']])
        owner = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+spec['branch']+'/Res/'+owner[0]+'/'+owner
        with ctx.transfer_lock:
            ctx.check()
            receipt = transport.download_to(url, _target(cache, spec), limit=item.size, expected_size=item.size,
                kind='asset', digests={'md5': item.digest, **({'sha256': spec['sha256']} if spec.get('sha256') else {})},
                original_range=(item.offset, item.size, item.object_size))
            ctx.check()
        transferred += receipt.bytes
    recheck()
    if not all(_retained(cache, spec) for spec in handle['files']):
        raise _failure()
    ctx.check()
    ctx.progress('verifying', transferred, plan.download_bytes, 'Original NTE indexes verified.')
    return PreparationStage({'schema': STAGE, 'inventory_sha256': _identity(handle['inventory'])},
        'Original NTE indexes are downloaded. Check the selected game-content preparation size.')
