"""Actual requested closures, native baseline equivalence and owned drift."""
import struct

import pytest

from backend import nte_required_schema as required, nte_seeded_schema as seeded
from backend.tests.test_nte_native_schema import PE
from backend.nte_native_schema import _seed
from backend.tests.test_nte_seeded_schema import fixture, seed, shapes


def primitive(fields=None, *, custom=False, flags=None, base=0x140000000):
    fields = fields if fields is not None else [('TextKey', 20)]
    pe = PE(base=base)
    offset = pe.native('Dialogue', fields, ops=not custom, flags=flags if flags is not None else 4 if custom else 1)
    return pe, offset


def enum(pe, *, changed=False):
    name = pe.name('Mood')
    members = [(0, pe.name('Mood::Calm')), (2 if changed else 1, pe.name('Mood::Alert'))]
    offset, address = pe.alloc(32)
    for index, (value, pointer) in enumerate(members):
        pe.put(offset+16*index, 'Qq', pointer, value)
    offset, _ = pe.alloc(48)
    pe.put(offset, '5QIHBB', pe.code, 0, name, pe.name('Mood::Type'), address, 0x45, 2, 0, 1)


def test_unrelated_native_drift_does_not_block_actual_required_closure():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))]), ('Unused', None, [('Count', 1, (2,))])])
    old, _ = primitive()
    current, _ = primitive(base=0x180000000)
    old.native('Unused', [('Count', 3)])
    current.native('Unused', [('Count', 21), ('AddedField', 3)])
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'])
    assert result.eligible and result.types == ('Dialogue',) and not result.enums
    assert result.evidence == (('Dialogue', 'native_equivalent'),)


def test_unresolved_required_added_field_fails_until_candidate_is_fully_refreshed():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive()
    current, _ = primitive([('TextKey', 20), ('VoiceEvent', 20)])
    stale = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'])
    assert not stale.eligible and stale.unresolved[0].reasons == ('stale_required_layout',)
    refreshed = seeded.refresh_seeded_native_types(metadata, current.bytes())
    result = required.validate(metadata, refreshed.data, old.bytes(), current.bytes(), ['Dialogue'])
    assert result.eligible and result.evidence == (('Dialogue', 'native_refreshed'),)


@pytest.mark.parametrize('change', ['size', 'alignment', 'flags', 'operations', 'field'])
def test_custom_serializer_requires_unchanged_original_baseline_contract(change):
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive(custom=True)
    current, descriptor = primitive(custom=True, base=0x180000000)
    same = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'])
    assert same.eligible and same.evidence == (('Dialogue', 'baseline_custom_descriptor'),)
    if change == 'size': current.put(descriptor+42, 'H', 80)
    elif change == 'alignment': current.put(descriptor+44, 'I', 16)
    elif change == 'flags': current.put(descriptor+52, 'I', 0x104)
    elif change == 'operations': current.put(descriptor+16, 'Q', current.code)
    else:
        current, _ = primitive([('TextKey', 21)], custom=True)
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'])
    assert not result.eligible


def test_switching_custom_serialization_to_reflected_layout_is_explicitly_rejected():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive(custom=True)
    current, _ = primitive()
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'])
    assert not result.eligible and result.unresolved[0].reasons == ('changed_native_serialization_flags',)


def test_existing_single_owner_identity_is_not_permission_for_a_new_required_type():
    metadata, old, _, _ = fixture(witnesses=1)
    _, current, _, _ = fixture(witnesses=1, base=0x180000000)
    enum(old); enum(current)
    existing = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Existing0'])
    assert existing.eligible
    rows = [(n, p, [(f, d, w) for _, f, d, w in fs]) for n, p, _, fs in shapes(metadata).values()]
    rows.append(('NewCaption', 'Base', [('Positions', 1, (8, (9, 'Vector'))), ('Mood', 1, (26, (0,), 'Mood'))]))
    result = required.validate(metadata, seed(rows), old.bytes(), current.bytes(), ['NewCaption'])
    assert not result.eligible and any('unproved_required_constructor' in row.reasons for row in result.unresolved)


def test_new_required_nested_type_with_independent_witnesses_and_actual_enum_arrays():
    metadata, old, _, _ = fixture()
    _, current, _, _ = fixture(base=0x180000000)
    enum(old); enum(current)
    candidate = seeded.append_seeded_native_types(metadata, current.bytes())
    result = required.validate(metadata, candidate.data, old.bytes(), current.bytes(), ['NewCaption'])
    assert result.eligible and result.enums == ('Mood',)
    assert set(result.types) == {'NewCaption', 'Vector', 'Base'}
    assert ('Mood', 'baseline_enum_equivalent') in result.evidence


def test_changed_required_original_enum_values_cannot_silently_use_seed_values():
    metadata, old, _, _ = fixture()
    _, current, _, _ = fixture(base=0x180000000)
    enum(old); enum(current, changed=True)
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Existing0'])
    assert not result.eligible and any(row.name == 'Mood' and row.reasons == ('stale_required_enum',) for row in result.unresolved)
    # An independently refreshed literal definition can pass; no numeric-only
    # fallback or invented runtime MAX name is needed.
    refreshed = bytearray(metadata)
    _, _, enum_start, _, _, _, _ = _seed(metadata)
    struct.pack_into('<Q', refreshed, 16+enum_start+22, 2)
    fresh = required.validate(metadata, bytes(refreshed), old.bytes(), current.bytes(), ['Existing0'])
    assert fresh.eligible and ('Mood', 'native_enum_refreshed') in fresh.evidence


def test_missing_dynamic_lookup_cannot_be_hidden_by_a_complete_static_root():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive(); current, _ = primitive()
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue', 'AddedDynamicType'])
    assert not result.eligible and result.unresolved[0].name == 'AddedDynamicType'


def test_frozen_reader_class_contract_is_distinct_from_native_descriptor_evidence():
    metadata = seed([('EngineTable', None, [('Row', 1, (5,))])])
    old, current = PE(), PE(base=0x180000000)
    no_contract = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['EngineTable'])
    assert not no_contract.eligible
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['EngineTable'],
                               reader_classes={'EngineTable': 'CUE4Parse.UE4.Assets.Exports.Engine.UEngineTable'})
    assert result.eligible and result.evidence == (('EngineTable', 'frozen_reader_class'),)
    with pytest.raises(ValueError):
        required.validate(metadata, metadata, old.bytes(), current.bytes(), ['EngineTable'],
                          reader_classes={'EngineTable': 'Game.Client.UEngineTable'})


def test_casefolding_requires_unique_fields_and_at_least_one_exact_field_anchor():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive(); current, _ = primitive([('textkey', 20)])
    assert not required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue']).eligible


def test_ambiguous_native_descriptors_cannot_fall_back_to_a_reader_class_contract():
    metadata = seed([('Dialogue', None, [('TextKey', 1, (5,))])])
    old, _ = primitive(); current, _ = primitive()
    old.native('Dialogue', [('TextKey', 20)])
    current.native('Dialogue', [('TextKey', 20)])
    result = required.validate(metadata, metadata, old.bytes(), current.bytes(), ['Dialogue'],
                               reader_classes={'Dialogue': 'CUE4Parse.UE4.Assets.Exports.Engine.UDialogue'})
    assert not result.eligible and result.unresolved[0].reasons == ('ambiguous_required_native_descriptor',)
