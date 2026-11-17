"""Original input authentication and transactional metadata lifecycle."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import starrail_metadata as metadata


def fixture(monkeypatch, generation=1):
    assets = {}
    for role, name in metadata.NAMES.items():
        data = f'authored {role} generation {generation}'.encode()
        asset = SimpleNamespace(name='relocated/official/' + name, size=len(data), digest=hashlib.md5(data).hexdigest())
        asset.read = lambda cache, start, length, data=data: data[start:start + length]
        assets[asset.name] = asset
    monkeypatch.setattr(metadata.sophon, 'manifest', lambda *args: assets)
    build = {'channel': 'starrail-global', 'manifests': {'game': ['https://official.invalid', 'manifest', 1, 1, str(generation), 'chunks']}}
    def run(operation, inputs, outputs, *, work):
        assert operation == 'metadata'
        assert all((inputs / name).is_file() for name in metadata.CANONICAL.values())
        outputs.mkdir()
        (outputs / 'dump.cs').write_text('authored metadata fixture')
        (outputs / 'stringliterals.json').write_text('[]')
    return build, SimpleNamespace(identity='authored-frozen-helper', run=run), assets


def test_complete_inputs_and_output_hashes_are_rechecked_before_cache_reuse(tmp_path, monkeypatch):
    build, reader, assets = fixture(monkeypatch)
    first = metadata.prepare(tmp_path, build, reader=reader)
    assert len(first.receipt['identity']['files']) == 3
    for role, name in metadata.CANONICAL.items():
        assert (first.inputs / name).read_bytes() == f'authored {role} generation 1'.encode()
    reader.run = lambda *a, **k: pytest.fail('Verified metadata must be reusable without rerunning the helper')
    second = metadata.prepare(tmp_path, build, reader=reader)
    assert second.outputs == first.outputs
    for asset in assets.values():
        asset.read = lambda *a: pytest.fail('Verified whole inputs must reuse their authenticated cache')
    assert metadata.prepare(tmp_path, build, reader=reader).receipt == first.receipt


def test_changed_generation_failure_preserves_old_outputs_and_receipt(tmp_path, monkeypatch):
    build, reader, _ = fixture(monkeypatch)
    first = metadata.prepare(tmp_path, build, reader=reader)
    before = (tmp_path / 'current.json').read_bytes()
    changed, reader, _ = fixture(monkeypatch, 2)
    def fail(operation, inputs, output, *, work):
        output.mkdir(); (output / 'dump.cs').write_text('incomplete')
        raise ValueError('authored interrupted helper')
    reader.run = fail
    with pytest.raises(ValueError):
        metadata.prepare(tmp_path, changed, reader=reader)
    assert (tmp_path / 'current.json').read_bytes() == before
    assert (first.outputs / 'dump.cs').read_text() == 'authored metadata fixture'
    _, reader, assets = fixture(monkeypatch, 2)
    for asset in assets.values():
        asset.read = lambda *a: pytest.fail('Interrupted metadata must retain verified immutable native inputs')
    repaired = metadata.prepare(tmp_path, changed, reader=reader)
    assert repaired.receipt['identity'] != first.receipt['identity']
    assert repaired.outputs != first.outputs


def test_chunk_success_cannot_substitute_for_whole_file_integrity(tmp_path, monkeypatch):
    build, reader, assets = fixture(monkeypatch)
    asset = next(iter(assets.values()))
    asset.read = lambda cache, start, length: b'x' * length
    with pytest.raises(ValueError):
        metadata.prepare(tmp_path, build, reader=reader)
    assert not (tmp_path / 'current.json').exists()
    assert not (tmp_path / 'native-files' / asset.digest).exists()


def test_source_helper_is_never_consulted_by_frozen_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(metadata, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    expected = SimpleNamespace(executable=tmp_path / 'StarRailMetadata.exe', source_identity='authored-closed-identity', manifest={'build_id': 'authored-build'})
    monkeypatch.setattr(metadata, 'prebuilt_reader', lambda kind, layout: expected)
    result = metadata.helper(tmp_path / 'absent-source-cache')
    assert result.command == (str(expected.executable),)
    assert not (tmp_path / 'absent-source-cache').exists()


def test_cache_only_probe_never_generates_unapproved_metadata(tmp_path, monkeypatch):
    build, reader, assets = fixture(monkeypatch)
    run = reader.run
    reader.run = lambda *a, **k: pytest.fail('Unapproved metadata generation')
    with pytest.raises(ValueError, match='not prepared'):
        metadata.prepare(tmp_path, build, reader=reader, allow_generate=False)
    assert not (tmp_path / 'native-files').exists()
    reader.run = run
    prepared = metadata.prepare(tmp_path, build, reader=reader)
    reader.run = lambda *a, **k: pytest.fail('Unapproved metadata regeneration')
    assert metadata.prepare(tmp_path, build, reader=reader, allow_generate=False).outputs == prepared.outputs
    (prepared.outputs / 'dump.cs').write_text('corrupt')
    with pytest.raises(ValueError, match='not prepared'):
        metadata.prepare(tmp_path, build, reader=reader, allow_generate=False)
