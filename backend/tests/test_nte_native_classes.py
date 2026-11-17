"""Owned class-registration metadata, including unbacked writable PE BSS."""
from collections import Counter

import pytest

from backend import nte_native_classes as classes
from backend.nte_native_schema import _PE
from backend.tests.test_nte_native_schema import PE


class ClassPE(PE):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.put(0x86, 'H', 3)
        self.put(0x98 + 56, 'I', self.data_rva + 0x5000)
        offset = self.section_table + 80
        self.blob[offset:offset + 8] = b'.ownbss\0'
        self.put(offset + 8, '4I', 0x1000, self.data_rva + 0x4000, 0, 0)
        self.put(offset + 36, 'I', 0xc0000080)
        self.number = 0

    def wide(self, value):
        raw = value.encode('utf-16le') + bytes(2)
        offset, pointer = self.alloc(len(raw))
        self.blob[offset:offset + len(raw)] = raw
        return pointer

    def declaration(self, name, fields=(), *, parent=None, flags=0x80, inner=None, cpp_abstract=False):
        self.number += 1
        outer = self.code + self.number * 32
        inner = inner or outer + 16
        info = self.base + self.data_rva + 0x4000 + self.number * 16
        register, _ = self.alloc(32)
        self.put(register, '4Q', outer, inner, self.wide('U' + name), info)
        fake = self.native('Fields' + str(self.number), fields)
        pointers, = self.unpack_at(fake + 32, 'Q')
        cpp_offset, cpp = self.alloc(1)
        self.blob[cpp_offset] = cpp_abstract
        deps_offset, deps = self.alloc(16 if parent else 8)
        self.put(deps_offset, '2Q' if parent else 'Q', *([parent, self.code] if parent else [self.code]))
        offset, _ = self.alloc(64)
        packed = (2 if parent else 1) | (len(fields) << 15)
        self.put(offset, '7Q2I', inner, 0, cpp, deps, 0, pointers, 0, packed, flags)
        return {'outer': outer, 'inner': inner, 'registration': register, 'parameters': offset, 'fields': fake}

    def unpack_at(self, offset, fmt):
        import struct
        return struct.unpack_from('<' + fmt, self.blob, offset)


@pytest.mark.parametrize('layout', [(0x140000000, 0x1000, 0x2000), (0x180000000, 0x3000, 0x7000)])
def test_original_registration_joins_complete_class_fields_and_parent_without_code(layout):
    pe = ClassPE(base=layout[0], code_rva=layout[1], data_rva=layout[2])
    root = pe.declaration('Root', [('CaptionKey', 20)])
    pe.declaration('Dialogue', [('NodeKey', 20), ('Count', 3, 2)], parent=root['outer'])
    pe.blob[0x400:0x600] = b'\xcc' * 0x200
    before = pe.bytes()
    rows = classes.descriptors(_PE(before))
    assert [(r.name, r.parent) for r in rows] == [('Root', None), ('Dialogue', 'Root')]
    assert rows[1].parent_callback == root['outer']
    assert rows[1].descriptors == (('NodeKey', 20, 1, 0), ('Count', 3, 2, 0))
    assert pe.bytes() == before


def test_unreal_abstract_flag_is_independent_of_cpp_abstract_trait():
    pe = ClassPE()
    pe.declaration('CaptionNode', [('Key', 20)], flags=0x81, cpp_abstract=False)
    row, = classes.descriptors(_PE(pe.bytes()))
    assert row.flags == 0x81 and not row.cpp_abstract


@pytest.mark.parametrize('change', ['bad_info', 'readonly_info', 'bad_fields', 'unknown_parent', 'blueprint', 'not_native'])
def test_unproved_registration_or_class_descriptor_is_not_returned(change):
    pe = ClassPE()
    row = pe.declaration('Dialogue', [('Key', 20)], parent=pe.code + 480 if change == 'unknown_parent' else None)
    if change == 'bad_info': pe.put(row['registration'] + 24, 'Q', pe.base + pe.data_rva + 0x5000)
    elif change == 'readonly_info': pe.put(row['registration'] + 24, 'Q', pe.name('NotWritable'))
    elif change == 'bad_fields': pe.put(row['parameters'] + 40, 'Q', pe.code)
    elif change == 'blueprint': pe.put(row['parameters'] + 60, 'I', 0x40080)
    elif change == 'not_native': pe.put(row['parameters'] + 60, 'I', 0)
    assert classes.descriptors(_PE(pe.bytes())) == ()


def test_conflicting_registration_names_cannot_share_a_static_class_identity():
    pe = ClassPE()
    first = pe.declaration('First', [('Key', 20)])
    pe.declaration('Second', [('Key', 20)], inner=first['inner'])
    assert classes.descriptors(_PE(pe.bytes())) == ()


def test_duplicate_class_names_remain_visible_for_required_validator_refusal():
    pe = ClassPE()
    pe.declaration('Caption', [('Key', 20)])
    pe.declaration('Caption', [('Other', 20)])
    assert Counter(row.name for row in classes.descriptors(_PE(pe.bytes()))) == {'Caption': 2}


def test_virtual_bss_bounds_and_aggregate_field_limits_are_enforced(monkeypatch):
    pe = ClassPE()
    pe.declaration('Dialogue', [('Key', 20)])
    monkeypatch.setattr(classes, 'MAX_NATIVE_PROPERTIES', 0)
    with pytest.raises(ValueError): classes.descriptors(_PE(pe.bytes()))
    monkeypatch.undo()
    pe.put(pe.section_table + 80 + 8, 'I', 0x2000)
    with pytest.raises(ValueError): classes.descriptors(_PE(pe.bytes()))
