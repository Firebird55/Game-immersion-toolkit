"""Authored resource closure tests; native decode probes are separate evidence."""
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import native_codecs as codecs
from backend.tests.test_runtime_bundle import frozen_layout


def fixture(tmp_path, monkeypatch, target='windows-x64'):
    layout = frozen_layout(tmp_path)
    monkeypatch.setattr(codecs, 'host_target', lambda: target)
    system = {'windows': 'win32', 'macos': 'darwin', 'linux': 'linux'}[target.split('-')[0]]
    monkeypatch.setattr(codecs, 'sys', SimpleNamespace(platform=system))
    root = layout.resource_root / codecs.PREFIX
    root.mkdir(parents=True)
    if system == 'win32':
        binary = bytearray(128)
        binary[:2] = b'MZ'
        binary[60:64] = (64).to_bytes(4, 'little')
        binary[64:70] = b'PE\0\0\x64\x86'
    elif system == 'linux':
        binary = bytearray(64)
        binary[:6] = b'\x7fELF\x02\x01'
        binary[18:20] = (62).to_bytes(2, 'little')
    else:
        binary = bytearray(64)
        binary[:4] = b'\xcf\xfa\xed\xfe'
        binary[4:8] = (0x0100000C).to_bytes(4, 'little')
    executable = 'ffmpeg' + ('.exe' if system == 'win32' else '')
    (root / executable).write_bytes(binary)
    (root / 'NOTICE.txt').write_text('Authored fixture; no actual third-party binary')
    value = {'schema': codecs.SCHEMA, 'target': target, 'tools': {'ffmpeg': executable}}
    return layout, root, value


def seal(layout, root, value):
    value['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.name != 'runtime.json'}
    (root / 'runtime.json').write_text(json.dumps(value))
    return replace(layout, resources={codecs.PREFIX + p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})


@pytest.mark.parametrize('target', ['windows-x64', 'linux-x64', 'macos-arm64'])
def test_verified_native_entry_and_missing_capability(tmp_path, monkeypatch, target):
    layout, root, value = fixture(tmp_path, monkeypatch, target)
    layout = seal(layout, root, value)
    assert codecs.packaged_codec_executable('ffmpeg', layout=layout) == root / value['tools']['ffmpeg']
    assert codecs.packaged_codec_executable('vgmstream', layout=layout) is None


@pytest.mark.parametrize('damage', ['wrong-target', 'wrong-entry', 'unbound', 'corrupt', 'extra-dll', 'missing-notice', 'non-native', 'wrong-companion-hash', 'traversal'])
def test_incomplete_or_modified_codec_is_unavailable(tmp_path, monkeypatch, damage):
    layout, root, value = fixture(tmp_path, monkeypatch)
    if damage == 'wrong-target': value['target'] = 'linux-x64'
    if damage == 'wrong-entry': value['tools']['ffmpeg'] = 'other.exe'
    if damage == 'missing-notice': (root / 'NOTICE.txt').unlink()
    if damage == 'non-native': (root / 'ffmpeg.exe').write_bytes(b'not an executable')
    layout = seal(layout, root, value)
    if damage == 'unbound': layout = replace(layout, resources={})
    if damage == 'corrupt': (root / 'ffmpeg.exe').write_bytes(b'changed')
    if damage == 'extra-dll': (root / 'unexpected.dll').write_bytes(b'not inventoried')
    if damage in {'wrong-companion-hash', 'traversal'}:
        value['files']['NOTICE.txt' if damage == 'wrong-companion-hash' else '../outside.exe'] = 'f' * 64
        (root / 'runtime.json').write_text(json.dumps(value))
        layout = replace(layout, resources={**layout.resources, codecs.PREFIX + 'runtime.json': hashlib.sha256((root / 'runtime.json').read_bytes()).hexdigest()})
    assert codecs.packaged_codec_executable('ffmpeg', layout=layout) is None


def test_unknown_tool_is_rejected_and_source_cannot_claim_bundled_codec():
    with pytest.raises(ValueError): codecs.packaged_codec_executable('arbitrary')
    assert codecs.packaged_codec_executable('ffmpeg', layout=SimpleNamespace(mode='source')) is None
