"""A build PC runtime update cannot silently change the bundled MSVC input."""
import base64
import hashlib
from importlib.metadata import PackagePath
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = spec_from_file_location('windows_runtime_supplier', Path(__file__).resolve().parents[2] / 'packaging/runtime-bundle/windows_runtime.py')
runtime = module_from_spec(spec)
spec.loader.exec_module(runtime)


def supplier(tmp_path):
    source = tmp_path / 'PySide6/msvcp140.dll'
    source.parent.mkdir()
    source.write_bytes(b'Authored exact supplier fixture')
    record = PackagePath('PySide6/msvcp140.dll')
    record.hash = SimpleNamespace(mode='sha256', value=base64.urlsafe_b64encode(hashlib.sha256(source.read_bytes()).digest()).decode().rstrip('='))
    return source, SimpleNamespace(files=[record], locate_file=lambda _: source)


def test_host_copy_replaced_and_other_destinations_preserved(tmp_path):
    source, dist = supplier(tmp_path)
    entries = [('msvcp140.dll', 'unverified-host-copy', 'BINARY'),
        ('PySide6/msvcp140.dll', 'another-host-copy', 'BINARY'),
        ('other.dll', 'already-verified', 'BINARY')]
    selected = runtime.select_msvc(entries, distribution=dist)
    assert selected[:2] == [(entry[0], str(source.absolute()), 'BINARY') for entry in entries[:2]]
    assert selected[2] == entries[2]
    assert entries[0][1] == 'unverified-host-copy'


def test_changed_supplier_cannot_replace_host_copy(tmp_path):
    source, dist = supplier(tmp_path)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='observed wheel'):
        runtime.select_msvc([('msvcp140.dll', 'host', 'BINARY')], distribution=dist)


def test_unneeded_runtime_is_not_added():
    entries = [('other.dll', 'supplier', 'BINARY')]
    assert runtime.select_msvc(entries, distribution=SimpleNamespace(files=[])) is entries
