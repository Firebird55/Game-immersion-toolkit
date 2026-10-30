"""Conservative constant voice-bank bindings in Persona's FLW0 bytecode.

This reads metadata only. It neither executes scripts nor assumes a bank carries
across calls, branches, unknown native functions or externally entered labels.
"""
from __future__ import annotations

from collections import defaultdict
import struct

from .persona_cri import invalid


# Message argument counts from the P5R native-function schema; message ID is
# first (top of stack). Including all these calls prevents a second, unresolved
# use of the same message from acquiring an unrelated bank.
_MESSAGES = {0x5: 2, 0x2a: 1, 0x5f: 3, 0x60: 3, 0x85: 1,
             0x86: 2, 0x136: 1, 0x159: 1, 0x15b: 2, 0x17c: 2}
_HARMLESS = {0x0, 0x1, 0x22, 0x23, 0x141, 0x181}
_SETUP = {0x140, 0x180}  # SND_VOICE_DNGEVT_SETUP / DLYEVT_SETUP


def constant_message_banks(data):
    if len(data) < 32 or data[8:12] not in (b'FLW0', b'0WLF'):
        return {}
    endian = '>' if data[8:12] == b'FLW0' else '<'
    size, count = struct.unpack_from(endian + 'I', data, 4)[0], struct.unpack_from(endian + 'I', data, 16)[0]
    if size != len(data) or not 1 <= count <= 32 or 32 + count * 16 > size:
        raise invalid('Invalid Persona flow binding sections.')
    labels, code, sections = set(), None, set()
    for at in range(32, 32 + count * 16, 16):
        kind, width, number, start = struct.unpack_from(endian + '4I', data, at)
        if kind in sections or start + width * number > size:
            raise invalid('Invalid Persona flow binding extent.')
        sections.add(kind)
        if kind in (0, 1):
            if width != 48 or number > 100000:
                raise invalid('Unsupported Persona flow label schema.')
            for index in range(number):
                labels.add(struct.unpack_from(endian + 'I', data, start + index * width + 40)[0])
        elif kind == 2:
            if width != 4 or number > 1000000:
                raise invalid('Unsupported Persona flow instruction schema.')
            code = data[start:start + width * number]
    if code is None:
        return {}
    instructions, starts, index = [], set(), 0
    while index < len(code) // 4:
        first = index
        op, arg = struct.unpack_from(endian + 'HH', code, index * 4)
        index += 1
        if op in (0, 1):  # PUSHI/PUSHF's next word is data, never an opcode.
            if index == len(code) // 4:
                raise invalid('Truncated Persona flow constant.')
            arg = struct.unpack_from(endian + 'I', code, index * 4)[0]
            index += 1
        starts.add(first)
        instructions.append((first, op, arg))
    if labels - starts:
        raise invalid('Persona flow label does not address an instruction.')
    uses, bank, constants, dynamic = defaultdict(set), None, [], False
    for index, op, arg in instructions:
        if index in labels:
            bank, constants = None, []
        if op in (0, 29):  # PUSHI / PUSHIS
            constants.append(arg)
            if len(constants) > 64:
                constants = constants[-64:]
            continue
        if op == 8:  # COMM
            if arg in _SETUP:
                bank = None
                if len(constants) >= 2:
                    major, minor = constants[-1], constants[-2]
                    if 0 <= major <= 999 and 0 <= minor <= 999:
                        bank = f'sound/event/e{major:03d}_{minor:03d}.acb'
            elif arg in _MESSAGES:
                if len(constants) >= _MESSAGES[arg]:
                    uses[constants[-1]].add(bank)
                else:
                    dynamic = True
            elif arg not in _HARMLESS:
                bank = None
            constants = []
        else:
            # Arithmetic could alter constants; calls/branches can alter the
            # active bank. Avoid following either without full runtime state.
            bank, constants = None, []
    if dynamic:
        return {}
    return {identity: next(iter(values)) for identity, values in uses.items()
            if len(values) == 1 and None not in values}
