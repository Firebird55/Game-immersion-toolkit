"""Find IL2CPP owners and literal references without revision addresses."""
from __future__ import annotations

import struct

from .endfield_client_source import check


class Owners:
    def __init__(self, metadata, image):
        self.metadata, self.image = metadata, image
        self.modules = {}
        needle = struct.pack('<Q', metadata.type_count)
        registrations = []
        for address in image.occurrences(needle):
            if address % 8:
                continue
            try:
                count, fields, count2, sizes = struct.unpack('<4Q', image.data_read(address, 32))
                if count2 == metadata.type_count:
                    image.q(fields + (count - 1) * 8)
                    image.q(sizes + (count - 1) * 8)
                    registrations.append((address, fields))
            except ValueError:
                continue
        check(len(registrations) == 1, 'Original IL2CPP metadata registration is ambiguous.')
        self.registration, self.field_table = registrations[0]
        self.type_count, self.type_table = struct.unpack('<2Q', image.data_read(self.registration - 32, 16))
        check(metadata.type_count <= self.type_count <= 2_000_000)
        image.q(self.type_table + (self.type_count - 1) * 8)

    def field(self, owner, name):
        row = self.metadata.fields(owner)[name]
        type_index = self.metadata.owner(owner)
        pointer = self.image.q(self.field_table + type_index * 8)
        offset, = struct.unpack('<i', self.image.data_read(pointer + row['ordinal'] * 4, 4))
        check(0 <= offset <= 65536)
        return {**row, 'offset': offset}

    def field_type(self, owner, name):
        index = self.metadata.fields(owner)[name]['type']
        check(0 <= index < self.type_count)
        return self.type_at(self.image.q(self.type_table + index * 8))

    def type_at(self, pointer, depth=0):
        check(depth < 8)
        raw = self.image.data_read(pointer, 16)
        value, = struct.unpack_from('<Q', raw)
        kind = raw[10]
        if kind == 0xe:
            return 'System.String'
        if kind == 0x8:
            return 'System.Int32'
        if kind in (0x11, 0x12):
            return self.metadata.type_name(value)
        if kind == 0x1d:
            return ('array', self.type_at(value, depth + 1))
        if kind == 0x15:
            definition, instance = struct.unpack('<2Q', self.image.data_read(value, 16))
            count, = struct.unpack('<I', self.image.data_read(instance, 4))
            check(0 < count <= 8)
            arguments = self.image.q(instance + 8)
            return ('generic', self.type_at(definition, depth + 1), tuple(
                self.type_at(self.image.q(arguments + n * 8), depth + 1) for n in range(count)))
        raise ValueError('Original parameter field type is unsupported.')

    def module(self, type_index):
        found = []
        for name, _assembly, begin, count in (struct.unpack_from('<IiiI', self.metadata.images, n)
                                             for n in range(0, len(self.metadata.images), 40)):
            if begin <= type_index < begin + count:
                found.append(self.metadata.string(name))
        check(len(found) == 1)
        name = found[0]
        if name in self.modules:
            return self.modules[name]
        candidates = []
        for string in self.image.occurrences(name.encode() + b'\0'):
            try:
                if self.image.data_read(string - 1, 1) != b'\0':
                    continue
            except ValueError:
                continue
            for address in self.image.occurrences(struct.pack('<Q', string)):
                if address % 8:
                    continue
                try:
                    _, count, table = struct.unpack('<3Q', self.image.data_read(address, 24))
                    if 0 < count <= 1_000_000:
                        self.image.q(table + (count - 1) * 8)
                        candidates.append((count, table))
                except ValueError:
                    continue
        candidates = sorted(set(candidates))
        check(len(candidates) == 1, 'Original codegen image is missing or ambiguous.')
        self.modules[name] = candidates[0]
        return candidates[0]

    def method(self, owner, name, parameters=None):
        row = self.metadata.method(owner, name, parameters)
        return self.addressed(row)

    def addressed(self, row):
        count, table = self.module(row['type'])
        rid = row['token'] & 0xffffff
        check(1 <= rid <= count)
        pointer = self.image.q(table + (rid - 1) * 8)
        self.image.offset(pointer, 1)
        return {**row, 'pointer': pointer}

    def called(self, rows, owner, name, parameters=None):
        targets = {row.operands[0].imm for row in rows if row.mnemonic in {'call', 'jmp'} and
                   row.operands and row.operands[0].type == 2}
        found = [value for row in self.metadata.methods_named(owner, name, parameters)
                 if (value := self.addressed(row))['pointer'] in targets]
        check(len(found) == 1, 'Original call has no unique metadata-owned overload.')
        return found[0]

    def method_at(self, pointer, parameters=None):
        """Resolve a real direct call through image tokens, including renamed helpers."""
        matches = {}
        needle = struct.pack('<Q', pointer)
        for at in range(0, len(self.metadata.images), 40):
            _name, _assembly, begin, count = struct.unpack_from('<IiiI', self.metadata.images, at)
            if begin < 0 or not count:
                continue
            try:
                number, table = self.module(begin)
            except ValueError:
                continue
            raw = self.image.data_read(table, number * 8)
            offset = 0
            while (offset := raw.find(needle, offset)) >= 0:
                if offset % 8 == 0:
                    matches[(begin, count, offset // 8 + 1)] = True
                offset += 1
        found = []
        for at in range(0, len(self.metadata.methods), 32):
            values = struct.unpack_from('<6I4H', self.metadata.methods, at)
            if parameters is not None and values[-1] != parameters:
                continue
            rid = values[5] & 0xffffff
            if any(start <= values[1] < start + count and token == rid for start, count, token in matches):
                found.append({'index': at // 32, 'owner': self.metadata.type_name(values[1]),
                              'name': self.metadata.string(values[0]), 'type': values[1],
                              'token': values[5], 'parameters': values[-1],
                              'return_type': values[2], 'pointer': pointer})
        check(len(found) == 1, 'Original direct callee identity is missing or ambiguous.')
        return found[0]

    def literal_usage(self, instruction):
        """An exact RIP-relative authored string-literal usage, not a scan hit."""
        references = []
        for operand in instruction.operands:
            if operand.type == 3 and instruction.reg_name(operand.mem.base) == 'rip':
                slot = instruction.address + instruction.size + operand.mem.disp
                value = self.image.q(slot)
                if value >> 29 == 5 and value & 1:
                    references.append(((value & 0x1fffffff) >> 1, slot))
        check(len(references) == 1, 'Expected one original literal usage.')
        index, slot = references[0]
        return {'index': index, 'slot': slot, 'text': self.metadata.literal(index)}

    def is_owner_usage(self, instruction, owner):
        for operand in instruction.operands:
            if operand.type == 3 and instruction.reg_name(operand.mem.base) == 'rip':
                value = self.image.q(instruction.address + instruction.size + operand.mem.disp)
                if value >> 29 in (1, 2) and value & 1:
                    index = (value & 0x1fffffff) >> 1
                    if not 0 <= index < self.type_count:
                        continue
                    pointer = self.image.q(self.type_table + index * 8)
                    raw = self.image.data_read(pointer, 16)
                    definition, = struct.unpack_from('<Q', raw)
                    if raw[10] in (0x11, 0x12) and definition == self.metadata.owner(owner):
                        return True
        return False
