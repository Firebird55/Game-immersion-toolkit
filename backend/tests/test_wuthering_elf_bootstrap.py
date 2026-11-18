"""Synthetic ELF/ARM64 source fixtures: no publisher code, assets or real keys."""
import hashlib
import struct

import pytest

from backend.wuthering_elf_bootstrap import CALLBACK, GETTER, REGISTER, default_output


def adrp(register, pc, target):
    immediate = ((target & ~4095) - (pc & ~4095)) >> 12
    assert -(1 << 20) <= immediate < 1 << 20
    return 0x90000000 | (immediate & 3) << 29 | (immediate >> 2 & 0x7ffff) << 5 | register


def add(target, source, immediate):
    return 0x91000000 | immediate << 10 | source << 5 | target


def load(target, source, offset):
    return 0xf9400000 | (offset // 8) << 10 | source << 5 | target


def branch(pc, target):
    return 0x94000000 | ((target - pc) >> 2 & 0x3ffffff)


def original(tmp_path, *, base=0, key=bytes(range(32)), register=8, vectors=(1, 0), fault=None):
    raw = bytearray(0x3800)
    sections = [('', 0, 0, 0, 0, 0, 0, 0),
                ('.rodata', 1, 2, 0x2000, 0x40, 0, 0, 0),
                ('.text', 1, 6, 0x1000, 0x100, 0, 0, 0),
                ('.got', 1, 3, 0x2100, 8, 0, 0, 0),
                ('.init_array', 14, 3, 0x2120, 8, 0, 0, 8),
                ('.dynstr', 3, 2, 0x3000, 0, 0, 0, 0),
                ('.dynsym', 11, 2, 0x3100, 96, 5, 0, 24),
                ('.rela.dyn', 4, 2, 0x3200, 48, 6, 0, 24),
                ('.eh_frame_hdr', 1, 2, 0x3300, 52, 0, 0, 0),
                ('.shstrtab', 3, 0, 0x3400, 0, 0, 0, 0)]
    q1, q0 = vectors
    callback = [adrp(register, base + 0x1000, base + 0x2020), add(register, register, 0x20),
                0xad400000 | q0 << 10 | register << 5 | q1,
                0xad000000 | q0 << 10 | q1, 0xd65f03c0]
    if fault == 'opaque':
        callback[0] = 0xffffffff
    if fault == 'wrong-output':
        callback[3] |= 1 << 5
    if fault == 'reordered-output':
        callback[3] = 0xad000000 | q1 << 10 | q0
    if fault == 'short-copy':
        callback[2] = 0x3dc00000 | register << 5 | q1
        callback[3] = 0x3d800000 | q1
    callback_data = struct.pack('<5I', *callback)
    raw[0x1000:0x1014] = callback_data
    receiver = 0x150 if fault == 'wrong-delegate' else 0x140
    handler = [adrp(8, base + 0x1040, base + 0x2100), add(8, 8, receiver),
               0xf9000000 | 8 << 5, 0xd65f03c0]
    if fault == 'does-not-bind-argument':
        handler[2] |= 31
    raw[0x1040:0x1050] = struct.pack('<4I', *handler)
    raw[0x1080:0x108c] = struct.pack('<3I', adrp(0, base + 0x1080, base + 0x2100), add(0, 0, 0x140), 0xd65f03c0)
    target = base + (0x1044 if fault == 'different-consumer' else 0x1040)
    constructor = [adrp(0, base + 0x10c0, base + 0x2100), load(0, 0, 0x100),
                   branch(base + 0x10c8, target), 0xd65f03c0]
    if fault == 'two-registrations':
        constructor = constructor[:3] + [adrp(0, base + 0x10cc, base + 0x2100), load(0, 0, 0x100),
                                       branch(base + 0x10d4, target), 0xd65f03c0]
    raw[0x10c0:0x10c0 + len(constructor) * 4] = struct.pack('<' + 'I' * len(constructor), *constructor)
    raw[0x2020:0x2040] = key
    strings = b'\0' + CALLBACK + b'\0' + REGISTER + b'\0' + GETTER + b'\0'
    raw[0x3000:0x3000 + len(strings)] = strings
    offsets = [strings.index(x) for x in [CALLBACK, REGISTER, GETTER]]
    for i, (no, at, size) in enumerate(zip(offsets, [0x1000, 0x1040, 0x1080], [20, 16, 12]), 1):
        struct.pack_into('<IBBHQQ', raw, 0x3100 + i * 24, no, 0x12, 0, 2, base + at, size)
    if fault == 'duplicate-symbol':
        raw[0x3100:0x3118] = raw[0x3118:0x3130]
    struct.pack_into('<QQq', raw, 0x3200, base + 0x2100, 1027,
                     base + (0x1004 if fault == 'unbound-callback' else 0x1000))
    struct.pack_into('<QQq', raw, 0x3218, base + 0x2120, 1027,
                     base + (0x1080 if fault == 'not-initialized' else 0x10c0))
    raw[0x3300:0x3304] = bytes((1, 0x1b, 3, 0x3b))
    struct.pack_into('<iI', raw, 0x3304, 0, 5)
    for i, start in enumerate([0x1000, 0x1040, 0x1080, 0x10c0, 0x1100]):
        struct.pack_into('<ii', raw, 0x330c + i * 8, start - 0x3300, 0)
    shnames = b'\0'
    no = {}
    for name, *_ in sections[1:]:
        no[name] = len(shnames)
        shnames += name.encode() + b'\0'
    raw[0x3400:0x3400 + len(shnames)] = shnames
    for i, (name, typ, flags, off, size, link, info, entry) in enumerate(sections):
        size = len(strings) if name == '.dynstr' else len(shnames) if name == '.shstrtab' else size
        if fault == 'writable-source' and name == '.rodata':
            flags |= 1
        struct.pack_into('<IIQQQQIIQQ', raw, 0x3500 + i * 64, no.get(name, 0), typ, flags,
                         base + off if flags & 2 else 0, off, size, link, info, 8, entry)
    ident = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<16sHHIQQQIHHHHHH', raw, 0, ident, 3, 183, 1, 0, 64, 0x3500, 0, 64, 56, 4, 64, 10, 9)
    for i, (flags, off, size) in enumerate([(4, 0, 0x1000), (5, 0x1000, 0x100), (4, 0x2000, 0x40), (6, 0x2100, 0x80)]):
        struct.pack_into('<IIQQQQQQ', raw, 64 + i * 56, 1, flags, off, base + off, 0, size, size, 0x1000)
    path = tmp_path / ('native-' + str(base) + '.elf')
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('base,register,vectors', [(0, 8, (1, 0)), (0x40000000, 9, (3, 2)),
                                                 (0x10_0000_0000, 12, (8, 9))])
def test_source_registration_and_output_survive_address_and_register_changes(tmp_path, base, register, vectors):
    path, sha = original(tmp_path, base=base, register=register, vectors=vectors)
    result = default_output(path, sha)
    assert result.parameter == bytes(range(32))
    assert result.initializer == base + 0x10c0
    assert result.source_address == base + 0x2020
    assert 'parameter=' not in repr(result)


def test_changed_native_output_is_rederived_without_any_old_candidate(tmp_path):
    path, sha = original(tmp_path)
    first = default_output(path, sha)
    path, sha = original(tmp_path, base=0x100000, key=bytes(range(32, 64)), register=11)
    second = default_output(path, sha)
    assert first.parameter != second.parameter == bytes(range(32, 64))


@pytest.mark.parametrize('fault', ['opaque', 'wrong-output', 'reordered-output', 'short-copy',
                                 'wrong-delegate', 'does-not-bind-argument', 'different-consumer',
                                 'two-registrations', 'duplicate-symbol', 'unbound-callback',
                                 'not-initialized', 'writable-source'])
def test_unproved_or_ambiguous_producer_is_not_a_default_key(tmp_path, fault):
    path, sha = original(tmp_path, fault=fault)
    with pytest.raises(ValueError):
        default_output(path, sha)


def test_corrupted_member_or_wrong_architecture_cannot_supply_a_key(tmp_path):
    path, sha = original(tmp_path)
    raw = bytearray(path.read_bytes())
    raw[0x2020] ^= 1
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        default_output(path, sha)
    struct.pack_into('<H', raw, 18, 62)
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        default_output(path, hashlib.sha256(raw).hexdigest())


def test_truncated_and_unbounded_elf_metadata_is_rejected(tmp_path):
    path, _ = original(tmp_path)
    raw = bytearray(path.read_bytes())
    struct.pack_into('<Q', raw, 40, len(raw) - 1)
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        default_output(path, hashlib.sha256(raw).hexdigest())



def test_section_validation_never_copies_unconsumed_mapped_sections(tmp_path):
    from backend.wuthering_elf_bootstrap import _Elf
    path, _sha = original(tmp_path)
    class Mapped:
        def __init__(self, raw): self.raw = raw
        def __len__(self): return len(self.raw)
        def find(self, *args): return self.raw.find(*args)
        def __getitem__(self, item):
            if isinstance(item, slice) and ((item.start == 0x1000 and item.stop == 0x1100) or
                    (item.start == 0x3000 and item.stop - item.start > 100)):
                pytest.fail('Bounds and symbol selection must not copy whole mapped sections')
            return self.raw[item]
    elf = _Elf(Mapped(path.read_bytes()))
    assert elf.output()[0] == bytes(range(32)) and elf.registration() == 0x10c0
    raw = bytearray(path.read_bytes())
    struct.pack_into('<Q', raw, 0x3500 + 2 * 64 + 32, len(raw))
    with pytest.raises(ValueError): _Elf(Mapped(raw))


@pytest.mark.parametrize('cancel_at', [1, 2, 3, 4, 5, 6, 7, 8])
def test_cancellation_propagates_through_hash_parse_and_registration_and_closes_map(tmp_path, cancel_at):
    path, sha = original(tmp_path)
    class Cancelled(Exception): pass
    calls = []
    def check():
        calls.append(True)
        if len(calls) == cancel_at: raise Cancelled('cancelled')
    with pytest.raises(Cancelled): default_output(path, sha, check=check)
    assert len(calls) == cancel_at
    # Windows cannot replace a file with a still-open mapping.
    other = path.with_suffix('.retained'); path.replace(other)
    assert hashlib.sha256(other.read_bytes()).hexdigest() == sha
