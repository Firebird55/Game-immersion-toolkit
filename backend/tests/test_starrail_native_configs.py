"""Native path arguments and constructor defaults require original provenance."""
from types import SimpleNamespace

import pytest

from backend.starrail_native_configs import Descriptions, _path_recipe


def path_fixture(change=None):
    methods = {
        0x500: [{'owner': 'System.String#1', 'signature': 'public int LastIndexOf(char, int, int)'}],
        0x600: [{'owner': 'System.String#1', 'signature': 'public string Substring(int, int)'}],
        0x700: [{'owner': 'OwnedPool#2', 'signature': 'public static System.Text.StringBuilder GetBuilder()'}],
        0x800: [{'owner': 'System.Text.StringBuilder#3', 'signature': 'public System.Text.StringBuilder Append(string)'}],
        0x900: [{'owner': 'System.Text.StringBuilder#3', 'signature': 'public override string ToString()'}]}
    rows = [('mov', 'rsi, rcx'), ('mov', 'dx, 0x2e' if change != 'wrong-dot' else 'dx, 0x2f'),
            ('call', '0x1500'), ('mov', 'rcx, rsi'), ('xor', 'edx, edx'), ('mov', 'r8d, eax'),
            ('call', '0x1600'), ('mov', 'rbx, rax'), ('mov', 'rsi, qword ptr [rip + 0xa00]'),
            ('mov', 'r14, qword ptr [rip + 0xb00]'), ('call', '0x1700'),
            ('mov', 'edi, eax' if change == 'truncated-builder' else 'rdi, rax'),
            ('mov', 'rcx, rdi'), ('mov', 'rdx, rsi'), ('call', '0x1800'),
            ('mov', 'rcx, rdi'), ('mov', 'rdx, rbx'), ('call', '0x1800'),
            ('mov', 'rcx, rdi'), ('mov', 'rdx, r14'), ('call', '0x1800'),
            ('mov', 'rcx, rdi'), ('jmp', '0x1900'), ('mov', 'r8, qword ptr [rip + 0xc00]'), ('ret', '')]
    if change == 'clobbered-stem':
        rows[16] = ('xor', 'edx, edx')
    if change == 'extra-builder-call':
        methods[0x800][0]['signature'] = 'public System.Text.StringBuilder Append(char)'
    if change == 'partial-dot':
        rows[1] = ('mov', 'dl, 0x2e')
    rows[1:1] = [('mov', 'r9d, dword ptr [rcx + 0x18]'),
                 ('lea', 'r8d, [r9 - 0x2]' if change == 'restricted-search' else 'r8d, [r9 - 0x1]')]
    index = SimpleNamespace(base=0x1000, methods=methods,
        blocks={'System.String': 'private int m_stringLength // Offset: 0x18, Token: 0x1'},
        literals={11 + 0xa00: 'Original/', 12 + 0xb00: '.bin', 26 + 0xc00: 'Unrelated/'})
    return index, [(i, op, args) for i, (op, args) in enumerate(rows)]


def test_path_prefix_and_suffix_reach_original_stem_append_chain_not_unrelated_literal():
    assert _path_recipe(*path_fixture()) == ('Original/', '.bin')


@pytest.mark.parametrize('change', ['wrong-dot', 'partial-dot', 'restricted-search', 'truncated-builder',
                                   'clobbered-stem', 'extra-builder-call'])
def test_path_recipe_rejects_unproved_substring_or_builder_argument(change):
    with pytest.raises(ValueError):
        _path_recipe(*path_fixture(change))


def factory_fixture(change=None):
    rows = [('mov', 'rsi, rcx'), ('mov', 'rcx, qword ptr [rip + 0x80]'), ('call', '0x1200'),
            ('mov', 'rdi, rax'), ('mov', 'dword ptr [rax + 0x18], 0x5b'),
            ('mov', 'word ptr [rax + 0x20], 0x101'), ('mov', 'rcx, rsi'),
            ('mov', 'edx, eax' if change == 'truncated-object' else 'rdx, rax'),
            ('call', '0x1300'), ('mov', 'eax, edi' if change == 'truncated-return' else 'rax, rdi'), ('ret', '')]
    if change == 'unproved-store':
        rows.insert(6, ('movups', 'xmmword ptr [rax + 0x20], xmm0'))
    if change == 'reader-clobber':
        rows[6] = ('mov', 'rcx, rdi')
    instance = Descriptions.__new__(Descriptions)
    instance.index = SimpleNamespace(base=0x1000, literals={}, methods={})
    instance.allocator, instance.varuint = 0x200, 0x100
    return instance, [(i, op, args) for i, (op, args) in enumerate(rows)]


def test_factory_default_literals_belong_to_the_object_passed_to_reader_and_returned():
    instance, rows = factory_fixture()
    assert instance._flow(rows, mode='factory', stop=0x300) == [(0x18, 'dword', 91), (0x20, 'word', 0x101)]


@pytest.mark.parametrize('change', ['truncated-object', 'truncated-return', 'unproved-store', 'reader-clobber'])
def test_factory_cannot_substitute_a_clobbered_reader_object_or_unproved_default(change):
    instance, rows = factory_fixture(change)
    with pytest.raises(ValueError):
        instance._flow(rows, mode='factory', stop=0x300)


def test_partial_register_literal_does_not_invent_unknown_upper_default_bits():
    instance, _ = factory_fixture()
    rows = [(0, 'mov', 'al, 0x1'), (1, 'mov', 'byte ptr [rcx + 0x10], al'), (2, 'ret', '')]
    assert instance._flow(rows, mode='constructor', stop=None) == [(0x10, 'byte', 1)]
    rows[1] = (1, 'mov', 'dword ptr [rcx + 0x10], eax')
    with pytest.raises(ValueError):
        instance._flow(rows, mode='constructor', stop=None)
    rows.insert(0, (-1, 'mov', 'eax, 0x100'))
    assert instance._flow(rows, mode='constructor', stop=None) == [(0x10, 'dword', 0x101)]


def test_literal_scalar_float_load_preserves_all_bits_of_a_combined_default_store():
    instance, rows = factory_fixture()
    instance.index.read = lambda address, count: bytes.fromhex('0000803f00000040')[:count]
    rows = list(rows)
    rows[4:6] = [(4, 'movsd', 'xmm0, qword ptr [rip + 0x80]'), (5, 'movsd', 'qword ptr [rax + 0x20], xmm0')]
    assert instance._flow(rows, mode='factory', stop=0x300) == [(0x20, 'qword', 0x400000003f800000)]
    rows.insert(5, (4, 'addsd', 'xmm0, xmm1'))
    with pytest.raises(ValueError):
        instance._flow(rows, mode='factory', stop=0x300)
