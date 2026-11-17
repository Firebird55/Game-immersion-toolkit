"""Recognize the original LuaCypher key's static source contract.

Only metadata-owned assignments and the evidenced formatting/conversion path
are read. No original instructions, Lua, patch callbacks or native ICalls run.
The resulting candidate still requires complete original Lua source controls.
"""
from __future__ import annotations

import re

from .endfield_client_code import Code, calls, literal_moves, reg
from .endfield_client_contract import array_fragments, masked_conversion
from .endfield_client_metadata import Owners
from .endfield_client_source import check

OWNER = 'Beyond.Lua.LuaCypher'


def _definition(rows, at, name, distance=128):
    """Find a local operand definition; never evaluate general instructions."""
    for number in range(at - 1, max(-1, at - distance - 1), -1):
        row = rows[number]
        if row.mnemonic == 'call' and name in {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}:
            break
        if row.operands and reg(row, row.operands[0]) == name and row.mnemonic not in {'cmp', 'test', 'push'}:
            check(row.mnemonic == 'mov' and len(row.operands) == 2,
                  'Original Lua argument has an unsupported definition.')
            return number, row
    raise ValueError('Original Lua argument definition is missing.')


def _argument(owners, rows, at, name, fragments):
    number, row = _definition(rows, at, name)
    try:
        return owners.literal_usage(row)['text']
    except ValueError:
        pass
    operand = row.operands[1]
    if operand.type == 1:
        # The call ABI copies a preserved fragment/literal register once.
        return _argument(owners, rows, number, reg(row, operand), fragments)
    check(operand.type == 3 and not operand.mem.index and operand.mem.disp >= 0x20 and
          (operand.mem.disp - 0x20) % 8 == 0)
    index = (operand.mem.disp - 0x20) // 8
    check(index in fragments)
    array_at, array = _definition(rows, number, row.reg_name(operand.mem.base))
    value = array.operands[1]
    check(value.type == 3 and not value.mem.index and
          value.mem.disp == owners.field(OWNER, 'KEYS')['offset'])
    static_at, static = _definition(rows, array_at, array.reg_name(value.mem.base))
    value = static.operands[1]
    check(value.type == 3 and value.mem.disp == 0xb8 and not value.mem.index)
    _, identity = _definition(rows, static_at, static.reg_name(value.mem.base))
    check(owners.is_owner_usage(identity, OWNER), 'Original Lua fragment belongs to another class.')
    return fragments[index]


def _stack_argument(rows, at, offset):
    matches = [(number, row) for number, row in enumerate(rows[max(0, at - 16):at], max(0, at - 16))
               if row.mnemonic == 'mov' and len(row.operands) == 2 and row.operands[0].type == 3 and
               row.reg_name(row.operands[0].mem.base) == 'rsp' and
               not row.operands[0].mem.index and row.operands[0].mem.disp == offset]
    check(len(matches) == 1 and matches[0][1].operands[1].type == 1,
          'Original Lua format stack argument is missing or ambiguous.')
    number, row = matches[0]
    return number, reg(row, row.operands[1])


def formatted_fragments(owners, rows, fragments):
    candidates = []
    for at, _pointer in calls(rows):
        window = rows[max(0, at - 16):at]
        values = [(number, value) for number, value in literal_moves(owners, window, 'rcx')
                  if not any(row.mnemonic == 'call' for row in window[number + 1:])]
        if not values:
            continue
        check(len(values) == 1, 'Original Lua format argument is ambiguous.')
        template = values[0][1]['text']
        if not re.fullmatch(r'(?:\{[0-4]\}){5}', template):
            continue
        order = [int(value) for value in re.findall(r'\{([0-4])\}', template)]
        check(sorted(order) == list(range(5)), 'Original Lua format arguments changed.')
        metadata_at, metadata_register = _stack_argument(rows, at, 0x30)
        _, reference = _definition(rows, metadata_at, metadata_register)
        method = owners.method_usage(reference)
        check(method == {'owner': 'Beyond.UnSafeString', 'name': 'Format', 'parameters': 6,
                         'arguments': ('System.String',) * 5},
              'Original Lua format call has no matching typed MethodSpec.')
        arguments = [_argument(owners, rows, at, name, fragments) for name in ('rdx', 'r8', 'r9')]
        for offset in (0x20, 0x28):
            number, name = _stack_argument(rows, at, offset)
            arguments.append(_argument(owners, rows, number, name, fragments))
        candidates.append(''.join(arguments[index] for index in order))
    check(len(candidates) == 1, 'Original Lua format caller is missing or ambiguous.')
    return candidates[0]


def derive(metadata, image):
    owners, code = Owners(metadata, image), Code(image)
    fragments = array_fragments(owners, code.linear(owners.method(OWNER, '.cctor', 0)), OWNER, 'KEYS')
    rows = code.linear(owners.method(OWNER, 'GetKey', 0))
    owners.called(rows, 'System.Text.Encoding', 'get_UTF8', 0)
    owners.called(rows, 'System.Text.Encoding', 'GetString', 1)
    result = masked_conversion(owners, code, rows, formatted_fragments(owners, rows, fragments), 16)
    # The original getter returns the decoded UTF-8 string. The existing Lua
    # format uses its complete 16-byte encoding, with no truncation or guessing.
    check(result.decode('utf-8', 'strict').encode('utf-8') == result)
    return result
