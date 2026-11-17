"""Synthetic immutable initial input; no original keys or game assets."""
import base64
import hashlib
import json

import pytest

from backend import wuthering_initial_seed as seed, wuthering_metadata as metadata
from backend import wuthering_release as release
from backend.preparation_errors import PreparationFailure
from backend.tests.test_wuthering_metadata import protected, encrypted_package
from backend.tests.test_wuthering_retained_preparation import original


@pytest.fixture
def initial(monkeypatch):
    raw = json.dumps({'owned': ['0x' + (b'a' * 32).hex(), '0x' + (b'b' * 32).hex()]}).encode()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    monkeypatch.setattr(seed, 'SIZE', len(raw))
    monkeypatch.setattr(seed, 'SHA256', hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(seed, 'BLOB', blob)
    monkeypatch.setattr(seed, 'URL', 'https://immutable.invalid/git/blobs/' + blob)
    wire = {'sha': blob, 'size': len(raw), 'encoding': 'base64',
            'content': base64.b64encode(raw).decode()}
    return raw, wire


def test_cold_seed_then_fresh_read_needs_no_community_request(tmp_path, monkeypatch, protected, initial):
    raw, wire = initial
    calls = []
    def fetch(url, *, limit):
        calls.append(url)
        assert url == seed.URL and url != release.PUBLIC_METADATA_URL and limit == seed.WIRE_LIMIT
        return json.dumps(wire).encode()
    monkeypatch.setattr(release, 'download', fetch)
    assert release._archive_parameters(tmp_path) == (b'a' * 32, b'b' * 32)
    assert not metadata.parameters(tmp_path)  # Candidate retention is not archive ownership.
    assert raw not in metadata._path(tmp_path, 'initial-seed').read_bytes()
    monkeypatch.setattr(release, 'download', lambda *a, **k: pytest.fail('Healthy updates use protected immutable seed'))
    assert release._archive_parameters(tmp_path) == (b'a' * 32, b'b' * 32)
    assert calls == [seed.URL]
    assert seed.provenance()['files']['keys.json']['sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('fault', ['blob', 'size', 'encoding', 'base64', 'changed-body', 'oversize'])
def test_modified_or_newer_seed_cannot_replace_retained_inputs(tmp_path, protected, initial, fault):
    _, wire = initial
    target = metadata._path(tmp_path, 'initial-seed')
    assert metadata._write(target, b'preserve existing invalid seed')
    before = target.read_bytes()
    if fault == 'blob': wire['sha'] = '0' * 40
    elif fault == 'size': wire['size'] += 1
    elif fault == 'encoding': wire['encoding'] = 'hex'
    elif fault == 'base64': wire['content'] = '@@'
    elif fault == 'changed-body': wire['content'] = base64.b64encode(b'newer candidates').decode()
    data = b' ' * (seed.WIRE_LIMIT + 1) if fault == 'oversize' else json.dumps(wire).encode()
    with pytest.raises(ValueError):
        seed.parameters(tmp_path, lambda *a, **k: data)
    assert target.read_bytes() == before and not metadata.parameters(tmp_path)


def test_interrupted_seed_publish_keeps_old_envelope_and_verified_fallback(tmp_path, monkeypatch, protected, initial):
    _, wire = initial
    assert metadata.remember_parameter(tmp_path, b'c' * 32, default_verified=True)
    path = metadata._path(tmp_path, 'verified-parameters'); before = path.read_bytes()
    monkeypatch.setattr(release, 'download', lambda *a, **k: json.dumps(wire).encode())
    monkeypatch.setattr(metadata, '_write', lambda *a, **k: False)
    assert release._archive_parameters(tmp_path) == (b'c' * 32,)
    assert path.read_bytes() == before and not metadata._path(tmp_path, 'initial-seed').exists()


def test_unknown_default_rotation_cannot_authorize_a_new_default(tmp_path, monkeypatch, protected, initial):
    _, wire = initial
    monkeypatch.setattr(release, 'download', lambda *a, **k: json.dumps(wire).encode())
    params = release._archive_parameters(tmp_path)
    original = encrypted_package(b'z' * 32)
    monkeypatch.setattr(release.pak, 'block', lambda u, total, offset, size: original[offset:offset+size])
    with pytest.raises(PreparationFailure) as failure:
        release._package(tmp_path, ('owned-default-rotation', len(original), 'owned-rotation'), params)
    assert failure.value.code == 'archive_parameters_missing'
    assert not metadata.parameters(tmp_path)


def test_ordinary_worker_unknown_default_preserves_existing_index_and_recording(original, monkeypatch, protected, initial):
    from backend import language_worker as worker, wuthering_assets as assets
    tools, _, _, _, _ = original
    payload = release.build_language(tools, 'en', ['zh-Hans'])
    output = tools / 'prepared-en.json'
    worker.write_payload('wuwa', payload, 'en', ['zh-Hans'], output)
    saved = tools / 'saved-owned-recording.bin'; saved.write_bytes(b'owned saved recording')
    before = output.read_bytes()
    _, wire = initial
    original_package = encrypted_package(b'z' * 32)
    monkeypatch.setattr(release.pak, 'block', lambda u, total, offset, size: original_package[offset:offset+size])
    def prepare(*args, **kwargs):
        params = seed.parameters(tools, lambda *a, **k: json.dumps(wire).encode())
        release._package(tools, ('owned-new-default', len(original_package), 'owned-new-default'), params)
        return payload
    monkeypatch.setattr(assets, 'index_language', prepare)
    with pytest.raises(PreparationFailure) as failure:
        worker.build('wuwa', None, tools, 'en', ['zh-Hans'], output)
    assert failure.value.code == 'archive_parameters_missing'
    assert output.read_bytes() == before and saved.read_bytes() == b'owned saved recording'
