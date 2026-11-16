"""Owned synthetic native/metadata evidence; no game bytes or addresses."""
import copy

import pytest

from backend import starrail_native_description as native
from backend.starrail_original_discovery import decode_bootstrap


READERS = {0x101: 'string', 0x202: 'u32', 0x303: 'bool'}


def evidence(offset=0x20, register='r12'):
    metadata = '\n'.join(f'    public {kind} {name} // Offset: {hex(offset + i * 8)}, Token: 0x1'
                         for i, (kind, name) in enumerate((
                             ('string', 'Label'), ('string[]', 'Endpoints'), ('uint', 'Index'), ('bool', 'Enabled'))))
    instructions = [
        ('call', '0x101'), ('mov', f'qword ptr [{register} + {hex(offset)}], rax'),
        ('call', '0x202'), ('call', '0x999'),
        ('mov', f'qword ptr [{register} + {hex(offset + 8)}], rax'),
        ('call', '0x101'), ('mov', 'qword ptr [rsi + rdi*8 + 0x20], rax'), ('jne', '0x5'),
        ('call', '0x202'), ('mov', f'dword ptr [{register} + {hex(offset + 16)}], eax'),
        ('call', '0x303'), ('mov', f'byte ptr [{register} + {hex(offset + 24)}], al')]
    return metadata, [(i + 1, op, args) for i, (op, args) in enumerate(instructions)]


@pytest.mark.parametrize(('offset', 'register'), [(0x20, 'r12'), (0x118, 'r15')])
def test_fields_move_and_new_scalar_without_release_allowlist(offset, register):
    schema = native.client_schema(*evidence(offset, register), READERS)
    assert schema == [{'kind': kind, 'semantic': name} for kind, name in (
        ('string', 'Label'), ('string_array', 'Endpoints'), ('u32', 'Index'), ('bool', 'Enabled'))]
    assert decode_bootstrap(b'\0\x01A\0\0\0\0\0\0\0\x05\x01', schema) == {
        'Label': 'A', 'Endpoints': [], 'Index': 5, 'Enabled': True}


def test_primitive_owner_and_obfuscated_names_are_derived():
    instructions = [(1, 'call', '0x1101'), (2, 'call', '0x1202'), (3, 'call', '0x1101'),
                    (4, 'call', '0x1404')]
    methods = {0x101: [{'owner': 'ReaderA', 'signature': 'public string X()'}],
               0x202: [{'owner': 'ReaderA', 'signature': 'public uint Y()'}],
               0x404: [{'owner': 'Unrelated', 'signature': 'public bool Z()'}]}
    assert native.primitive_readers(instructions, methods, 0x1000) == {0x1101: 'string', 0x1202: 'u32'}
    methods[0x101].append({'owner': 'ReaderA', 'signature': 'public uint Q()'})
    with pytest.raises(ValueError):
        native.primitive_readers(instructions, methods, 0x1000)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'width', 'register', 'kind',
                                      'clobbered', 'allocation', 'array_loop', 'unknown_type',
                                      'duplicate_name', 'unknown_reader', 'instruction_bounds'])
def test_incomplete_or_ambiguous_native_evidence_is_rejected(mutation):
    metadata, instructions = evidence()
    readers = copy.copy(READERS)
    if mutation == 'missing':
        instructions.pop()
    elif mutation == 'duplicate':
        instructions.append((99, 'mov', 'byte ptr [r12 + 0x38], al'))
    elif mutation == 'width':
        instructions[-1] = (12, 'mov', 'dword ptr [r12 + 0x38], al')
    elif mutation == 'register':
        instructions[-1] = (12, 'mov', 'byte ptr [r13 + 0x38], al')
    elif mutation == 'kind':
        readers[0x303] = 'u32'
    elif mutation == 'clobbered':
        instructions.insert(1, (1.5, 'call', '0x999'))
        instructions = [(i, op, args) for i, (_, op, args) in enumerate(instructions)]
    elif mutation == 'allocation':
        instructions[3] = (4, 'nop', '')
    elif mutation == 'array_loop':
        instructions[6] = (7, 'nop', '')
    elif mutation == 'unknown_type':
        metadata += '\n    public long Other // Offset: 0x90, Token: 0x2'
    elif mutation == 'duplicate_name':
        metadata += '\n    public uint Index // Offset: 0x90, Token: 0x2'
    elif mutation == 'unknown_reader':
        readers[0x303] = 'float'
    elif mutation == 'instruction_bounds':
        instructions[-1] = (1, 'ret', '')
    with pytest.raises(ValueError):
        native.client_schema(metadata, instructions, readers)


@pytest.mark.parametrize('instructions,methods', [
    ([], {}), ([(1, 'call', '0x101')], {0x101: [{'owner': 'A', 'signature': 'public string A()', 'extra': 1}]}),
    ([(1, 'call', '0x101'), (2, 'call', '0x202')],
     {0x101: [{'owner': 'A', 'signature': 'public string A()'}],
      0x202: [{'owner': 'B', 'signature': 'public uint B()'}]}),
])
def test_malformed_or_ambiguous_primitive_metadata(instructions, methods):
    with pytest.raises(ValueError):
        native.primitive_readers(instructions, methods, 0)
