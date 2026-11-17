"""Current original declarations, preserving seed history and unknown symbols."""
from backend import nte_class_schema as schema, nte_required_schema as required
from backend.nte_native_schema import _PE, _seed
from backend.nte_native_classes import descriptors
from backend.nte_seeded_schema import _seed_shapes, _enum_names
from backend.tests.test_nte_native_classes import ClassPE
from backend.tests.test_nte_seeded_schema import seed, shapes


def context(metadata, pe, *, numeric=None):
    body, names, ne, so, ss, count, _ = _seed(metadata)
    retained = _seed_shapes(body, names, ss, count)
    targets = {'struct': set(retained), 'enum': _enum_names(body, names, ne, so)}
    return required._context(pe.bytes(), retained, targets, class_declarations=descriptors(_PE(pe.bytes())),
        numeric_fields=numeric, normalize_names=True)


def test_changed_original_class_fields_and_parent_refresh_without_mutating_seed():
    original = seed([('Root', None, [('Caption', 1, (5,))]), ('Node', 'Root', [('Key', 1, (5,))])])
    current = ClassPE()
    parent = current.declaration('Root', [('Caption', 20)])
    current.declaration('Node', [('Key', 20), ('Added', 3)], parent=parent['outer'])
    before = bytes(original)
    result = schema.refresh(original, original, current.bytes())
    assert shapes(result.data)['Node'][1:] == ('Root', 2, [(0, 'Key', 1, (5,)), (1, 'Added', 1, (2,))])
    assert 'Node' in result.refreshed and not result.numeric_enums
    assert original == before and shapes(original)['Node'][2] == 1
    assert schema.refresh(original, original, current.bytes()).data == result.data


def test_new_enum_field_preserves_anonymous_integer_without_inventing_a_name():
    original = seed([('Node', None, [('Key', 1, (5,))])])
    current = ClassPE()
    current.declaration('Node', [('Key', 20), ('Order_Underlying', 0), ('Order', 30, 1, True)])
    result = schema.refresh(original, original, current.bytes())
    assert shapes(result.data)['Node'][3][-1] == (1, 'Order', 1, (26, (0,), None))
    assert any(row.owner == 'Node' and row.property == 'Order' and row.underlying == 0 for row in result.numeric_enums)
    assert all(row.property != 'Key' for row in result.numeric_enums)


def test_unproved_existing_enum_semantics_cannot_be_downgraded_to_anonymous():
    original = seed([('Node', None, [('Key', 1, (5,)), ('Order', 1, (26, (0,), 'Mood'))])])
    current = ClassPE()
    current.declaration('Node', [('Key', 20), ('Added', 3), ('Order_Underlying', 0), ('Order', 30, 1, True)])
    result = schema.refresh(original, original, current.bytes())
    assert shapes(result.data)['Node'] == shapes(original)['Node']
    assert not any(row.owner == 'Node' for row in result.numeric_enums)
    assert any(row.name == 'Node' for row in result.excluded)


def test_unsigned_64_enum_cannot_use_a_codec_that_narrows_to_signed_integer():
    original = seed([('Node', None, [('Key', 1, (5,))])])
    current = ClassPE()
    current.declaration('Node', [('Key', 20), ('Order_Underlying', 7), ('Order', 30, 1, True)])
    result = schema.refresh(original, original, current.bytes())
    assert shapes(result.data)['Node'] == shapes(original)['Node']
    assert not any(row.owner == 'Node' for row in result.numeric_enums)


def test_class_callback_witness_needs_unique_full_fname_shape_and_an_exact_field():
    original = seed([('Node', None, [('Name', 1, (5,)), ('Guid', 1, (9, 'Value'))]), ('Value', None, [])])
    current = ClassPE()
    current.declaration('Node', [('Name', 20), ('GUID', 25, 1, True)])
    _, _, _, describe, _ = context(original, current)
    assert required._equivalent(describe('Node'), shapes(original)['Node'])
    different = ClassPE()
    different.declaration('Node', [('NAME', 20), ('GUID', 25, 1, True)])
    _, _, _, describe, _ = context(original, different)
    try:
        describe('Node')
    except ValueError as error:
        assert str(error) == 'unproved_required_constructor'
    else:
        raise AssertionError('A whole type acquired identity only by case folding')


def test_opaque_native_tag_has_no_meaning_in_generation():
    original = seed([('Node', None, [('Key', 1, (255,))])])
    current = ClassPE()
    current.declaration('Node', [('Key', 35)])
    result = schema.refresh(original, original, current.bytes())
    assert shapes(result.data)['Node'] == shapes(original)['Node']
    assert any(row.name == 'Node' for row in result.excluded)
