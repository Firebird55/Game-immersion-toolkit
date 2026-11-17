"""Quote only original blocks actually requested by owned dialogue processing."""
import hashlib
import json
from pathlib import Path
import re

from . import nte_game_data_content as content, nte_game_data_iostore as imports
from . import nte_game_data_prepare as processing
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .game_tools import _atomic_file
from .private_data_paths import _no_links

STAGE = 'nte-original-required-imports-v1'
MAX_BYTES = 64*1024**2


def _failure():
    return GameDataError('nte_required_imports_changed',
        'The required NTE dialogue download information changed. Check its size again; your previous library is retained.', 409)


def _base(ctx):
    path = Path(ctx.cache_directory)/'tools/nte-publisher/game-data-imports'; _no_links(path)
    return path


class RequestedBlocks:
    def __init__(self, ctx):
        self.ctx, self.values, self.rows = ctx, {}, {}

    def __call__(self, source, at, size):
        self.ctx.check()
        names = [name for name, value in self.values.items() if value is source and not name.endswith('/global.utoc')]
        first = [i for i, block in enumerate(source.blocks) if block.offset == at]
        if (len(names) != 1 or len(first) != 1 or type(at) is not int or type(size) is not int
                or not 0 < size <= 4*1024**2 or not 0 <= at <= source.ucas.size-size):
            raise _failure()
        first = first[0]; stop = first; end = at
        while stop < len(source.blocks) and end < at+size:
            block = source.blocks[stop]
            if block.offset != end: raise _failure()
            end += block.length; stop += 1
        if end != at+size: raise _failure()
        row = {'toc': names[0], 'toc_md5': source.toc.digest, 'ucas_md5': source.ucas.digest,
            'first': first, 'stop': stop}
        self.rows[(names[0], first, stop)] = row
        if len(self.rows) > 4096: raise _failure()
        raise GameDataError('nte_original_bytes_missing',
            'Additional original NTE dialogue information is required. Check the download size again.', 409)


def publish(packet, rows, ctx):
    if not rows: raise _failure()
    value = {'schema': STAGE, 'owner': packet, 'ranges': sorted(rows, key=lambda row: (row['toc'], row['first'], row['stop']))}
    raw = processing._json(value)
    if len(raw) > 1024**2: raise _failure()
    digest = hashlib.sha256(raw).hexdigest(); base = _base(ctx)
    with ctx.transfer_lock:
        ctx.check(); _no_links(base/(digest+'.receipt.json')); _atomic_file(base/(digest+'.receipt.json'), raw)
        ctx.check()
        _atomic_file(base/(content._identity(packet)+'.json'), processing._json({'owner': content._identity(packet), 'receipt': digest}))
        ctx.check()
    return digest


def retained(packet, ctx):
    base = _base(ctx); identity = content._identity(packet); path = base/(identity+'.json'); _no_links(path)
    try:
        if not path.is_file() or path.stat().st_size > 4096: return None
        pointer = json.loads(path.read_bytes())
        if (set(pointer) != {'owner', 'receipt'} or pointer['owner'] != identity
                or re.fullmatch('[0-9a-f]{64}', pointer['receipt']) is None): return None
        path = base/(pointer['receipt']+'.receipt.json'); _no_links(path)
        if not path.is_file() or path.stat().st_size > 1024**2: return None
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pointer['receipt']: return None
        value = json.loads(raw)
        if set(value) != {'schema', 'owner', 'ranges'} or value['schema'] != STAGE or value['owner'] != packet: return None
        return pointer['receipt'], value['ranges']
    except (OSError, ValueError, KeyError, TypeError): return None


def _runs(rows, values):
    if not isinstance(rows, list) or not 0 < len(rows) <= 4096: raise _failure()
    selected = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'toc', 'toc_md5', 'ucas_md5', 'first', 'stop'}
                or row['toc'] not in values or row['toc'].endswith('/global.utoc')): raise _failure()
        source = values[row['toc']]; first, stop = row['first'], row['stop']
        if (row['toc_md5'] != source.toc.digest or row['ucas_md5'] != source.ucas.digest
                or type(first) is not int or type(stop) is not int or not 0 <= first < stop <= len(source.blocks)
                or sum(block.length for block in source.blocks[first:stop]) > 4*1024**2): raise _failure()
        selected.setdefault(row['toc'], set()).update(range(first, stop))
    runs, size = [], 0
    for name, indices in sorted(selected.items()):
        source = values[name]
        for index in sorted(indices):
            if source._cached(index) is not None: continue
            length = source.blocks[index].length
            if size+length > MAX_BYTES: return runs, size
            runs.append({'toc': name, 'first': index, 'stop': index+1}); size += length
    return runs, size


def plan(packet, values, ctx):
    found = retained(packet, ctx)
    if found is None: return None
    receipt, rows = found; runs, size = _runs(rows, values)
    if not runs: return None
    handle = packet['metadata_recipe']['imports']['indices']
    quote = {'schema': STAGE, 'owner': packet, 'receipt': receipt, 'ranges': runs}
    return GameDataPlan('nte-required-imports-'+content._identity(quote),
        size+2*sum(row['bytes'] for row in handle['verification'].values()), size+128*1024,
        handle=quote, runtime_available=True, download_is_upper_bound=True, stage='authoring-import-ranges',
        message='Download additional original dialogue information requested during NTE preparation.')


def download(approved, ctx, reader, transport):
    quote = approved.handle
    if (not isinstance(quote, dict) or set(quote) != {'schema', 'owner', 'receipt', 'ranges'}
            or quote['schema'] != STAGE or approved.stage != 'authoring-import-ranges'
            or approved.revision != 'nte-required-imports-'+content._identity(quote)): raise _failure()
    packet = quote['owner']; recipe = packet['metadata_recipe']; handle = recipe['imports']['indices']
    cache, host = content.validate_handle(handle, ctx, reader)
    if packet['reader'] != reader.identity or not all(content._retained(cache, row) for row in handle['files']): raise _failure()
    metadata = processing._read(recipe, ctx)
    if metadata is None or metadata['receipt'] != packet['metadata_receipt']: raise _failure()
    values = imports.containers(handle, ctx, reader)
    expected = plan(packet, values, ctx)
    if expected is None or expected.handle != quote or expected.download_bytes != approved.download_bytes: raise _failure()
    transferred = 0
    def recheck():
        nonlocal transferred
        for url, row in handle['verification'].items():
            ctx.check()
            _, receipt = transport.fetch_bytes(url, kind='metadata', limit=row['bytes'], expected_size=row['bytes'],
                digests={'sha256': row['sha256']})
            transferred += receipt.bytes
    recheck()
    for row in quote['ranges']:
        ctx.check(); source = values[row['toc']]; index = row['first']; block = source.blocks[index]; item = source.ucas
        owner = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner[0]+'/'+owner
        with ctx.transfer_lock:
            ctx.check()
            raw, receipt = transport.fetch_bytes(url, kind='asset', limit=block.length, expected_size=block.length,
                original_range=(item.offset+block.offset, block.length, item.object_size))
            if not source._valid(index, raw):
                raise GameDataError('publisher_checksum_mismatch',
                    'Required original NTE dialogue information failed its checksum. Your previous library is retained.', 409)
            source._store(index, raw); ctx.check()
        transferred += receipt.bytes
    recheck()
    if not all(values[row['toc']]._cached(row['first']) is not None for row in quote['ranges']): raise _failure()
    ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Required original NTE dialogue information verified.')
    return PreparationStage({'schema': STAGE, 'plan_sha256': content._identity(quote),
        'request_receipt': quote['receipt'], 'reader': reader.identity, 'transferred_bytes': transferred},
        'Additional original NTE dialogue information is downloaded. Continue local processing.')
