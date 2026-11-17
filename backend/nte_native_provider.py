"""Original-publisher NTE metadata recipe and verified authoring preparation.

The immutable source snapshot describes the derivation before large native
downloads. The language worker materializes and validates it before returning
records. No current community index or mapping is part of this path.
"""
import hashlib
import json
from pathlib import Path
import tempfile

from . import nte_assets as assets, nte_native_baseline as baseline_source
from . import nte_native_metadata as metadata, nte_required_schema as required
from . import nte_release as release
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

KIND = 'nte-original-native-v1'
MAX_SOURCE_BYTES = 768 * 1024**2
MAX_SOURCE_FILES = 16
OUTPUTS = ('dialogue-events.json', 'sequence-cues.json', 'voice-events.json', 'movie-tables.json')
DIALOGUE_GRAPHS = True
ORIGINAL_AUTHORING = True
AUTHORING = 'nte-original-authoring-v1'


def discovery(snapshot):
    return metadata.inventory({key: snapshot[key] for key in ('region', 'branch', 'version', 'sections')}
                              | {'files': snapshot['publisher_files']})


def source_reference(value, reader, *, dialogue_graphs=None, original_authoring=None):
    normalized = metadata.inventory(value)
    metadata._digest(reader)
    graphs = DIALOGUE_GRAPHS if dialogue_graphs is None else dialogue_graphs
    authoring = ORIGINAL_AUTHORING and graphs if original_authoring is None else original_authoring
    metadata._check(isinstance(graphs, bool) and isinstance(authoring, bool) and (not authoring or graphs))
    return {'kind': KIND, 'generator': metadata.CLASS_GENERATOR if graphs else metadata.ENUM_GENERATOR,
            'validator': required.CLASS_VALIDATOR if graphs else required.VALIDATOR,
            'inventory_sha256': hashlib.sha256(metadata._json(normalized)).hexdigest(),
            'seed_sha256': metadata.SEED_SHA256, 'reader_sha256': reader,
            'baseline_inventory_sha256': baseline_source.BASELINE['inventory_sha256'],
            'baseline_native_sha256': baseline_source.BASELINE['native_sha256'],
            **({'authoring': AUTHORING} if authoring else {})}


def seed(cache):
    cache = Path(cache)
    path = cache / (metadata.SEED_SHA256 + '.usmap')
    raw = path.read_bytes() if path.is_file() and path.stat().st_size <= metadata.MAX_SEED else b''
    if hashlib.sha256(raw).hexdigest() != metadata.SEED_SHA256:
        raw = assets.download(assets.TABLE_SCHEMA_URL, limit=metadata.MAX_SEED)
    metadata._check(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == metadata.SEED_SHA256)
    metadata._seed(raw)
    if not path.exists() or path.read_bytes() != raw: _atomic_file(path, raw)
    return raw


def _order(candidates, lineage, prior=None):
    first = [name for name in (prior, lineage) if name in candidates]
    remaining = sorted(candidates, key=lambda name: (Path(name).suffix.lower() != '.exe', -candidates[name].size, name))
    return list(dict.fromkeys(first + remaining))


def _profile(path, source, snapshot, cache):
    if not path.exists(): return None
    metadata._check(path.is_file() and path.stat().st_size <= metadata.MAX_RECEIPT)
    value = json.loads(path.read_bytes())
    metadata._check(isinstance(value, dict) and set(value) == {'source', 'snapshot', 'candidate', 'native_path', 'validation'}
                    and value['source'] == source and value['snapshot'] == snapshot)
    candidate = metadata.load(value['candidate'], cache)
    metadata._check(candidate.receipt['source_manifest_sha256'] == source['inventory_sha256']
                    and candidate.receipt['generator'] == source['generator']
                    and candidate.receipt['dependencies']['reader'] == source['reader_sha256']
                    and candidate.receipt['baseline_sha256'] == source['baseline_native_sha256']
                    and candidate.receipt['native_path'] == value['native_path'])
    metadata._digest(value['validation'])
    receipt = Path(cache)/'validations'/(value['validation']+'.json')
    metadata._check(receipt.is_file() and receipt.stat().st_size <= metadata.MAX_RECEIPT
                    and hashlib.sha256(receipt.read_bytes()).hexdigest() == value['validation'])
    return value


def _registry(catalog):
    names = [row[2] for row in catalog.locations.values()
             if row and row[2].endswith('/AssetRegistry.bin') and catalog.location(row[2])]
    metadata._check(len(names) == 1)
    _, archive, path = catalog.location(names[0])
    metadata._check(0 < archive.entry(path).size <= 256*1024**2)
    return catalog.read(path)


def read_authoring(catalog, executable, staging, progress=lambda _: None):
    """Resolve original native metadata and validate this extraction's closure.

    A manifest-derived lineage entry is only a hint. Renamed/failed candidates
    use a deterministic generic PE order with explicit aggregate file/byte
    bounds. A partial plugin cannot return authoring without passing the actual
    complete managed lookup closure. Every candidate remains installation-free.
    """
    from .nte_publisher import _reader_identity
    value = catalog.snapshot
    metadata._check(value['reader'] == _reader_identity())
    original = discovery(value)
    graphs = value['type_schema'].get('generator') == metadata.CLASS_GENERATOR
    authoring = value['type_schema'].get('authoring') == AUTHORING
    reference = source_reference(original, value['reader'], dialogue_graphs=graphs, original_authoring=authoring)
    metadata._check(value['type_schema'] == reference)
    cache = catalog.cache/'native-candidates'
    profile_path = catalog.cache/'native-epochs'/catalog.stamp/'profile.json'
    prior = _profile(profile_path, reference, catalog.stamp, cache)
    if 'original_updater' in value:
        from . import nte_updater_source as official
        baseline_parameters = official.parameters_for_reference(value['original_updater'], catalog.cache/'format')
        baseline = baseline_source.load(catalog.cache/'native-baseline', parameters=baseline_parameters)
    else:
        baseline = baseline_source.load(catalog.cache/'native-baseline')
    mapping_seed = seed(catalog.cache/'native-seed')
    registry = _registry(catalog) if graphs else None
    containers = catalog.containers()
    if graphs:
        from .nte_graph_prefetch import prefetch
        with tempfile.TemporaryDirectory(prefix='native-inventory-', dir=staging.parent) as temporary:
            packages = assets.read_dialogue_inventory(catalog.cache/'empty-context', executable, Path(temporary),
                containers, catalog.reader_keys() if hasattr(catalog, 'reader_keys') else catalog.format.parameters[catalog.region], registry,
                **({'capture_original_authoring': True} if authoring else {}))
        prefetch(containers, packages, progress)
    candidates = metadata.sources(original)
    dependencies = {'reader': value['reader'], 'archive_parameters': value['archive'][1],
                    'localization_parameters': value['localization'][1],
                    'updater_format': (hashlib.sha256(metadata._json(value['original_updater'])).hexdigest()
                        if 'original_updater' in value else
                        hashlib.sha256(metadata._json(value['updater_metadata'])).hexdigest()
                        if 'updater_metadata' in value else
                        (release.CN_FORMAT if catalog.region == 'nte-cn' else release.GLOBAL_FORMAT)[1])}
    charged, attempts = 0, 0
    for name in _order(candidates, baseline.identity['native_path'], prior['native_path'] if prior else None):
        item = candidates[name]
        if attempts >= MAX_SOURCE_FILES or charged + item.size > MAX_SOURCE_BYTES:
            break
        charged += item.size; attempts += 1
        progress('Checking original NTE format metadata for this publisher version')
        try:
            retained = catalog.cache/'native-baseline'/'originals'/(item.digest+'.native')
            if retained.is_file() and item.digest == baseline.identity['native_md5']:
                path = retained
            else:
                path = metadata.stage_original(original, name, catalog.cache/'native-originals')
            candidate = metadata.prepare(original, mapping_seed, {name: path}, cache,
                                         dependencies=dependencies, baseline=baseline, native_classes=graphs)
            with tempfile.TemporaryDirectory(prefix='native-tables-', dir=staging.parent) as temporary:
                output = Path(temporary)
                usage = assets.run_publisher_reader(catalog.cache/'empty-context', executable, output,
                    containers, catalog.reader_keys() if hasattr(catalog, 'reader_keys') else catalog.format.parameters[catalog.region], schema_cache=catalog.cache/'schemas',
                    table_schema=candidate.schema, capture_schema_usage=True,
                    capture_dialogue_graphs=graphs, dialogue_registry=registry,
                    **({'capture_original_authoring': True} if authoring else {}))
                if graphs and usage['schema'] != 'nte-schema-usage-v2':
                    raise ValueError('Missing current graph codec evidence')
                report, validation = metadata.check_required(candidate.schema.reference, cache, mapping_seed,
                    baseline, path, usage['lookups'], reader_classes=usage['classes'],
                    reader_codecs=usage.get('codecs') if graphs else None)
                if not report.eligible:
                    # An explicit complete required-closure rejection may
                    # identify a partial native owner. I/O/reader failures
                    # supply no such evidence and must never reach fallback.
                    continue
                resolved = {'source': reference, 'snapshot': catalog.stamp, 'candidate': candidate.schema.reference,
                            'native_path': name, 'validation': validation}
                encoded = metadata._json(resolved)
                if profile_path.exists():
                    metadata._check(profile_path.read_bytes() == encoded)
                else:
                    _atomic_file(profile_path, encoded)
                for filename in (*OUTPUTS, *(('dialogue-graphs.json',) if graphs else ()),
                                 *(('original-authoring.json',) if authoring else ())):
                    metadata._check(not (staging/filename).exists())
                    (staging/filename).write_bytes((output/filename).read_bytes())
                if graphs:
                    metadata._check(not (staging/'dialogue.usmap').exists())
                    (staging/'dialogue.usmap').write_bytes(candidate.schema.data)
                return candidate.schema.reference, validation
        except metadata.NativeDerivationRejected:
            continue
        except PreparationFailure:
            raise
        except (OSError, ValueError, TypeError, KeyError):
            raise PreparationFailure('game_metadata_unavailable',
                'Original NTE metadata could not be read or verified. Retry preparation; '
                'the previous completed index is retained.') from None
    raise PreparationFailure('game_metadata_unavailable',
        'Original NTE format metadata could not be verified within the bounded source search. '
        'The previous completed index is retained.')
