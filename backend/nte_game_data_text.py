"""Original subtitle quotes and canonical text-only dataset preparation."""
import json
import os
from pathlib import Path
import re
import tempfile

from . import nte_game_data_content as content, nte_game_data_prepare as processing
from . import nte_game_data_authoring as authoring, nte_game_data_ranges as ranges
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .game_tools import _atomic_file

STAGE = 'nte-original-text-normalization-v1'
SUBTITLES = 'nte-original-authored-subtitles-v1'


def _failure():
    return GameDataError('nte_text_plan_changed',
        'The original NTE text preparation information changed. Check its size again; your previous library is retained.', 409)


def _parts(owner, receipt, ctx, reader):
    if owner.get('reader') != reader.identity: raise _failure()
    handle = owner['metadata_recipe']['imports']['indices']
    cache, host = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']): raise _failure()
    metadata = processing._read(owner['metadata_recipe'], ctx)
    native = authoring._read(owner, ctx)
    if (metadata is None or metadata['receipt'] != owner['metadata_receipt']
            or native is None or native['receipt'] != receipt): raise _failure()
    catalog = processing._catalog(handle, ctx, reader)
    from .nte_cinematics import catalog_rows, movie_bindings, movie_namespaces
    movies = json.loads((native['root']/'movie-tables.json').read_bytes())
    if not isinstance(movies, dict) or 'OriginalMovieTables.json' not in movies: raise _failure()
    bindings = movie_bindings(catalog_rows(movies), movie_namespaces(movies, required=True))
    members, missing = [], 0
    for path in sorted({binding['subtitle'] for binding in bindings}):
        row = catalog.location(path)
        if row is None:
            missing += 1; continue
        name, archive, actual = row; entry, at, size = archive.stored_range(actual)
        if not 0 <= entry.size <= 4*1024**2: raise _failure()
        members.append({'pak': name, 'path': actual, 'offset': at, 'stored_bytes': size, 'raw_bytes': entry.size})
    if len(members) > 4096 or sum(row['raw_bytes'] for row in members) > 128*1024**2: raise _failure()
    packet = {'schema': STAGE, 'owner': owner, 'authoring_receipt': receipt,
        'subtitle_selection': {'sha256': content._identity(members), 'count': len(members), 'missing': missing}}
    sources = {name: archive.source for name, archive in catalog.archives.items()}
    wanted = {}
    from .nte_publisher_pak import CHUNK, TRANSFER
    for row in members:
        source = sources[row['pak']]
        for index in range(row['offset']//CHUNK, (row['offset']+row['stored_bytes']+CHUNK-1)//CHUNK):
            if source._cached(index) is None: wanted.setdefault(row['pak'], set()).add(index)
    runs = []
    for name, indices in sorted(wanted.items()):
        ordered = sorted(indices); at = 0
        while at < len(ordered):
            stop = at+1
            while stop < len(ordered) and ordered[stop] == ordered[stop-1]+1 and stop-at < TRANSFER//CHUNK: stop += 1
            runs.append({'pak': name, 'first': ordered[at], 'stop': ordered[stop-1]+1}); at = stop
    return packet, metadata, native, catalog, bindings, members, sources, ranges._batch(sources, runs), host


def plan(owner, retained, ctx, reader):
    if ctx.request.content_mode != 'text':
        return GameDataPlan('nte-original-audio-'+content._identity(owner), None, None, stage='content',
            message='Original NTE dialogue formats are verified. Selected original audio still needs its bounded download preparation.')
    packet, _, _, _, _, _, sources, wanted, _ = _parts(owner, retained['receipt'], ctx, reader)
    checks = 2*sum(row['bytes'] for row in owner['metadata_recipe']['imports']['indices']['verification'].values())
    if wanted:
        quote = {'schema': SUBTITLES, 'text_recipe': packet, 'ranges': wanted}
        size = ranges._cost(sources, wanted)
        return GameDataPlan('nte-authored-subtitles-'+content._identity(quote), size+checks, size+128*1024,
            handle=quote, runtime_available=True, download_is_upper_bound=True, stage='authored-subtitle-ranges',
            message='Download the original subtitles declared by NTE dialogue authoring before preparing text.')
    return GameDataPlan('nte-original-text-'+content._identity(packet), checks, 3*1024**3,
        handle=packet, runtime_available=True, download_is_upper_bound=True, stage='normalize-text',
        message='Prepare downloaded NTE text and translations and verify the current original source. Audio is not requested.')


def _recheck(handle, ctx, transport):
    transferred = 0
    for url, row in handle['verification'].items():
        ctx.check()
        _, receipt = transport.fetch_bytes(url, kind='metadata', limit=row['bytes'], expected_size=row['bytes'],
            digests={'sha256': row['sha256']})
        transferred += receipt.bytes
    return transferred


def download_subtitles(approved, ctx, reader, transport):
    quote = approved.handle
    if (not isinstance(quote, dict) or set(quote) != {'schema', 'text_recipe', 'ranges'} or quote['schema'] != SUBTITLES
            or approved.stage != 'authored-subtitle-ranges' or approved.revision != 'nte-authored-subtitles-'+content._identity(quote)):
        raise _failure()
    recipe = quote['text_recipe']; owner = recipe['owner']; handle = owner['metadata_recipe']['imports']['indices']
    packet, _, _, _, _, _, sources, wanted, host = _parts(owner, recipe['authoring_receipt'], ctx, reader)
    checks = 2*sum(row['bytes'] for row in handle['verification'].values())
    if packet != recipe or wanted != quote['ranges'] or approved.download_bytes != ranges._cost(sources, wanted)+checks:
        raise _failure()
    transferred = _recheck(handle, ctx, transport)
    from .nte_publisher_pak import CHUNK
    for row in wanted:
        ctx.check(); source = sources[row['pak']]; item = source.item
        begin, end = row['first']*CHUNK, min(row['stop']*CHUNK, item.size)
        owner_name = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner_name[0]+'/'+owner_name
        with ctx.transfer_lock:
            ctx.check()
            raw, receipt = transport.fetch_bytes(url, kind='asset', limit=end-begin, expected_size=end-begin,
                original_range=(item.offset+begin, end-begin, item.object_size))
            pieces = [(index, raw[index*CHUNK-begin:min((index+1)*CHUNK,item.size)-begin]) for index in range(row['first'],row['stop'])]
            if not all(source._valid(index, part) for index, part in pieces):
                raise GameDataError('publisher_checksum_mismatch', 'An original NTE subtitle failed its checksum.', 409)
            for index, part in pieces:
                ctx.check(); source._store(index, part)
            ctx.check()
        transferred += receipt.bytes
    transferred += _recheck(handle, ctx, transport)
    if not all(sources[row['pak']]._cached(index) is not None for row in wanted for index in range(row['first'],row['stop'])):
        raise _failure()
    ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Original authored NTE subtitles verified.')
    return PreparationStage({'schema': SUBTITLES, 'plan_sha256': content._identity(quote), 'transferred_bytes': transferred},
        'Original NTE subtitles are downloaded. Continue text preparation.')


def _link(source, destination):
    _no_links(source); _no_links(destination)
    os.link(source, destination)


def download_text(approved, ctx, reader, transport):
    packet = approved.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'owner', 'authoring_receipt', 'subtitle_selection'}
            or packet['schema'] != STAGE or approved.stage != 'normalize-text'
            or approved.revision != 'nte-original-text-'+content._identity(packet) or ctx.request.content_mode != 'text'):
        raise _failure()
    owner = packet['owner']; handle = owner['metadata_recipe']['imports']['indices']
    actual, metadata, native, catalog, bindings, members, _, wanted, _ = _parts(owner, packet['authoring_receipt'], ctx, reader)
    expected = 2*sum(row['bytes'] for row in handle['verification'].values())
    if actual != packet or wanted or approved.download_bytes != expected: raise _failure()
    transferred = _recheck(handle, ctx, transport)
    from . import nte_assets as assets
    from .language_worker import write_payload
    from . import nte_game_data_snapshot as snapshot, nte_game_data_initial as initial
    with tempfile.TemporaryDirectory(prefix='nte-text-normalize-', dir=ctx.directory) as name:
        staging = Path(name)
        for filename in authoring.OUTPUTS: _link(native['root']/filename, staging/filename)
        _link(metadata['root']/'localization.json', staging/'localization.json')
        tables = json.loads((staging/'localization.json').read_bytes())
        requested = {ctx.request.source_locale, *ctx.request.target_locales}
        missing = sorted(locale for locale in requested if not tables.get(assets.TEXT_LOCALES[locale]))
        if missing:
            raise GameDataError('missing_text_pack', 'This NTE snapshot does not provide every selected text language. Your previous library is retained.', 409)
        subtitles = {binding['subtitle']: catalog.read(binding['subtitle']).decode('utf-8-sig')
            for binding in bindings if catalog.location(binding['subtitle'])}
        _atomic_file(staging/'cinema-subtitles.json', processing._json(subtitles))
        language = assets.VOICE_LOCALES[ctx.request.source_locale]
        prefix = 'HT/Content/WwiseAudio/Event/'+language+'/'
        banks = sorted(path for _, _, path in catalog.locations.values() if path.casefold().startswith(prefix.casefold())
            and re.fullmatch(r'Play_Vo_[A-Za-z0-9_]+\.bnk', Path(path).name, re.I) and catalog.location(path))
        _atomic_file(staging/'voice-bank-paths.json', processing._json(banks))
        ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Preparing original NTE text and translations without audio.')
        records = assets.build_records(staging, bindings, source_locale=ctx.request.source_locale,
            target_locales=set(ctx.request.target_locales)-{ctx.request.source_locale}, dialogue_graphs=True, content_mode='text')
        warnings = assets.coverage_warnings(records, publisher=True)
        if packet['subtitle_selection']['missing']:
            warnings.append('Some authored movie subtitles are absent in this original snapshot; their unresolved captions are retained without invented voice bindings.')
        source_count = len(tables[assets.TEXT_LOCALES[ctx.request.source_locale]])
        warnings.extend(f'NTE {code} translations cover {len(rows):,} of {source_count:,} matching original text keys.'
            for code, rows in tables.items() if code != assets.TEXT_LOCALES[ctx.request.source_locale] and len(rows)<source_count)
        payload = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': ctx.request.region,
            'content_mode': 'text', 'fingerprint': approved.revision, 'source_locale': ctx.request.source_locale,
            'records': records, 'missing_translation_locales': [], 'coverage_warnings': warnings,
            'message': f'{len(records):,} original {ctx.request.source_locale} text rows; audio not requested'}
        write_payload('nte', payload, ctx.request.source_locale, ctx.request.target_locales, staging/'validated-text.json')
        ctx.check()
        transferred += _recheck(handle, ctx, transport)
        final, final_metadata, final_native, _, _, _, _, final_missing, _ = _parts(owner, packet['authoring_receipt'], ctx, reader)
        if (final != packet or final_missing or final_metadata['receipt'] != metadata['receipt']
                or final_native['receipt'] != native['receipt']): raise _failure()
        native_receipt = json.loads((native['root']/'receipt.json').read_bytes())
        inputs = {'recipe_sha256': content._identity(packet), 'metadata_receipt_sha256': metadata['receipt'],
            'authoring_receipt_sha256': native['receipt'], 'native_validation_sha256': native_receipt['validation'],
            'reader': reader.identity, 'initial_descriptions': {key: row['sha256'] for key, row in initial.descriptions().items()}}
        result = snapshot.publish(payload, inputs, ctx, _atomic_file)
    ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Original NTE text library verified; audio was not requested.')
    return result
