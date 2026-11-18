"""Local original native/schema validation after explicitly acquired packages."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from . import nte_game_data_content as content, nte_game_data_prepare as processing
from . import nte_game_data_iostore as imports, nte_game_data_ranges as ranges
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .game_tools import _atomic_file
from .private_data_paths import _no_links

STAGE = 'nte-original-local-authoring-v1'
OUTPUTS = ('dialogue-events.json', 'sequence-cues.json', 'voice-events.json', 'movie-tables.json',
           'dialogue-graphs.json', 'original-authoring.json', 'dialogue.usmap')
MAX_OUTPUT = 128*1024**2


def _failure():
    return GameDataError('nte_original_authoring_unavailable',
        'The original NTE dialogue information could not be completed. Your previous library is retained.', 409)


def _base(ctx):
    path = Path(ctx.cache_directory)/'tools/nte-publisher/game-data-authoring'; _no_links(path)
    return path


def _read(packet, ctx):
    base = _base(ctx); identity = content._identity(packet); pointer = base/(identity+'.json'); _no_links(pointer)
    try:
        if not pointer.is_file() or pointer.stat().st_size > 4096: return None
        reference = json.loads(pointer.read_bytes())
        if (set(reference) != {'recipe', 'receipt'} or reference['recipe'] != identity
                or re.fullmatch('[0-9a-f]{64}', reference['receipt']) is None): return None
        root = base/'objects'/reference['receipt']; path = root/'receipt.json'; _no_links(path)
        if not path.is_file() or path.stat().st_size > 256*1024: return None
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['receipt']: return None
        receipt = json.loads(raw)
        if (set(receipt) != {'schema', 'recipe', 'metadata_receipt', 'reader', 'type_schema', 'validation', 'files'}
                or receipt['schema'] != STAGE or receipt['recipe'] != identity
                or receipt['metadata_receipt'] != packet['metadata_receipt'] or receipt['reader'] != packet['reader']
                or set(receipt['files']) != set(OUTPUTS)
                or receipt['files']['dialogue.usmap'] != receipt['type_schema']['sha256']): return None
        for name in OUTPUTS:
            path = root/name; _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_OUTPUT: return None
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != receipt['files'][name]: return None
        from . import nte_native_metadata as native
        candidate = native.load(receipt['type_schema'], Path(ctx.cache_directory)/'tools/nte-publisher/native-candidates')
        native._digest(receipt['validation'])
        proof = Path(ctx.cache_directory)/'tools/nte-publisher/native-candidates/validations'/(receipt['validation']+'.json')
        _no_links(proof)
        if (not proof.is_file() or proof.stat().st_size > native.MAX_RECEIPT
                or hashlib.sha256(proof.read_bytes()).hexdigest() != receipt['validation']
                or candidate.receipt['dependencies']['reader'] != packet['reader']['source_sha256']): return None
        validation = json.loads(proof.read_bytes())
        if (not isinstance(validation, dict) or validation.get('required_schema_eligible') is not True or validation.get('schema') != receipt['type_schema']
                or validation.get('reader_sha256') != packet['reader']['source_sha256']
                or candidate.receipt['source_manifest_sha256'] != hashlib.sha256(native._json(packet['metadata_recipe']['imports']['indices']['inventory'])).hexdigest()):
            return None
        return {'receipt': reference['receipt'], 'root': root}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def plan(recipe, retained, ctx, reader, values):
    packet = {'schema': STAGE, 'metadata_recipe': recipe, 'metadata_receipt': retained['receipt'], 'reader': reader.identity}
    from . import nte_game_data_imports as dependencies
    required = dependencies.plan(packet, values, ctx)
    if required is not None:
        return required
    completed = _read(packet, ctx)
    if completed is not None:
        return GameDataPlan('nte-language-records-'+content._identity(packet), None, None, handle=packet,
            stage='content', message='Original NTE dialogue formats are verified. Complete language and audio preparation still follows.')
    # Reserve temporary registry/output copies and immutable publication, not
    # merely the final JSON sizes. No original native file is copied here.
    return GameDataPlan('nte-process-authoring-'+content._identity(packet), 0, 3*1024**3,
        handle=packet, runtime_available=True, stage='process-authoring',
        message='Process downloaded NTE dialogue and verify its format locally. No game data is downloaded in this step.')


def download(plan, ctx, reader):
    packet = plan.handle
    if (not isinstance(packet, dict) or set(packet) != {'schema', 'metadata_recipe', 'metadata_receipt', 'reader'}
            or packet['schema'] != STAGE or packet['reader'] != reader.identity
            or plan.stage != 'process-authoring' or plan.download_bytes != 0
            or plan.revision != 'nte-process-authoring-'+content._identity(packet)):
        raise _failure()
    recipe = packet['metadata_recipe']; original = recipe['imports']; handle = original['indices']
    cache, _ = content.validate_handle(handle, ctx, reader)
    if not all(content._retained(cache, spec) for spec in handle['files']): raise _failure()
    retained = processing._read(recipe, ctx)
    if retained is None or retained['receipt'] != packet['metadata_receipt']: raise _failure()
    from . import nte_game_data_imports as dependencies
    requested = dependencies.RequestedBlocks(ctx)
    values = imports.containers(handle, ctx, reader, range_reader=requested)
    requested.values = values
    from .nte_graph_prefetch import plan as package_plan
    if package_plan(values, retained['packages'], max_new_bytes=None).runs: raise _failure()
    _, pending, selection = ranges._pending(handle, ctx, reader)
    global_name, global_source = imports._global(values)
    if pending or selection != original['pak_selection'] or global_name != original['global'] or not imports.retained(global_source):
        raise _failure()
    from . import nte_native_provider as native
    from .preparation_errors import PreparationFailure
    from .nte_publisher import NATIVE_ARCHIVE, NATIVE_LOCALIZATION
    from . import nte_game_data_initial as initial
    if not all(initial._retained(cache, row) for row in initial.descriptions().values()): raise _failure()
    current = handle['inventory']; catalog = processing._catalog(handle, ctx, reader)
    value = {key: current[key] for key in ('region', 'branch', 'version', 'sections')}
    value.update(publisher_files=current['files'], reader=reader.source_identity,
        archive=list(NATIVE_ARCHIVE), localization=list(NATIVE_LOCALIZATION), original_updater=handle['updater'])
    value['type_schema'] = native.source_reference(current, reader.source_identity)
    catalog.snapshot, catalog.cache, catalog.region = value, cache/'tools/nte-publisher', current['region']
    catalog.stamp = 'nte-'+content._identity(packet)
    catalog.containers = lambda: values
    catalog.reader_keys = lambda: sorted({archive.selected_key for archive in catalog.archives.values() if archive.selected_key is not None})
    with tempfile.TemporaryDirectory(prefix='nte-local-authoring-', dir=ctx.directory) as name:
        staging = Path(name)
        def progress(message):
            ctx.check(); ctx.progress('verifying', 0, 0, message)
        try:
            proof, validation = native.read_authoring(catalog, reader.executable, staging, progress, game_data_reader=reader)
        except PreparationFailure as error:
            if not requested.rows or error.code != 'game_metadata_unavailable':
                raise
            # A real owned read discovered an additional original dependency.
            # No partial authoring output is retained or marked complete.
            ctx.check(); content.validate_handle(handle, ctx, reader)
            digest = dependencies.publish(packet, list(requested.rows.values()), ctx)
            return PreparationStage({'schema': dependencies.STAGE, 'request_receipt': digest,
                'reader': reader.identity, 'transferred_bytes': 0},
                'Additional original NTE dialogue information is needed. Check its download size before continuing.')
        ctx.check()
        outputs = {}
        for filename in OUTPUTS:
            path = staging/filename; _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_OUTPUT: raise _failure()
            outputs[filename] = path.read_bytes()
        receipt = {'schema': STAGE, 'recipe': content._identity(packet), 'metadata_receipt': retained['receipt'],
            'reader': reader.identity, 'type_schema': proof, 'validation': validation,
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()}}
        raw = processing._json(receipt); digest = hashlib.sha256(raw).hexdigest()
        content.validate_handle(handle, ctx, reader)
        _, missing, actual = ranges._pending(handle, ctx, reader)
        if (missing or actual != original['pak_selection'] or not imports.retained(global_source)
                or package_plan(values, retained['packages'], max_new_bytes=None).runs): raise _failure()
        root = _base(ctx)/'objects'/digest
        with ctx.transfer_lock:
            ctx.check(); _no_links(root)
            for filename, data in (*outputs.items(), ('receipt.json', raw)):
                _no_links(root/filename); _atomic_file(root/filename, data)
            ctx.check()
            _atomic_file(_base(ctx)/(content._identity(packet)+'.json'), processing._json({'recipe': content._identity(packet), 'receipt': digest}))
            ctx.check()
    if _read(packet, ctx) is None: raise _failure()
    return PreparationStage({'schema': STAGE, 'recipe': content._identity(packet), 'receipt': digest,
        'reader': reader.identity, 'validation': validation, 'transferred_bytes': 0},
        'Original NTE dialogue formats are verified. Complete language and audio preparation still follows.')
