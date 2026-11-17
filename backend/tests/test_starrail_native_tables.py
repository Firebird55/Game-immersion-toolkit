"""Synthetic relocated table ownership and strict masked-field data flow."""
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_native_tables as tables


def binding_fixture(*, heap_store=False, clobber=False):
    blocks, all_blocks, bodies, raw, sizes, literals = {}, [], {}, {}, {}, {}
    names = {'NewTableA', 'NewTableB'}
    for i, name in enumerate(sorted(names)):
        start, literal = 0x1000 + i * 0x100, 0x9000 + i * 0x100
        native_offset = 0x200 + i * 0x80
        row = name + 'Row'
        block = (f'    private static string[] paths // Offset: {hex(native_offset + 0x40)}, Token: 0x1\n'
                 f'    private static Dictionary<uint, {row}> rows // Offset: 0x50, Token: 0x2\n'
                 f'    private static void .cctor() {{}} // VA: 0x180001000, RVA: {hex(start)}, Token: 0x3\n')
        blocks[row] = ('    public uint NewlyAdded // Offset: 0x28, Token: 0x4\n'
                       '    public static void FromBinary(Reader, Row&) {} // VA: 0x180003000, RVA: 0x3000, Token: 0x5\n')
        all_blocks.append(('RenamedContainer' + name, 'identity' + name, block))
        literals[literal] = 'relocated/new/' + name + '.bytes'
        args = [('call', '0x180004000'), ('mov', 'rbx, rax'),
                ('mov', f'rcx, qword ptr [rip + {hex(literal - start - 2 - 7)}]'),
                ('mov', 'qword ptr [rbx + 0x20], rcx'),
                ('mov', f'rcx, qword ptr [rip + {hex(0x8000 - start - 4 - 7)}]')]
        if clobber:
            args.append(('xor', 'ecx, ecx'))
        args.append(('mov', f'qword ptr [{"rbx" if heap_store else "rcx"} + {hex(native_offset)}], rbx'))
        bodies[start] = [(start + at, op, value) for at, (op, value) in enumerate(args)]
        raw[start] = b'\x48\x8b\x05' + struct.pack('<i', literal - start - 7)
        sizes[start] = {row[0]: 7 for row in bodies[start]}
    index = SimpleNamespace(blocks=blocks, all_blocks=all_blocks, literals=literals,
        extent=lambda start: start + 7, read=lambda start, count: raw[start],
        body=lambda start: (bodies[start], 'a' * 64), instruction_sizes=lambda start: sizes[start])
    return index, names


def test_table_binding_uses_original_literals_and_typed_arrays_after_names_and_offsets_move():
    index, names = binding_fixture()
    result = tables.bindings(index, names)
    assert set(result) == names
    assert all(row['fields'][0]['name'] == 'NewlyAdded' for row in result.values())


@pytest.mark.parametrize('changes', [{'heap_store': True}, {'clobber': True}])
def test_unowned_heap_or_clobbered_receiver_cannot_become_a_static_path_binding(changes):
    index, names = binding_fixture(**changes)
    with pytest.raises(ValueError):
        tables.bindings(index, names)


def row_fixture(*, clobber=False, unknown_bit=False, wrong_width=False):
    base = 0x180000000
    rows = [('mov', 'rbx, rdx'), ('mov', 'rsi, rcx'), ('call', hex(base + 0x300)),
            ('mov', 'rdi, rax'), ('test', 'dil, 0x2' if unknown_bit else 'dil, 0x1'),
            ('mov', 'rcx, rsi'), ('call', hex(base + 0x400)), ('mov', 'rdx, qword ptr [rbx]')]
    if clobber:
        rows.append(('xor', 'eax, eax'))
    rows.append(('mov', ('byte' if wrong_width else 'dword') + ' ptr [rdx + 0x28], ' + ('al' if wrong_width else 'eax')))
    index = SimpleNamespace(base=base, blocks={}, methods={
        0x300: [{'owner': 'Reader', 'signature': 'public static ulong ReadMask(Reader)'}],
        0x400: [{'owner': 'Reader', 'signature': 'public static uint ReadUnsigned(Reader)'}]},
        body=lambda address: ([(at, op, args) for at, (op, args) in enumerate(rows)], 'b' * 64))
    binding = {'fields': [{'type': 'uint', 'name': 'NewlyAdded', 'offset': 0x28}],
        'row_block': '    public static void FromBinary(Reader, Row&) {}', 'from_binary': 0x100,
        'table_block': ''}
    return index, binding


def test_new_field_order_comes_from_native_mask_and_store_not_managed_offset_order():
    index, binding = row_fixture()
    assert tables.descriptions(index, {'NewTable': binding})['NewTable'] == {
        'fields': [['NewlyAdded', 'u32']], 'identity': [], 'hash_byte_prefix': False, 'enums': {}}


@pytest.mark.parametrize('changes', [{'clobber': True}, {'unknown_bit': True}, {'wrong_width': True}])
def test_row_description_rejects_unbound_values_unknown_mask_bits_and_wrong_store_width(changes):
    index, binding = row_fixture(**changes)
    with pytest.raises(ValueError):
        tables.descriptions(index, {'NewTable': binding})


@pytest.mark.parametrize('clobber', [False, True])
def test_inline_textid_requires_owned_zigzag_and_both_ordered_varint_reads(clobber):
    base = 0x180000000
    rows = [('mov', 'rbx, rdx'), ('mov', 'rsi, rcx'), ('call', hex(base + 0x300)), ('mov', 'rdi, rax'),
            ('test', 'dil, 0x1'), ('mov', 'rcx, rsi'), ('call', hex(base + 0x300)),
            ('mov', 'r15, rax'), ('shr', 'eax, 0x1'), ('and', 'r15d, 0x1'),
            ('neg', 'r15d'), ('xor', 'r15d, eax'), ('mov', 'rcx, rsi'), ('call', hex(base + 0x300)),
            ('mov', 'rdx, qword ptr [rbx]')]
    if clobber:
        rows.append(('xor', 'r15d, r15d'))
    rows.extend([('mov', 'dword ptr [rdx + 0x28], r15d'), ('mov', 'dword ptr [rdx + 0x2c], 0x0'),
                 ('mov', 'qword ptr [rdx + 0x30], rax')])
    index = SimpleNamespace(base=base, blocks={}, methods={
        0x300: [{'owner': 'Reader', 'signature': 'public static ulong ReadUnsigned(Reader)'}]},
        body=lambda address: ([(at, op, args) for at, (op, args) in enumerate(rows)], 'b' * 64))
    binding = {'fields': [{'type': 'RPG.Client.TextID', 'name': 'NewText', 'offset': 0x28}],
        'row_block': '    public static void FromBinary(Reader, Row&) {}', 'from_binary': 0x100, 'table_block': ''}
    if clobber:
        with pytest.raises(ValueError):
            tables.descriptions(index, {'NewTable': binding})
    else:
        assert tables.descriptions(index, {'NewTable': binding})['NewTable']['fields'] == [['NewText', 'textid']]


def test_signed_scalar_allows_the_other_register_to_hold_the_shifted_half():
    index, binding = row_fixture()
    rows, digest = index.body(0x100)
    shape = [('mov', 'ecx, eax'), ('shr', 'ecx, 0x1'), ('and', 'eax, 0x1'),
             ('neg', 'eax'), ('xor', 'eax, ecx')]
    combined = [(op, args) for _, op, args in rows[:7]] + shape + [(op, args) for _, op, args in rows[7:]]
    index.body = lambda address: ([(at, op, args) for at, (op, args) in enumerate(combined)], digest)
    binding['fields'][0]['type'] = 'int'
    assert tables.descriptions(index, {'NewTable': binding})['NewTable']['fields'] == [['NewlyAdded', 's32']]
