"""Original class closure and narrowly evidenced frozen concrete-codec leaves."""
import pytest

from backend import nte_class_schema as classes, nte_required_schema as required
from backend.tests.test_nte_native_classes import ClassPE
from backend.tests.test_nte_native_schema import PE
from backend.tests.test_nte_seeded_schema import seed


def test_current_class_additions_require_fresh_complete_original_layout():
    metadata = seed([('Root', None, []), ('Node', 'Root', [('Key', 1, (5,))])])
    old, current = ClassPE(), ClassPE(base=0x180000000)
    for pe in (old, current):
        root = pe.declaration('Root')
        pe.declaration('Node', [('Key', 20)] + ([('Count', 3)] if pe is current else []), parent=root['outer'])
    stale = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Node'], native_classes=True)
    assert not stale.eligible and stale.unresolved[0].reasons == ('stale_required_layout',)
    candidate = classes.refresh(metadata, metadata, current.bytes()).data
    fresh = required.validate(metadata, candidate, old.bytes(), current.bytes(), ['Node'], native_classes=True)
    assert fresh.eligible and fresh.validator == required.CLASS_VALIDATOR
    assert ('Node', 'native_class_refreshed') in fresh.evidence
    assert ('Root', 'native_class_equivalent') in fresh.evidence


def test_new_numeric_enum_field_is_preserved_without_semantic_order_claim():
    metadata = seed([('Node', None, [('Key', 1, (5,))])])
    old, current = ClassPE(), ClassPE(base=0x180000000)
    old.declaration('Node', [('Key', 20)])
    current.declaration('Node', [('Key', 20), ('Order_Value', 0), ('Order', 30, 1, True)])
    candidate = classes.refresh(metadata, metadata, current.bytes()).data
    result = required.validate(metadata, candidate, old.bytes(), current.bytes(), ['Node'], native_classes=True)
    assert result.eligible and not result.enums
    assert result.evidence == (('Node', 'native_class_refreshed'),)


def opaque(base=0x140000000):
    pe = PE(base=base)
    pe.native('Root', [('Path', 25, 1, True), ('Anchor', 20)])
    descriptor = pe.native('OpaquePath', [('Leaf', 35)], ops=False, flags=8)
    pe.native('OwnerWitness')
    return pe, descriptor


def opaque_seed():
    return seed([('Root', None, [('Path', 1, (9, 'OpaquePath')), ('Anchor', 1, (5,))]),
        ('OpaquePath', None, [('Leaf', 1, (255,))]), ('OwnerWitness', None, [])])


def check_opaque(old, current, *, requested=('Root',), codecs=True):
    metadata = opaque_seed()
    return required.validate(metadata, metadata, old.bytes(), current.bytes(), requested, native_classes=True,
        reader_codecs={'OpaquePath': 'CUE4Parse.UE4.Objects.Owned.FOpaquePath'} if codecs else {})


def test_opaque_dependency_requires_actual_codec_bypass_and_original_descriptor_equivalence():
    old, _ = opaque(); current, _ = opaque(0x180000000)
    assert not check_opaque(old, current, codecs=False).eligible
    result = check_opaque(old, current)
    assert result.eligible and ('OpaquePath', 'baseline_opaque_concrete_codec') in result.evidence
    with pytest.raises(ValueError):
        check_opaque(old, current, requested=('Root', 'OpaquePath'))


@pytest.mark.parametrize('change', ['size', 'align', 'flags', 'ops', 'tag', 'offset', 'property_flags',
                                    'setter', 'getter', 'notify', 'owner'])
def test_opaque_leaf_rejects_any_unproved_current_native_contract_change(change):
    old, _ = opaque(); current, descriptor = opaque(0x180000000)
    import struct
    pointers, = struct.unpack_from('<Q', current.blob, descriptor+32)
    at = 0x600 + pointers-current.base-current.data_rva
    pointer, = struct.unpack_from('<Q', current.blob, at)
    field = 0x600 + pointer-current.base-current.data_rva
    if change == 'size': current.put(descriptor+42, 'H', 80)
    elif change == 'align': current.put(descriptor+44, 'I', 16)
    elif change == 'flags': current.put(descriptor+52, 'I', 0x108)
    elif change == 'ops': current.put(descriptor+16, 'Q', current.code)
    elif change == 'tag': current.put(field+24, 'I', 36)
    elif change == 'offset': current.put(field+50, 'H', 8)
    elif change == 'property_flags': current.put(field+16, 'Q', 4)
    elif change == 'setter': current.put(field+32, 'Q', current.code)
    elif change == 'getter': current.put(field+40, 'Q', current.code)
    elif change == 'notify': current.put(field+8, 'Q', current.name('Changed'))
    else: current.put(descriptor, 'Q', current.code+16)
    assert not check_opaque(old, current).eligible


def test_changed_original_class_flags_cannot_be_hidden_by_same_mapping():
    metadata = seed([('Node', None, [('Key', 1, (5,))])])
    old, current = ClassPE(), ClassPE(base=0x180000000)
    old.declaration('Node', [('Key', 20)])
    current.declaration('Node', [('Key', 20)], flags=0x81)
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Node'], native_classes=True)
    assert not result.eligible and result.unresolved[0].reasons == ('changed_native_class_flags',)
