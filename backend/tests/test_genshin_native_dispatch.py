"""Authored pointer/metadata controls, without publisher bytes or seed values."""
import hashlib
import platform
import struct
import sys
from types import SimpleNamespace

import pytest

from backend import genshin_native_dispatch as dispatch, genshin_native_x64 as native


pytestmark = pytest.mark.skipif(not (sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')),
                                reason='Pinned Windows-amd64 decoder only')


def fixture(generation=0, *, alias=False, change=None):
    base, entry = 0x100000 + generation * 0x100000, 0x100 + generation * 32
    offset, slot, identity = 0x80 + generation * 8, 13 + generation, 71 + generation
    static, array = 0x1800 + generation * 16, 0x2000 + generation * 32
    code = bytearray()
    def rip(prefix, target):
        code.extend(bytes.fromhex(prefix) + struct.pack('<i', target - entry - len(code) - 7))
    rip('488b05', static)
    rip('488b0d', array + slot * 8)
    if alias:
        code.extend(bytes.fromhex('4989c24989cb'))  # r10=rax, r11=rcx
    if change == 'clobber':
        code.extend(bytes.fromhex('31c9'))
    if change == 'call':
        code.extend(bytes.fromhex('e800000000'))
    if change == 'branch':
        code.extend(bytes.fromhex('85d2740731c9eb03909090'))
    store = (bytes.fromhex('4d899a') if alias else bytes.fromhex('488988')) + struct.pack('<i', offset)
    if change == 'partial':
        store = bytes.fromhex('8988') + struct.pack('<i', offset)
    code.extend(store)
    if change == 'duplicate':
        code.extend(store)
    code.extend(b'\xc3')
    sequence = list(native.decoder().disasm(bytes(code), base + entry))
    image = SimpleNamespace(base=base, data=bytes(code), sections={'data': (0x1000, 0x3000, 0, 0x3000)},
                            instructions=lambda rva: sequence, window=lambda rva: bytes(code))
    field = {'index': 33 + generation, 'name': 'dispatchSeed', 'type': {'index': 7 + generation, 'kind': 14},
             'authored_offset_word': 4 << 24 | offset}
    attrs = 6 if change == 'instance' else 22
    raw_type = bytearray(16); raw_type[8:10] = attrs.to_bytes(2, 'little')
    method = {'index': 90 + generation, 'name': '.cctor', 'rva': entry, 'parameters': [], 'return_type': {'kind': 1}}
    view = SimpleNamespace(image=image, metadata=b'authored metadata ' + bytes([generation]),
        named=lambda ns, name: {'definition': 5 + generation, 'namespace': ns, 'name': name},
        field_offsets=lambda definition: [field, field] if change == 'fields' else [field],
        methods=lambda definition: [method], bindings=SimpleNamespace(type_record=lambda index: bytes(raw_type)))
    pairs = [(5, identity, slot)]
    if change == 'literal-owner':
        pairs.append((5, identity + 1, slot))
    usages, arrays = SimpleNamespace(pairs=pairs), {5: {'array_rva': array}}
    value = format(0x123456789abcdef0 + generation, '016x')
    literals = SimpleNamespace(text=lambda index: value if index == identity else pytest.fail('Unowned literal'))
    return view, usages, arrays, literals, value


@pytest.mark.parametrize('generation', [0, 1, 7])
@pytest.mark.parametrize('alias', [False, True])
def test_initial_seed_follows_relocated_original_owner_and_full_pointer_aliases(generation, alias):
    view, usages, arrays, literals, expected = fixture(generation, alias=alias)
    result = dispatch.derive_initial_seed(view, usages, arrays, literals)
    assert result.value == expected and expected not in repr(result)
    assert result.proof['field']['index'] == 33 + generation
    assert result.proof['literal_index'] == 71 + generation
    assert result.proof['value_sha256'] == hashlib.sha256(expected.encode()).hexdigest()
    assert result.proof['later_override_excluded'] is result.proof['complete_dispatch_bootstrap'] is False


@pytest.mark.parametrize('change', ['clobber', 'call', 'branch', 'partial', 'duplicate', 'instance', 'fields', 'literal-owner'])
def test_unproven_or_ambiguous_store_never_produces_a_seed(change):
    view, usages, arrays, literals, _ = fixture(change=change)
    with pytest.raises(ValueError):
        dispatch.derive_initial_seed(view, usages, arrays, literals)


def test_stale_whole_owner_fails_before_native_or_literal_parsing(monkeypatch):
    from backend import genshin_original_excel
    monkeypatch.setattr(genshin_original_excel, 'native_environment', lambda *a: pytest.fail('Stale owner reached native parser'))
    with pytest.raises(ValueError, match='owner changed'):
        dispatch.read_initial_seed(b'new original', b'new metadata', expected_owner={
            'executable_sha256': hashlib.sha256(b'old original').hexdigest(),
            'metadata_sha256': hashlib.sha256(b'old metadata').hexdigest()})


def test_public_reader_uses_current_original_parser_inputs_only(monkeypatch):
    from backend import genshin_original_excel
    view, usages, arrays, literals, expected = fixture(1)
    def environment(executable, metadata):
        assert executable == view.image.data and metadata == view.metadata
        return view, None, usages, arrays, literals
    monkeypatch.setattr(genshin_original_excel, 'native_environment', environment)
    owner = {'executable_sha256': hashlib.sha256(view.image.data).hexdigest(),
             'metadata_sha256': hashlib.sha256(view.metadata).hexdigest()}
    assert dispatch.read_initial_seed(view.image.data, view.metadata, expected_owner=owner).value == expected
