"""Authored archive bytes; no publisher constants, files, names or recordings."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import zlib

import pytest
import zstandard

from backend import re_pak as pak
from backend import re_pak_metadata as metadata
from backend import ree_extractor

SPEC = importlib.util.spec_from_file_location('owned_pak_fixtures', Path(__file__).resolve().parents[2] / 'scripts/game-helper-fixtures.py')
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)
NAME = 'natives/owned/one.bin'
OTHER = 'natives/owned/not-selected.bin'
KEY = bytes(range(1, 129))
PARAMETERS = pak.CipherParameters((1 << 1032) - 109, 1)


def hashes(name):
    return tuple(FIXTURE.murmur32(value.encode('utf-16le')) for value in (name.lower(), name.upper()))


def encode_table(table):
    # An owned identity modular transform, unrelated to any real game's keys.
    return bytes(byte ^ ((i + KEY[i % 32] * KEY[i % 29]) & 255) for i, byte in enumerate(table))


def archive(path, rows, *, feature=0, major=4, minor=2):
    extras = (bytes(4) if feature == 24 else bytes(9) if feature in {12, 44} else b'') + (KEY if feature else b'')
    start = 16 + len(rows) * (24 if major == 2 else 48) + len(extras)
    table, body = b'', b''
    for name, encoded, size, flags in rows:
        lower, upper = hashes(name)
        if major == 2:
            table += struct.pack('<qqII', start + len(body), size, lower, upper)
        else:
            table += struct.pack('<IIqqqqQ', lower, upper, start + len(body), len(encoded), size, flags, 0)
        body += encoded
    if feature:
        table = encode_table(table)
    path.write_bytes(struct.pack('<4sBBHII', b'KPKA', major, minor, feature, len(rows), 0) + table + extras + body)
    return path


def test_independent_fixture_selection_and_hash_vectors(tmp_path):
    FIXTURE.fixture(tmp_path / 'fixture')
    output = tmp_path / 'output'
    assert pak.extract_selected(tmp_path / 'fixture/owned.pak', output, [NAME]) == 1
    assert hashlib.sha256((output / NAME).read_bytes()).hexdigest() == '40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880'
    assert [p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()] == [NAME]
    for value in (b'', b'f', b'fo', b'foo', b'fooo', b'longer message'):
        assert pak.murmur32(value) == FIXTURE.murmur32(value)


@pytest.mark.parametrize('feature', [0, 8, 12, 24])
@pytest.mark.parametrize('codec', [0, 1, 2])
def test_selected_raw_deflate_and_zstd_with_encrypted_tables(tmp_path, feature, codec):
    body = bytes(range(256)) * 7
    encoded = [body, zlib.compress(body, wbits=-15), zstandard.ZstdCompressor().compress(body)][codec]
    source = archive(tmp_path / 'owned.pak', [(NAME, encoded, len(body), codec), (OTHER, b'invalid', 99, 15)], feature=feature)
    assert pak.extract_selected(source, tmp_path / 'out', [NAME], parameters=lambda _: PARAMETERS) == 1
    assert (tmp_path / 'out' / NAME).read_bytes() == body


def test_version_two_raw_and_empty_resources(tmp_path):
    source = archive(tmp_path / 'owned.pak', [(NAME, b'raw', 3, 0), (OTHER, b'', 0, 0)], major=2, minor=0)
    assert pak.extract_selected(source, tmp_path / 'out', [NAME, OTHER]) == 2
    assert (tmp_path / 'out' / NAME).read_bytes() == b'raw'
    assert (tmp_path / 'out' / OTHER).read_bytes() == b''


@pytest.mark.parametrize('feature', [40, 44, 104])
def test_chunked_archive_combines_raw_and_zstd_with_last_chunk_padding(tmp_path, feature):
    first, second = b'a' * pak.CHUNK_SIZE, b'b' * 72 + bytes(12)
    compressed = zstandard.ZstdCompressor().compress(second)
    extras = bytes(9) if feature == 44 else b''
    if feature == 104:
        extras += struct.pack('<II', 0, pak.CHUNK_SIZE)
    extras += KEY
    start = 16 + 48 + len(extras) + 8 + 16
    chunks = struct.pack('<II', pak.CHUNK_SIZE, 2)
    chunks += struct.pack('<II', start, len(first) << 10)
    chunks += struct.pack('<II', start + len(first), len(compressed) << 10)
    lower, upper = hashes(NAME)
    table = struct.pack('<IIqqqqQ', lower, upper, 0, len(first) + len(compressed), len(first) + 72, 0x1000000, 0)
    source = tmp_path / 'owned.pak'
    source.write_bytes(struct.pack('<4sBBHII', b'KPKA', 4, 2, feature, 1, 0) + encode_table(table) + extras + chunks + first + compressed)
    assert pak.extract_selected(source, tmp_path / 'out', [NAME], parameters=lambda _: PARAMETERS) == 1
    assert (tmp_path / 'out' / NAME).read_bytes() == first + b'b' * 72


def test_resource_encryption_is_bounded_and_decoded_before_compression(tmp_path):
    original = b'An authored compressed archive resource.'
    compressed = zlib.compress(original, wbits=-15)
    encrypted = struct.pack('<q', len(compressed))
    for pos in range(0, len(compressed), 8):
        encrypted += (1).to_bytes(64, 'little') + int.from_bytes(compressed[pos:pos + 8], 'little').to_bytes(64, 'little')
    source = archive(tmp_path / 'owned.pak', [(NAME, encrypted, len(original), (1 << 16) | 1)])
    pak.extract_selected(source, tmp_path / 'out', [NAME], parameters=lambda _: PARAMETERS)
    assert (tmp_path / 'out' / NAME).read_bytes() == original


@pytest.mark.parametrize('name', ['../escape', 'natives/../escape', 'natives/a\\b', 'natives/a:b', 'natives//a', 'natives/a.', 'natives/NUL.txt'])
def test_unsafe_selection_rejected_before_archive_or_output_access(tmp_path, name):
    with pytest.raises(ValueError, match='Unsafe'):
        pak.extract_selected(tmp_path / 'absent', tmp_path / 'out', [name])
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('codec', [1, 2])
def test_expansion_limit_or_trailing_stream_preserves_previous_patch(tmp_path, codec):
    previous = tmp_path / 'out' / NAME
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b'previous verified patch')
    encode = (lambda data: zlib.compress(data, wbits=-15)) if codec == 1 else zstandard.ZstdCompressor().compress
    for encoded, declared in [(encode(b'x' * 10000), 10), (encode(b'x') + encode(b'y'), 2)]:
        source = archive(tmp_path / 'owned.pak', [(NAME, b'new content', 11, 0), (OTHER, encoded, declared, codec)])
        with pytest.raises((ValueError, zstandard.ZstdError)):
            pak.extract_selected(source, tmp_path / 'out', [NAME, OTHER])
        assert previous.read_bytes() == b'previous verified patch'
        assert not (tmp_path / 'out' / OTHER).exists()


def test_invalid_count_selected_extent_and_unknown_feature(tmp_path):
    source = tmp_path / 'owned.pak'
    source.write_bytes(struct.pack('<4sBBHII', b'KPKA', 4, 2, 0, pak.MAX_FILES + 1, 0))
    with pytest.raises(ValueError, match='count'):
        pak.extract_selected(source, tmp_path / 'out', [NAME])
    source = archive(source, [(NAME, b'payload', 7, 0)])
    data = bytearray(source.read_bytes()); struct.pack_into('<q', data, 24, len(data) + 1); source.write_bytes(data)
    with pytest.raises(ValueError, match='Truncated'):
        pak.extract_selected(source, tmp_path / 'out', [NAME])
    struct.pack_into('<H', data, 6, 999); source.write_bytes(data)
    with pytest.raises(ValueError, match='feature'):
        pak.extract_selected(source, tmp_path / 'out', [NAME])


def test_project_adapter_never_invokes_compiler_or_process(tmp_path, monkeypatch):
    source = archive(tmp_path / 'owned.pak', [(NAME, b'payload', 7, 0)])
    tools = tmp_path / 'tools'; (tools / 'Projects').mkdir(parents=True)
    (tools / 'Projects/Owned.list').write_text(NAME)
    monkeypatch.setattr(ree_extractor, 'ensure_extractor', lambda *_: pytest.fail('compiler invoked'))
    monkeypatch.setattr(ree_extractor.subprocess, 'run', lambda *_a, **_k: pytest.fail('external process invoked'))
    ree_extractor.extract_project(tools, 'Owned', source, tmp_path / 'out')
    assert (tmp_path / 'out' / NAME).read_bytes() == b'payload'


def test_metadata_checksum_failure_preserves_cache_and_does_not_execute_source(tmp_path, monkeypatch):
    from backend import game_tools
    target = tmp_path / 'format-metadata/re-pak-v1/PakCipher.cs'
    target.parent.mkdir(parents=True); target.write_bytes(b'preserved invalid source')
    monkeypatch.setattr(game_tools, 'download', lambda *_a, **_k: b'unverified source')
    with pytest.raises(ValueError, match='verification'):
        metadata.parameters(tmp_path, 'table')
    assert target.read_bytes() == b'preserved invalid source'


def test_owned_metadata_values_are_parsed_as_data_and_reused(tmp_path, monkeypatch):
    from backend import game_tools
    data = b'Byte[] lpModulus = {0x05,0x01}; Byte[] lpExponent = {0x01};'
    monkeypatch.setitem(metadata.SOURCES, 'table', ('Owned.cs', hashlib.sha256(data).hexdigest(), (2, 1)))
    calls = []
    monkeypatch.setattr(game_tools, 'download', lambda *_a, **_k: calls.append(1) or data)
    assert metadata.parameters(tmp_path, 'table') == pak.CipherParameters(261, 1)
    assert metadata.parameters(tmp_path, 'table') == pak.CipherParameters(261, 1)
    assert calls == [1]
