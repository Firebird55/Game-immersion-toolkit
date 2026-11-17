"""Original signed-index proofs gate metadata fallback and mixed patch keys."""
import hashlib
import json

import pytest

from backend import nte_archive_keys as keys, nte_archive_metadata as metadata
from backend import nte_community_metadata as community, nte_publisher_pak as pak, nte_release as release
from backend.preparation_errors import PreparationFailure
from backend.tests import test_nte_publisher_pak as fixtures


def description(key):
    return (f'Neverness to Everness (global) 0x{key.hex()}\n'
            f'Neverness to Everness (chinese) 0x{bytes(32).hex()}\n').encode()


def fixture(tmp_path, monkeypatch, *, new_key=None):
    old_key = bytes(range(32))
    new_key = bytes(reversed(range(32))) if new_key is None else new_key
    cache = tmp_path/'format'
    raw = description(old_key)
    primary = metadata.load(revision='a'*40, digest=hashlib.sha256(raw).hexdigest(),
                            cache=cache, fetch=lambda *_: raw)
    original = {'region': 'nte-global', 'branch': 'PC_150', 'version': '1.5.4', 'sha256': 'c'*64}
    ring = keys.KeyRing(primary, cache/'community', original, allow_community_fallback=True)
    rows = []
    for key, name in [(old_key, 'base.wem'), (new_key, 'patch.wem')]:
        monkeypatch.setattr(fixtures, 'KEY', key)
        data = fixtures.package([(name, b'owned complete recording', 0, False, False)])
        sig = fixtures.signature(data)
        rows.append((data, sig, fixtures.descriptor(data), fixtures.descriptor(sig)))
    payloads = {record.digest: raw for data, sig, item, signature in rows
                for record, raw in [(item, data), (signature, sig)]}
    def read(region, branch, record, position, length):
        assert region == original['region'] and branch == original['branch']
        return payloads[record.digest][position:position+length]
    monkeypatch.setattr(release, 'read_range', read)
    requests = []
    def fetch(url, limit):
        requests.append(url)
        if 'api.github.com/repos/luk-gg/UnrealExporter/commits?' in url:
            return json.dumps([{'sha': 'b'*40}]).encode()
        assert url == 'https://raw.githubusercontent.com/luk-gg/UnrealExporter/'+'b'*40+'/UnrealExporter/aes.txt'
        return description(new_key)
    monkeypatch.setattr(community, 'download', fetch)
    sources = [pak.SignedSource(original['region'], original['branch'], item, signature, tmp_path/'ranges')
               for _, _, item, signature in rows]
    return ring, sources, requests, old_key, new_key


def test_old_base_and_rotated_patch_keep_separate_complete_index_proofs(tmp_path, monkeypatch):
    ring, sources, requests, old, new = fixture(tmp_path, monkeypatch)
    first = pak.Archive(sources[0], ring)
    assert requests == [] and first.read('HT/Content/base.wem') == b'owned complete recording'
    second = pak.Archive(sources[1], ring)
    assert len(requests) == 2 and second.read('HT/Content/patch.wem') == b'owned complete recording'
    assert ring.proved_keys([first, second]) == ['0x'+old.hex(), '0x'+new.hex()]
    assert len(ring.bindings) == 2
    assert ring.bindings[first.source.item.digest]['metadata']['source']['revision'] == 'a'*40
    assert ring.bindings[second.source.item.digest]['metadata']['source']['revision'] == 'b'*40
    assert ring.bindings[first.source.item.digest]['key_sha256'] != ring.bindings[second.source.item.digest]['key_sha256']
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Verified source refreshed latest'))
    again = keys.KeyRing(ring.primary, ring.cache, ring.original, allow_community_fallback=True)
    reopened = pak.Archive(sources[1], again)
    assert reopened.read('HT/Content/patch.wem') == b'owned complete recording'


def test_wrong_region_or_original_generation_cannot_supply_a_cipher(tmp_path, monkeypatch):
    ring, sources, requests, _, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(PreparationFailure):
        ring.verified_key(sources[0].read, sources[0].item.size, 'nte-cn', source=sources[0])
    sources[0].branch = 'PC_149'
    with pytest.raises((AssertionError, PreparationFailure)):
        pak.Archive(sources[0], ring)
    assert not ring.bindings and requests == []


def test_acquisition_timeout_never_queries_metadata(tmp_path, monkeypatch):
    ring, sources, requests, _, _ = fixture(tmp_path, monkeypatch)
    sources[0].read = lambda *_: (_ for _ in ()).throw(TimeoutError('owned source acquisition'))
    with pytest.raises(TimeoutError):
        pak.Archive(sources[0], ring)
    assert requests == [] and not ring.bindings


def test_default_rotation_does_not_skip_unresolved_official_key_derivation(tmp_path, monkeypatch):
    ring, sources, requests, _, _ = fixture(tmp_path, monkeypatch)
    ordinary = keys.KeyRing(ring.primary, ring.cache, ring.original)
    with pytest.raises(metadata.ArchiveParameterMismatch): pak.Archive(sources[1], ordinary)
    assert requests == [] and not ordinary.bindings


def test_unproved_key_cannot_enter_the_managed_reader_set(tmp_path, monkeypatch):
    ring, sources, _, _, _ = fixture(tmp_path, monkeypatch)
    archive = pak.Archive(sources[0], ring)
    ring.bindings.clear()
    with pytest.raises(PreparationFailure):
        ring.proved_keys([archive])


def test_sealed_original_profile_reopens_without_latest_and_rejects_receipt_swap(tmp_path, monkeypatch):
    ring, sources, _, _, _ = fixture(tmp_path, monkeypatch)
    pak.Archive(sources[0], ring); pak.Archive(sources[1], ring)
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Sealed profile consulted latest'))
    sealed = keys.KeyRing(None, ring.cache, ring.original, sealed=ring.bindings)
    assert pak.Archive(sources[1], sealed).read('HT/Content/patch.wem') == b'owned complete recording'
    import copy
    changed = copy.deepcopy(ring.bindings)
    changed[sources[1].item.digest]['metadata'] = changed[sources[0].item.digest]['metadata']
    with pytest.raises(PreparationFailure):
        pak.Archive(sources[1], keys.KeyRing(None, ring.cache, ring.original, sealed=changed))


def test_source_hint_migration_preserves_all_legacy_candidates(tmp_path):
    import shutil
    candidates = [community.retain('archive', char*40, hashlib.sha256(char.encode()).hexdigest(),
                                  char.encode(), tmp_path) for char in ('a', 'b', 'c')]
    origin = {'region': 'nte-global', 'branch': 'PC_9', 'version': '9.0.1', 'sha256': 'd'*64}
    for candidate in candidates[:2]: community.remember(candidate, origin, 'archive-index', b'index', tmp_path)
    shutil.rmtree(tmp_path/'candidates')
    community.remember(candidates[2], origin, 'archive-index', b'index', tmp_path)
    assert {ref['revision'] for ref in community.known('archive', tmp_path, 'nte-global')} == {'a'*40, 'b'*40, 'c'*40}


def test_repeated_original_updates_do_not_exhaust_historical_proof_budget(tmp_path):
    candidate = community.retain('updater-global', 'a'*40, hashlib.sha256(b'owned description').hexdigest(),
                                 b'owned description', tmp_path)
    for revision in range(community.MAX_PROOFS+1):
        community.remember(candidate, {'region': 'nte-global', 'branch': 'PC_9',
            'version': f'9.0.{revision}', 'sha256': hashlib.sha256(str(revision).encode()).hexdigest()},
            'publisher-manifest', f'owned verified manifest {revision}'.encode(), tmp_path)
    assert community.known('updater-global', tmp_path, 'nte-global') == [candidate.reference]
    assert len(list((tmp_path/'proofs/updater-global').glob('*.json'))) == community.MAX_PROOFS+1


def test_parallel_original_index_proofs_publish_one_retained_source_hint(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    raw = b'one owned description'
    candidate = community.retain('archive', 'a'*40, hashlib.sha256(raw).hexdigest(), raw, tmp_path)
    original = {'region': 'nte-global', 'branch': 'PC_150', 'version': '1.5.4', 'sha256': 'b'*64}
    with ThreadPoolExecutor(max_workers=8) as pool:
        proofs = list(pool.map(lambda i: community.remember(candidate, original, 'archive-index',
                                                          f'original index {i}'.encode(), tmp_path), range(32)))
    assert len({proof['proof_sha256'] for proof in proofs}) == 32
    assert community.known('archive', tmp_path, 'nte-global') == [candidate.reference]
    assert len(list((tmp_path/'candidates/archive/nte-global').glob('*.json'))) == 1
