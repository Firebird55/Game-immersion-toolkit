"""Find an AKPK parameter candidate through the current original import owner.

This is a bounded static contract recognizer, not an instruction interpreter.
Its result is NEVER an active master until complete original package controls
pass. In particular, a matching integer elsewhere in the DLL proves nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .endfield_client_code import calls, direct, reg
from .endfield_client_source import check


@dataclass(frozen=True)
class Candidate:
    multiplier: int = field(repr=False)
    xor_constant: int = field(repr=False)


def _memory(row, operand):
    check(operand.type == 3 and not operand.mem.index)
    return row.reg_name(operand.mem.base), operand.mem.disp, operand.size


def _package_loader(rows):
    """The selected export passes nine owned output pointers on the stack."""
    found = []
    previous = 0
    for at, target in calls(rows):
        window = rows[max(previous, at - 48):at]
        stores = [row for row in window if row.mnemonic == 'mov' and len(row.operands) == 2 and
                  row.operands[0].type == 3 and row.reg_name(row.operands[0].mem.base) == 'rsp' and
                  not row.operands[0].mem.index and row.operands[0].size == 8 and
                  row.operands[0].mem.disp in range(0x20, 0x68, 8)]
        offsets = [row.operands[0].mem.disp for row in stores]
        mode = [row for row in window if row.mnemonic == 'mov' and len(row.operands) == 2 and
                reg(row, row.operands[0]) == 'r9b' and row.operands[1].type == 2 and row.operands[1].imm == 0x32]
        if len(offsets) == 9 and set(offsets) == set(range(0x20, 0x68, 8)) and len(mode) == 1:
            # Every selected stack output has a directly defined stack address,
            # not a value borrowed from unrelated static storage or another call.
            for store in stores:
                source = reg(store, store.operands[1])
                check(source)
                position = window.index(store)
                definitions = [row for row in window[:position] if row.operands and
                               reg(row, row.operands[0]) == source and row.mnemonic not in {'cmp', 'test', 'push'}]
                check(definitions)
                row = definitions[-1]
                check(row.mnemonic == 'lea' and row.operands[1].type == 3 and
                      row.reg_name(row.operands[1].mem.base) in {'rsp', 'rbp'} and not row.operands[1].mem.index)
            found.append(target)
        previous = at + 1
    check(len(found) == 1, 'Original export has no unique package-loader output contract.')
    return found[0]


def _custom_transform(rows):
    standard, custom = int.from_bytes(b'AKPK', 'little'), int.from_bytes(b':)xD', 'little')
    magic = [(n, row) for n, row in enumerate(rows) if row.mnemonic == 'cmp' and len(row.operands) == 2 and
             row.operands[1].type == 2 and row.operands[1].imm & 0xffffffff == custom]
    check(len(magic) == 1)
    at, custom_row = magic[0]
    check(4 <= at <= len(rows) - 5)
    prefix = rows[at - 4:at]
    check([row.mnemonic for row in prefix] == ['cmp', 'jne', 'xor', 'jmp'] and
          prefix[0].operands[1].type == 2 and prefix[0].operands[1].imm & 0xffffffff == standard and
          reg(prefix[0], prefix[0].operands[0]) == reg(custom_row, custom_row.operands[0]) and
          direct(prefix[1]) == custom_row.address and
          reg(prefix[2], prefix[2].operands[0]) == reg(prefix[2], prefix[2].operands[1]))
    flag = reg(prefix[2], prefix[2].operands[0])
    reject, enable = rows[at + 1:at + 3]
    check(reject.mnemonic == 'jne' and enable.mnemonic == 'mov' and
          reg(enable, enable.operands[0]) == flag and enable.operands[1].type == 2 and enable.operands[1].imm == 1)
    join = direct(prefix[3])
    check(join == rows[at + 3].address)
    stores = [row for row in rows[at + 3:at + 7] if row.mnemonic == 'mov' and
              row.operands[0].type == 3 and reg(row, row.operands[1]) == flag]
    check(len(stores) == 1 and stores[0].operands[0].size == 1)
    flag_memory = _memory(stores[0], stores[0].operands[0])
    writes = [row for row in rows if row.mnemonic not in {'cmp', 'test'} and row.operands and
              row.operands[0].type == 3 and not row.operands[0].mem.index and
              _memory(row, row.operands[0]) == flag_memory]
    check(writes == stores, 'Original custom package flag is reassigned before its transform guard.')
    found = []
    for n, row in enumerate(rows):
        if row.mnemonic != 'cmp' or len(row.operands) != 2 or row.operands[0].type != 3 or row.operands[1].type != 2:
            continue
        if _memory(row, row.operands[0]) != flag_memory or row.operands[1].imm != 0:
            continue
        part = rows[n + 1:n + 7]
        check(len(part) == 6 and [row.mnemonic for row in part] == ['je', 'lea', 'xor', 'lea', 'mov', 'call'])
        skip, length, offset, buffer, seed, call = part
        check(n + 7 < len(rows) and direct(skip) == rows[n + 7].address and
              reg(length, length.operands[0]) == 'r8d' and length.operands[1].type == 3 and
              length.operands[1].mem.disp == -4 and not length.operands[1].mem.index and
              reg(offset, offset.operands[0]) == reg(offset, offset.operands[1]) == 'r9d' and
              reg(buffer, buffer.operands[0]) == 'rcx' and buffer.operands[1].type == 3 and
              buffer.operands[1].mem.disp == 12 and not buffer.operands[1].mem.index and
              reg(seed, seed.operands[0]) == 'edx' and seed.operands[1].type == 1)
        # The size is the same authored 32-bit seed minus four bytes. No
        # numeric seed, buffer pointer or runtime register value is evaluated.
        source = length.reg_name(length.operands[1].mem.base)
        seed_name = reg(seed, seed.operands[1])
        check(seed_name == source + 'd' and direct(call) is not None)
        found.append(direct(call))
    check(len(found) == 1, 'Original custom package branch has no unique guarded transform.')
    return found[0]


def transform_candidate(rows):
    """Require all three byte/word paths to declare the same four-round fields.

    Complete owned code, guard/caller provenance and full original package
    validation are separate necessary gates. Counts alone never activate keys.
    """
    check(not any(row.mnemonic == 'call' for row in rows))
    multiply = [row for row in rows if row.mnemonic in {'imul', 'mul'}]
    check(len(multiply) == 12 and all(row.mnemonic == 'imul' and len(row.operands) == 3 and
          row.operands[0].type == row.operands[1].type == 1 and row.operands[0].size == row.operands[1].size == 4 and
          row.operands[2].type == 2 for row in multiply))
    multipliers = {row.operands[2].imm & 0xffffffff for row in multiply}
    masks = [row for row in rows if row.mnemonic == 'xor' and len(row.operands) == 2 and row.operands[1].type == 2]
    check(len(masks) == 3 and all(row.operands[0].type == 1 and row.operands[0].size == 4 for row in masks))
    constants = {row.operands[1].imm & 0xffffffff for row in masks}
    check(len(multipliers) == len(constants) == 1 and next(iter(multipliers)) > 0)
    shifts = [row.operands[1].imm for row in rows if row.mnemonic == 'shr' and
              len(row.operands) == 2 and row.operands[0].type == 1 and row.operands[1].type == 2]
    check(all(shifts.count(value) == 3 for value in (8, 16, 24)), 'Original byte-round order changed.')
    output = [row for row in rows if row.mnemonic == 'xor' and row.operands[0].type == 3]
    check(sum(row.operands[0].size == 4 for row in output) == 1 and
          sum(row.operands[0].size == 1 for row in output) == 2 and
          all(row.operands[1].type == 1 and row.operands[1].size == row.operands[0].size for row in output),
          'Original transform does not own its byte/word buffer outputs.')
    check(sum(row.mnemonic == 'xorps' for row in rows) == 5,
          'Original leading-byte vector path changed.')
    return Candidate(next(iter(multipliers)), next(iter(constants)))


def derive(image, original_import):
    root = image.thunk(image.export(original_import.entrypoint))
    package = _package_loader(image.body(root)) - image.base
    transform = _custom_transform(image.body(package)) - image.base
    return transform_candidate(image.body(transform))
