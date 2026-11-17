"""Authored changing import names, export ownership and native continuations."""
import struct
from types import SimpleNamespace

import pytest

from backend.endfield_native_import import NativeImage, import_descriptor
from backend.tests.endfield_parameter_fixture import instruction, immediate, memory, register


def descriptor(module='AuthoredSound', entrypoint='ChangedEntry'):
    data = {0x9000: module.encode('utf-16-le') + b'\0\0', 0xa000: entrypoint.encode() + b'\0'}
    rows = []
    def append(name, *operands):
        row = instruction(name, *operands)
        row.address = 0x4000 + len(rows)
        rows.append(row)
        return row
    def pointer(offset, address):
        row = append('lea', register('rax'), memory('rip'))
        row.operands[1].mem.disp = address - row.address - row.size
        append('mov', memory('rsp', offset), register('rax'))
    def constant(offset, value, size):
        operand = immediate(value)
        operand.size = size
        append('mov', memory('rsp', offset, size=size), operand)
    append('sub', register('rsp'), immediate(0x58))
    pointer(0x20, 0x9000)
    constant(0x28, len(module), 8)
    append('lea', register('rcx'), memory('rsp', 0x20))
    pointer(0x30, 0xa000)
    constant(0x38, len(entrypoint), 8)
    for offset, value, size in ((0x40, 0, 4), (0x44, 2, 4), (0x48, 16, 4), (0x4c, 0, 1)):
        constant(offset, value, size)
    append('call', immediate(0x7777))
    append('add', register('rsp'), immediate(0x58))
    append('ret')
    def read(address, size):
        assert address in data and size == len(data[address])
        return data[address]
    return rows, SimpleNamespace(data_read=read)


@pytest.mark.parametrize('module,entrypoint', [('AuthoredSound', 'ChangedEntry'), ('New_Module', 'CSharp_AfterUpdate')])
def test_import_comes_from_current_complete_descriptor_not_an_export_name_list(module, entrypoint):
    rows, image = descriptor(module, entrypoint)
    result = import_descriptor(rows, image)
    assert (result.module, result.entrypoint) == (module, entrypoint)


@pytest.mark.parametrize('change', ['wrong_abi', 'duplicate_assignment', 'second_call', 'branch', 'unsafe_module', 'unsafe_entry'])
def test_import_definition_changes_are_fail_closed(change):
    rows, image = descriptor('../Wrong' if change == 'unsafe_module' else 'Owned',
                             'Wrong/name' if change == 'unsafe_entry' else 'OwnedEntry')
    if change == 'wrong_abi':
        next(row for row in rows if row.mnemonic == 'mov' and row.operands[0].mem.disp == 0x44).operands[1].imm = 3
    elif change == 'duplicate_assignment':
        rows.insert(-3, next(row for row in rows if row.mnemonic == 'mov'))
    elif change == 'second_call':
        rows.insert(-3, instruction('call', immediate(0x9999)))
    elif change == 'branch':
        rows.insert(-3, instruction('jne', immediate(rows[0].address)))
    with pytest.raises(ValueError):
        import_descriptor(rows, image)


def native_fixture(*, name='RenamedOwnedExport', shift=0):
    raw, pe = bytearray(0x1200), 0x80
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, pe)
    raw[pe:pe + 4] = b'PE\0\0'
    struct.pack_into('<HH', raw, pe + 4, 0x8664, 3)
    struct.pack_into('<H', raw, pe + 20, 240)
    opt = pe + 24
    struct.pack_into('<H', raw, opt, 0x20b)
    struct.pack_into('<Q', raw, opt + 24, 0x190000000)
    struct.pack_into('<I', raw, opt + 108, 16)
    for n, (section, rva, size, at) in enumerate([(b'.text', 0x1000, 0x200, 0x400),
                (b'.rdata', 0x2000, 0x400, 0x600), (b'.pdata', 0x3000, 24, 0xa00)]):
        struct.pack_into('<8sIIII', raw, opt + 240 + n * 40, section, size, rva, size, at)
        struct.pack_into('<I', raw, opt + 240 + n * 40 + 36, 0x60000020 if n == 0 else 0x40000040)
    struct.pack_into('<II', raw, opt + 112, 0x2200, 0x100)
    struct.pack_into('<II', raw, opt + 136, 0x3000, 24)
    start = 0x1000 + shift
    raw[0x400 + shift:0x403 + shift] = b'\x75\x0e\xc3'  # Conditional edge to owned continuation.
    raw[0x410 + shift:0x412 + shift] = b'\x90\xc3'
    raw[0x430 + shift:0x435 + shift] = b'\xe9' + struct.pack('<i', -0x35)
    struct.pack_into('<III', raw, 0xa00, start, start + 3, 0x2100)
    struct.pack_into('<III', raw, 0xa0c, start + 16, start + 18, 0x2110)
    raw[0x700:0x704] = b'\x01\0\0\0'
    raw[0x710:0x714] = b'\x21\0\0\0'
    struct.pack_into('<III', raw, 0x714, start, start + 3, 0x2100)
    struct.pack_into('<IIHH7I', raw, 0x800, 0, 0, 0, 0, 0, 1, 1, 1, 0x2280, 0x2290, 0x22a0)
    struct.pack_into('<I', raw, 0x880, start + 0x30)
    struct.pack_into('<I', raw, 0x890, 0x22b0)
    struct.pack_into('<H', raw, 0x8a0, 0)
    raw[0x8b0:0x8b0 + len(name) + 1] = name.encode() + b'\0'
    return bytes(raw), start


@pytest.mark.parametrize('shift,name', [(0, 'RenamedOwnedExport'), (0x40, 'A_New_Entry_After_Update')])
def test_current_eat_and_chained_unwind_resolve_without_version_addresses(shift, name):
    raw, root = native_fixture(shift=shift, name=name)
    image = NativeImage(raw)
    assert image.thunk(image.export(name)) == root
    assert [row.mnemonic for row in image.body(root)] == ['jne', 'ret', 'nop', 'ret']
    with pytest.raises(ValueError, match='unique current export'):
        image.export('OldExport')


@pytest.mark.parametrize('mutation', ['forwarded', 'wrong_owner', 'middle_branch', 'outside_branch', 'indirect_thunk', 'cycle'])
def test_native_export_and_continuation_changes_never_borrow_adjacent_code(mutation):
    raw, root = native_fixture()
    raw = bytearray(raw)
    if mutation == 'forwarded':
        struct.pack_into('<I', raw, 0x880, 0x22b0)
    elif mutation == 'wrong_owner':
        raw[0x710] = 1
    elif mutation == 'middle_branch':
        raw[0x401] = 0xff
    elif mutation == 'outside_branch':
        raw[0x401] = 40
    elif mutation == 'indirect_thunk':
        raw[0x430:0x435] = b'\xff\xe0\x90\x90\x90'
    elif mutation == 'cycle':
        struct.pack_into('<i', raw, 0x431, -5)
    image = NativeImage(bytes(raw))
    with pytest.raises(ValueError):
        image.body(image.thunk(image.export('RenamedOwnedExport')))
