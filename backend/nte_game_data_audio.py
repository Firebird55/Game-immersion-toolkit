"""Explicit original bank/WEM quotes and zero-transfer audio processing."""
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile

from . import nte_game_data_text as text, nte_game_data_ranges as ranges
from . import nte_game_data_content as content, nte_game_data_prepare as processing
from . import nte_game_data_authoring as authoring
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import MAX_TEXT, _no_links
from .game_tools import _atomic_file

BINDINGS = 'nte-original-audio-bindings-v1'
MEDIA = 'nte-original-audio-members-v1'
RANGES = 'nte-original-audio-ranges-v1'
FINAL = 'nte-original-audio-finalize-v1'
MAX_MEMBERS = 100000


def _validate_bank_header(raw, event_id, language_id):
    if (len(raw) < 20 or raw[:4] != b'BKHD'
            or not 12 <= struct.unpack_from('<I', raw, 4)[0] <= len(raw)-8
            or struct.unpack_from('<I', raw, 8)[0] != 154):
        raise GameDataError('unsupported_game_format',
            'An original NTE voice bank has an unsupported format.', 409)
    if struct.unpack_from('<II', raw, 12) != (event_id, language_id):
        raise GameDataError('nte_voice_binding_unverified',
            'An original NTE voice bank does not match its declared event or voice language. '
            'Check the game download; your previous library is retained.', 409)


def _failure():
    return GameDataError('nte_audio_plan_changed',
        'The original NTE audio preparation information changed. Check its size again; your previous library is retained.', 409)


def _handle(packet):
    return packet['text_recipe']['owner']['metadata_recipe']['imports']['indices']


def _base(ctx):
    path = Path(ctx.cache_directory)/'tools/nte-publisher/game-data-audio'; _no_links(path)
    return path


def _members(catalog, paths, maximum):
    result = []
    for path in sorted(set(paths)):
        row = catalog.location(path)
        if row is None: raise _failure()
        pak, archive, actual = row; entry, offset, size = archive.stored_range(actual)
        if not 0 < entry.size <= maximum: raise _failure()
        result.append({'pak': pak, 'path': actual, 'reference': path, 'offset': offset, 'stored_bytes': size, 'raw_bytes': entry.size})
    if len(result) > MAX_MEMBERS: raise _failure()
    return result


def _wanted(sources, members):
    from .nte_publisher_pak import CHUNK, TRANSFER
    wanted = {}
    for row in members:
        source = sources[row['pak']]
        for index in range(row['offset']//CHUNK, (row['offset']+row['stored_bytes']+CHUNK-1)//CHUNK):
            if source._cached(index) is None: wanted.setdefault(row['pak'], set()).add(index)
    runs = []
    for name, values in sorted(wanted.items()):
        ordered = sorted(values); at = 0
        while at < len(ordered):
            stop = at+1
            while stop < len(ordered) and ordered[stop] == ordered[stop-1]+1 and stop-at < TRANSFER//CHUNK: stop += 1
            runs.append({'pak': name, 'first': ordered[at], 'stop': ordered[stop-1]+1}); at = stop
    return ranges._batch(sources, runs)


def _parts(owner, receipt, ctx, reader):
    if ctx.request.content_mode != 'text-audio': raise _failure()
    original, metadata, native, catalog, bindings, subtitles, sources, needed_srt, host = text._parts(owner, receipt, ctx, reader)
    from .nte_assets import VOICE_LOCALES
    prefix = 'HT/Content/WwiseAudio/Event/'+VOICE_LOCALES[ctx.request.source_locale]+'/'
    paths = [path for _, _, path in catalog.locations.values() if path.casefold().startswith(prefix.casefold())
        and re.fullmatch(r'Play_Vo_[A-Za-z0-9_]+\.bnk', Path(path).name, re.I) and catalog.location(path)]
    banks = _members(catalog, paths, 4*1024**2)
    if sum(row['raw_bytes'] for row in banks) > 1024**3: raise _failure()
    codec_identity, _ = _runtime(reader)
    packet = {'schema': BINDINGS, 'text_recipe': original, 'codecs': codec_identity,
        'banks': {'sha256': content._identity(banks), 'count': len(banks)}}
    return packet, metadata, native, catalog, bindings, banks, sources, needed_srt, host


def _read(packet, ctx, *, media=False):
    identity = content._identity(packet); base = _base(ctx)/('media' if media else 'bindings')
    path = base/(identity+'.json'); _no_links(path)
    try:
        if not path.is_file() or path.stat().st_size > 4096: return None
        pointer = json.loads(path.read_bytes())
        if set(pointer) != {'recipe', 'receipt'} or pointer['recipe'] != identity or re.fullmatch('[0-9a-f]{64}', pointer['receipt']) is None: return None
        root = base/'objects'/pointer['receipt']; receipt = root/'receipt.json'; _no_links(receipt)
        if not receipt.is_file() or receipt.stat().st_size > 256*1024: return None
        raw = receipt.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pointer['receipt']: return None
        value = json.loads(raw)
        names = {'originals.json'} if media else {'payload.json', 'needed-media.json'}
        if (not isinstance(value, dict) or set(value) != {'schema', 'recipe', 'files'} or value['recipe'] != identity
                or value['schema'] != (MEDIA if media else BINDINGS) or set(value['files']) != names): return None
        for name in names:
            file = root/name; _no_links(file)
            if not file.is_file() or not 0 < file.stat().st_size <= (MAX_TEXT if name == 'payload.json' else 32*1024**2): return None
            with file.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != value['files'][name]: return None
        if media:
            originals = json.loads((root/'originals.json').read_bytes())
            if not isinstance(originals, dict) or len(originals) > MAX_MEMBERS: return None
            for item in originals.values():
                if (not isinstance(item, dict) or set(item) != {'sha256', 'bytes', 'member_sha256'}
                        or any(not isinstance(item[key], str) or re.fullmatch('[0-9a-f]{64}', item[key]) is None for key in ('sha256', 'member_sha256'))
                        or type(item['bytes']) is not int or not 12 <= item['bytes'] <= 512*1024**2): return None
                path = _base(ctx)/'originals'/(item['sha256']+'.wem'); _no_links(path)
                if not path.is_file() or path.stat().st_size != item['bytes']: return None
                with path.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']: return None
        return {'receipt': pointer['receipt'], 'root': root}
    except (OSError, ValueError, KeyError, TypeError): return None


def _publish(packet, files, ctx, *, media=False):
    identity = content._identity(packet); base = _base(ctx)/('media' if media else 'bindings')
    receipt = {'schema': MEDIA if media else BINDINGS, 'recipe': identity,
        'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    raw = processing._json(receipt); digest = hashlib.sha256(raw).hexdigest(); root = base/'objects'/digest
    with ctx.transfer_lock:
        ctx.check(); _no_links(root)
        for name, data in (*files.items(), ('receipt.json', raw)):
            path = root/name; _no_links(path); _atomic_file(path, data)
        ctx.check(); _no_links(base/(identity+'.json'))
        _atomic_file(base/(identity+'.json'), processing._json({'recipe': identity, 'receipt': digest})); ctx.check()
    return digest


def _media_selection(packet, retained, catalog):
    members = json.loads((retained['root']/'needed-media.json').read_bytes())
    if not isinstance(members, list) or len(members) > MAX_MEMBERS: raise _failure()
    if _members(catalog, [row['reference'] for row in members], 512*1024**2) != members: raise _failure()
    if sum(row['raw_bytes'] for row in members) > 64*1024**3: raise _failure()
    return members, {'schema': MEDIA, 'binding_recipe': packet, 'binding_receipt': retained['receipt'],
        'selection': {'sha256': content._identity(members), 'count': len(members)}}


def _runtime(reader):
    from .nte_game_data_voice import codecs
    try: return codecs(reader.codec_layout)[1], None
    except GameDataError as error: return None, error.message


def _quote(packet, members, sources, host, reader, ctx, *, kind):
    wanted = _wanted(sources, members)
    if not wanted: return None
    quote = {'schema': RANGES, 'kind': kind, 'recipe': packet, 'ranges': wanted}
    handle = _handle(packet if kind == 'banks' else packet['binding_recipe'])
    size = ranges._cost(sources, wanted); _, missing = _runtime(reader)
    return GameDataPlan('nte-audio-ranges-'+content._identity(quote),
        size+2*sum(row['bytes'] for row in handle['verification'].values()), size+128*1024,
        handle=quote, runtime_available=missing is None, download_is_upper_bound=True, stage='audio-member-ranges',
        message=missing or ('Download selected original NTE voice banks, then check the recording download size.' if kind == 'banks' else 'Download the original recordings required by the selected NTE dialogue.'))


def plan(owner, retained, ctx, reader):
    packet, _, _, catalog, _, banks, sources, srt, host = _parts(owner, retained['receipt'], ctx, reader)
    _, missing_runtime = _runtime(reader)
    if not banks:
        return GameDataPlan('nte-missing-voice-'+content._identity(packet), None, None, stage='content',
            message='This original NTE inventory does not provide the selected voice pack. Your previous library is retained.')
    if srt:
        quote = {'schema': text.SUBTITLES, 'text_recipe': packet['text_recipe'], 'ranges': srt}
        size = ranges._cost(sources, srt)
        return GameDataPlan('nte-authored-subtitles-'+content._identity(quote), size+2*sum(row['bytes'] for row in _handle(packet)['verification'].values()),
            size+128*1024, handle=quote, runtime_available=missing_runtime is None, download_is_upper_bound=True,
            stage='authored-subtitle-ranges', message=missing_runtime or 'Download original authored subtitles before NTE audio preparation.')
    quote = _quote(packet, banks, sources, host, reader, ctx, kind='banks')
    if quote is not None: return quote
    binding_receipt = _read(packet, ctx)
    if binding_receipt is None:
        return GameDataPlan('nte-process-banks-'+content._identity(packet), 0, 3*1024**3+sum(row['raw_bytes'] for row in banks),
            handle=packet, runtime_available=missing_runtime is None, stage='process-audio-bindings',
            message=missing_runtime or 'Process downloaded NTE voice banks locally. No game data is downloaded in this step.')
    members, media_packet = _media_selection(packet, binding_receipt, catalog)
    quote = _quote(media_packet, members, sources, host, reader, ctx, kind='media')
    if quote is not None: return quote
    materialized = _read(media_packet, ctx, media=True)
    if materialized is None:
        return GameDataPlan('nte-materialize-audio-'+content._identity(media_packet), 0,
            3*1024**3+sum(row['raw_bytes'] for row in members), handle=media_packet,
            runtime_available=missing_runtime is None, stage='materialize-audio',
            message=missing_runtime or 'Verify downloaded original NTE recordings locally. No game data is downloaded in this step.')
    final = {'schema': FINAL, 'media_recipe': media_packet, 'media_receipt': materialized['receipt']}
    checks = 2*sum(row['bytes'] for row in _handle(packet)['verification'].values())
    return GameDataPlan('nte-finalize-audio-'+content._identity(final), checks, 3*1024**3, handle=final,
        runtime_available=missing_runtime is None, download_is_upper_bound=True, stage='finalize-audio',
        message=missing_runtime or 'Verify the original source and prepare the complete downloaded NTE text and audio library.')


def _validate(packet, ctx, reader):
    owner = packet['text_recipe']['owner']; receipt = packet['text_recipe']['authoring_receipt']
    parts = _parts(owner, receipt, ctx, reader)
    if parts[0] != packet or parts[7]: raise _failure()
    if packet['codecs'] is None:
        raise GameDataError('nte_audio_runtime_unavailable', 'This application needs its compatible original-voice decoder before preparing NTE audio.', 409)
    return parts


def download_ranges(approved, ctx, reader, transport):
    quote = approved.handle
    if (not isinstance(quote, dict) or set(quote) != {'schema', 'kind', 'recipe', 'ranges'} or quote['schema'] != RANGES
            or quote['kind'] not in {'banks', 'media'} or approved.stage != 'audio-member-ranges'
            or approved.revision != 'nte-audio-ranges-'+content._identity(quote)): raise _failure()
    packet = quote['recipe'] if quote['kind'] == 'banks' else quote['recipe']['binding_recipe']
    _, _, _, catalog, _, banks, sources, _, host = _validate(packet, ctx, reader)
    members = banks
    if quote['kind'] == 'media':
        retained = _read(packet, ctx)
        if retained is None: raise _failure()
        members, actual = _media_selection(packet, retained, catalog)
        if actual != quote['recipe']: raise _failure()
    wanted = _wanted(sources, members); handle = _handle(packet)
    if (wanted != quote['ranges'] or approved.download_bytes != ranges._cost(sources, wanted)
            +2*sum(row['bytes'] for row in handle['verification'].values())): raise _failure()
    transferred = text._recheck(handle, ctx, transport)
    from .nte_publisher_pak import CHUNK
    for row in wanted:
        ctx.check(); source = sources[row['pak']]; item = source.item
        begin, end = row['first']*CHUNK, min(row['stop']*CHUNK, item.size)
        owner = item.object_digest+'.'+str(item.object_size)
        url = 'https://'+host+'/clientRes/'+source.branch+'/Res/'+owner[0]+'/'+owner
        with ctx.transfer_lock:
            ctx.check()
            raw, receipt = transport.fetch_bytes(url, kind='asset', limit=end-begin, expected_size=end-begin,
                original_range=(item.offset+begin, end-begin, item.object_size))
            pieces = [(index, raw[index*CHUNK-begin:min((index+1)*CHUNK,item.size)-begin]) for index in range(row['first'],row['stop'])]
            if not all(source._valid(index, part) for index, part in pieces):
                raise GameDataError('publisher_checksum_mismatch', 'An original NTE voice download failed its checksum.', 409)
            for index, raw in pieces: ctx.check(); source._store(index, raw)
            ctx.check()
        transferred += receipt.bytes
    transferred += text._recheck(handle, ctx, transport)
    if not all(sources[row['pak']]._cached(index) is not None
            for row in wanted for index in range(row['first'], row['stop'])): raise _failure()
    ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Selected original NTE voice bytes verified.')
    return PreparationStage({'schema': RANGES, 'plan_sha256': content._identity(quote), 'transferred_bytes': transferred},
        'Original NTE voice data downloaded. Check the remaining local preparation.')


def download_bindings(approved, ctx, reader):
    packet = approved.handle
    if approved.stage != 'process-audio-bindings' or approved.download_bytes != 0 or approved.revision != 'nte-process-banks-'+content._identity(packet): raise _failure()
    _, metadata, native, catalog, bindings, banks, sources, _, _ = _validate(packet, ctx, reader)
    if _wanted(sources, banks): raise _failure()
    from . import nte_assets as assets
    from .language_worker import write_payload
    from .nte_publisher_pak import TRANSFER
    with tempfile.TemporaryDirectory(prefix='nte-audio-bindings-', dir=ctx.directory) as name:
        staging = Path(name); bank_dir = staging/'banks'; bank_dir.mkdir()
        for filename in authoring.OUTPUTS: text._link(native['root']/filename, staging/filename)
        text._link(metadata['root']/'localization.json', staging/'localization.json')
        tables = json.loads((staging/'localization.json').read_bytes())
        if not all(tables.get(assets.TEXT_LOCALES[locale]) for locale in {ctx.request.source_locale, *ctx.request.target_locales}):
            raise GameDataError('missing_text_pack', 'This NTE snapshot does not provide every selected text language.', 409)
        subtitles = {binding['subtitle']: catalog.read(binding['subtitle']).decode('utf-8-sig') for binding in bindings if catalog.location(binding['subtitle'])}
        _atomic_file(staging/'cinema-subtitles.json', processing._json(subtitles))
        language = assets.VOICE_LOCALES[ctx.request.source_locale]; batches = {}
        for member in banks: batches.setdefault(member['pak'], []).append(member)
        seen = set()
        ctx.progress('verifying', 0, 0, 'Reading downloaded original NTE voice banks locally.')
        for pak, members in batches.items():
            archive = catalog.archives[pak]; at = 0
            while at < len(members):
                stop, raw_size, stored_size = at, 0, 0
                while stop < len(members) and stop-at < 256:
                    row = members[stop]
                    if stop > at and (raw_size+row['raw_bytes'] > TRANSFER or stored_size+row['stored_bytes'] > 2*TRANSFER): break
                    raw_size += row['raw_bytes']; stored_size += row['stored_bytes']; stop += 1
                for member, raw in zip(members[at:stop], archive.read_many([row['path'] for row in members[at:stop]])):
                    ctx.check(); filename = Path(member['path']).name; event = Path(filename).stem
                    _validate_bank_header(raw, assets.wwise_hash(event), assets.wwise_hash(language))
                    if filename.casefold() in seen: raise _failure()
                    seen.add(filename.casefold()); _atomic_file(bank_dir/filename, raw)
                at = stop
                ctx.progress('verifying', 0, 0, f'Verified {len(seen):,} of {len(banks):,} original NTE voice banks.')
        prefix = 'HT/Content/WwiseAudio/Media/'+language+'/'
        media = sorted(prefix+Path(path).name for _, _, path in catalog.locations.values() if path.casefold().startswith(prefix.casefold())
            and re.fullmatch(r'[0-9]+\.wem', Path(path).name) and catalog.location(path))
        _atomic_file(staging/'media.json', processing._json(media))
        records = assets.build_records(staging, bindings, source_locale=ctx.request.source_locale,
            target_locales=set(ctx.request.target_locales)-{ctx.request.source_locale}, dialogue_graphs=True)
        payload = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': ctx.request.region,
            'content_mode': 'text-audio', 'fingerprint': approved.revision, 'source_locale': ctx.request.source_locale,
            'records': records, 'missing_translation_locales': [], 'coverage_warnings': assets.coverage_warnings(records, publisher=True)}
        path = staging/'validated-audio.json'; write_payload('nte', payload, ctx.request.source_locale, ctx.request.target_locales, path)
        if path.stat().st_size > MAX_TEXT: raise _failure()
        needed = _members(catalog, [row['audio']['depot'] for row in records if row.get('audio')], 512*1024**2)
        raw_members = processing._json(needed)
        if len(raw_members) > 32*1024**2: raise _failure()
        _validate(packet, ctx, reader)
        digest = _publish(packet, {'payload.json': path.read_bytes(), 'needed-media.json': raw_members}, ctx)
    return PreparationStage({'schema': BINDINGS, 'recipe': content._identity(packet), 'receipt': digest, 'transferred_bytes': 0},
        'Original NTE voice bindings verified. Check the required recording download size.')


def _media_parts(packet, ctx, reader):
    binding_packet = packet['binding_recipe']; parts = _validate(binding_packet, ctx, reader)
    retained = _read(binding_packet, ctx)
    if retained is None: raise _failure()
    members, actual = _media_selection(binding_packet, retained, parts[3])
    if actual != packet: raise _failure()
    return parts, retained, members


def download_materialize(approved, ctx, reader):
    packet = approved.handle
    if approved.stage != 'materialize-audio' or approved.download_bytes != 0 or approved.revision != 'nte-materialize-audio-'+content._identity(packet): raise _failure()
    parts, retained, members = _media_parts(packet, ctx, reader)
    catalog, sources = parts[3], parts[6]
    if _wanted(sources, members): raise _failure()
    from .nte_game_data_voice import check_wem
    originals = {}
    for position, row in enumerate(members):
        ctx.check(); raw = catalog.read(row['path']); check_wem(raw)
        if len(raw) != row['raw_bytes']: raise _failure()
        digest = hashlib.sha256(raw).hexdigest(); path = _base(ctx)/'originals'/(digest+'.wem'); _no_links(path)
        with ctx.transfer_lock:
            ctx.check()
            retained = False
            if path.is_file() and path.stat().st_size == len(raw):
                with path.open('rb') as stream:
                    retained = hashlib.file_digest(stream, 'sha256').hexdigest() == digest
            if not retained: _atomic_file(path, raw)
            ctx.check()
        originals[row['reference']] = {'sha256': digest, 'bytes': len(raw), 'member_sha256': content._identity(row)}
        if position%128 == 0 or position+1 == len(members):
            ctx.progress('verifying', 0, 0, f'Verified {position+1:,} of {len(members):,} downloaded original NTE recordings.')
    _media_parts(packet, ctx, reader)
    raw = processing._json(originals)
    if len(raw) > 32*1024**2: raise _failure()
    digest = _publish(packet, {'originals.json': raw}, ctx, media=True)
    return PreparationStage({'schema': MEDIA, 'recipe': content._identity(packet), 'receipt': digest, 'transferred_bytes': 0},
        'Original NTE recordings are locally verified. Continue the final source check.')


def download_finalize(approved, ctx, reader, transport):
    final = approved.handle
    if (not isinstance(final, dict) or set(final) != {'schema', 'media_recipe', 'media_receipt'} or final['schema'] != FINAL
            or approved.stage != 'finalize-audio' or approved.revision != 'nte-finalize-audio-'+content._identity(final)): raise _failure()
    packet = final['media_recipe']; parts, bindings, members = _media_parts(packet, ctx, reader)
    media = _read(packet, ctx, media=True); handle = _handle(packet['binding_recipe'])
    expected = 2*sum(row['bytes'] for row in handle['verification'].values())
    if media is None or media['receipt'] != final['media_receipt'] or approved.download_bytes != expected or _wanted(parts[6], members): raise _failure()
    transferred = text._recheck(handle, ctx, transport)
    payload = json.loads((bindings['root']/'payload.json').read_bytes())
    originals = json.loads((media['root']/'originals.json').read_bytes())
    if (set(originals) != {row['reference'] for row in members} or any(originals[row['reference']]['bytes'] != row['raw_bytes']
            or originals[row['reference']]['member_sha256'] != content._identity(row) for row in members)): raise _failure()
    from . import nte_game_data_initial as initial, nte_game_data_audio_snapshot as snapshot
    from .nte_game_data_voice import codecs, binding
    codec = codecs(reader.codec_layout)[1]
    owner = packet['binding_recipe']['text_recipe']['owner']; native = parts[2]
    native_receipt = json.loads((native['root']/'receipt.json').read_bytes())
    inputs = {'recipe_sha256': content._identity(final), 'metadata_receipt_sha256': owner['metadata_receipt'],
        'authoring_receipt_sha256': packet['binding_recipe']['text_recipe']['authoring_receipt'],
        'native_validation_sha256': native_receipt['validation'], 'reader': reader.identity,
        'initial_descriptions': {key: row['sha256'] for key, row in initial.descriptions().items()}}
    original_receipt = {'schema': snapshot.SCHEMA, 'request': ctx.request.json(), 'recipe_sha256': inputs['recipe_sha256'],
        'files': originals, 'bindings': sorted({binding(row) for row in payload['records'] if row.get('audio')}), 'codecs': codec}
    objects = {item['sha256']: _base(ctx)/'originals'/(item['sha256']+'.wem') for item in originals.values()}
    transferred += text._recheck(handle, ctx, transport)
    _media_parts(packet, ctx, reader)
    if _read(packet, ctx, media=True) != media: raise _failure()
    result = snapshot.publish(payload, inputs, original_receipt, objects, ctx, reader.codec_layout, _atomic_file)
    ctx.check(); ctx.progress('verifying', transferred, approved.download_bytes, 'Original NTE text and all selected playable recordings verified.')
    return result
