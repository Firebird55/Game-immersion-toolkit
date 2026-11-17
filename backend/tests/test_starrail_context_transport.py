"""Explicit caller transport survives each original preparation boundary."""
import base64
import hashlib
from types import SimpleNamespace

import pytest

from backend import starrail_metadata as metadata, starrail_original_discovery as discovery
from backend import starrail_original_tables as tables
from backend.tests.test_starrail_metadata import fixture as metadata_fixture
from backend.tests.test_starrail_original_discovery import fixture as discovery_fixture, text, uint


def test_metadata_manifest_and_all_input_reads_keep_the_same_context(tmp_path, monkeypatch):
    build, reader, assets = metadata_fixture(monkeypatch)
    calls = []
    def fetch(url, *, limit):
        calls.append(url)
        return ('authored ' + url + ' generation 1').encode()[:limit]
    def manifest(*args, **kwargs):
        assert kwargs == {'fetch': fetch}
        return assets
    monkeypatch.setattr(metadata.sophon, 'manifest', manifest)
    for role, asset in zip(metadata.NAMES, assets.values()):
        def read(directory, start, length, *, fetch, role=role):
            assert start == 0
            return fetch(role, limit=length)
        asset.read = read
    prepared = metadata.prepare(tmp_path, build, reader=reader, fetch=fetch)
    assert calls == list(metadata.NAMES) and prepared.outputs.is_dir()


def test_source_helper_cannot_implicitly_build_or_fetch_software_in_data_service(tmp_path, monkeypatch):
    monkeypatch.setattr(metadata, 'discover_layout', lambda: SimpleNamespace(mode='source'))
    monkeypatch.setattr(metadata, '_run', lambda *a, **k: pytest.fail('Implicit helper build'))
    with pytest.raises(ValueError, match='not prepared'):
        metadata.helper(tmp_path, allow_build=False)
    assert not (tmp_path / 'software').exists()


def test_original_dispatch_bootstrap_and_all_markers_use_only_explicit_fetch(tmp_path, monkeypatch):
    protobuf_get = discovery._protobuf_get
    build, description, state, files = discovery_fixture(tmp_path, monkeypatch)
    request, marker = discovery._protobuf_get, discovery.hotfix.download
    calls = []
    def fetch(url, *, limit):
        calls.append(url)
        if '/query_' in url:
            rows = request(url)
            data = b''.join(text(number, value) if wire == 2 else uint(number << 3) + uint(value)
                            for number, wire, value in rows)
            return base64.b64encode(data)
        return marker(url, limit=limit)
    for asset in files.values():
        old = asset.read
        def read(directory, start, length, *, fetch, old=old):
            assert fetch is explicit_fetch
            return old(directory, start, length)
        asset.read = read
    explicit_fetch = fetch
    monkeypatch.setattr(discovery.sophon, 'manifest', lambda *args, **kwargs: files if kwargs == {'fetch': fetch} else pytest.fail('Lost manifest context'))
    monkeypatch.setattr(discovery, '_protobuf_get', protobuf_get)
    monkeypatch.setattr(discovery, 'urlopen', lambda *a, **k: pytest.fail('Hidden dispatch transport'))
    monkeypatch.setattr(discovery.hotfix, 'download', lambda *a, **k: pytest.fail('Hidden marker transport'))
    result = discovery.prepare(tmp_path, build, description, fetch=fetch)
    assert len(calls) == 7 and len(state['requests']) == 2
    assert set(result['hotfix']['indexes']) == set(discovery.hotfix.INDEXES)


def test_context_package_body_requires_whole_publisher_md5_before_reusable_cache(tmp_path, monkeypatch):
    original = b'original complete authored package'
    digest = hashlib.md5(original).hexdigest()
    asset = discovery.hotfix.AudioFile('owned.bytes', len(original), digest, 'https://publisher.invalid/owned.bytes')
    source = tables.OriginalTables.__new__(tables.OriginalTables)
    source.directory = tmp_path
    supplied = [b'x' * len(original)]
    def fetch(url, *, limit):
        assert url == asset.url and limit == len(original)
        return supplied[0]
    source.package_fetch = fetch
    monkeypatch.setattr(discovery.hotfix.AudioFile, 'read', lambda *a, **k: pytest.fail('Hidden package range request'))
    with pytest.raises(ValueError):
        source._package(asset)
    target = tmp_path / 'starrail-design-packages' / (digest + '.bytes')
    assert not target.exists()
    supplied[0] = original
    assert source._package(asset) == original and target.read_bytes() == original
