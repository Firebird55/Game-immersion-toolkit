"""The static reader loads only the pinned licensed software binary."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import endfield_xxhash as hash_reader


def test_hash_closure_registers_the_exact_license_and_native_member():
    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / 'packaging/native-codecs/endfield-xxhash-4.1.0-windows-amd64.json').read_bytes())
    assert receipt['version'] == hash_reader.VERSION
    assert receipt['all_installed_wheel_members_sha256'][receipt['native_member']] == hash_reader.NATIVE_SHA256
    notice = root / receipt['retained_license']
    assert hashlib.sha256(notice.read_bytes()).hexdigest() == hash_reader.NOTICE_SHA256


@pytest.mark.parametrize('bad_library,bad_notice', [(True, False), (False, True), (True, True)])
def test_changed_native_or_notice_is_rejected_before_import(tmp_path, monkeypatch, bad_library, bad_notice):
    package = tmp_path / 'xxhash'
    package.mkdir()
    native = package / '_xxhash.cp312-win_amd64.pyd'
    notice = tmp_path / 'xxhash-4.1.0.dist-info/licenses/LICENSE'
    notice.parent.mkdir(parents=True)
    native.write_bytes(b'authored inert fixture')
    notice.write_bytes(b'authored fixture notice')
    monkeypatch.setattr(hash_reader, 'NATIVE_SHA256', hashlib.sha256(native.read_bytes()).hexdigest())
    monkeypatch.setattr(hash_reader, 'NOTICE_SHA256', hashlib.sha256(notice.read_bytes()).hexdigest())
    if bad_library:
        native.write_bytes(b'changed inert fixture')
    if bad_notice:
        notice.write_bytes(b'changed fixture notice')
    monkeypatch.setattr(hash_reader.sys, 'platform', 'win32')
    monkeypatch.setattr(hash_reader.platform, 'machine', lambda: 'AMD64')
    monkeypatch.setattr(hash_reader.importlib.metadata, 'distribution', lambda _: SimpleNamespace(
        version=hash_reader.VERSION, locate_file=lambda name: tmp_path / name))
    monkeypatch.setattr(hash_reader.importlib.util, 'find_spec', lambda _: SimpleNamespace(origin=package / '__init__.py'))
    imported = []
    monkeypatch.setattr(hash_reader.importlib, 'import_module', lambda name: imported.append(name))
    hash_reader.implementation.cache_clear()
    with pytest.raises(ValueError, match='differs'):
        hash_reader.implementation()
    assert imported == []


@pytest.mark.parametrize('data', [bytearray(b'x'), 'text', b'x' * 4097])
def test_invalid_parameter_input_never_loads_native_software(monkeypatch, data):
    monkeypatch.setattr(hash_reader, 'implementation', lambda: pytest.fail('invalid input loaded native software'))
    with pytest.raises(ValueError):
        hash_reader.hash64(data)
