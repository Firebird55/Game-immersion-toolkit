"""Immutable original-source candidates; owned files only, no client execution."""
import hashlib
from pathlib import Path

import pytest

from backend import nte_native_metadata as metadata, nte_release as release
from backend.tests.test_nte_seeded_schema import fixture


def setup(tmp_path, monkeypatch):
    seed, client, _, _ = fixture()
    raw = client.bytes()
    monkeypatch.setattr(metadata, 'SEED_SHA256', hashlib.sha256(seed).hexdigest())
    name = 'Client/RenamedProject/Native/Unfamiliar.DLL'
    digest = hashlib.md5(raw).hexdigest()
    item = release.File(len(raw), digest, len(raw) + 99, 'c' * 32, 99)
    value = dict(region='nte-global', branch='PC_500', version='5.0.1',
                 files={name: item, 'Client/Other/Tools.exe': release.File(4, 'd' * 32, 4, 'd' * 32, 0),
                        'Client/Content/A.pak': release.File(9, 'e' * 32, 9, 'e' * 32, 0)},
                 sections={'baseTag': [1000, '5.0.1'], 'ResList.bin': [123, 'a' * 64]})
    original = tmp_path / 'input.dat'
    original.write_bytes(raw)
    dependencies = {key: 'f' * 64 for key in metadata.DEPENDENCIES}
    return seed, value, name, original, dependencies


def test_renamed_packaged_original_generates_immutable_schema_and_complete_source_receipt(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    cache = tmp_path / 'candidates'
    result = metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    receipt = result.receipt
    assert receipt['native_path'] == name and receipt['native_file']['offset'] == 99
    assert receipt['appended'] == ['NewCaption'] and not receipt['production_eligible']
    assert receipt['uninspected_native_sources'] == ['Client/Other/Tools.exe']
    assert set(metadata.inventory(value)['files']) == set(value['files'])
    assert metadata.load(result.schema.reference, cache) == result
    assert metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies) == result
    assert not (cache / 'current.json').exists()
    # No source file or fixed seed is modified.
    assert hashlib.sha256(seed).hexdigest() == metadata.SEED_SHA256
    assert hashlib.md5(original.read_bytes()).hexdigest() == receipt['native_file']['digest']


def test_new_generation_and_failed_update_leave_old_candidate_readable(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    cache = tmp_path / 'candidates'
    old = metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    value['version'] = '5.0.2'
    current = metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    assert old.schema.reference != current.schema.reference
    before = {p.relative_to(cache): p.read_bytes() for p in cache.rglob('*') if p.is_file()}
    original.write_bytes(b'X' * original.stat().st_size)
    with pytest.raises(ValueError):
        metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    assert metadata.load(old.schema.reference, cache) == old
    assert metadata.load(current.schema.reference, cache) == current
    assert before == {p.relative_to(cache): p.read_bytes() for p in cache.rglob('*') if p.is_file()}


def test_partial_generation_is_never_visible_and_retry_recovers(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    cache = tmp_path / 'candidates'
    rename = Path.rename
    def interrupt(path, target):
        if path.name == 'candidate':
            raise OSError('owned interruption')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', interrupt)
    with pytest.raises(OSError, match='owned interruption'):
        metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    assert list(cache.iterdir()) == []
    monkeypatch.setattr(Path, 'rename', rename)
    result = metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    assert metadata.load(result.schema.reference, cache) == result


def test_ambiguous_positive_native_sources_are_rejected(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    second = 'Client/Alternate.exe'
    value['files'][second] = value['files'][name]
    with pytest.raises(ValueError):
        metadata.prepare(value, seed, {name: original, second: original}, tmp_path / 'c', dependencies=dependencies)
    assert not (tmp_path / 'c').exists()


def test_full_file_authentication_precedes_native_parser(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    original.write_bytes(b'Y' * original.stat().st_size)
    monkeypatch.setattr(metadata, 'refresh_seeded_native_types', lambda *_: pytest.fail('parsed unauthenticated bytes'))
    with pytest.raises(ValueError):
        metadata.prepare(value, seed, {name: original}, tmp_path / 'c', dependencies=dependencies)


def test_corrupted_retained_schema_is_rejected_without_rewriting(tmp_path, monkeypatch):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    cache = tmp_path / 'candidates'
    result = metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    path = cache / result.schema.reference['generation'] / 'schema.usmap'
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        metadata.load(result.schema.reference, cache)
    with pytest.raises(ValueError):
        metadata.prepare(value, seed, {name: original}, cache, dependencies=dependencies)
    assert path.read_bytes() == b'corrupt'


@pytest.mark.parametrize('bad', ['seed', 'dependency', 'path', 'range'])
def test_untrusted_identity_and_inventory_fields_fail_closed(tmp_path, monkeypatch, bad):
    seed, value, name, original, dependencies = setup(tmp_path, monkeypatch)
    if bad == 'seed': seed += b'x'
    elif bad == 'dependency': dependencies['reader'] = 'latest'
    elif bad == 'path': value['files']['Client/../escape.exe'] = value['files'].pop(name)
    else: value['files'][name] = release.File(5, 'a' * 32, 7, 'a' * 32, 3)
    with pytest.raises(ValueError):
        metadata.prepare(value, seed, {name: original}, tmp_path / 'c', dependencies=dependencies)


def test_original_acquisition_passes_exact_publisher_range_and_checks_complete_file(tmp_path, monkeypatch):
    _, value, name, original, _ = setup(tmp_path, monkeypatch)
    calls = []
    def save(region, branch, item, path):
        calls.append((region, branch, item))
        path.write_bytes(original.read_bytes())
    target = metadata.stage_original(value, name, tmp_path / 'native', save=save)
    assert calls == [('nte-global', 'PC_500', value['files'][name])]
    assert target.read_bytes() == original.read_bytes()
    metadata.stage_original(value, name, tmp_path / 'native', save=lambda *_: pytest.fail('redownloaded'))
    bad = tmp_path / 'bad'
    def wrong(_region, _branch, item, path): path.write_bytes(b'x' * item.size)
    with pytest.raises(ValueError):
        metadata.stage_original(value, name, bad, save=wrong)
    assert list(bad.iterdir()) == []
