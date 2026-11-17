"""Allowlisted data-only metadata candidates, with immutable original-source proofs.

Fetching a candidate never approves it. Callers must verify the complete original
resource before retaining a generation proof; downloaded source is never executed.
"""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.parse import quote

from .game_tools import _atomic_file
from .publisher_http import download

LIMIT = 256 * 1024
MAX_PROOFS = 512
SOURCES = {
    'archive': ('luk-gg/UnrealExporter', 'UnrealExporter/aes.txt', LIMIT),
    'localization': ('FabianFG/CUE4Parse',
                     'CUE4Parse/GameTypes/NTE/Encryption/NevernessToEvernessLocresEncryption.cs', LIMIT),
    'updater-global': ('Tobiichi-Origuchi/nte_patcher', 'tests/test_integration.rs', 64 * 1024),
    'updater-cn': ('kuaichu/game-cdn-archive', 'scripts/nte_downloader.py', 64 * 1024),
    'schema-index': ('555me/NTE-usmap', 'index.json', LIMIT),
}
KINDS = {'archive': 'archive-index', 'localization': 'localization',
         'updater-global': 'publisher-manifest', 'updater-cn': 'publisher-manifest',
         'schema-index': 'required-schema'}
_HINT_LOCK = threading.RLock()


def _check(condition):
    if not condition:
        raise ValueError('Compatible NTE update information could not be verified.')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw):
    _check(isinstance(raw, bytes) and 0 < len(raw) <= LIMIT)
    def pairs(rows):
        result = {}
        for key, value in rows:
            _check(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def reference(value):
    _check(isinstance(value, dict) and set(value) == {'family', 'revision', 'sha256'}
           and value['family'] in SOURCES)
    _check(isinstance(value['revision'], str) and re.fullmatch('[0-9a-f]{40}', value['revision'])
           and isinstance(value['sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['sha256']))
    return dict(value)


def _publish(path, raw):
    path = Path(path)
    try:
        if path.is_file() and path.read_bytes() == raw:
            return
        _atomic_file(path, raw)
    except PermissionError:
        if not path.is_file() or path.read_bytes() != raw:
            raise


@dataclass(frozen=True)
class Candidate:
    reference: dict
    data: bytes = field(repr=False)


def load(family, cache, *, retained=None, fetch=None):
    """Resolve one fixed repository/path; historical reads never query latest."""
    _check(family in SOURCES)
    fetch = fetch or download
    repository, path, limit = SOURCES[family]
    if retained is None:
        rows = _decode(fetch(f'https://api.github.com/repos/{repository}/commits?'
                             f'path={quote(path, safe="/")}&per_page=1', LIMIT))
        _check(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict))
        revision = rows[0].get('sha')
        _check(isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision))
    else:
        retained = reference(retained)
        _check(retained['family'] == family)
        revision = retained['revision']
    target = Path(cache) / 'sources' / family
    cached = target / (retained['sha256'] + '.data') if retained else None
    raw = cached.read_bytes() if cached is not None and cached.is_file() and cached.stat().st_size <= limit else b''
    if not raw or _sha(raw) != retained['sha256']:
        raw = fetch(f'https://raw.githubusercontent.com/{repository}/{revision}/{path}', limit)
    _check(isinstance(raw, bytes) and 0 < len(raw) <= limit)
    digest = _sha(raw)
    _check(retained is None or digest == retained['sha256'])
    _publish(target / (digest + '.data'), raw)
    return Candidate({'family': family, 'revision': revision, 'sha256': digest}, raw)


def retain(family, revision, digest, raw, cache):
    """Import an already hash-checked fixed description without a network request."""
    ref = reference({'family': family, 'revision': revision, 'sha256': digest})
    _check(isinstance(raw, bytes) and 0 < len(raw) <= SOURCES[family][2] and _sha(raw) == digest)
    _publish(Path(cache) / 'sources' / family / (digest + '.data'), raw)
    return Candidate(ref, raw)


def original(value):
    _check(isinstance(value, dict) and set(value) == {'region', 'branch', 'version', 'sha256'}
           and value['region'] in ('nte-global', 'nte-cn')
           and isinstance(value['branch'], str) and re.fullmatch(r'PC_[0-9]+', value['branch'])
           and isinstance(value['version'], str) and re.fullmatch(r'\d+\.\d+\.\d+', value['version'])
           and isinstance(value['sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['sha256']))
    return dict(value)


def _proof(value):
    _check(isinstance(value, dict) and set(value) == {'schema', 'source', 'original', 'verification'}
           and value['schema'] == 'nte-community-metadata-proof-v1')
    source = reference(value['source'])
    origin = original(value['original'])
    if source['family'].startswith('updater-'):
        _check(source['family'] == 'updater-' + origin['region'].removeprefix('nte-'))
    verification = value['verification']
    _check(isinstance(verification, dict) and set(verification) == {'kind', 'sha256'}
           and verification['kind'] == KINDS[source['family']] and isinstance(verification['sha256'], str)
           and re.fullmatch('[0-9a-f]{64}', verification['sha256']))
    return value


def remember(candidate, original, kind, verified_bytes, cache):
    """Retain evidence after the caller's complete original-resource validation.

    This publishes no active/current pointer and never replaces an older proof.
    The source reference and proof hash belong in the immutable publisher recipe.
    """
    _check(isinstance(candidate, Candidate) and isinstance(verified_bytes, bytes) and verified_bytes)
    _check(_sha(candidate.data) == reference(candidate.reference)['sha256'])
    value = _proof({'schema': 'nte-community-metadata-proof-v1', 'source': candidate.reference,
                    'original': original, 'verification': {'kind': kind, 'sha256': _sha(verified_bytes)}})
    raw = _json(value)
    digest = _sha(raw)
    hints = Path(cache) / 'candidates' / candidate.reference['family'] / original['region']
    if not any(hints.glob('*.json')):
        # Migrate every bounded legacy source before creating the first hint;
        # otherwise a newly retained source could hide an older usable one.
        known(candidate.reference['family'], cache, original['region'])
    _publish(Path(cache) / 'proofs' / candidate.reference['family'] / (digest + '.json'), raw)
    # This bounded lookup hint is not an activation pointer. Historical proofs
    # remain immutable; hundreds of ordinary updates reusing one description
    # must not exhaust a per-generation directory-scan budget.
    _hint(candidate.reference, digest, original['region'], cache)
    return {'source': dict(candidate.reference), 'proof_sha256': digest}


def _hint(source, digest, region, cache):
    target = (Path(cache) / 'candidates' / source['family'] / region /
              (_sha(_json(source)) + '.json'))
    def retained():
        if not target.is_file(): return False
        _check(0 < target.stat().st_size <= 8192)
        value = _decode(target.read_bytes())
        _check(isinstance(value, dict) and set(value) == {'source', 'proof_sha256'} and value['source'] == source)
        return True
    # One unchanged description can prove many archives concurrently. The
    # first complete proof is enough for discovery; never replace its hint
    # for each mounted archive or ordinary update on Windows.
    with _HINT_LOCK:
        if retained(): return
        try:
            _publish(target, _json({'source': dict(source), 'proof_sha256': digest}))
        except PermissionError:
            if not retained(): raise


def known(family, cache, region):
    """Previously proved candidates are hints; every new original needs validation."""
    _check(family in SOURCES and region in ('nte-global', 'nte-cn'))
    hints = sorted((Path(cache) / 'candidates' / family / region).glob('*.json'))
    _check(len(hints) <= MAX_PROOFS)
    paths = []
    for hint in hints:
        _check(hint.is_file() and 0 < hint.stat().st_size <= 8192)
        value = _decode(hint.read_bytes())
        _check(isinstance(value, dict) and set(value) == {'source', 'proof_sha256'})
        ref = reference(value['source'])
        _check(ref['family'] == family and hint.stem == _sha(_json(ref))
               and isinstance(value['proof_sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['proof_sha256']))
        paths.append((Path(cache) / 'proofs' / family / (value['proof_sha256'] + '.json'), ref))
    if not hints:
        # Upgrade the first receipt format; later updates use source hints.
        legacy = sorted((Path(cache) / 'proofs' / family).glob('*.json'))
        _check(len(legacy) <= MAX_PROOFS)
        paths = [(path, None) for path in legacy]
    refs = {}
    for path, expected in paths:
        _check(path.is_file() and 0 < path.stat().st_size <= 8192)
        raw = path.read_bytes()
        _check(path.stem == _sha(raw))
        value = _proof(_decode(raw))
        _check(value['source']['family'] == family and (expected is None or expected == value['source']))
        if value['original']['region'] == region:
            version = tuple(map(int, value['original']['version'].split('.')))
            key = _json(value['source'])
            if key not in refs or refs[key][0] < version:
                refs[key] = (version, value['source'], path.stem)
    if not hints:
        for _, ref, digest in refs.values():
            _hint(ref, digest, region, cache)
    ordered = sorted(refs.items(), key=lambda row: (row[1][0], row[0]), reverse=True)
    return [row[1][1] for row in ordered[:8]]


def check_receipt(value, original, cache):
    _check(isinstance(value, dict) and set(value) == {'source', 'proof_sha256'})
    source = reference(value['source'])
    digest = value['proof_sha256']
    _check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest))
    path = Path(cache) / 'proofs' / source['family'] / (digest + '.json')
    _check(path.is_file() and 0 < path.stat().st_size <= 8192)
    raw = path.read_bytes()
    _check(_sha(raw) == digest)
    proof = _proof(_decode(raw))
    _check(proof['source'] == source and proof['original'] == original)
    return proof
