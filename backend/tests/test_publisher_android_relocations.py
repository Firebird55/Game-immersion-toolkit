"""Authored APS2 bytes exercise sparse ownership without any real native code.

No existing plain-RELA test protects APS2's signed deltas, group state or early
match/trailing-corruption boundary. These are format fixtures, not key discovery.
"""
import pytest

from backend.publisher_android_relocations import select_aps2_relocations as select


def sleb(value):
    output = bytearray()
    while True:
        low, value = value & 127, value >> 7
        done = value == 0 and low & 64 == 0 or value == -1 and low & 64 != 0
        output.append(low if done else low | 128)
        if done: return bytes(output)


def raw(*values):
    return b'APS2' + b''.join(sleb(value) for value in values)


@pytest.mark.parametrize('flags', range(16))
def test_all_defined_groups_preserve_offsets_info_and_actual_addend_rules(flags):
    fields = [2, 0x100, 2, flags]
    if flags & 2: fields += [8]
    if flags & 1: fields += [1027]
    if flags & 12 == 12: fields += [7]
    for i in range(2):
        if flags & 2 == 0: fields += [8 if i == 0 else 16]
        if flags & 1 == 0: fields += [1027]
        if flags & 8 and flags & 4 == 0: fields += [7 if i == 0 else -2]
    result = select(raw(*fields), offsets=(0x108, 0x110, 0x118))
    assert result.records_checked == 2 and result.groups_checked == 1
    expected_addends = [7, 7] if flags & 12 == 12 else [7, 5] if flags & 8 else [0, 0]
    assert [(r.offset, r.info, r.addend) for r in result.selected] == [
        (0x108, 1027, expected_addends[0]), (0x110 if flags & 2 else 0x118, 1027, expected_addends[1])]


def test_cross_group_addend_carry_signed_offset_delta_and_reset():
    value = raw(4, 0x100, 2, 15, 8, 1027, 10,
                1, 9, 1027, -8, -3,
                1, 7, 8, 1027)
    result = select(value, addends=(10, 7, 0))
    assert [(r.offset, r.addend) for r in result.selected] == [(0x108, 10), (0x110, 10), (0x108, 7), (0x110, 0)]
    assert result.groups_checked == 3


def test_sparse_selection_checks_entire_section_before_returning_any_match():
    value = raw(3, 0, 3, 15, 8, 1027, 99)
    assert select(value, offsets=(16,)).records_checked == 3
    assert [r.offset for r in select(value, offsets=(16,)).selected] == [16]
    assert select(value).selected == ()
    for broken in (value + b'\0', value[:-1], value + raw(0, 0)):
        with pytest.raises(ValueError): select(broken, addends=(99,))
    with pytest.raises(ValueError): select(value, addends=(99,), maximum_matches=2)


@pytest.mark.parametrize('value', [
    b'', b'APS1\0\0', b'APS2\x80\0\0', b'APS2\xff\x7f\0', b'APS2' + b'\x80' * 10 + b'\0',
    raw(-1, 0), raw(1, -1), raw(1, 0, 0, 0), raw(1, 0, 2, 0), raw(1, 0, 1, -1),
    raw(1, 0, 1, 16), raw(1, 0, 1, 3, 8, -1), raw(1, 0, 1, 3, -1, 1027),
    raw(2, 0, 1, 15, 8, 1027, 2**63-1, 1, 15, 8, 1027, 1),
    raw(2, 0, 1, 15, 8, 1027, -2**63, 1, 15, 8, 1027, -1),
    raw(2, 2**63-1, 2, 3, 2**63-1, 1027),
    b'APS2' + sleb(2**63) + b'\0',
])
def test_truncation_unsupported_fields_arithmetic_and_count_bound_fail_closed(value):
    with pytest.raises(ValueError): select(value, offsets=(8,))


def test_every_truncated_group_field_fails_without_partial_results():
    value = raw(3, 0x100, 3, 8, 8, 1027, 9, 8, 1027, -1, 8, 1027, 2)
    for end in range(len(value)):
        with pytest.raises(ValueError): select(value[:end], addends=(9,))


def test_caller_limits_and_empty_section_are_explicit():
    assert select(raw(0, 0)).records_checked == 0
    for options in ({'maximum_records': 0}, {'maximum_records': 8_000_001}, {'maximum_matches': 0},
                    {'offsets': (True,)}, {'addends': (2**63,)}, {'offsets': tuple(range(65))}):
        with pytest.raises(ValueError): select(raw(0, 0), **options)
    with pytest.raises(ValueError): select(raw(3, 0, 3, 3, 8, 1027), maximum_records=2)
    with pytest.raises(ValueError): select(b'APS2' + b'\0' * (16 * 1024**2))


def test_explicit_aosp_uint64_delta_dialect_matches_canonical_signed_bytes():
    prefix = raw(2, 0, 1, 15, 8, 1027, 44233980, 1, 11, 8, 1027)
    # Authored literal encodings of -95284 and uint64(2^64-95284), respectively.
    signed = prefix + bytes.fromhex('cc977a')
    word = prefix + bytes.fromhex('cc97faffffffffffff01')
    with pytest.raises(ValueError): select(word, offsets=(8, 16))
    reference = select(signed, offsets=(8, 16))
    assert [r.addend for r in reference.selected] == [44233980, 44138696]
    assert select(word, offsets=(8, 16), allow_unsigned_delta_words=True) == reference
    # Both the grouped/per-record offset and addend fields need the same rule.
    minus8 = bytes.fromhex('f8ffffffffffffffff01')
    minus2 = bytes.fromhex('feffffffffffffffff01')
    value = raw(2, 16, 2, 9, 1027) + minus8 + sleb(7) + sleb(8) + minus2
    result = select(value, offsets=(8, 16), allow_unsigned_delta_words=True)
    assert [(r.offset, r.addend) for r in result.selected] == [(8, 7), (16, 5)]


def test_unsigned_delta_opt_in_never_relaxes_metadata_or_arithmetic_bounds():
    minus1 = bytes.fromhex('ffffffffffffffffff01')
    above64 = b'\x80' * 9 + b'\x02'
    for value in (b'APS2' + minus1 + sleb(0),  # Count.
                  b'APS2' + sleb(0) + minus1,  # Initial offset.
                  raw(1, 0, 1) + minus1,       # Flags.
                  raw(1, 0, 1, 3, 8) + minus1,  # Info.
                  raw(1, 0, 1, 15, 8, 1027) + above64,
                  raw(1, 0, 1, 15, 8, 1027) + minus1[:-1],
                  raw(1, 0, 1, 3) + minus1 + sleb(1027),  # Negative offset.
                  raw(2, 0, 1, 15, 8, 1027, -2**63, 1, 15, 8, 1027) + minus1):
        with pytest.raises(ValueError): select(value, allow_unsigned_delta_words=True)
    with pytest.raises(ValueError): select(raw(0, 0), allow_unsigned_delta_words=1)
