"""Experimental immutable metadata candidates from authenticated original files.

No current-generation pointer, default provider or community latest index is
changed here. Original files are read as data, never loaded or executed. The
caller supplies a coherent publisher discovery and explicitly frozen parameter
and reader identities; this module does not derive new archive/localization keys.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile

from . import nte_release as release
from .nte_native_schema import MAX_CLIENT, MAX_SEED, _check, _seed
from .nte_seeded_schema import refresh_seeded_native_types
from .nte_type_metadata import Schema

SEED_SHA256 = '7651a4e56f79b2c6c9d7bde31a8dadbfc929b2e923691461c6970ce0bdb0ff58'
GENERATOR = 'nte-seeded-native-v2'
DEPENDENCIES = {'reader', 'archive_parameters', 'localization_parameters', 'updater_format'}
MAX_FILES = 200_000
MAX_RECEIPT = 16 * 1024**2
MAX_INSPECTED_SOURCES = 64
MAX_INSPECTED_BYTES = 2 * 1024**3


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value, length=64):
    _check(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value))
    return value


def inventory(discovery):
    """Preserve the complete original inventory, including non-asset files.

    Native candidates use file-format suffixes, not a game executable/path or
    version allowlist. This only identifies candidates, not their semantics.
    """
    _check(isinstance(discovery, dict) and set(discovery) == {'region', 'branch', 'version', 'files', 'sections'})
    _check(discovery['region'] in release.HOSTS and isinstance(discovery['branch'], str)
           and re.fullmatch(r'PC_[0-9]+', discovery['branch'])
           and isinstance(discovery['version'], str) and re.fullmatch(r'\d+\.\d+\.\d+', discovery['version']))
    files = discovery['files']
    _check(isinstance(files, dict) and 0 < len(files) <= MAX_FILES)
    normalized = {}
    for name, descriptor in files.items():
        _check(isinstance(name, str) and name.startswith('Client/') and '\\' not in name
               and name == str(PurePosixPath(name)) and '..' not in PurePosixPath(name).parts)
        row = asdict(descriptor) if isinstance(descriptor, release.File) else descriptor
        _check(isinstance(row, dict) and set(row) == {'size', 'digest', 'object_size', 'object_digest', 'offset'})
        _check(all(type(row[key]) is int for key in ('size', 'object_size', 'offset'))
               and 0 < row['size'] <= row['object_size'] < 2**63
               and 0 <= row['offset'] <= row['object_size'] - row['size'])
        _digest(row['digest'], 32); _digest(row['object_digest'], 32)
        normalized[name] = dict(row)
    sections = discovery['sections']
    _check(isinstance(sections, dict) and len(sections) <= 1024)
    for name, value in sections.items():
        _check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name)
               and (isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+', value)
                    or isinstance(value, list) and len(value) == 2 and type(value[0]) is int
                    and 0 <= value[0] < 2**63 and isinstance(value[1], str)
                    and re.fullmatch(r'\d+\.\d+\.\d+|[0-9a-f]{64}', value[1])))
    value = {**discovery, 'files': normalized,
             'sections': {name: list(row) if isinstance(row, list) else row for name, row in sections.items()}}
    raw = _json(value)
    _check(len(raw) <= MAX_RECEIPT)
    return value


def sources(discovery):
    """List all original PE candidates; selection requires structural evidence."""
    value = inventory(discovery)
    return {name: release.File(**row) for name, row in value['files'].items()
            if PurePosixPath(name).suffix.lower() in ('.exe', '.dll') and row['size'] <= MAX_CLIENT}


def _original(path, descriptor):
    path = Path(path)
    _check(path.is_file() and path.stat().st_size == descriptor.size <= MAX_CLIENT)
    raw = path.read_bytes()
    # Authenticate every byte before any PE or reflection parsing.
    _check(hashlib.md5(raw).hexdigest() == descriptor.digest)
    return raw


def stage_original(discovery, name, cache, *, save=None):
    """Fetch a chosen original candidate, bounded by its manifest descriptor.

    Source selection/budget is deliberately a separate decision. No downloaded
    code is executed. Even retained files are checked against the full-file MD5.
    """
    value = inventory(discovery)
    candidates = sources(value)
    _check(name in candidates)
    item = candidates[name]
    target = Path(cache) / (item.digest + '.native')
    if target.exists():
        _original(target, item)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        staged = Path(temporary) / 'original'
        (save or release.save_file)(value['region'], value['branch'], item, staged)
        _original(staged, item)
        staged.rename(target)
    return target


@dataclass(frozen=True)
class Candidate:
    schema: Schema
    receipt: dict


def prepare(discovery, seed_usmap, originals, cache, *, dependencies):
    """Generate one immutable candidate from available original PE sources.

    Only a unique structurally witnessed source is eligible. Missing candidates
    remain explicit, so a partial source scan is never evidence of complete
    game coverage. This API never writes a latest/current pointer.
    """
    value = inventory(discovery)
    _check(isinstance(seed_usmap, bytes))
    _check(_sha(seed_usmap) == SEED_SHA256)
    _seed(seed_usmap)
    _check(isinstance(dependencies, dict) and set(dependencies) == DEPENDENCIES)
    for digest in dependencies.values():
        _digest(digest)
    available = sources(value)
    _check(isinstance(originals, dict) and 0 < len(originals) <= MAX_INSPECTED_SOURCES
           and set(originals) <= available.keys()
           and sum(available[name].size for name in originals) <= MAX_INSPECTED_BYTES)
    inspected, positive = [], []
    for name, path in sorted(originals.items()):
        raw = _original(path, available[name])
        inspected.append(name)
        try:
            result = refresh_seeded_native_types(seed_usmap, raw)
        except ValueError:
            # Unsupported/non-PE candidates are not positive schema witnesses.
            continue
        if result.native_count and result.matched_seed_types >= 2 and result.callbacks:
            positive.append((name, result))
    _check(len(positive) == 1)
    name, result = positive[0]
    data = result.data
    _check(len(data) <= MAX_SEED)
    _seed(data)
    source = _json(value)
    identity = {'generator': GENERATOR, 'source_manifest_sha256': _sha(source),
                'native_sha256': result.client_sha256, 'seed_sha256': result.seed_sha256,
                'dependencies': dict(dependencies), 'inspected_native_sources': inspected}
    generation = _sha(_json(identity))
    reference = {'native_generator': GENERATOR, 'generation': generation, 'sha256': _sha(data)}
    receipt = {**identity, 'reference': reference, 'native_path': name,
               'native_file': asdict(available[name]), 'inspected_native_sources': inspected,
               'uninspected_native_sources': sorted(available.keys() - originals.keys()),
               'native_count': result.native_count, 'matched_seed_types': result.matched_seed_types,
               'appended': list(result.appended), 'refreshed': list(result.refreshed),
               'excluded': [{'name': row.name, 'reasons': list(row.reasons)} for row in result.excluded],
               'enum_values_refreshed': False, 'production_eligible': False}
    encoded = _json(receipt)
    _check(len(encoded) <= MAX_RECEIPT)
    root = Path(cache)
    destination = root / generation
    if destination.exists():
        existing = load(reference, root)
        _check(existing.receipt == receipt and existing.schema.data == data
               and (destination / 'source.json').read_bytes() == source)
        return existing
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        staged = Path(temporary) / 'candidate'
        staged.mkdir()
        (staged / 'schema.usmap').write_bytes(data)
        (staged / 'receipt.json').write_bytes(encoded)
        (staged / 'source.json').write_bytes(source)
        # The generation is visible only after all three files are complete.
        staged.rename(destination)
    return load(reference, root)


def load(reference, cache):
    """Read a retained candidate without network access or regeneration."""
    _check(isinstance(reference, dict) and set(reference) == {'native_generator', 'generation', 'sha256'}
           and reference['native_generator'] == GENERATOR)
    _digest(reference['generation']); _digest(reference['sha256'])
    root = Path(cache) / reference['generation']
    for name, limit in [('schema.usmap', MAX_SEED), ('receipt.json', MAX_RECEIPT), ('source.json', MAX_RECEIPT)]:
        _check((root / name).is_file() and (root / name).stat().st_size <= limit)
    data = (root / 'schema.usmap').read_bytes()
    _check(_sha(data) == reference['sha256'])
    _seed(data)
    receipt = json.loads((root / 'receipt.json').read_bytes())
    identity = {key: receipt[key] for key in ('generator', 'source_manifest_sha256', 'native_sha256', 'seed_sha256', 'dependencies', 'inspected_native_sources')}
    _check(receipt['reference'] == reference and _sha(_json(identity)) == reference['generation']
           and receipt['generator'] == GENERATOR and receipt['seed_sha256'] == SEED_SHA256
           and receipt['production_eligible'] is False and receipt['enum_values_refreshed'] is False)
    raw_source = (root / 'source.json').read_bytes()
    _check(_sha(raw_source) == receipt['source_manifest_sha256'])
    source = inventory(json.loads(raw_source))
    _check(receipt['native_file'] == source['files'][receipt['native_path']])
    return Candidate(Schema(dict(reference), data), receipt)
