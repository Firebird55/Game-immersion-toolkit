"""Local-only preparation of already authenticated original NTE metadata."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from . import nte_game_data_content as content, nte_game_data_ranges as ranges
from . import nte_game_data_iostore as imports
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .game_tools import _atomic_file

STAGE = 'nte-original-local-metadata-v1'
MAX_RECEIPT = 256*1024
MAX_LOCALIZATION = 512*1024**2


def _text_budget(request):
    from .game_data_protocol import GameDataRequest
    selected = GameDataRequest.parse(request)
    count = len({selected.source_locale, *selected.target_locales})
    if not 1 <= count <= 9: raise _failure()
    return min(MAX_LOCALIZATION, count*128*1024**2)


def _failure():
    return GameDataError('nte_metadata_processing_failed',
        'The downloaded NTE dialogue information could not be verified. Your previous library is retained.', 409)


def _localization(ctx):
    from . import nte_archive_metadata as metadata
    from .nte_publisher import NATIVE_LOCALIZATION
    cache = Path(ctx.cache_directory)/'tools/nte-publisher/format'
    _no_links(cache/(NATIVE_LOCALIZATION[0]+'-'+NATIVE_LOCALIZATION[1]+'.txt'))
    def missing(*_a, **_k):
        raise GameDataError('nte_initial_localization_description_required',
            'The application needs its initial NTE text compatibility information before local processing.', 409)
    return metadata.load_localization(revision=NATIVE_LOCALIZATION[0], digest=NATIVE_LOCALIZATION[1],
                                     cache=cache, fetch=missing)


def _base(ctx):
    path = Path(ctx.cache_directory)/'tools/nte-publisher/game-data-metadata'
    _no_links(path)
    return path


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _read(packet, ctx):
    """A missing/broken metadata receipt needs processing, never a ready source."""
    base = _base(ctx); identity = content._identity(packet)
    pointer = base/(identity+'.json'); _no_links(pointer)
    try:
        if not pointer.is_file() or pointer.stat().st_size > 4096:
            return None
        reference = json.loads(pointer.read_bytes())
        if set(reference) != {'recipe', 'receipt'} or reference['recipe'] != identity or re.fullmatch('[0-9a-f]{64}', reference['receipt']) is None:
            return None
        root = base/'objects'/reference['receipt']; receipt_path = root/'receipt.json'
        _no_links(receipt_path)
        if not receipt_path.is_file() or receipt_path.stat().st_size > MAX_RECEIPT:
            return None
        raw = receipt_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['receipt']:
            return None
        receipt = json.loads(raw)
        if (receipt.get('schema') != STAGE or receipt.get('recipe') != identity
                or receipt.get('reader') != packet['reader'] or receipt.get('registry_eof_verified') is not True):
            return None
        for name, maximum in (('localization.json', _text_budget(packet['imports']['indices']['request'])),
                              ('dialogue-inventory.json', 16*1024**2)):
            path = root/name; _no_links(path)
            if not path.is_file() or path.stat().st_size > maximum:
                return None
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != receipt['files'][name]:
                    return None
        inventory = json.loads((root/'dialogue-inventory.json').read_bytes())
        if (not isinstance(inventory, dict) or set(inventory) != {'schema', 'complete', 'registry_sha256', 'nonce',
                'package_count', 'packages', 'registry_bytes', 'registry_eof_verified'}
                or inventory.get('schema') != 'nte-original-dialogue-inventory-v2'
                or inventory.get('registry_eof_verified') is not True
                or inventory.get('registry_sha256') != receipt['registry_sha256']
                or inventory.get('registry_bytes') != receipt['registry_bytes']
                or inventory.get('nonce') != receipt['inventory_nonce'] or inventory.get('complete') is not True
                or type(inventory.get('package_count')) is not int or not isinstance(inventory.get('packages'), dict)
                or inventory['package_count'] != len(inventory['packages']) or not 0 < inventory['package_count'] <= 8192):
            return None
        return {'receipt': reference['receipt'], 'packages': inventory['packages'], 'root': root}
    except (OSError, ValueError, KeyError, TypeError, GameDataError):
        return None


def plan(original, values, ctx, reader):
    try:
        localization = _localization(ctx)
    except GameDataError as error:
        if error.code != 'nte_initial_localization_description_required':
            raise
        from . import nte_game_data_initial as initial
        result = initial.plan(original['indices'], ('localization',), ctx, reader)
        if result is None:
            raise
        return result
    packet = {'schema': STAGE, 'imports': original, 'reader': reader.identity,
              'localization': [localization.revision, localization.digest]}
    retained = _read(packet, ctx)
    if retained is not None:
        from . import nte_game_data_packages as packages
        return packages.plan(packet, retained, values, ctx, reader)
    # Reserve both immutable/temporary text copies plus registry processing.
    disk = 2*_text_budget(original['indices']['request'])+2*256*1024**2+64*1024**2
    return GameDataPlan('nte-process-metadata-'+content._identity(packet), 0, disk,
        handle=packet, runtime_available=True, stage='process-metadata',
        message='Process downloaded NTE text and dialogue information locally. No game data is downloaded in this step.')


def _catalog(handle, ctx, reader):
    from types import SimpleNamespace
    from .nte_publisher import _overlay
    from . import nte_publisher_pak as pak
    sources = ranges._sources(handle, ctx, imports._offline)
    description = ranges._format(ctx)
    archives = {name: pak.Archive(source, description, oodle=reader.oodle) for name, source in sources.items()}
    locations = _overlay(archives, lambda archive: archive.locations)
    def location(name):
        row = locations.get(name.casefold())
        return row if row and row[1].entry(row[2]) is not None else None
    def read(name):
        row = location(name)
        if row is None: raise _failure()
        return row[1].read(row[2])
    return SimpleNamespace(locations=locations, location=location, read=read, archives=archives)


def download(plan, ctx, reader):
    packet = plan.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'imports', 'reader', 'localization'}
            or packet['schema'] != STAGE or packet['reader'] != reader.identity
            or plan.stage != 'process-metadata' or plan.download_bytes != 0
            or plan.revision != 'nte-process-metadata-'+content._identity(packet)):
        raise _failure()
    original = packet['imports']; handle = original['indices']
    cache, _ = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']):
        raise _failure()
    _, pending, selection = ranges._pending(handle, ctx, reader)
    if pending or selection != original['pak_selection']:
        raise _failure()
    localization = _localization(ctx)
    if [localization.revision, localization.digest] != packet['localization']:
        raise _failure()
    values = imports.containers(handle, ctx, reader, inventory_only=True)
    global_name, global_source = imports._global(values)
    if global_name != original['global'] or not imports.retained(global_source):
        raise _failure()
    catalog = _catalog(handle, ctx, reader)
    from .nte_native_provider import registry_location
    from .nte_assets import TEXT_LOCALES, read_dialogue_inventory
    from .nte_locres import parse
    _, registry_path = registry_location(catalog)
    ctx.progress('verifying', 0, 0, 'Processing downloaded NTE dialogue information locally.')
    registry = catalog.read(registry_path)
    registry_sha = hashlib.sha256(registry).hexdigest()
    tables, text_owners = {}, {}
    ctx.progress('verifying', 0, 0, 'Checking downloaded NTE language tables.')
    for locale in (ctx.request.source_locale, *ctx.request.target_locales):
        ctx.check(); code = TEXT_LOCALES[locale]
        path = 'HT/Content/Localization/Game/'+code+'/Game.locres'
        row = catalog.location(path)
        if row is None: continue
        raw = catalog.read(path)
        tables[code] = parse(raw, localization.parameter)
        text_owners[code] = {'pak': row[0], 'path': row[2], 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    source = tables.get(TEXT_LOCALES[ctx.request.source_locale])
    if not source: raise _failure()
    hashes = {(r['ns'], r['key']): r['source_hash'] for r in source}
    filtered = {code: [r for r in rows if hashes.get((r['ns'], r['key'])) == r['source_hash']] for code, rows in tables.items()}
    encoded = _json(filtered)
    if len(encoded) > _text_budget(handle['request']): raise _failure()
    context = Path(ctx.cache_directory)/'tools/nte-publisher/empty-context'; _no_links(context); context.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='nte-local-metadata-', dir=ctx.directory) as name:
        destination = Path(name)
        keys = sorted({archive.selected_key for archive in catalog.archives.values() if archive.selected_key is not None})
        if not keys: raise _failure()
        ctx.progress('verifying', 0, 0, 'Checking the original NTE dialogue inventory locally.')
        read_dialogue_inventory(context, reader.executable, destination, values, keys, registry,
            capture_original_authoring=True, game_data_reader=reader, require_registry_eof=True)
        inventory_raw = (destination/'dialogue-inventory.json').read_bytes()
        inventory = json.loads(inventory_raw)
    ctx.check()
    receipt = {'schema': STAGE, 'recipe': content._identity(packet), 'reader': reader.identity,
        'registry_path': registry_path, 'registry_sha256': registry_sha, 'registry_bytes': len(registry),
        'registry_eof_verified': True, 'inventory_nonce': inventory['nonce'], 'locales': text_owners,
        'files': {'localization.json': hashlib.sha256(encoded).hexdigest(),
                  'dialogue-inventory.json': hashlib.sha256(inventory_raw).hexdigest()}}
    raw = _json(receipt); digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_RECEIPT: raise _failure()
    # Recheck the retained original recipe immediately before publication.
    # This local-only stage cannot contact current publisher pointers; the
    # following preflight/final source activation owns those network checks.
    content.validate_handle(handle, ctx, reader)
    _, missing, actual_selection = ranges._pending(handle, ctx, reader)
    if missing or actual_selection != original['pak_selection'] or not imports.retained(global_source):
        raise _failure()
    base = _base(ctx); root = base/'objects'/digest
    with ctx.transfer_lock:
        ctx.check(); _no_links(root)
        for filename, data in (('localization.json', encoded), ('dialogue-inventory.json', inventory_raw), ('receipt.json', raw)):
            _no_links(root/filename); _atomic_file(root/filename, data)
        ctx.check()
        _atomic_file(base/(content._identity(packet)+'.json'), _json({'recipe': content._identity(packet), 'receipt': digest}))
        ctx.check()
    if _read(packet, ctx) is None: raise _failure()
    return PreparationStage({'schema': STAGE, 'recipe': content._identity(packet), 'receipt': digest,
        'registry_sha256': registry_sha, 'registry_eof_verified': True, 'reader': reader.identity, 'transferred_bytes': 0},
        'Original NTE text and dialogue information is processed. Check the remaining package download size.')
