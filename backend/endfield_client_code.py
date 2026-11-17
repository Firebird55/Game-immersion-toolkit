"""Bounded original x64 instruction records; static contracts, no emulation."""
from __future__ import annotations

from .endfield_client_source import check
from .genshin_native_x64 import decoder


def reg(instruction, operand):
    return instruction.reg_name(operand.reg) if operand.type == 1 else ''


def direct(instruction):
    if instruction.operands and instruction.operands[0].type == 2:
        return instruction.operands[0].imm
    return None


class Code:
    def __init__(self, image):
        self.image, self.decoder = image, decoder()
        self.used = 0
        self.cache = {}

    def linear(self, method):
        """Read the primary owned spans, excluding addressed inline switch pools.

        Calls and exceptional/patch paths are not executed. Source recognizers
        bind the relevant assignments and callees; original index CRC/schema
        validation remains mandatory for the resulting candidate.
        """
        root = method['pointer']
        if root in self.cache:
            return self.cache[root]
        address, rows, bases, pools = root, [], {}, set()
        for _ in range(64):
            begin, end, unwind = entry = self.image.boundary(address)
            check(self.image.unwind_owner(entry) == root and address == self.image.base + begin,
                  'Original body leaves its named unwind owner.')
            size = end - begin
            self.used += size
            check(size <= 64 * 1024 and self.used <= 256 * 1024,
                  'Original parameter code exceeds its static bound.')
            raw = self.image.read_code(address, size)
            instructions = list(self.decoder.disasm(raw, address))
            for n, instruction in enumerate(instructions):
                limits = [p for p in pools if address <= p < address + size]
                if limits and instruction.address >= min(limits):
                    break
                operands = instruction.operands
                if instruction.mnemonic == 'lea' and len(operands) == 2 and operands[0].type == 1 and operands[1].type == 3:
                    mem = operands[1].mem
                    if instruction.reg_name(mem.base) == 'rip':
                        bases[operands[0].reg] = instruction.address + instruction.size + mem.disp
                if instruction.mnemonic == 'jmp' and operands[0].type == 1 and n >= 2:
                    add, load = instructions[n - 1], instructions[n - 2]
                    if add.mnemonic == 'add' and load.mnemonic == 'mov' and len(add.operands) == len(load.operands) == 2:
                        op, memory = add.operands, load.operands[1]
                        if op[0].type == op[1].type == 1 and op[0].reg == operands[0].reg and memory.type == 3:
                            base = bases.get(op[1].reg)
                            if base is not None and memory.mem.base == op[1].reg and memory.mem.scale == 4:
                                bounds = [i.operands[1].imm for i in instructions[max(0, n - 12):n]
                                          if i.mnemonic == 'cmp' and len(i.operands) == 2 and
                                          i.operands[1].type == 2 and 0 <= i.operands[1].imm <= 15]
                                check(bounds)
                                pools.add(base + memory.mem.disp)
            cuts = [p for p in pools if address <= p < address + size]
            code_end = min(cuts) if cuts else address + size
            instructions = list(self.decoder.disasm(raw[:code_end - address], address))
            check(instructions and sum(i.size for i in instructions) == code_end - address,
                  'Original code has an unrecognized instruction/data boundary.')
            rows.extend(instructions)
            last = next(i for i in reversed(instructions) if i.mnemonic != 'nop')
            if last.mnemonic in {'ret', 'int3'}:
                self.cache[root] = rows
                return rows
            if last.mnemonic == 'jmp':
                if method['name'] != '.cctor' and direct(last) in {row.address for row in rows}:
                    self.cache[root] = rows
                    return rows
                next_entry = self.image.boundary(address + size)
                if self.image.unwind_owner(next_entry) != root:
                    self.cache[root] = rows
                    return rows
            check(code_end == address + size, 'Unexpected fallthrough into original literal data.')
            address += size
        raise ValueError('Original parameter body has too many continuations.')


def calls(rows):
    return [(number, direct(row)) for number, row in enumerate(rows)
            if row.mnemonic == 'call' and direct(row) is not None]


def literal_moves(owners, rows, destination=None):
    result = []
    for number, instruction in enumerate(rows):
        if instruction.mnemonic == 'mov' and instruction.operands and instruction.operands[0].type == 1:
            if destination is not None and reg(instruction, instruction.operands[0]) != destination:
                continue
            try:
                result.append((number, owners.literal_usage(instruction)))
            except ValueError:
                continue
    return result
