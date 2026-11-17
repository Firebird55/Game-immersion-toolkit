"""Synthetic native enum-name/slot switches with changed current operands."""
import struct
from types import SimpleNamespace

import pytest

from backend.genshin_native_locale_slots import ALIASES, named_returns, selected_slots
from backend.genshin_native_words import Context
from backend.genshin_native_x64 import decoder
from backend.tests.test_genshin_native_bootstrap import requires_decoder


class Assembly:
    def __init__(self, start):
        self.start, self.raw, self.labels, self.fixups = start, bytearray(), {}, []

    def emit(self, value):
        self.raw.extend(bytes.fromhex(value))

    def label(self, name):
        self.labels[name] = self.start + len(self.raw)

    def relative(self, prefix, target):
        self.emit(prefix)
        self.fixups.append((len(self.raw), target))
        self.raw.extend(bytes(4))

    def finish(self):
        for offset, target in self.fixups:
            target = self.labels[target] if isinstance(target, str) else target
            struct.pack_into('<i', self.raw, offset, target - self.start - offset - 4)
        return bytes(self.raw)


def fixture(*, first=1, rotate=0, bad_name=False, duplicate=False, wrong_argument=False):
    names, slots = Assembly(0x100), Assembly(0x500)
    vocabulary = list(ALIASES)
    literal_addresses = {0x1800 + 8 * i: value for i, value in enumerate(vocabulary)}
    if bad_name: literal_addresses[0x1800] = 'unrecognized-language'
    names.emit('4883ec28' + ('89fa' if wrong_argument else '89ca') + '83ea' + f'{first:02x}' + '83fa0e')
    names.relative('0f87', 'default')
    names.relative('488d05', 'table')
    names.emit('48630c904801c1ffe1')
    cases = []
    for i in range(15):
        names.label(str(i)); cases.append(names.labels[str(i)])
        names.relative('488b05', 0x1800 + 8 * i)
        names.emit('4883c428c3')
    names.label('default'); names.relative('488b05', 0x1900); names.emit('4883c428c3')
    name_size = len(names.raw)
    names.label('table')
    for target in cases:
        names.raw.extend(struct.pack('<i', target - names.labels['table']))

    getter = 0x1400
    slots.emit('4883ec284889ce4189d04183e8' + f'{first:02x}' + '4183f80e')
    slots.relative('0f87', 'default')
    slots.emit('4963c0')
    slots.relative('488d0d', 'table')
    slots.emit('8b1481488b4e084881e100ffffff')
    slots.relative('e8', getter)
    slots.emit('4885c0'); slots.relative('0f84', 'default')
    slots.emit('83781000'); slots.relative('0f84', 'default')
    slots.emit('4883c428c3')
    slots.label('default'); slots.emit('488b4e084881e100ffffffba780000004883c428')
    slots.relative('e9', getter)
    slot_size = len(slots.raw)
    slots.label('table')
    values = [8 * ((i + rotate) % 15) for i in range(15)]
    if duplicate: values[-1] = values[0]
    slots.raw.extend(struct.pack('<15I', *values))
    data = bytearray(0x2000)
    data[names.start:names.start + len(names.raw)] = names.finish()
    data[slots.start:slots.start + len(slots.raw)] = slots.finish()
    bodies = {names.start: bytes(data[names.start:names.start + name_size]),
              slots.start: bytes(data[slots.start:slots.start + slot_size])}
    def window(rva):
        if rva not in bodies: raise ValueError('No authored native body')
        return bodies[rva]
    def offset(rva, size):
        if not 0 <= rva <= len(data) - size: raise ValueError('Native table is out of bounds')
        return rva
    image = SimpleNamespace(base=0x1000, data=bytes(data), offset=offset, window=window,
        instructions=lambda rva: list(decoder().disasm(window(rva), 0x1000 + rva)))
    return Context(image, names.start), Context(image, slots.start), literal_addresses, getter, values


@requires_decoder
@pytest.mark.parametrize('first,rotate', [(1, 0), (3, 4)])
def test_current_native_switches_own_enum_values_and_changed_locale_slot_order(first, rotate):
    names, slots, literals, getter, expected = fixture(first=first, rotate=rotate)
    decoded = named_returns(names, literals)
    values, fallback = selected_slots(slots, getter, tuple(range(0, 128, 8)))
    assert set(decoded) == set(range(first, first + 15))
    assert [decoded[i] for i in range(first, first + 15)] == list(ALIASES.values())
    assert [values[i] for i in range(first, first + 15)] == expected
    assert fallback == 120


@requires_decoder
@pytest.mark.parametrize('change', ['language', 'argument', 'duplicate', 'missing-fallback'])
def test_unknown_names_other_inputs_and_ambiguous_storage_cannot_supply_a_locale(change):
    names, slots, literals, getter, _ = fixture(bad_name=change == 'language', wrong_argument=change == 'argument',
                                               duplicate=change == 'duplicate')
    with pytest.raises(ValueError):
        if change in {'language', 'argument'}:
            named_returns(names, literals)
        else:
            selected_slots(slots, getter, tuple(range(0, 120 if change == 'missing-fallback' else 128, 8)))
