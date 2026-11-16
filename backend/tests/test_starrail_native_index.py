"""Managed identity boundaries and native range joins use authored metadata."""
import json
import struct
from types import SimpleNamespace

import pytest

from backend.starrail_native_index import NativeIndex


def fixture(tmp_path):
    inputs, outputs = tmp_path / 'inputs', tmp_path / 'outputs'
    inputs.mkdir(); outputs.mkdir()
    native = bytearray(0x500); native[:2] = b'MZ'; pe = 0x80
    struct.pack_into('<I', native, 60, pe); native[pe:pe + 4] = b'PE\0\0'
    struct.pack_into('<HH', native, pe + 4, 0x8664, 1)
    struct.pack_into('<H', native, pe + 20, 0xf0)
    struct.pack_into('<H', native, pe + 24, 0x20b)
    struct.pack_into('<Q', native, pe + 48, 0x180000000)
    struct.pack_into('<4I', native, pe + 24 + 0xf0 + 8, 0x100, 0x1000, 0x100, 0x400)
    (inputs / 'GameAssembly.dll').write_bytes(native)
    blocks = []
    for index, name, rva in [(1, 'Repeated.Name', 0x1000), (2, 'Repeated.Name', 0x1010),
                             (3, 'Unique.Owner', 0x1020), (4, '', 0x1030)]:
        blocks.append(f'// TypeDefIndex: {index}\n// Full Name: {name}\n'
                      f'    public void Read() {{}} // VA: 0x{0x180000000+rva:X}, RVA: 0x{rva:X}, Token: 0x1\n')
    (outputs / 'dump.cs').write_text(''.join(blocks))
    (outputs / 'stringliterals.json').write_text(json.dumps([{'Address': '0x2000', 'Value': 'authored.bytes'}]))
    return SimpleNamespace(inputs=inputs, outputs=outputs,
        disassemble=lambda ranges: [[[row['address'], 'ret', '']] for row in ranges])


def test_duplicate_display_names_do_not_merge_managed_owners_or_hide_unrelated_methods(tmp_path):
    prepared = fixture(tmp_path)
    index = NativeIndex(prepared)
    assert 'Repeated.Name' not in index.blocks
    assert len(index.all_blocks) == 4
    assert index.methods[0x1000][0]['owner'] != index.methods[0x1010][0]['owner']
    assert index.method('Unique.Owner', r'public void Read\(\)') == 0x1020
    with pytest.raises(ValueError):
        index.method('Repeated.Name', r'public void Read\(\)')
    assert index.literals[0x2000] == 'authored.bytes'
    body, digest = index.body(0x1020)
    assert body == [(0x1020, 'ret', '')]
    assert len(digest) == 64


def test_method_ranges_must_stay_in_one_file_backed_native_section(tmp_path):
    index = NativeIndex(fixture(tmp_path))
    for start, length in [(0xfff, 1), (0x10ff, 2), (0x1000, 0)]:
        with pytest.raises(ValueError):
            index.offset(start, length)


def test_managed_decoder_cannot_return_instructions_from_another_method(tmp_path):
    prepared = fixture(tmp_path)
    prepared.disassemble = lambda ranges: [[[ranges[0]['address'] + 0x10000, 'ret', '']]]
    index = NativeIndex(prepared)
    with pytest.raises(ValueError):
        index.body(0x1020)


def test_nested_methods_keep_their_own_field_and_constructor_scope(tmp_path):
    prepared = fixture(tmp_path)
    path = prepared.outputs / 'dump.cs'
    text = path.read_text().replace('// TypeDefIndex: 4',
        '    private static void .cctor() {} // VA: 0x180001040, RVA: 0x1040, Token: 0x1\n'
        '    public class Child : object { // Token: 0x2\n'
        '        public string Name // Offset: 0x88, Token: 0x3\n'
        '        public void SetUrls(string[]) {} // VA: 0x180001050, RVA: 0x1050, Token: 0x4\n'
        '        private static void .cctor() {} // VA: 0x180001060, RVA: 0x1060, Token: 0x5\n'
        '    }\n// TypeDefIndex: 4')
    path.write_text(text)
    index = NativeIndex(prepared)
    assert index.method('Unique.Owner', r'private static void \.cctor\(\)') == 0x1040
    with pytest.raises(ValueError):
        index.method('Unique.Owner', r'public void SetUrls\(string\[\]\)')
    address = index.method('Unique.Owner', r'public void SetUrls\(string\[\]\)', include_nested=True)
    scope = index.methods[address][0]['owner']
    assert 'string Name' in index.scopes[scope]
    assert 'string Name' not in index.scopes[index.owners['Unique.Owner'][0]]
