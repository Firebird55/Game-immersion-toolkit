"""Semantic return/store joins must survive unrelated work, never clobbers."""
from types import SimpleNamespace

import pytest

from backend.starrail_native_routes import _version_schema, _enum_converter


@pytest.mark.parametrize('intervening,expected', [
    ([], 'DispatchSeed'), ([('test', 'rax, rax')], 'DispatchSeed'),
    ([('xor', 'eax, eax')], None), ([('mov', 'rsi, rdi')], None),
    ([('call', '0x9999')], None)])
def test_version_semantics_require_unclobbered_return_and_receiver(intervening, expected):
    index = SimpleNamespace(base=0, blocks={'RPG.GameCore.VersionData':
        '    public uint DispatchSeed // Offset: 0x48, Token: 0x1'})
    rows = [('mov', 'rsi, rcx'), ('call', '0x1234'), *intervening, ('mov', 'dword ptr [rsi + 0x48], eax')]
    assert _version_schema(index, [(i, op, args) for i, (op, args) in enumerate(rows)], {0x1234: 'u32'}) == [
        {'kind': 'u32', 'semantic': expected}]


def test_uint_return_can_be_widened_into_an_original_ulong_field():
    index = SimpleNamespace(base=0, blocks={'RPG.GameCore.VersionData':
        '    public ulong DispatchSeed // Offset: 0x68, Token: 0x1'})
    assert _version_schema(index, [(0, 'mov', 'rsi, rcx'), (1, 'call', '0x1234'), (2, 'mov', 'qword ptr [rsi + 0x68], rax')],
                           {0x1234: 'u32'}) == [{'kind': 'u32', 'semantic': 'DispatchSeed'}]


def test_saved_string_return_remains_owned_across_a_write_barrier_call():
    index = SimpleNamespace(base=0, blocks={'RPG.GameCore.VersionData':
        '    public string PakType // Offset: 0x28, Token: 0x1'})
    instructions = [(0, 'mov', 'rsi, rcx'), (1, 'call', '0x1234'), (2, 'mov', 'rbx, rax'),
                    (3, 'call', '0x9999'), (4, 'mov', 'qword ptr [rsi + 0x28], rbx')]
    assert _version_schema(index, instructions, {0x1234: 'string'}) == [{'kind': 'string', 'semantic': 'PakType'}]


@pytest.mark.parametrize('change', [None, 'constant', 'result-clobber', 'input-rebound'])
def test_enum_wire_labels_require_original_constants_return_flow_and_string_argument(change):
    rows = [('mov', 'rsi, rcx'), ('je', '0x5'), ('mov', 'rdx, qword ptr [rip + 0x7fd]'),
            ('mov', 'edi, 0x6' if change == 'constant' else 'edi, 0x4'), ('jmp', '0x8'),
            ('mov', 'rdx, qword ptr [rip + 0x8fa]'), ('mov', 'edi, 0x5'), ('jmp', '0x8'),
            ('mov', 'rcx, rbx' if change == 'input-rebound' else 'rcx, rsi'), ('call', '0x500'),
            ('test', 'al, al'), ('jne', '0xd'), ('int3', ''),
            ('xor', 'edi, edi') if change == 'result-clobber' else ('test', 'eax, eax'),
            ('mov', 'eax, edi'), ('ret', '')]
    index = SimpleNamespace(base=0, blocks={'PackageKind':
        'public enum PackageKind {\n    public const PackageKind ALPHA = 4 // Offset: 0x0\n'
        '    public const PackageKind BETA = 5 // Offset: 0x0\n'},
        literals={0x800: 'ALPHA', 0x900: 'BETA'},
        graph=lambda address: ([(at, op, args) for at, (op, args) in enumerate(rows)], 'a' * 64),
        methods={0x500: [{'owner': 'System.String#4', 'signature': 'private static bool EqualsHelper(string, string)'}]})
    if change:
        with pytest.raises(ValueError):
            _enum_converter(index, 0x100, 'PackageKind')
    else:
        assert _enum_converter(index, 0x100, 'PackageKind') == 'PackageKind'


@pytest.mark.parametrize('transfer,expected', [('scalar', 0x48), ('vector', 0x38), ('swap', 0x40)])
def test_region_name_belongs_to_setter_receiver_and_not_same_offset_in_gateway_array(transfer, expected):
    # Array element zero shares the region Name offset. This used to select the
    # primary gateway as the name when a compiler combined adjacent field copies.
    from backend.starrail_native_routes import _region_sources
    rows = [('mov', 'rdx, qword ptr [rsi + 0x18]'), ('mov', 'qword ptr [rax + 0x20], rdx'),
            ('mov', 'rcx, qword ptr [rsi + 0x28]'), ('mov', 'qword ptr [rax + 0x28], rcx'),
            ('mov', 'rcx, rbx'), ('mov', 'rdx, rax'), ('call', '0x500')]
    rows += ([('mov', 'rcx, qword ptr [rsi + 0x48]'), ('mov', 'qword ptr [rbx + 0x20], rcx')]
             if transfer == 'scalar' else [('movdqu', 'xmm0, xmmword ptr [rsi + 0x38]')]
             + ([('pshufd', 'xmm0, xmm0, 0x4e')] if transfer == 'swap' else [])
             + [('movdqu', 'xmmword ptr [rbx + 0x20], xmm0')])
    assert _region_sources([(i, op, args) for i, (op, args) in enumerate(rows)], 0x500, 0x20) == {
        'name': expected, 'primary_gateway': 0x18, 'alternate_gateway': 0x28}


@pytest.mark.parametrize('change', ['clobber-source', 'clobber-receiver', 'wrong-shuffle', 'wrong-array', 'clobber-vector'])
def test_region_transfer_rejects_unproved_aliases_and_lane_operations(change):
    from backend.starrail_native_routes import _region_sources
    rows = [('mov', 'rdx, qword ptr [rsi + 0x18]'), ('mov', 'qword ptr [rax + 0x20], rdx'),
            ('mov', 'rcx, qword ptr [rsi + 0x28]'), ('mov', 'qword ptr [rax + 0x28], rcx'),
            ('mov', 'rcx, rbx'), ('mov', 'rdx, rdi' if change == 'wrong-array' else 'rdx, rax'), ('call', '0x500')]
    if change.startswith('clobber-') and change != 'clobber-vector':
        rows.append(('xor', 'esi, esi' if change == 'clobber-source' else 'ebx, ebx'))
    rows += [('movdqu', 'xmm0, xmmword ptr [rsi + 0x38]'),
             ('pshufd', 'xmm0, xmm0, 0x1b' if change == 'wrong-shuffle' else 'xmm0, xmm0, 0x4e')]
    if change == 'clobber-vector':
        rows.append(('pxor', 'xmm0, xmm0'))
    rows.append(('movdqu', 'xmmword ptr [rbx + 0x20], xmm0'))
    with pytest.raises(ValueError):
        _region_sources([(i, op, args) for i, (op, args) in enumerate(rows)], 0x500, 0x20)
