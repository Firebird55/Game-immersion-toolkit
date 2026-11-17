"""Bounded BLB data contracts from authenticated original PE input.

These are structural candidates, not claims about method names or semantics.
The caller must select exactly one complete contract by strict original catalog
and selected TextMap validation. No original native code is executed.
"""
from dataclasses import dataclass
import base64
import hashlib
import json
import re
import struct

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, register


MAX_CONTRACTS = 128
MAX_REFERENCES = 2_000_000


def check(value):
    if not value:
        raise ValueError('The official Genshin BLB parameter contract is unsupported or ambiguous.')


def multiply(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = ((a << 1) ^ (0x11b if a & 128 else 0)) & 255
        b >>= 1
    return result


def standard_tables():
    """Generic GF(256) and Rijndael format mathematics, no game constants."""
    exp, log, state = [], [0] * 256, 1
    for index in range(255):
        exp.append(state); log[state] = index; state = multiply(state, 3)
    exp.append(state)
    def inverse(value):
        result, power, count = 1, value, 254
        while count:
            if count & 1:
                result = multiply(result, power)
            power = multiply(power, power); count >>= 1
        return result if value else 0
    def rotate(value, count):
        return ((value << count) | (value >> (8 - count))) & 255
    sbox = []
    for index in range(256):
        value = inverse(index)
        sbox.append(value ^ rotate(value, 1) ^ rotate(value, 2) ^ rotate(value, 3)
                    ^ rotate(value, 4) ^ 0x63 ^ index)
    return {'GF256Exp': bytes(exp), 'GF256Log': bytes(log), 'Blb3AESSBox': bytes(sbox),
            'Blb3AESShift': bytes(4 * (i % 4) + i // 4 for i in range(16))}


def _constant(image, target, count):
    try:
        at = image.offset(target, count)
        # Parameters must remain in bounded file-backed, non-executable data.
        if any(image.sections[name][0] <= target < image.sections[name][0] + image.sections[name][3]
               for name in image.executable_sections):
            return None
        return image.data[at:at + count]
    except ValueError:
        return None


def _schedule(raw):
    return raw is not None and len(raw) == 48 and all(
        len({value & 15 for value in raw[offset:offset + 16]}) == 16 for offset in (0, 16, 32))


def _methods(image):
    """One bounded RIP-relative reference pass; no parameter byte signatures."""
    found, references = {}, 0
    expression = re.compile(rb'(?=([\x48-\x4f]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....))', re.S)
    for section in image.executable_sections:
        rva, _, offset, size = image.sections[section]
        code = image.data[offset:offset + size]
        for hit in expression.finditer(code):
            references += 1
            check(references <= MAX_REFERENCES)
            site = rva + hit.start()
            target = site + 7 + struct.unpack_from('<i', hit.group(1), 3)[0]
            if not _schedule(_constant(image, target, 48)):
                continue
            owner = image.function_start(site)
            if owner is not None:
                found.setdefault(owner, []).append((site, target))
                check(len(found) <= 4096)
    return found


def _instructions(image, start):
    body = image.window(start)
    rows = image.instructions(start)
    check(rows and rows[-1].address + rows[-1].size == image.base + start + len(body))
    return body, rows


def _family(instruction, value):
    return register(instruction.reg_name(value))[0]


def _descramble(image, start, references, standard):
    body, instructions = _instructions(image, start)
    boundaries = {row.address - image.base for row in instructions}
    schedules = {target for source, target in references if source in boundaries}
    roots, loads, all_roots, byte_offsets, pairs, immediates = {}, {}, set(), {}, [], set()
    for instruction in instructions:
        operands = instruction.operands
        immediates.update(op.imm for op in operands if op.type == CS_OP_IMM and 0 <= op.imm <= 4096)
        def memory_root(operand):
            if operand.type != CS_OP_MEM:
                return None
            options = [roots.get(_family(instruction, reg)) for reg in (operand.mem.base, operand.mem.index)]
            options = [value for value in options if value is not None]
            return options[0] if len(options) == 1 else None
        if (instruction.mnemonic == 'xor' and len(operands) == 2 and operands[0].type == CS_OP_REG
                and operands[1].type == CS_OP_MEM and operands[1].size == 1):
            key, sbox = loads.get(_family(instruction, operands[0].reg)), memory_root(operands[1])
            if key is not None and sbox is not None:
                pairs.append((key, sbox))
        for operand in operands:
            if operand.type == CS_OP_MEM and operand.size == 1:
                root = memory_root(operand)
                if root is not None:
                    byte_offsets.setdefault(root, set()).add(operand.mem.disp)
        new_roots, new_loads = {}, {}
        if len(operands) == 2 and operands[0].type == CS_OP_REG:
            destination = _family(instruction, operands[0].reg)
            other = operands[1]
            if instruction.mnemonic == 'lea' and other.type == CS_OP_MEM and instruction.reg_name(other.mem.base) == 'rip':
                target = instruction.address + instruction.size + other.mem.disp - image.base
                new_roots[destination] = target; all_roots.add(target)
            elif instruction.mnemonic == 'mov' and other.type == CS_OP_REG:
                source = _family(instruction, other.reg)
                if source in roots:
                    new_roots[destination] = roots[source]
            elif instruction.mnemonic in {'add', 'sub'} and destination in roots:
                new_roots[destination] = roots[destination]
            if instruction.mnemonic in {'mov', 'movzx'} and other.type == CS_OP_MEM and other.size == 1:
                root = memory_root(other)
                if root is not None:
                    new_loads[destination] = root
        for reg in instruction.regs_access()[1]:
            reg = _family(instruction, reg)
            roots.pop(reg, None); loads.pop(reg, None)
        roots.update(new_roots); loads.update(new_loads)
    # log(0) is guarded by the native multiplication consumer. Its sentinel
    # is not part of the nonzero GF domain and must not become a fixed key.
    logs = {target for target in all_roots if _constant(image, target, 256) is not None
            and _constant(image, target, 256)[1:] == standard['GF256Log'][1:]}
    exps = {target for target in all_roots if _constant(image, target, 255) == standard['GF256Exp'][:255]}
    contracts = []
    for schedule in schedules:
        if not set(range(32, 48)) <= byte_offsets.get(schedule, set()) or not {3, 4, 7, 15, 256, 768} <= immediates:
            continue
        for key, sbox in set(pairs):
            other = all_roots - {schedule, key, sbox} - logs - exps
            if len(logs) != 1 or len(exps) != 1 or len(other) != 1:
                continue
            mul, = other
            roles = {'Blb3ShiftRow': (schedule, 48), 'Blb3Key': (key, 8),
                     'Blb3SBox': (sbox, 1024), 'Blb3Mul': (mul, 8)}
            values = {name: _constant(image, target, size) for name, (target, size) in roles.items()}
            if all(value is not None for value in values.values()) and all(values['Blb3Mul']):
                contracts.append(values)
    return body, instructions, contracts


def _rc4(image, start):
    body, instructions = _instructions(image, start)
    if not 128 <= len(body) <= 4096:
        return None
    constants = {op.imm for row in instructions for op in row.operands if op.type == CS_OP_IMM}
    operations = {row.mnemonic for row in instructions if any(op.type == CS_OP_MEM and op.size == 1 for op in row.operands)}
    if not {7, 255, 0xab, 9, 2, 1} <= constants or not {'add', 'sub', 'xor', 'mov', 'movzx'} <= operations:
        return None
    copies = []
    for index, instruction in enumerate(instructions):
        ops = instruction.operands
        if not (instruction.mnemonic == 'lea' and len(ops) == 2 and ops[0].type == CS_OP_REG
                and instruction.reg_name(ops[0].reg) == 'rdx' and ops[1].type == CS_OP_MEM
                and instruction.reg_name(ops[1].mem.base) == 'rip'):
            continue
        following = instructions[index + 1:index + 5]
        if any(row.mnemonic == 'mov' and len(row.operands) == 2 and row.operands[0].type == CS_OP_REG
               and row.reg_name(row.operands[0].reg) == 'r8d' and row.operands[1].type == CS_OP_IMM
               and row.operands[1].imm == 256 for row in following) and any(row.mnemonic == 'call' for row in following):
            copies.append(instruction.address + instruction.size + ops[1].mem.disp - image.base)
    if len(copies) != 1:
        return None
    value = _constant(image, copies[0], 256)
    return (value, hashlib.sha256(body).hexdigest()) if value is not None else None


@dataclass(frozen=True)
class Candidate:
    parameters: bytes
    method_sha256s: tuple[str, ...]

    @property
    def sha256(self):
        return hashlib.sha256(self.parameters).hexdigest()


def discover_candidates(image):
    """Return all unique full contracts; publisher validation must disambiguate."""
    standard, descriptions, rc4s = standard_tables(), [], {}
    for start, references in sorted(_methods(image).items()):
        try:
            body, instructions, contracts = _descramble(image, start, references, standard)
        except ValueError:
            continue
        if not contracts:
            continue
        owner_hash = hashlib.sha256(body).hexdigest()
        descriptions.extend((values, owner_hash) for values in contracts)
        check(len(descriptions) <= MAX_CONTRACTS)
        for instruction in instructions:
            if (instruction.mnemonic != 'call' or len(instruction.operands) != 1
                    or instruction.operands[0].type != CS_OP_IMM):
                continue
            target = instruction.operands[0].imm - image.base
            if image.function_start(target) != target:
                continue
            try:
                result = _rc4(image, target)
            except ValueError:
                continue
            if result is not None:
                value, method_hash = result
                rc4s.setdefault(value, set()).update((owner_hash, method_hash))
    check(descriptions and rc4s and len(descriptions) * len(rc4s) <= MAX_CONTRACTS)
    unique = {}
    for values, method_hash in descriptions:
        for rc4, owners in rc4s.items():
            parameters = {**standard, **values, 'Blb3RC4Key': rc4}
            raw = json.dumps({name: base64.b64encode(value).decode('ascii') for name, value in parameters.items()},
                             sort_keys=True, separators=(',', ':')).encode()
            unique.setdefault(raw, set()).update((*owners, method_hash))
    return tuple(Candidate(raw, tuple(sorted(methods))) for raw, methods in sorted(unique.items()))
