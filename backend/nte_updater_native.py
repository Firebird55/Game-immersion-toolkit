"""Bounded original-updater instruction metadata; never execute publisher code.

This deliberately supports a small native compiler vocabulary. Unknown forms,
ambiguous ownership or incomplete functions reject derivation. No disassembler,
downloaded helper, native game runtime or per-release addresses are required.
"""
from bisect import bisect_right
from dataclasses import dataclass
import re
import struct

from .nte_native_schema import _PE


def check(value):
    if not value:
        raise ValueError('Unsupported original NTE updater instruction metadata')


@dataclass(frozen=True)
class Instruction:
    address: int
    size: int
    opcode: tuple[int, ...]
    rex: int
    modrm: int | None
    sib: int | None
    displacement: int
    immediate: int | None
    rip: int | None
    prefix: tuple[int, ...]

    @property
    def next(self):
        return self.address + self.size

    @property
    def destination(self):
        return None if self.modrm is None else (self.modrm >> 3 & 7) + (8 if self.rex & 4 else 0)

    @property
    def base_register(self):
        if self.modrm is None or self.modrm >> 6 == 3 or self.rip is not None:
            return None
        if self.sib is not None:
            if self.sib >> 3 & 7 != 4 or self.rex & 2 or self.modrm >> 6 == 0 and self.sib & 7 == 5:
                return None
            return (self.sib & 7) + (8 if self.rex & 1 else 0)
        return (self.modrm & 7) + (8 if self.rex & 1 else 0)

    @property
    def call(self):
        return self.next + self.immediate if self.opcode == (0xe8,) else None

    @property
    def rm_register(self):
        return ((self.modrm & 7) + (8 if self.rex & 1 else 0)
                if self.modrm is not None and self.modrm >> 6 == 3 else None)

    @property
    def immediate_register(self):
        if len(self.opcode) == 1 and 0xb0 <= self.opcode[0] <= 0xbf:
            return (self.opcode[0] & 7) + (8 if self.rex & 1 else 0)
        return None


def decode(data: bytes, address: int) -> Instruction:
    """Read one supported instruction, retaining operands needed for ownership.

    Length decoding is explicit so bytes inside immediates and displacements
    cannot become invented calls or string references.
    """
    check(isinstance(data, bytes) and data)
    position, rex, prefixes = 0, 0, []

    def take(count):
        nonlocal position
        check(0 < count <= len(data) - position and position + count <= 15)
        result = data[position:position + count]
        position += count
        return result

    while position < len(data) and data[position] in (0x66, 0x67, 0xf0, 0xf2, 0xf3, 0x64, 0x65):
        prefix = take(1)[0]
        check(prefix not in prefixes or prefix == 0x66)
        prefixes.append(prefix)
    if position < len(data) and 0x40 <= data[position] <= 0x4f:
        rex = take(1)[0]
    first = take(1)[0]
    opcode = (first,)
    operand_size = 2 if 0x66 in prefixes else 4
    has_modrm, immediate_size, relative = False, 0, False
    if first == 0x0f:
        second = take(1)[0]
        opcode += (second,)
        if 0x80 <= second <= 0x8f:
            immediate_size, relative = 4, True
        elif second in (0x05, 0x0b, 0x31, 0x77, 0xa0, 0xa1, 0xa2, 0xa8, 0xa9):
            pass
        elif second in (0x38, 0x3a):
            opcode += (take(1)[0],)
            has_modrm = True
            immediate_size = int(second == 0x3a)
        elif (0x10 <= second <= 0x1f or 0x28 <= second <= 0x2f
                or 0x40 <= second <= 0x76 or 0x7e <= second <= 0x7f
                or 0x90 <= second <= 0x9f or second in (0xa3, 0xa4, 0xa5, 0xab, 0xac, 0xad, 0xaf)
                or 0xb0 <= second <= 0xbf or 0xc0 <= second <= 0xc7 or 0xd0 <= second <= 0xfe):
            has_modrm = True
            immediate_size = int(second in (0x70, 0x71, 0x72, 0x73, 0xa4, 0xac, 0xba, 0xc2, 0xc4, 0xc5, 0xc6))
        else:
            check(False)
    elif (first < 0x40 and first & 7 <= 3 and first >> 3 <= 7
            or first in (0x63, 0x69, 0x6b, 0x80, 0x81, 0x83)
            or 0x84 <= first <= 0x8f or first in (0xc0, 0xc1, 0xc6, 0xc7)
            or 0xd0 <= first <= 0xd3 or first in (0xf6, 0xf7, 0xfe, 0xff)):
        has_modrm = True
        if first in (0x69, 0x81, 0xc7): immediate_size = operand_size
        elif first in (0x6b, 0x80, 0x83, 0xc0, 0xc1, 0xc6): immediate_size = 1
    elif first in (0xe8, 0xe9):
        immediate_size, relative = 4, True
    elif first == 0xeb or 0x70 <= first <= 0x7f or first == 0xe3:
        immediate_size, relative = 1, True
    elif 0xb8 <= first <= 0xbf:
        immediate_size = 8 if rex & 8 else operand_size
    elif 0xb0 <= first <= 0xb7 or first in (0x6a, 0xa8) or first < 0x40 and first & 7 == 4:
        immediate_size = 1
    elif first in (0x68, 0xa9) or first < 0x40 and first & 7 == 5:
        immediate_size = operand_size
    elif first == 0xc2:
        immediate_size = 2
    elif 0x50 <= first <= 0x5f or first in (0x90, 0x98, 0x99, 0x9c, 0x9d, 0xc3, 0xcc, 0xfc, 0xfd):
        pass
    else:
        check(False)
    modrm, sib, displacement, rip_displacement = None, None, 0, None
    if has_modrm:
        modrm = take(1)[0]
        mode, register = modrm >> 6, modrm & 7
        sib = take(1)[0] if mode != 3 and register == 4 else None
        sib_base = sib & 7 if sib is not None else None
        if mode == 1:
            displacement = int.from_bytes(take(1), 'little', signed=True)
        elif mode == 2 or mode == 0 and (register == 5 or sib_base == 5):
            displacement = int.from_bytes(take(4), 'little', signed=True)
            if mode == 0 and register == 5 and 0x67 not in prefixes:
                rip_displacement = displacement
        if first in (0xf6, 0xf7) and modrm >> 3 & 7 <= 1:
            immediate_size = 1 if first == 0xf6 else operand_size
    immediate = int.from_bytes(take(immediate_size), 'little', signed=relative) if immediate_size else None
    return Instruction(address, position, opcode, rex, modrm, sib, displacement, immediate,
        address + position + rip_displacement if rip_displacement is not None else None, tuple(prefixes))


class Image(_PE):
    def __init__(self, data):
        check(len(data) <= 32 * 1024**2)
        super().__init__(data)
        optional = self.unpack('I', 60)[0] + 24
        table, size = self.unpack('II', optional + 112 + 3 * 8)
        check(0 < size <= 12 * 100_000 and size % 12 == 0)
        offset = self.pointer(self.base + table, size)
        check(offset is not None)
        self.functions = []
        for index in range(0, size, 12):
            start, end, unwind = self.unpack('III', offset + index)
            check(0 < start < end and self.pointer(self.base + start, end - start, code=True) is not None
                  and self.pointer(self.base + unwind, 4) is not None)
            check(not self.functions or self.functions[-1][1] <= self.base + start)
            self.functions.append((self.base + start, self.base + end))
        self.starts = [start for start, _ in self.functions]
        self.decoded = {}

    def owner(self, address):
        index = bisect_right(self.starts, address) - 1
        if index >= 0 and address < self.functions[index][1]:
            return self.functions[index]
        return None

    def instructions(self, owner):
        check(owner in self.functions and owner[1] - owner[0] <= 65536)
        if owner not in self.decoded:
            rows, current = [], owner[0]
            while current < owner[1]:
                check(len(rows) < 8192)
                offset = self.pointer(current, code=True)
                instruction = decode(self.read(offset, min(15, owner[1] - current)), current)
                rows.append(instruction)
                current = instruction.next
            check(current == owner[1])
            self.decoded[owner] = tuple(rows)
        return self.decoded[owner]

    def target(self, address):
        seen = set()
        while True:
            check(address not in seen and len(seen) < 8)
            seen.add(address)
            offset = self.pointer(address, 5, code=True)
            check(offset is not None)
            if self.data[offset] != 0xe9:
                return address
            address += 5 + self.unpack('i', offset + 1)[0]

    def leaf(self, address, limit=128):
        """Inspect a proved entry through its first return or direct tail jump."""
        rows, end = [], address + limit
        while address < end:
            offset = self.pointer(address, min(15, end - address), code=True)
            check(offset is not None)
            row = decode(self.read(offset, min(15, end - address)), address)
            rows.append(row)
            if row.opcode in ((0xc3,), (0xc2,), (0xe9,), (0xeb,)):
                return tuple(rows)
            address = row.next
        check(False)

    def data_bytes(self, address, count):
        offset = self.pointer(address, count)
        check(offset is not None)
        return self.read(offset, count)

    def string(self, value):
        check(isinstance(value, bytes) and value and len(value) <= 256)
        results = []
        for start, size, offset, flags in self.sections:
            if flags & 0x20000000 or not flags & 0x40000000:
                continue
            results.extend(start + hit.start() for hit in re.finditer(re.escape(value + b'\0'), self.read(offset, size)))
        check(len(results) == 1)
        return results[0]

    def lea_hits(self, target):
        for start, size, offset, flags in self.sections:
            if not flags & 0x20000000:
                continue
            for hit in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', self.read(offset, size)):
                position = offset + hit.start()
                if position + 7 <= offset + size:
                    row = decode(self.read(position, 7), start + hit.start())
                    if row.rip == target:
                        yield row

    def callers(self, target):
        """Validate aligned calls, including original direct-jump entry thunks."""
        targets = {target}
        code = [(start, self.read(offset, size)) for start, size, offset, flags in self.sections if flags & 0x20000000]
        for _ in range(8):
            previous = set(targets)
            for start, data in code:
                for hit in re.finditer(b'\xe9', data):
                    at = hit.start()
                    if at + 5 <= len(data) and start + at + 5 + struct.unpack_from('<i', data, at + 1)[0] in targets:
                        targets.add(start + at)
                        check(len(targets) <= 1024)
            if targets == previous:
                break
        else:
            check(False)
        owners = set()
        for start, data in code:
            for hit in re.finditer(b'\xe8', data):
                at = hit.start()
                if at + 5 <= len(data) and start + at + 5 + struct.unpack_from('<i', data, at + 1)[0] in targets:
                    owner = self.owner(start + at)
                    if owner is not None:
                        owners.add(owner)
                        check(len(owners) <= 4096)
        return tuple((owner, row) for owner in sorted(owners) for row in self.instructions(owner)
                     if row.call in targets and self.target(row.call) == target)

    def references(self, target):
        """Return only aligned LEA references inside complete original functions."""
        candidates = {owner for row in self.lea_hits(target) if (owner := self.owner(row.address)) is not None}
        return tuple((owner, row) for owner in sorted(candidates) for row in self.instructions(owner)
                     if row.opcode == (0x8d,) and row.rip == target)
