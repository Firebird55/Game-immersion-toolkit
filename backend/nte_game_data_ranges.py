"""Explicit original PAK index-range stages; planning never downloads blocks.

Each range is derived by the existing archive parser using a complete original
SIG. This stage acquires only missing authenticated bytes, never a ready library.
"""
from pathlib import Path
from types import SimpleNamespace

from . import nte_game_data_content as content, nte_publisher_pak as pak
from . import nte_release as release
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .preparation_errors import PreparationFailure

STAGE = 'nte-original-archive-index-ranges-v1'
MAX_RANGE_BYTES = 64*1024**2
ROOT = 'Client/WindowsNoEditor/HT/Content/'


class RequiredRange(Exception):
    """A cache-only parser asks the caller for an explicitly planned range."""


def _failure():
    return GameDataError('nte_archive_plan_invalid',
        'NTE package download information changed or could not be verified. Check the download size again.', 409)


def _sources(handle, ctx, callback):
    current = handle['inventory']; result = {}
    files = {name: release.File(**row) for name, row in current['files'].items()}
    cache = Path(ctx.cache_directory)/'tools/nte-publisher/ranges'
    for name, item in sorted(files.items()):
        if not name.startswith(ROOT) or not name.endswith('.pak'):
            continue
        signature = files.get(name[:-4]+'.sig')
        if signature is None:
            raise _failure()
        root = cache/current['region']/item.digest/signature.digest
        _no_links(root)
        result[name] = pak.SignedSource(current['region'], current['branch'], item, signature, cache,
            range_reader=callback)
    if not 0 < len(result) <= 128:
        raise _failure()
    return result


def _format(ctx):
    from . import nte_archive_metadata as metadata
    from .nte_publisher import NATIVE_ARCHIVE
    def unavailable(*_a, **_k):
        raise GameDataError('nte_initial_description_required',
            'The application needs its initial NTE compatibility information before preparing these packages.', 409)
    cache = Path(ctx.cache_directory)/'tools/nte-publisher/format'
    _no_links(cache/(NATIVE_ARCHIVE[0]+'-'+NATIVE_ARCHIVE[1]+'.txt'))
    return metadata.load(revision=NATIVE_ARCHIVE[0], digest=NATIVE_ARCHIVE[1], cache=cache, fetch=unavailable)


def _pending(handle, ctx, reader):
    try:
        return _inspect(handle, ctx, reader)
    except PreparationFailure as error:
        raise GameDataError(error.code, str(error), 409) from error


def _inspect(handle, ctx, reader):
    wanted = []
    names = {}
    def missing(source, at, size):
        ctx.check()
        first, stop = at//pak.CHUNK, (at+size+pak.CHUNK-1)//pak.CHUNK
        if (at != first*pak.CHUNK or at+size != min(stop*pak.CHUNK, source.item.size)
                or not 0 < size <= pak.TRANSFER or source not in names):
            raise _failure()
        wanted.append({'pak': names[source], 'first': first, 'stop': stop})
        raise RequiredRange()
    sources = _sources(handle, ctx, missing)
    names.update((source, name) for name, source in sources.items())
    catalog = _format(ctx)
    archives = {}
    for name, source in sources.items():
        ctx.check()
        try:
            archives[name] = pak.Archive(source, catalog, oodle=reader.oodle)
        except RequiredRange:
            pass
    if wanted:
        return sources, wanted, {'purpose': 'indexes', 'members': []}
    members = _members(handle['request'], archives)
    missing = {}
    for member in members:
        ctx.check(); source = sources[member['pak']]
        first = member['offset']//pak.CHUNK
        stop = (member['offset']+member['stored_bytes']+pak.CHUNK-1)//pak.CHUNK
        for index in range(first, stop):
            # Inspect retained compressed blocks only for integrity/cache cost;
            # no selected member read, decompression, UE parse or online lookup.
            if source._cached(index) is None:
                missing.setdefault(member['pak'], set()).add(index)
    for name, blocks in sorted(missing.items()):
        ordered = sorted(blocks); i = 0
        while i < len(ordered):
            end = i+1
            while (end < len(ordered) and ordered[end] == ordered[end-1]+1
                   and end-i < pak.TRANSFER//pak.CHUNK):
                end += 1
            wanted.append({'pak': name, 'first': ordered[i], 'stop': ordered[end-1]+1})
            i = end
    return sources, wanted, {'purpose': 'selected-text-metadata', 'members_sha256': content._identity(members),
                             'members_count': len(members)}


def _members(request, archives):
    from .nte_assets import TEXT_LOCALES
    from .nte_publisher import _overlay
    from .nte_native_provider import registry_location
    locations = _overlay(archives, lambda archive: archive.locations)
    def live(name):
        row = locations.get(name.casefold())
        return row if row and row[1].entry(row[2]) is not None else None
    prefix = 'HT/Content/Localization/Game/'
    # No recognized text layout is still an unfinished source, never Ready.
    if not any(row[2].startswith(prefix) for row in locations.values()):
        return []
    source = prefix+TEXT_LOCALES[request['source_locale']]+'/Game.locres'
    if live(source) is None:
        raise GameDataError('missing_text_pack', 'This NTE edition does not provide the selected study text.', 409)
    selected = {prefix+TEXT_LOCALES[locale]+'/Game.locres'
                for locale in (request['source_locale'], *request['target_locales'])}
    if request['content_mode'] != 'text':
        selected.update(row[2] for row in locations.values()
            if row[2].startswith('HT/Content/SrtFile/FFMpeg/Story/') and row[2].endswith('.srt') and live(row[2]))
    # Text preparation first validates original authoring. Only its declared
    # subtitle members are quoted afterward; no wildcard body acquisition.
    try:
        _, registry = registry_location(SimpleNamespace(locations=locations, location=live))
    except ValueError as error:
        raise GameDataError('nte_registry_unavailable',
            'The original NTE dialogue inventory is missing or ambiguous. Your previous library is retained.', 409) from error
    selected.add(registry)
    result = []
    for path in sorted(selected):
        row = live(path)
        if row is None:  # An absent target translation is not invented.
            continue
        owner, archive, original = row
        entry, start, length = archive.stored_range(original)
        if length:
            result.append({'pak': owner, 'path': original, 'offset': start,
                           'stored_bytes': length, 'raw_bytes': entry.size})
    if not 0 < len(result) <= 4096:
        raise _failure()
    return result


def _cost(sources, records):
    if not isinstance(records, list) or not 0 < len(records) <= 4096:
        raise _failure()
    total = 0; seen = set()
    for row in records:
        if not isinstance(row, dict) or set(row) != {'pak', 'first', 'stop'} or row['pak'] not in sources:
            raise _failure()
        first, stop = row['first'], row['stop']; source = sources[row['pak']]
        if (type(first) is not int or type(stop) is not int or not 0 <= first < stop <= len(source.checksums)//4
                or stop-first > pak.TRANSFER//pak.CHUNK or (row['pak'], first, stop) in seen):
            raise _failure()
        seen.add((row['pak'], first, stop))
        total += min(stop*pak.CHUNK, source.item.size)-first*pak.CHUNK
    if not 0 < total <= MAX_RANGE_BYTES:
        raise _failure()
    return total


def _batch(sources, records):
    # More/larger normal update indexes use further explicit stages rather
    # than turning the per-stage transfer bound into a permanent refusal.
    selected, total = [], 0
    for row in records:
        size = _cost(sources, [row])
        if selected and total+size > MAX_RANGE_BYTES:
            break
        selected.append(row); total += size
    return selected


def plan(handle, ctx, reader):
    try:
        sources, wanted, selection = _pending(handle, ctx, reader)
    except GameDataError as error:
        if error.code != 'nte_initial_description_required':
            raise
        from . import nte_game_data_initial as initial
        result = initial.plan(handle, ('archive',), ctx, reader)
        if result is None:
            raise
        return result
    if not wanted:
        if selection.get('members_count', 0):
            from . import nte_game_data_iostore as imports
            return imports.plan(handle, selection, ctx, reader)
        return GameDataPlan('nte-archive-blocks-'+content._identity(handle), None, None, handle=handle,
            stage='content', message='Original NTE package indexes are verified. Selected text and audio preparation still needs a bounded content plan.')
    wanted = _batch(sources, wanted)
    payload = _cost(sources, wanted)
    packet = {'schema': STAGE, 'indices': handle, 'ranges': wanted, 'selection': selection}
    checks = sum(row['bytes'] for row in handle['verification'].values())
    return GameDataPlan('nte-ranges-'+content._identity(packet), payload+2*checks, payload+128*1024,
        handle=packet, download_is_upper_bound=True, runtime_available=True, stage='archive-index-ranges',
        message=('Download verified NTE package indexes, then check the selected text and audio size.'
            if selection['purpose'] == 'indexes' else
            'Download selected NTE text and dialogue information, then check the remaining preparation.'))


def download(plan, ctx, reader, transport):
    packet = plan.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'indices', 'ranges', 'selection'}
            or packet['schema'] != STAGE or plan.stage != 'archive-index-ranges'
            or plan.revision != 'nte-ranges-'+content._identity(packet)):
        raise _failure()
    handle = packet['indices']; cache, host = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']):
        raise _failure()
    sources, wanted, selection = _pending(handle, ctx, reader)
    wanted = _batch(sources, wanted)
    if wanted != packet['ranges'] or selection != packet['selection']:
        raise _failure()
    checks = handle['verification']
    total = _cost(sources, wanted)+2*sum(row['bytes'] for row in checks.values())
    if total != plan.download_bytes:
        raise _failure()
    transferred = 0
    def recheck():
        nonlocal transferred
        for url, row in checks.items():
            ctx.check()
            _, receipt = transport.fetch_bytes(url, limit=row['bytes'], expected_size=row['bytes'],
                digests={'sha256': row['sha256']}, kind='metadata')
            transferred += receipt.bytes
    recheck()
    for row in wanted:
        ctx.check(); source = sources[row['pak']]; item = source.item
        first, stop = row['first'], row['stop']
        at, end = first*pak.CHUNK, min(stop*pak.CHUNK, item.size)
        owner = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner[0]+'/'+owner
        with ctx.transfer_lock:
            ctx.check()
            raw, receipt = transport.fetch_bytes(url, limit=end-at, expected_size=end-at, kind='asset',
                original_range=(item.offset+at, end-at, item.object_size))
            blocks = [raw[i*pak.CHUNK:(i+1)*pak.CHUNK] for i in range(stop-first)]
            if not all(source._valid(first+i, block) for i, block in enumerate(blocks)):
                raise GameDataError('publisher_checksum_mismatch', 'The original NTE package failed its checksum.', 409)
            # Authenticate every block before publishing any of this response.
            for i, block in enumerate(blocks):
                ctx.check(); source._store(first+i, block)
            ctx.check()
        transferred += receipt.bytes
    recheck(); ctx.check()
    ctx.progress('verifying', transferred, plan.download_bytes, 'Original NTE package ranges verified.')
    return PreparationStage({'schema': STAGE, 'inventory_sha256': content._identity(handle['inventory']),
        'plan_sha256': content._identity(packet), 'ranges_sha256': content._identity(wanted),
        'selection': selection, 'reader': reader.identity, 'transferred_bytes': transferred,
        'official_verification_sha256': content._identity(checks)},
        'Original NTE package ranges are downloaded. Check the remaining game-content size.')
