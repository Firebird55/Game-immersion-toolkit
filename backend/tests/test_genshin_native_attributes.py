"""Independent metadata/ABI fixtures; no game bytes, indices or keys."""
import platform
import struct
import sys
from types import SimpleNamespace

import pytest

from backend import genshin_native_x64 as native
from backend.genshin_native_attributes import Attributes, attribute_profile
from backend.genshin_native_metadata import HEADER_SIZE


pytestmark = pytest.mark.skipif(not (sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')),
                                reason='Pinned Windows-amd64 decoder only')


def fixture(generation=0, *, wrong_global=False, wrong_index_store=False, clobber=False):
    header_key, multiplier, salt, bias = 0x13579 + generation, 17 + 2 * generation, 9 + generation, 33 + generation
    code, entry = bytearray(), 0x100

    def rip(prefix, target):
        code.extend(bytes.fromhex(prefix) + struct.pack('<i', target - entry - len(code) - 7))

    rip('488b3d', 0x808)
    rip('4c8b0d', 0x818 if wrong_global else 0x800)
    code.extend(bytes.fromhex('89d5496341484835') + struct.pack('<I', header_key) + bytes.fromhex('4801f889e94c69e1'))
    code.extend(struct.pack('<I', multiplier) + bytes.fromhex('4181f4') + struct.pack('<I', salt))
    code.extend(bytes.fromhex('488d14894c8d1c924901cb4901c3'))
    code.extend(bytes.fromhex('8943' if wrong_index_store else '896b') + bytes([32 + 4 * generation]))
    if clobber:
        code.extend(bytes.fromhex('41bc00000000'))
    code.extend(bytes.fromhex('410fb74b164429e181c1') + struct.pack('<I', bias) + bytes.fromhex('66894b2cc3'))
    seq = list(native.decoder().disasm(bytes(code), 0x1000 + entry))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    table_offset = 32
    header = bytearray(HEADER_SIZE)
    struct.pack_into('<I', header, 0x48, table_offset ^ header_key)
    expected = (150, 134, 6)
    metadata = header + bytearray(table_offset + 26 * len(expected))
    for index, flags in enumerate(expected):
        raw = (flags + ((index * multiplier) ^ salt) - bias) & 0xffff
        struct.pack_into('<H', metadata, HEADER_SIZE + table_offset + 26 * index + 0x16, raw)
    identifiers = SimpleNamespace(header=bytes(header), owner=SimpleNamespace(global_rva=0x800),
                                  profile=SimpleNamespace(body_global_rva=0x808))
    bindings = SimpleNamespace(identifiers=identifiers, roles={'method_offset': {'field': 0x48}},
                               methods=tuple(range(len(expected))), role=lambda name: table_offset)
    view = SimpleNamespace(image=image, bindings=bindings, metadata=bytes(metadata))
    return view, entry, expected


@pytest.mark.parametrize('generation', [0, 1, 5])
def test_original_attributes_follow_current_native_operands_and_abi(generation):
    view, entry, expected = fixture(generation)
    attributes = Attributes.__new__(Attributes)
    attributes.view, attributes.profile = view, attribute_profile(view, entry)
    assert tuple(attributes.flags(index) for index in range(3)) == expected
    parameters = [{'type': {'kind': 18}}, {'type': {'kind': 9}}]
    static = {'index': 0, 'parameters': parameters, 'return_type': {'kind': 1}}
    instance = {**static, 'index': 1}
    assert attributes.argument_register(static, 0) == 'rcx'
    assert attributes.argument_register(static, 1) == 'rdx'
    assert attributes.argument_register(instance, 0) == 'rdx'
    assert attributes.argument_register(instance, 1) == 'r8'
    for index in (-1, True, 3):
        with pytest.raises(ValueError):
            attributes.flags(index)
    with pytest.raises(ValueError, match='unsupported native argument'):
        attributes.argument_register({**static, 'parameters': [{'type': {'kind': 17}}]}, 0)
    with pytest.raises(ValueError, match='unsupported native argument'):
        attributes.argument_register({**static, 'return_type': {'kind': 17}}, 0)
    view.metadata = view.metadata[:HEADER_SIZE + 32 + 26 * 2 + 0x17]
    with pytest.raises(ValueError):
        attributes.flags(2)


@pytest.mark.parametrize('changes', [{'wrong_global': True}, {'wrong_index_store': True}, {'clobber': True}])
def test_unowned_header_or_changed_method_index_key_provenance_rejects(changes):
    view, entry, _ = fixture(**changes)
    with pytest.raises(ValueError):
        attribute_profile(view, entry)
