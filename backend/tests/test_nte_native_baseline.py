"""Cold original provenance and immutable-cache failures, with owned resources."""
import hashlib
import io
from zipfile import ZipFile

import pytest

from backend import nte_native_baseline as baseline
from backend.tests.test_nte_seeded_schema import fixture


def source(monkeypatch):
    _, client, _, _ = fixture()
    raw = client.bytes()
    digest = hashlib.md5(raw).hexdigest()
    xml = (f'<ResList version="4.2.1" tag="baseTag"><Package><Pak filesize="{len(raw)+11}" md5="{"e"*32}">'
           f'<Entry name="Client/Unfamiliar/Original.DLL" size="{len(raw)}" offset="11" md5="{digest}" />'
           '</Pak></Package></ResList>').encode()
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('ResList.bin', xml)
    manifest = buffer.getvalue()
    ref = dict(region='nte-global', branch='PC_42', version='4.2.1',
               manifest_url='https://ntecdn1.perfectworld.com/owned-fixture.zip',
               manifest_sha256=hashlib.sha256(manifest).hexdigest(), xml_md5=hashlib.md5(xml).hexdigest(),
               native_md5=digest, native_size=len(raw), native_sha256=hashlib.sha256(raw).hexdigest())
    inventory = {key: ref[key] for key in ('region', 'branch', 'version')} | {
        'sections': {'baseTag': '4.2.1'}, 'files': {'Client/Unfamiliar/Original.DLL': {
            'size': len(raw), 'digest': digest, 'object_size': len(raw)+11, 'object_digest': 'e'*32, 'offset': 11}}}
    ref['inventory_sha256'] = hashlib.sha256(baseline.metadata._json(inventory)).hexdigest()
    monkeypatch.setattr(baseline, 'BASELINE', ref)
    return raw, manifest


def test_cold_baseline_uses_original_manifest_identity_and_exact_publisher_package_range(tmp_path, monkeypatch):
    raw, manifest = source(monkeypatch)
    calls = []
    def fetch(url, *, limit):
        calls.append(('manifest', url, limit)); return manifest
    def save(region, branch, item, path):
        calls.append(('native', region, branch, item.offset, item.object_size)); path.write_bytes(raw)
    result = baseline.load(tmp_path, fetch=fetch, save=save)
    assert result.data == raw and result.identity['native_path'] == 'Client/Unfamiliar/Original.DLL'
    assert calls[1] == ('native', 'nte-global', 'PC_42', 11, len(raw)+11)
    assert result.identity['native_file']['offset'] == 11
    def offline(*_, **__): pytest.fail('A retained baseline attempted networking')
    monkeypatch.setattr(baseline.release, '_xml', offline)
    assert baseline.load(tmp_path, fetch=offline, save=offline) == result


def test_changed_manifest_is_rejected_before_source_acquisition(tmp_path, monkeypatch):
    _, manifest = source(monkeypatch)
    with pytest.raises(ValueError):
        baseline.load(tmp_path, fetch=lambda *_, **__: manifest+b'x', save=lambda *_: pytest.fail('native fetched'))
    assert list(tmp_path.iterdir()) == []


def test_full_file_sha256_is_required_even_when_publisher_md5_was_valid(tmp_path, monkeypatch):
    raw, manifest = source(monkeypatch)
    monkeypatch.setitem(baseline.BASELINE, 'native_sha256', '0'*64)
    def save(_region, _branch, _item, path): path.write_bytes(raw)
    with pytest.raises(ValueError):
        baseline.load(tmp_path, fetch=lambda *_, **__: manifest, save=save)
