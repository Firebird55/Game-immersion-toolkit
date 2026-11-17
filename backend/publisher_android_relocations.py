"""Passive, sparse APS2 RELA metadata; no relocation is applied or executed.

The group/additive-state format is evidenced by AOSP bionic's
linker/linker_reloc_iterators.h. This bounded ELF64 profile is independent of a
game, native-address list, key selector or filesystem. Callers own authenticated
ELF/section bounds, relocation-type interpretation and producer ownership.
"""
from dataclasses import dataclass


MAX_BYTES = 16 * 1024**2
MAX_RECORDS = 8_000_000
U64 = 2**64 - 1
I64_MIN, I64_MAX = -2**63, 2**63 - 1


def _check(value):
    if not value:
        raise ValueError('Could not verify bounded original Android relocation metadata.')


class _Reader:
    def __init__(self, raw):
        _check(type(raw) is bytes and 6 <= len(raw) <= MAX_BYTES and raw[:4] == b'APS2')
        self.raw, self.at = raw, 4

    def number(self, *, allow_unsigned_word=False):
        start, value, shift = self.at, 0, 0
        for _ in range(10):
            _check(self.at < len(self.raw))
            byte = self.raw[self.at]
            self.at += 1
            value |= (byte & 127) << shift
            shift += 7
            if byte & 128:
                continue
            if byte & 64:
                value -= 1 << shift
            if allow_unsigned_word and self.at - start == 10 and byte == 1 and I64_MAX < value <= U64:
                # AOSP accumulates into size_t and skips sign extension once
                # shift >= word width. An evidenced producer zero-extends a
                # wrapped uint64 delta; reinterpret precisely that whole word.
                # No oversized integer is truncated and no arithmetic wraps.
                value -= 2**64
            _check(I64_MIN <= value <= I64_MAX)
            # The evidenced lld/AOSP source uses minimal signed LEBs. Reject
            # redundant sign-extension bytes rather than admitting more dialects.
            if self.at - start > 1:
                previous = self.raw[self.at - 2]
                _check(not (byte == 0 and previous & 64 == 0) and
                       not (byte == 127 and previous & 64 != 0))
            return value
        raise ValueError('The original Android relocation integer exceeds its bound.')


@dataclass(frozen=True)
class Relocation:
    offset: int
    info: int
    addend: int


@dataclass(frozen=True)
class Aps2Selection:
    records_checked: int
    groups_checked: int
    selected: tuple[Relocation, ...]


def select_aps2_relocations(raw, *, addends=(), offsets=(), maximum_records=MAX_RECORDS,
                            maximum_matches=64, allow_unsigned_delta_words=False):
    """Validate the entire section, returning only requested sparse identities.

    Both selector sets have at most 64 integers. Matching offset OR addend is
    intentional; the caller then checks type/symbol/ELF ownership. Even a match
    in the first group cannot return before validating counts, arithmetic and
    EOF. No full pointer map is retained or returned.

    An evidenced source may opt into exactly ten-byte zero-extended uint64
    deltas, consistent with AOSP's size_t decoder. Only offset/addend delta
    operands use that dialect; counts, flags, info and initial offset retain
    strict signed LEB framing. Arithmetic still rejects overflow/underflow.
    """
    _check(isinstance(addends, (tuple, list, set, frozenset)) and
           isinstance(offsets, (tuple, list, set, frozenset)) and len(addends) <= 64 and len(offsets) <= 64)
    _check(all(type(value) is int and I64_MIN <= value <= I64_MAX for value in addends) and
           all(type(value) is int and 0 <= value <= U64 for value in offsets) and
           type(maximum_records) is int and 0 < maximum_records <= MAX_RECORDS and
           type(maximum_matches) is int and 0 < maximum_matches <= 256 and
           type(allow_unsigned_delta_words) is bool)
    addends, offsets = frozenset(addends), frozenset(offsets)
    reader = _Reader(raw)
    count, offset = reader.number(), reader.number()
    _check(0 <= count <= maximum_records and 0 <= offset <= U64)
    checked, groups, info, addend, selected = 0, 0, 0, 0, []
    while checked < count:
        size, flags = reader.number(), reader.number()
        _check(0 < size <= count - checked and 0 <= flags <= 15)
        groups += 1
        delta = reader.number(allow_unsigned_word=allow_unsigned_delta_words) if flags & 2 else None
        if flags & 1:
            info = reader.number()
            _check(0 <= info <= U64)
        has_addend, grouped_addend = bool(flags & 8), bool(flags & 4)
        if has_addend and grouped_addend:
            addend += reader.number(allow_unsigned_word=allow_unsigned_delta_words)
            _check(I64_MIN <= addend <= I64_MAX)
        elif not has_addend:
            # AOSP also resets this when bit 4 is present without bit 8.
            addend = 0
        for _ in range(size):
            offset += delta if flags & 2 else reader.number(allow_unsigned_word=allow_unsigned_delta_words)
            _check(0 <= offset <= U64)
            if flags & 1 == 0:
                info = reader.number()
                _check(0 <= info <= U64)
            if has_addend and not grouped_addend:
                addend += reader.number(allow_unsigned_word=allow_unsigned_delta_words)
                _check(I64_MIN <= addend <= I64_MAX)
            if offset in offsets or addend in addends:
                _check(len(selected) < maximum_matches)
                selected.append(Relocation(offset, info, addend))
        checked += size
    _check(checked == count and reader.at == len(raw))
    return Aps2Selection(checked, groups, tuple(selected))
