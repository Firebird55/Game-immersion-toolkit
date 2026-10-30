"""Owned binary fixtures cover native parsing previously hidden behind a compiler.

These cases protect 64-bit voice identity, embedded-bank offsets, random access,
missing optional packs and malformed archives without distributing game files.
"""
import hashlib
import io
import json
from pathlib import Path
import struct

from Crypto.Cipher import ChaCha20
import pytest

from backend import endfield_vfs as vfs, endfield_metadata as metadata

PARAMETERS = vfs.Parameters(bytes(range(32)), {block: f'{index:08X}' for index, block in
    enumerate((1, 21, 101, 102, 103, 104), 1)}, 5, 7)
WAVE = b'RIFF' + struct.pack('<I', 16) + b'WAVEfmt ' + bytes(8)
CHUNK = bytes(range(16)).hex().upper() + '.chk'
EXTERNAL_ID = 0xfedcba9876543210


def pack(format, *values):
    return struct.pack('<' + format, *values)


def encrypt(data, nonce, offset=0):
    cipher = ChaCha20.new(key=PARAMETERS.key, nonce=nonce)
    cipher.seek(offset + 64)
    return cipher.encrypt(data)


def mask(data, seed, offset=0):
    # Deliberately scalar fixture encoder, independent of the reader's NumPy
    # range implementation; constants belong solely to this authored fixture.
    result = bytearray()
    for position, value in enumerate(data, offset):
        counter = (seed + position // 4) & 0xffffffff
        key = 7
        for shift in (0, 8, 16, 24):
            key = ((key ^ ((counter >> shift) & 255)) * 5) & 0xffffffff
        result.append(value ^ ((key >> (position % 4 * 8)) & 255))
    return bytes(result)


def index(size, *, schema=5, block=102, offset=0, encrypted=True, name='../unused-name.pck',
          chunk_size=None):
    import zlib
    def text(value):
        encoded = value.encode()
        return pack('H', len(encoded)) + encoded
    tag = bytes({3: 0, 4: 4, 5: 8}[schema])
    body = pack('ii', schema, 17) + text('authored') + pack('qi qBi', 99, 1, size, block, 1)
    body += bytes(range(16)) + bytes(16) + pack('qB', chunk_size or size + offset, block) + tag + pack('i', 1)
    body += text(name) + pack('q', -123) + bytes(32) + pack('qqBB', offset, size, block, encrypted)
    if encrypted:
        body += pack('q', -9)
    body += tag + (bytes(10) if schema == 5 else b'')
    body += pack('I', zlib.crc32(body))
    nonce = bytes(range(12))
    return nonce + encrypt(body, nonce)


def package(*, encrypted_header=True, bad_bank=False):
    # A metadata chunk separates BKHD and DIDX, exercising generic bank sections.
    bank = b'BKHD' + pack('I', 4) + bytes(4) + b'HIRC' + pack('I', 0)
    bank += b'DIDX' + pack('I', 12) + pack('III', 31337, 3, len(WAVE))
    bank += b'DATA' + pack('I', len(WAVE) + 3) + b'pad' + WAVE
    if bad_bank:
        bank = bank.replace(pack('III', 31337, 3, len(WAVE)), pack('III', 31337, 100000, len(WAVE)))
    language_sector = pack('I', 0)
    sizes = (len(language_sector), 28, 24, 28)
    first = 28 + sum(sizes)
    bank_sector = pack('I', 1) + pack('IIQII', 6789, 1, len(bank), first, 0)
    sound_sector = pack('I', 1) + pack('IIIII', 99, 1, len(WAVE), first + len(bank), 0)
    external_sector = pack('I', 1) + pack('IIIIII', EXTERNAL_ID & 0xffffffff, EXTERNAL_ID >> 32,
                                          1, len(WAVE), first + len(bank) + len(WAVE), 0)
    body = pack('IIII', *sizes) + language_sector + bank_sector + sound_sector + external_sector
    header_size = len(body) + 4
    header = (b':)xD' if encrypted_header else b'AKPK') + pack('II', header_size, 1)
    data = header + (mask(body, header_size) if encrypted_header else body)
    return data + mask(bank, 6789) + WAVE + mask(WAVE, EXTERNAL_ID & 0xffffffff)


def write_package(tmp_path, *, layer='StreamingAssets', block=102, schema=5, with_chunk=True):
    assets = tmp_path / 'Endfield_Data' / layer
    directory = assets / 'VFS' / PARAMETERS.directories[block]
    directory.mkdir(parents=True)
    data = package()
    (directory / (directory.name + '.blc')).write_bytes(index(len(data), schema=schema, block=block, offset=11))
    if with_chunk:
        (directory / CHUNK).write_bytes(b'prefix-data' + encrypt(data, pack('iq', 3, -9)))
    return assets


@pytest.mark.parametrize('schema', [3, 4, 5])
@pytest.mark.parametrize('language,block', list(vfs.LOCALE_BLOCKS.items()))
def test_official_voice_namespaces_read_bank_and_64bit_external_media(tmp_path, schema, language, block):
    assets = write_package(tmp_path, schema=schema, block=block)
    rows = json.loads(vfs.run(assets, PARAMETERS, 'inventory', {'language': language}))
    assert {row['file_id'] for row in rows} == {'0000000000007a69', '0000000000000063', 'fedcba9876543210'}
    assert all(row['block'] == block and row['chunk'] == CHUNK and row['file_hash'] == '-123' for row in rows)
    for row in rows:
        assert vfs.run(assets, PARAMETERS, 'voice', {**row, 'language': language}) == WAVE


def test_patch_index_falls_back_to_base_chunk_and_absent_pack_stays_empty(tmp_path):
    write_package(tmp_path)
    patch = write_package(tmp_path, layer='Persistent', with_chunk=False)
    assert len(json.loads(vfs.run(patch, PARAMETERS, 'inventory', {'language': 'english'}))) == 3
    assert json.loads(vfs.run(patch, PARAMETERS, 'inventory', {'language': 'japanese'})) == []
    (tmp_path / 'Endfield_Data/StreamingAssets/VFS' / PARAMETERS.directories[102] / CHUNK).unlink()
    assert json.loads(vfs.run(patch, PARAMETERS, 'inventory', {'language': 'english'})) == []


def test_range_reading_does_not_load_multigigabyte_package():
    data = package(encrypted_header=False)
    class Sparse:
        size = 2 * 1024**3
        def read(self, offset, size):
            assert size < 1024
            assert offset + size <= len(data)
            return data[offset:offset + size]
    reader = vfs.Package(Sparse(), PARAMETERS)
    assert [reader.voice(entry) for entry in reader.entries] == [WAVE] * 3


@pytest.mark.parametrize('offset,size', [(0, 37), (1, 31), (3, 4), (4, 32), (97, 19)])
def test_unaligned_xor_ranges_agree_with_independent_fixture_encoder(offset, size):
    data = bytes(range(128))
    encrypted = mask(data, 0xfffffff9)
    assert vfs.xor_data(encrypted[offset:offset + size], 0xfffffff9, PARAMETERS, offset) == data[offset:offset + size]


@pytest.mark.parametrize('kind', ['crc', 'schema', 'count', 'extent', 'trailer'])
def test_present_malformed_indexes_fail_instead_of_disappearing(kind):
    import zlib
    data = index(200)
    plain = bytearray(encrypt(data[12:], data[:12]))
    if kind == 'crc':
        plain[-1] ^= 1
    else:
        if kind == 'schema':
            plain[:4] = pack('i', 6)
        elif kind == 'count':
            plain[10 + len('authored') + 8:10 + len('authored') + 12] = pack('i', -1)
        elif kind == 'extent':
            data = index(200, chunk_size=199)
            with pytest.raises(vfs.FormatError):
                vfs.parse_index(data, PARAMETERS, 102)
            return
        else:
            plain = plain[:-14] + plain[-4:]
        plain[-4:] = pack('I', zlib.crc32(plain[:-4]))
    with pytest.raises(vfs.FormatError):
        vfs.parse_index(data[:12] + encrypt(plain, data[:12]), PARAMETERS, 102)


@pytest.mark.parametrize('bad', ['header', 'bank', 'sector', 'span', 'truncated'])
def test_invalid_package_headers_and_embedded_offsets_are_rejected(bad):
    data = bytearray(package(encrypted_header=False, bad_bank=bad == 'bank'))
    if bad == 'header':
        data[4:8] = pack('I', vfs.MAX_INDEX + 1)
    elif bad == 'sector':
        data[12:16] = pack('I', 99999)
    elif bad == 'span':
        data[28 + 4 + 4 + 16:28 + 4 + 4 + 20] = pack('I', len(data) + 1)
    elif bad == 'truncated':
        data = data[:8]
    with pytest.raises(vfs.FormatError):
        source = vfs.PackageSource(io.BytesIO(data), vfs.File('a.pck', 1, CHUNK, 0, len(data), None), PARAMETERS)
        vfs.Package(source, PARAMETERS)


def test_wrong_locale_or_voice_identity_never_falls_back(tmp_path):
    assets = write_package(tmp_path)
    row = json.loads(vfs.run(assets, PARAMETERS, 'inventory', {'language': 'english'}))[0]
    for changes in ({'language': 'japanese'}, {'file_id': '0000000000000000'}, {'chunk': '../escape.chk'},
                    {'file_hash': '999'}, {'block': 12}):
        with pytest.raises(vfs.FormatError):
            vfs.run(assets, PARAMETERS, 'voice', {**row, 'language': 'english', **changes})


def documents():
    import base64
    return {
        'Keys.cs': ('VfsProtoVersion = 3; ChaCha20Key = Convert.FromBase64String("' +
                    base64.b64encode(PARAMETERS.key).decode() + '");').encode(),
        'BlockHashes.cs': '\n'.join('[BlockType.' + name + '] = "' + PARAMETERS.directories[block] + '"'
                                   for name, block in metadata.BLOCKS.items()).encode(),
        'Processors/AkpkCrypto.cs': b'MulConst = 5u; XorConst = 0x7u;',
    }


def test_verified_private_metadata_is_data_and_failed_download_retains_cache(tmp_path, monkeypatch):
    from backend import game_tools
    values = documents()
    monkeypatch.setattr(metadata, 'SOURCES', {name: hashlib.sha256(value).hexdigest() for name, value in values.items()})
    monkeypatch.setattr(game_tools, 'download', lambda url, **_kwargs: values[url.removeprefix(metadata.BASE)])
    assert metadata.parameters(tmp_path) == PARAMETERS
    assert metadata.ready(tmp_path)
    monkeypatch.setattr(game_tools, 'download', lambda *_args, **_kwargs: pytest.fail('Valid private cache should be offline'))
    assert metadata.parameters(tmp_path) == PARAMETERS
    target = metadata.cache_root(tmp_path) / 'Keys.cs'
    target.write_bytes(b'old cache')
    monkeypatch.setattr(game_tools, 'download', lambda *_args, **_kwargs: b'tampered')
    with pytest.raises(metadata.PreparationFailure, match='verification'):
        metadata.parameters(tmp_path)
    assert target.read_bytes() == b'old cache'


def test_normal_adapter_never_discovers_sdk_or_launches_compiler(tmp_path, monkeypatch):
    import subprocess
    from backend import endfield_assets, nte_assets, prebuilt_readers
    from types import SimpleNamespace
    monkeypatch.setattr(prebuilt_readers, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('No native compiler/process is needed'))
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('No SDK discovery is needed'))
    monkeypatch.setattr(metadata, 'parameters', lambda _tools: PARAMETERS)
    write_package(tmp_path)
    rows = json.loads(endfield_assets.reader(tmp_path, tmp_path / 'tools/legacy.dll', 'inventory', {'language': 'english'}))
    assert len(rows) == 3
    assert endfield_assets.ensure_extractor(tmp_path / 'tools') == metadata.cache_root(tmp_path / 'tools')
