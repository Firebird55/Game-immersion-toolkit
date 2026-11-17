"""Original usage records must preserve kind/owner and reject malformed bounds."""
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_native_usages as usages


def fixture(*, methods=(10, 10), kind=3, relocated=False):
    # All codec operands are authored small values, unrelated to a game profile.
    p = dict(list_add=5, list_slot=0x24 if relocated else 0x10, list_mul=7,
        list_shift=2, list_key_add=3, list_key_xor=9, list_bias=11,
        mul1=3, xor1=5, mul2=11, add1=13, shift1=2, mul3=17, add2=19, shift2=3,
        pair_slot=0x38 if relocated else 0x20, pair_add=17, source_add=23,
        kind_shift=29, kind_max=7, destination_xor=29, index_mask=(1 << 29) - 1)
    header, body = bytearray(0x208), bytearray(256)
    lists, pairs = (80, 160) if relocated else (64, 128)
    struct.pack_into('<I', header, p['list_slot'], lists - p['list_add'])
    struct.pack_into('<I', header, p['pair_slot'], pairs - p['pair_add'])
    for i, start in enumerate((0, 3)):
        key = (((i * p['list_mul']) >> p['list_shift']) + p['list_key_add']) ^ p['list_key_xor']
        struct.pack_into('<I', body, lists + i * 4, (start - key - p['list_bias']) & usages.U32)
    # The first record deliberately has the same numeric destination in another
    # cache kind. It must never collide with the method-definition cache.
    for i, (record_kind, method) in enumerate(((1, 99), (kind, methods[0]), (3, methods[1]))):
        value = (((i * p['mul1']) ^ p['xor1']) * p['mul2'] + p['add1']) & usages.U64
        value >>= p['shift1']
        key = ((value * p['mul3'] + p['add2']) & usages.U64) >> p['shift2']
        destination = ((9 + key) & usages.U32) ^ p['destination_xor']
        source = (((record_kind << p['kind_shift']) | method) + key - p['source_add']) & usages.U32
        struct.pack_into('<II', body, pairs + i * 8, destination, source)
    return bytes(header), bytes(body), p, 0, 0x5000, {0x5048}, {10: None, 11: None}


@pytest.mark.parametrize('relocated', [False, True])
def test_original_method_kind_join_survives_moved_tables_and_other_cache_kind_collision(relocated):
    assert usages.decode_usages(*fixture(relocated=relocated)) == {0x5048: 10}


@pytest.mark.parametrize('change', ['unknown-field', 'bad-slot', 'bad-shift', 'truncated-header', 'truncated-body',
                                   'missing-method', 'conflicting-method', 'generic-method', 'missing-destination'])
def test_unsupported_or_malformed_usage_description_cannot_publish_a_factory_binding(change):
    args = list(fixture(methods=(10, 11) if change == 'conflicting-method' else (10, 10),
                        kind=6 if change == 'generic-method' else 3))
    if change == 'unknown-field':
        args[2]['ignored'] = 1
    elif change == 'bad-slot':
        args[2]['list_slot'] = 0x207
    elif change == 'bad-shift':
        args[2]['shift1'] = 64
    elif change == 'truncated-header':
        args[0] = args[0][:-1]
    elif change == 'truncated-body':
        args[1] = args[1][:140]
    elif change == 'missing-method':
        args[-1] = {}
    elif change == 'missing-destination':
        args[-2] = {0x5050}
    with pytest.raises(ValueError):
        usages.decode_usages(*args)


def constructor_fixture(change=None):
    rows = [('sub', 'rsp, 0x28'), ('cmp', 'byte ptr [rip + 0x100], 0x0'), ('je', 'COLD'),
            ('mov', 'rcx, qword ptr [rip + 0x20]'), ('mov', 'edx, 0x2'), ('call', '0x1500'),
            ('test', 'rax, rax'), ('je', '0x900'), ('mov', 'ecx, dword ptr [rax + 0x18]'),
            ('mov', 'rdx, qword ptr [rip + 0x30]'), ('mov', 'qword ptr [rax + 0x20], rdx')]
    if change == 'clobber-array':
        rows.append(('xor', 'eax, eax'))
    if change == 'clobber-source':
        rows.insert(10, ('xor', 'edx, edx'))
    if change == 'partial-array-write':
        rows.append(('mov', 'byte ptr [rax + 0x20], 0x0'))
    rows += [('mov', 'qword ptr [rax + 0x28], 0x0'), ('mov', 'rcx, qword ptr [rip + 0x50]'),
             ('mov', 'qword ptr [rcx + 0x48], rax'), ('add', 'rsp, 0x28'), ('ret', ''), ('call', '0x900')]
    cold = len(rows)
    rows += [('mov', 'ecx, 0x5'), ('call', '0x1700'),
             ('mov', f'byte ptr [rip + {hex(0x102 - (cold + 3))}], 0x1'), ('jmp', '0x1003'), ('int3', '')]
    rows[2] = ('je', hex(0x1000 + cold))
    return SimpleNamespace(base=0x1000, method=lambda *args: 0,
        linear_body=lambda address: ([(i, op, args) for i, (op, args) in enumerate(rows)], 'a' * 64))


def test_constructor_retains_explicit_empty_slots_and_original_static_storage_owner():
    value = usages.constructor(constructor_fixture(), 'AuthoredRegistry')
    assert value['elements'] == {0: 0x103a, 1: None}
    assert value['storage'] == (0x5d, 0x48)
    assert value['list_id'] == 5 and value['initializer'] == 0x700


@pytest.mark.parametrize('change', ['clobber-array', 'clobber-source', 'partial-array-write'])
def test_constructor_cannot_bind_overwritten_array_or_unowned_pointer(change):
    with pytest.raises(ValueError):
        usages.constructor(constructor_fixture(change), 'AuthoredRegistry')


def dispatcher_fixture(change=None):
    rows = [('mov', 'rdi, rcx'), ('mov', 'r14, rdx'), ('mov', 'rcx, rdi'), ('call', '0x1100'),
            ('mov', 'rbx, rax'), ('mov', 'rax, qword ptr [rip + 0x4a]'),
            ('mov', 'rax, qword ptr [rax + 0x48]'), ('mov', 'esi, ebx'),
            ('mov', 'rax, qword ptr [rax + rsi*8 + 0x20]'), ('mov', 'rcx, rdi'),
            ('call', 'qword ptr [rax + 0x8]'), ('mov', 'qword ptr [r14], rax'), ('ret', '')]
    if change == 'wrong-storage':
        rows[5] = ('mov', 'rax, qword ptr [rip + 0x5a]')
    elif change == 'pointer-truncation':
        rows[0] = ('mov', 'edi, ecx')
    elif change == 'wrong-index-codec':
        rows[3] = ('call', '0x1200')
    elif change == 'return-clobber':
        rows.insert(11, ('xor', 'eax, eax'))
    elif change == 'branch-bypass':
        rows[2] = ('je', '0x1006')
    return SimpleNamespace(base=0x1000, method=lambda *args: 0,
        graph=lambda address: ([(i, op, args) for i, (op, args) in enumerate(rows)], 'a' * 64))


def test_dispatcher_owns_original_reader_index_table_and_returned_object():
    assert usages._dispatcher(dispatcher_fixture(), 'Registry', 'Reader', 'Base', (0x50, 0x48), 0x100) == 0


@pytest.mark.parametrize('change', ['wrong-storage', 'pointer-truncation', 'wrong-index-codec', 'return-clobber', 'branch-bypass'])
def test_dispatcher_rejects_alias_substitution_or_a_path_bypassing_its_table_owner(change):
    with pytest.raises(ValueError):
        usages._dispatcher(dispatcher_fixture(change), 'Registry', 'Reader', 'Base', (0x50, 0x48), 0x100)


def codec_fixture():
    p = fixture()[2]
    h = lambda key: hex(p[key])
    lines = [
        f'mov eax, {h("list_add")}', f'add eax, dword ptr [rdx + {h("list_slot")}]',
        'mov esi, ecx', 'cdqe ', 'mov r14, qword ptr [rip + 0x20]', 'add rax, r14',
        f'movabs r12, {h("list_mul")}', 'mov edi, dword ptr [rax + rsi*4]', 'imul rsi, r12',
        f'shr rsi, {h("list_shift")}', 'inc ecx', 'imul r12, rcx', f'shr r12, {h("list_shift")}',
        f'add esi, {h("list_key_add")}', f'xor esi, {h("list_key_xor")}', 'lea ebx, [rdi + rsi]',
        f'add r12d, {h("list_key_add")}', f'xor r12d, {h("list_key_xor")}',
        'add r12d, dword ptr [rax + rcx*4]', 'sub r12d, ebx',
        'lea r13d, [rdi + rsi]', f'add r13d, {h("list_bias")}',
        'mov ecx, r13d', f'imul rax, rcx, {h("mul1")}', f'xor rax, {h("xor1")}',
        f'imul rax, {h("mul2")}', f'movabs rbx, {h("add1")}', 'add rax, rbx',
        f'shr rax, {h("shift1")}', f'imul rdi, rax, {h("mul3")}', f'movabs rax, {h("add2")}',
        'add rdi, rax', f'shr rdi, {h("shift2")}', f'mov eax, dword ptr [rdx + {h("pair_slot")}]',
        f'mov ebx, {h("pair_add")}', 'add eax, ebx', 'movsxd rsi, eax', 'add rsi, r14',
        'mov eax, dword ptr [rsi + rcx*8 + 0x4]', 'sub eax, edi', f'add eax, {h("source_add")}',
        'mov ebx, eax', f'shr ebx, {h("kind_shift")}', f'cmp ebx, {h("kind_max")}', 'ja 0x9000',
        'mov esi, dword ptr [rsi + rcx*8]', f'mov ecx, {h("destination_xor")}', 'xor esi, ecx',
        'sub esi, edi', 'mov ecx, eax', f'and ecx, {h("index_mask")}']
    return [(i, *line.split(' ', 1)) for i, line in enumerate(lines)], p


def test_codec_parameters_come_from_authored_native_operands_and_require_unclobbered_expression():
    rows, p = codec_fixture()
    assert usages.codec_parameters(rows) == p
    rows.insert(1, (0, 'xor', 'eax, eax'))
    rows = [(i, operation, args) for i, (_, operation, args) in enumerate(rows)]
    with pytest.raises(ValueError):
        usages.codec_parameters(rows)


@pytest.mark.parametrize('rows,expected', [
    ([(0, 'call', '0x9000'), (1, 'int', '0x3'), (2, 'ret', '')], True),
    ([(0, 'je', '0x1002'), (1, 'int3', ''), (2, 'ret', '')], False),
    ([(0, 'jmp', '0x9000')], False),
    ([(0, 'call', '0x9000')], False)])
def test_nonreturning_callee_requires_all_reachable_exits_to_trap(rows, expected):
    index = SimpleNamespace(base=0x1000, linear_body=lambda *args, **kwargs: (rows, 'a' * 64))
    assert usages._nonreturning(index, 0) is expected


def test_proved_exception_trap_does_not_create_a_false_path_into_factory_dispatch():
    index = dispatcher_fixture()
    rows, digest = index.graph(0)
    # A null/error call is laid immediately before another cold block. Treating
    # this proved trap as returning would invent a path bypassing table setup.
    rows = list(rows)
    rows[2] = (2, 'je', '0x100d')
    rows += [(13, 'call', '0x1300'), (14, 'jmp', '0x1006')]
    index.graph = lambda address: (rows, digest)
    index.linear_body = lambda address, **kwargs: (
        [(0x300, 'call', '0x9000'), (0x301, 'int', '0x3')] if address == 0x300 else [(address, 'ret', '')], 'b' * 64)
    assert usages._dispatcher(index, 'Registry', 'Reader', 'Base', (0x50, 0x48), 0x100) == 0
