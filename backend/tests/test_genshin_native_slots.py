"""Authored native slots and output-pointer ownership; no original game bytes."""
import struct
from types import SimpleNamespace

import pytest

from backend.genshin_native_x64 import Definitions, decoder
from backend.genshin_native_words import Context
from backend.genshin_native_fields import pointer_states
from backend.genshin_native_slots import _getter, _handle, _wrapper
from backend.tests.test_genshin_native_bootstrap import requires_decoder


def context(raw):
    seq = list(decoder().disasm(raw, 0x1000))
    def missing(_rva): raise ValueError('No authored callee body')
    return Context(SimpleNamespace(base=0x1000, instructions=lambda rva: seq, window=missing), 0)


@requires_decoder
@pytest.mark.parametrize('offset', [0, 8])
def test_only_the_declared_native_output_populates_its_actual_stack_field(offset):
    target = 0x200
    raw = bytes.fromhex('488d4c2420e8') + struct.pack('<i', target - 10)
    raw += bytes.fromhex('488b4424') + bytes([0x20 + offset]) + bytes.fromhex('895008c3')
    ctx = context(raw)
    owned = pointer_states(ctx, output_pointers={target: (32, {offset: ('native-buffer', 0)})})
    assert owned[0x100f][('reg', 'rax')] == ('native-buffer', 0)
    unknown = pointer_states(ctx, output_pointers={target + 1: (32, {offset: ('native-buffer', 0)})})
    assert ('reg', 'rax') not in unknown[0x100f]


@requires_decoder
@pytest.mark.parametrize('overwrite', ['c644242300', '660fefc0f30f7f442418'])
def test_partial_or_vector_stack_writes_expire_an_owned_output_pointer(overwrite):
    target = 0x200
    raw = bytes.fromhex('488d4c2420e8') + struct.pack('<i', target - 10)
    raw += bytes.fromhex(overwrite + '488b442420895008c3')
    ctx = context(raw)
    states = pointer_states(ctx, output_pointers={target: (32, {0: ('native-buffer', 0)})})
    store = ctx.seq[-2]
    assert ('reg', 'rax') not in states[store.address]


@requires_decoder
def test_competing_output_destinations_reject_instead_of_picking_a_branch():
    prefix = bytes.fromhex('85d27407488d4c2420eb05488d4c2428')
    raw = prefix + b'\xe8' + struct.pack('<i', 0x200 - len(prefix) - 5) + b'\xc3'
    with pytest.raises(ValueError, match='unambiguous stack destination'):
        pointer_states(context(raw), output_pointers={0x200: (32, {0: ('native-buffer', 0)})})


@requires_decoder
@pytest.mark.parametrize('slot', [0, 48, 120])
@pytest.mark.parametrize('padding', [False, True])
def test_original_getter_follows_changed_native_slot_and_typed_helper(slot, padding):
    start, target = 0x20, 0x200
    raw = bytes.fromhex('488b4908' + ('90' if padding else '') + '4881e100ffffff')
    raw += bytes.fromhex('31d2') if slot == 0 else b'\xba' + struct.pack('<I', slot)
    raw += b'\xe9' + struct.pack('<i', target - start - len(raw) - 5)
    image = bytearray(0x300); image[start:start + len(raw)] = raw
    method = {'rva': start}
    helper = {'owner': {'definition': 7}, 'method': {'rva': target, 'return_type': {'kind': 14},
        'parameters': [{'type': {'kind': 11}}, {'type': {'kind': 8}}]}}
    view = SimpleNamespace(image=SimpleNamespace(base=0x1000, data=bytes(image), offset=lambda at, size=1: at),
                           methods_at=lambda at: (helper,) if at == target else ())
    result = _getter(view, method, [start, 0x60])
    assert result['slot'] == slot and result['handle_offset'] == 8 and result['handle_mask'] == (1 << 64) - 256
    assert result['helper'] == helper
    helper['method']['return_type']['kind'] = 9
    with pytest.raises(ValueError): _getter(view, method, [start, 0x60])


@requires_decoder
@pytest.mark.parametrize('changed', [False, True])
def test_slot_helpers_must_use_the_same_current_object_handle(changed):
    offset = 16 if changed else 8
    raw = bytes.fromhex('4889cb488b73') + bytes([offset]) + bytes.fromhex('4881e600ffffff4889f1e800000000c3')
    ctx = context(raw)
    call = ctx.seq[-2]
    invoke = lambda: _handle(ctx, Definitions(ctx.seq), pointer_states(ctx), call.address,
                             'rcx', 8, (1 << 64) - 256)
    if changed:
        with pytest.raises(ValueError, match='another object'): invoke()
    else:
        assert invoke() == 'masked'


@pytest.mark.parametrize('buffer_offset', [16, 24])
def test_wrapper_buffer_position_comes_from_current_typed_metadata(buffer_offset):
    fields = [
        {'name': '_buffer', 'authored_offset_word': buffer_offset, 'type': {'kind': 15}},
        {'name': '_page', 'authored_offset_word': 40 - buffer_offset, 'type': {'kind': 18}},
        {'name': '_size', 'authored_offset_word': 36, 'type': {'kind': 8}},
        {'name': '_flag', 'authored_offset_word': 40, 'type': {'kind': 2}},
    ]
    method = {'name': 'QueryWrapperInternal', 'rva': 128, 'parameters': [{'type': {'kind': 11}}],
              'return_type': {'namespace': 'MoleMole.NativeConfig', 'name': 'NativeWrapper', 'definition': 9}}
    view = SimpleNamespace(named=lambda *args: {'definition': 7}, methods=lambda _: [method], field_offsets=lambda _: fields)
    assert _wrapper(view) == (method, 32, buffer_offset - 16)
    fields[0]['type']['kind'] = 8
    with pytest.raises(ValueError): _wrapper(view)
