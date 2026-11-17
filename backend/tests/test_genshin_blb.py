"""Private parameter data never becomes compiler input or executable code."""
import base64
import json
from pathlib import Path
import struct

import pytest

from backend import genshin_blb as blb


def source():
    return '\n'.join('public static readonly byte[] ' + name + ' = new byte[' + str(size)
                     + '] { ' + ','.join(str(n % 256) for n in range(size)) + ' };'
                     for name, size in blb.PARAMETERS.items()).encode()


def test_numeric_description_is_bounded_data_and_preserves_each_byte():
    rows = json.loads(blb.parameter_data(source()))
    assert set(rows) == set(blb.PARAMETERS)
    assert all(base64.b64decode(rows[name]) == bytes(n % 256 for n in range(size))
               for name, size in blb.PARAMETERS.items())


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'expression', 'long', 'overflow', 'wrong-size'])
def test_untrusted_description_never_runs_or_supplies_partial_parameters(change):
    raw = source()
    if change == 'duplicate': raw += raw
    elif change == 'missing': raw = raw.split(b'\n', 1)[1]
    elif change == 'expression': raw = raw.replace(b'{ 0,1', b'{ CallCode(),1', 1)
    elif change == 'long': raw += b' ' * 1024**2
    elif change == 'overflow': raw = raw.replace(b'{ 0,1', b'{ 256,1', 1)
    else: raw = raw.replace(b'byte[256]', b'byte[255]', 1)
    with pytest.raises(ValueError):
        blb.parameter_data(raw)


def decoded(raw=b'hello', compressed=False):
    body = bytes([len(raw) << 4]) + raw if compressed else raw
    head = bytearray(72)
    struct.pack_into('<I', head, 4, len(raw)); head[21] = 8
    struct.pack_into('<ii', head, 24, 1, 1)
    struct.pack_into('<q', head, 32, 24)
    struct.pack_into('<I', head, 56, len(body))
    struct.pack_into('<q', head, 40, 24)
    struct.pack_into('<ii', head, 64, 0, len(raw))
    return b'Blb\x03' + struct.pack('<I', len(head)) + bytes(20) + head + body


@pytest.mark.parametrize('compressed', [False, True])
def test_decoded_single_body_has_exact_size_and_eof_without_lz4_dependency(tmp_path, compressed):
    source, target = tmp_path / 'decoded', tmp_path / 'body'
    source.write_bytes(decoded(compressed=compressed))
    blb.unpack(source, target)
    assert target.read_bytes() == b'hello'
    with pytest.raises(ValueError):
        blb.unpack(source, target)


@pytest.mark.parametrize('change', ['node-count', 'node-offset', 'node-size', 'table-bounds', 'output-bound', 'truncated', 'trailing'])
def test_incomplete_or_oversized_decompression_cannot_replace_previous_body(tmp_path, change):
    source, target = tmp_path / 'decoded', tmp_path / 'body'
    raw = bytearray(decoded())
    if change == 'node-count': struct.pack_into('<i', raw, 28 + 28, 2)
    elif change == 'node-offset': struct.pack_into('<i', raw, 28 + 64, 1)
    elif change == 'node-size': struct.pack_into('<i', raw, 28 + 68, 4)
    elif change == 'table-bounds': struct.pack_into('<q', raw, 28 + 32, 500)
    elif change == 'output-bound': struct.pack_into('<I', raw, 28 + 4, 1000)
    elif change == 'truncated': raw = raw[:-1]
    else: raw += b'garbage'
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        blb.unpack(source, target)


def test_prebuilt_path_never_consults_sdk_or_downloads(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(blb, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    expected = SimpleNamespace(executable=tmp_path / 'GenshinBlb.exe', source_identity='a' * 64,
                               manifest={'build_id': 'b' * 64})
    monkeypatch.setattr(blb, 'prebuilt_reader', lambda kind, layout: expected if kind == 'genshin' else None)
    from backend import nte_assets
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('A packaged helper consulted the host SDK'))
    assert blb.helper(tmp_path).command == (str(expected.executable),)
