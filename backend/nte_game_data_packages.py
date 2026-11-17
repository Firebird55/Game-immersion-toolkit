"""TOC-bound package quotes from an owned original metadata receipt."""
from dataclasses import replace
from . import nte_game_data_content as content, nte_game_data_iostore as imports
from . import nte_game_data_prepare as processing
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage

STAGE = 'nte-original-dialogue-package-ranges-v1'


def _failure():
    return GameDataError('nte_package_plan_changed',
        'The original NTE dialogue package plan changed. Check the download size again.', 409)


def _selection(recipe, retained, values):
    from .nte_graph_prefetch import plan as select
    # Enumerate metadata for the complete bounded package closure, then quote
    # at most 64 MiB per consented stage. Normal growth can use further stages.
    wanted = select(values, retained['packages'], max_new_bytes=None)
    selected, new_bytes = [], 0
    for source, first, stop in wanted.runs:
        size = sum(block.length for block in source.blocks[first:stop])
        if selected and new_bytes+size > 64*1024**2:
            break
        selected.append((source, first, stop)); new_bytes += size
    wanted = replace(wanted, runs=tuple(selected), new_bytes=new_bytes)
    names = {source: name for name, source in values.items()}
    records = [{'toc': names[source], 'first': first, 'stop': stop} for source, first, stop in wanted.runs]
    return wanted, {'schema': STAGE, 'metadata_recipe': recipe, 'receipt': retained['receipt'], 'ranges': records}


def plan(recipe, retained, values, ctx, reader):
    wanted, packet = _selection(recipe, retained, values)
    if wanted.new_bytes == 0:
        from . import nte_game_data_initial as initial
        prerequisite = initial.plan(recipe['imports']['indices'], ('seed',), ctx, reader)
        if prerequisite is not None:
            return prerequisite
        from . import nte_game_data_authoring as authoring
        return authoring.plan(recipe, retained, ctx, reader, values)
    guards = recipe['imports']['indices']['verification']
    return GameDataPlan('nte-package-ranges-'+content._identity(packet),
        wanted.new_bytes+2*sum(row['bytes'] for row in guards.values()), wanted.new_bytes+128*1024,
        handle=packet, runtime_available=True, download_is_upper_bound=True, stage='dialogue-package-ranges',
        message='Download verified original NTE dialogue packages before complete language extraction.')


def download(plan, ctx, reader, transport):
    packet = plan.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'metadata_recipe', 'receipt', 'ranges'}
            or packet['schema'] != STAGE or plan.stage != 'dialogue-package-ranges'
            or plan.revision != 'nte-package-ranges-'+content._identity(packet)):
        raise _failure()
    recipe = packet['metadata_recipe']; handle = recipe['imports']['indices']
    if recipe['reader'] != reader.identity:
        raise _failure()
    cache, host = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']):
        raise _failure()
    retained = processing._read(recipe, ctx)
    if retained is None or retained['receipt'] != packet['receipt']:
        raise _failure()
    values = imports.containers(handle, ctx, reader)
    wanted, actual = _selection(recipe, retained, values)
    guards = handle['verification']
    if actual != packet or plan.download_bytes != wanted.new_bytes+2*sum(row['bytes'] for row in guards.values()):
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
    for source, first, stop in wanted.runs:
        ctx.check(); blocks = source.blocks[first:stop]
        start, end = blocks[0].offset, blocks[-1].offset+blocks[-1].length
        item = source.ucas; owner = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner[0]+'/'+owner
        with ctx.transfer_lock:
            ctx.check()
            raw, receipt = transport.fetch_bytes(url, kind='asset', limit=end-start, expected_size=end-start,
                original_range=(item.offset+start, end-start, item.object_size))
            parts = [raw[block.offset-start:block.offset-start+block.length] for block in blocks]
            if not all(source._valid(index, part) for index, part in zip(range(first, stop), parts)):
                raise GameDataError('publisher_checksum_mismatch', 'An original NTE dialogue package failed its checksum.', 409)
            for index, part in zip(range(first, stop), parts):
                ctx.check(); source._store(index, part)
            ctx.check()
        transferred += receipt.bytes
    recheck()
    if not all(source._cached(index) is not None for source, first, stop in wanted.runs for index in range(first, stop)):
        raise _failure()
    ctx.check(); ctx.progress('verifying', transferred, plan.download_bytes, 'Original NTE dialogue packages verified.')
    return PreparationStage({'schema': STAGE, 'plan_sha256': content._identity(packet),
        'metadata_receipt': retained['receipt'], 'reader': reader.identity, 'transferred_bytes': transferred},
        'Original NTE dialogue packages are downloaded. Check the remaining native language extraction.')
