"""Static managed import and signed-native ownership, with no version addresses.

This module consumes inert original bytes. It does not resolve imports through
the OS, load the original DLL or run any original instructions.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct

from .endfield_client_code import Code, calls, direct, reg
from .endfield_client_metadata import Owners
from .endfield_client_source import check
from .genshin_native_x64 import Image, decoder


@dataclass(frozen=True)
class Import:
    module: str
    entrypoint: str


def _rip(row, operand):
    check(operand.type == 3 and row.reg_name(operand.mem.base) == 'rip' and not operand.mem.index)
    return row.address + row.size + operand.mem.disp


def import_descriptor(rows, image):
    """Recognize the typed StringView descriptor in its exact original caller."""
    check(0 < len(rows) <= 64 and rows[-1].mnemonic == 'ret')
    edges = calls(rows)
    check(len(edges) == 1 and not any(row.mnemonic.startswith('j') for row in rows),
          'Original import descriptor is not a single bounded static definition.')
    at, _ = edges[0]
    registers, stack, argument = {}, {}, None
    for row in rows[:at]:
        operands = row.operands
        if row.mnemonic == 'lea' and len(operands) == 2 and operands[0].type == 1 and operands[1].type == 3:
            name, memory = reg(row, operands[0]), operands[1].mem
            if row.reg_name(memory.base) == 'rip':
                registers[name] = ('literal', _rip(row, operands[1]))
            elif name == 'rcx' and row.reg_name(memory.base) == 'rsp' and not memory.index:
                argument = memory.disp
            else:
                raise ValueError('Original import descriptor has an unsupported pointer definition.')
        elif row.mnemonic == 'mov' and len(operands) == 2 and operands[0].type == 3:
            memory, value = operands[0].mem, operands[1]
            check(row.reg_name(memory.base) == 'rsp' and not memory.index and memory.disp not in stack)
            stack[memory.disp] = ((value.imm, value.size) if value.type == 2 else
                                 (registers.get(reg(row, value)), value.size) if value.type == 1 else None)
        else:
            check(row.mnemonic in {'sub', 'nop', 'endbr64'} and
                  (row.mnemonic != 'sub' or reg(row, operands[0]) == 'rsp'))
    check(argument is not None and set(stack) == {argument + n for n in (0, 8, 16, 24, 32, 36, 40, 44)})
    for offset, value, size in ((32, 0, 4), (36, 2, 4), (40, 16, 4), (44, 0, 1)):
        check(stack[argument + offset] == (value, size), 'Original import ABI descriptor changed.')
    strings = []
    for offset, width, encoding in ((0, 2, 'utf-16-le'), (16, 1, 'ascii')):
        pointer, size = stack[argument + offset]
        length, length_size = stack[argument + offset + 8]
        check(isinstance(pointer, tuple) and pointer[0] == 'literal' and size == length_size == 8 and
              type(length) is int and 0 < length <= 128)
        raw = image.data_read(pointer[1], (length + 1) * width)
        check(raw[-width:] == bytes(width))
        strings.append(raw[:-width].decode(encoding, 'strict'))
    check(re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,127}', strings[0]) and
          re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', strings[1]))
    return Import(*strings)


def managed_import(metadata, image):
    owners, code = Owners(metadata, image), Code(image)
    wrapper = owners.method('.AkSoundEngine', 'LoadFilePackage', 2)
    wrapper_rows = code.linear(wrapper)
    pinvoke = owners.called(wrapper_rows, '.AkSoundEnginePINVOKE', 'CSharp_LoadFilePackage', 2)
    flags = struct.unpack_from('<H', metadata.methods, pinvoke['index'] * 32 + 24)[0]
    check(flags & 0x2000, 'Original managed native owner is not a declared PInvoke.')
    rows = code.linear(pinvoke)
    edges = calls(rows)
    check(len(edges) == 1, 'Original native import stub has an ambiguous lazy resolver.')
    at, resolver = edges[0]
    check(at + 2 < len(rows) and rows[at + 1].mnemonic == 'mov' and
          rows[at + 1].operands[0].type == 3 and reg(rows[at + 1], rows[at + 1].operands[1]) == 'rax')
    slot = _rip(rows[at + 1], rows[at + 1].operands[0])
    loads = [row for row in rows[:at] if row.mnemonic == 'mov' and len(row.operands) == 2 and
             reg(row, row.operands[0]) == 'rax' and row.operands[1].type == 3 and
             row.reg_name(row.operands[1].mem.base) == 'rip']
    check(len(loads) == 1 and _rip(loads[0], loads[0].operands[1]) == slot and
          any(row.mnemonic == 'jmp' and reg(row, row.operands[0]) == 'rax' for row in rows[:at]) and
          rows[at + 2].mnemonic == 'jmp' and direct(rows[at + 2]) in {row.address for row in rows[:at]},
          'Original lazy import cache does not own the indirect native dispatch.')
    descriptor = code.linear({'pointer': resolver, 'name': 'owned_import_descriptor'})
    return import_descriptor(descriptor, image)


class NativeImage(Image):
    """Endfield-owned chained-unwind view, using the shared verified decoder."""

    def __init__(self, raw):
        super().__init__(raw)
        optional = self.unpack('<I', 0x3c)[0] + 24
        rva, size = self.unpack('<II', optional + 112 + 8 * 3)
        at = self.offset(rva, size)
        self.entries = dict((start, (start, end, unwind)) for start, end, unwind in
                            struct.iter_unpack('<III', raw[at:at + size]))
        check(len(self.entries) == size // 12, 'Original unwind roots are duplicated.')
        self.optional = optional

    def owner(self, entry):
        seen = set()
        while True:
            begin, end, unwind = entry
            check(unwind not in seen and len(seen) < 16)
            seen.add(unwind)
            at = self.offset(unwind, 4)
            header = self.data[at:at + 4]
            check(header[0] & 7 == 1)
            if not header[0] >> 3 & 4:
                return begin
            check(not header[0] >> 3 & 3)
            chained = self.offset(unwind + 4 + ((header[2] + 1) // 2) * 4, 12)
            entry = self.unpack('<III', chained)
            check(self.entries.get(entry[0]) == entry, 'Original chained unwind owner is undeclared.')

    def body(self, start):
        check(start in self.entries and self.owner(self.entries[start]) == start)
        # Inventory only links to this selected owner. Unrelated exception
        # handlers may use another unwind version and are not source callers.
        selected = {start: self.entries[start]}
        for _ in range(64):
            additions = {}
            for row in self.entries.values():
                if row[0] in selected:
                    continue
                at = self.offset(row[2], 4)
                header = self.data[at:at + 4]
                if header[0] & 7 != 1 or not header[0] >> 3 & 4:
                    continue
                chained = self.offset(row[2] + 4 + ((header[2] + 1) // 2) * 4, 12)
                parent = self.unpack('<III', chained)
                if selected.get(parent[0]) == parent:
                    check(self.owner(row) == start)
                    additions[row[0]] = row
            if not additions:
                break
            selected.update(additions)
        else:
            raise ValueError('Original native unwind chain exceeds its bound.')
        entries = sorted(selected.values())
        check(entries and len(entries) <= 64 and sum(end - begin for begin, end, _ in entries) <= 65536)
        check(all(left[1] <= right[0] for left, right in zip(entries, entries[1:])),
              'Original native owner spans overlap.')
        rows = []
        for begin, end, _ in entries:
            check(any(self.sections[name][0] <= begin < end <= self.sections[name][0] + self.sections[name][3]
                      for name in self.executable_sections))
            at = self.offset(begin, end - begin)
            part = list(decoder().disasm(self.data[at:at + end - begin], self.base + begin))
            check(part and sum(row.size for row in part) == end - begin)
            rows += part
        addresses = {row.address for row in rows}
        check(len(addresses) == len(rows) and any(row.mnemonic == 'ret' for row in rows))
        for row in rows:
            if row.mnemonic.startswith('j'):
                check(direct(row) in addresses, 'Original owned native branch leaves its complete function.')
            if row.mnemonic not in {'ret', 'int3', 'jmp'}:
                check(row.address + row.size in addresses,
                      'Original owned native fallthrough leaves its complete function.')
        return rows

    def export(self, name):
        check(isinstance(name, str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', name))
        rva, size = self.unpack('<II', self.optional + 112)
        check(40 <= size <= 8 * 1024**2)
        row = self.unpack('<IIHH7I', self.offset(rva, 40))
        check(0 < row[7] <= row[6] <= 100000)
        def string(rva):
            at = self.offset(rva)
            for count in range(129):
                self.offset(rva, count + 1)
                if self.data[at + count] == 0:
                    return self.data[at:at + count].decode('ascii', 'strict')
            raise ValueError('Original export name is unbounded.')
        found = []
        for n in range(row[7]):
            pointer, = self.unpack('<I', self.offset(row[9] + n * 4, 4))
            if string(pointer) == name:
                ordinal, = self.unpack('<H', self.offset(row[10] + n * 2, 2))
                check(ordinal < row[6])
                target, = self.unpack('<I', self.offset(row[8] + ordinal * 4, 4))
                check(not rva <= target < rva + size, 'Original native export forwards to another module.')
                check(any(self.sections[s][0] <= target < self.sections[s][0] + self.sections[s][3]
                          for s in self.executable_sections))
                found.append(target)
        check(len(found) == 1, 'Original native import has no unique current export.')
        return found[0]

    def thunk(self, start):
        """Follow only a bounded owned export wrapper's direct tail transfer."""
        seen = set()
        while start not in self.entries:
            check(start not in seen and len(seen) < 4)
            seen.add(start)
            at = self.offset(start)
            section = next(self.sections[s] for s in self.executable_sections
                           if self.sections[s][0] <= start < self.sections[s][0] + self.sections[s][3])
            size = min(64, section[0] + section[3] - start)
            for row in decoder().disasm(self.data[at:at + size], self.base + start):
                if row.mnemonic == 'jmp':
                    target = direct(row)
                    check(target is not None)
                    start = target - self.base
                    break
                check(row.mnemonic in {'mov', 'lea', 'nop', 'endbr64'},
                      'Original export wrapper has an unsupported operation.')
            else:
                raise ValueError('Original export wrapper has no bounded direct tail transfer.')
        return start
