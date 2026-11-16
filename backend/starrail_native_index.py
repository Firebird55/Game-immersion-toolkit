"""Bounded managed/native joins over freshly authenticated original metadata."""
import bisect
import hashlib
import json
import re
import struct

from .starrail_metadata import _check


METHOD = re.compile(r'// VA: (0x[0-9A-Fa-f]+), RVA: (0x[0-9A-Fa-f]+), Token: (0x[0-9A-Fa-f]+)')


class NativeIndex:
    def __init__(self, prepared):
        self.prepared = prepared
        self.native = prepared.inputs / 'GameAssembly.dll'
        with self.native.open('rb') as stream:
            header = stream.read(8192)
        _check(len(header) >= 64 and header[:2] == b'MZ')
        pe = struct.unpack_from('<I', header, 60)[0]
        _check(pe <= len(header) - 264 and header[pe:pe + 4] == b'PE\0\0'
               and struct.unpack_from('<H', header, pe + 4)[0] == 0x8664
               and struct.unpack_from('<H', header, pe + 24)[0] == 0x20b)
        count = struct.unpack_from('<H', header, pe + 6)[0]
        optional = struct.unpack_from('<H', header, pe + 20)[0]
        self.base = struct.unpack_from('<Q', header, pe + 48)[0]
        _check(0 < count <= 96 and pe + 24 + optional + 40 * count <= len(header))
        self.sections = []
        for i in range(count):
            at = pe + 24 + optional + i * 40
            virtual, rva, size, offset = struct.unpack_from('<4I', header, at + 8)
            _check(offset + size <= self.native.stat().st_size)
            self.sections.append((rva, size, offset))
        self.blocks, self.methods, self.owners, self.owner_methods = {}, {}, {}, {}
        self.scopes = {}
        self.all_blocks, ambiguous = [], set()
        lines = []
        def add_block(lines):
            text = ''.join(lines)
            names = re.findall(r'^[ \t]*// Full Name: ([^\n]*)$', text, re.M)
            indexes = re.findall(r'^\s*// TypeDefIndex: ([0-9]+)$', text, re.M)
            if not names and not indexes:
                return
            _check(len(names) == len(indexes) == 1)
            owner = names[0]
            _check(len(owner) <= 2048 and len(self.all_blocks) <= 1024**2)
            identity = owner + '#' + indexes[0]
            self.all_blocks.append((owner, identity, text))
            if owner in self.blocks or owner in ambiguous:
                self.blocks.pop(owner, None); ambiguous.add(owner)
            else:
                self.blocks[owner] = text
            self.owners.setdefault(owner, []).append(identity)
            scopes = [(0, identity)]
            self.scopes[identity] = []
            for line_number, line in enumerate(lines):
                indent = len(line) - len(line.lstrip(' '))
                if re.match(r'^ +.*\{ // Token: 0x[0-9A-Fa-f]+\s*$', line):
                    while len(scopes) > 1 and scopes[-1][0] >= indent:
                        scopes.pop()
                    child = identity + '/nested@' + str(line_number)
                    scopes.append((indent, child)); self.scopes[child] = []
                elif line.strip() == '}':
                    while len(scopes) > 1 and scopes[-1][0] >= indent:
                        scopes.pop()
                scope = scopes[-1][1]
                self.scopes[scope].append(line)
                match = METHOD.search(line)
                if match and int(match[2], 16):
                    rva = int(match[2], 16)
                    _check(rva < 1 << 32)
                    record = {'owner': scope,
                              'signature': line.split('{}')[0].strip()}
                    self.methods.setdefault(rva, []).append(record)
                    self.owner_methods.setdefault(scope, []).append((rva, record['signature']))
        with (prepared.outputs / 'dump.cs').open(encoding='utf-8-sig') as stream:
            for line in stream:
                _check(len(line) <= 1024**2)
                if re.match(r'^\s*// TypeDefIndex: ', line):
                    add_block(lines); lines = []
                lines.append(line)
            add_block(lines)
        _check(self.blocks and self.methods and len(self.methods) <= 4 * 1024**2)
        self.ordered = sorted(self.methods)
        self.literals = {}
        values = json.loads((prepared.outputs / 'stringliterals.json').read_text(encoding='utf-8-sig'))
        _check(isinstance(values, list) and len(values) <= 4 * 1024**2)
        for row in values:
            _check(isinstance(row, dict) and set(row) == {'Address', 'Value'}
                   and isinstance(row['Address'], str) and re.fullmatch(r'0x[0-9A-Fa-f]+', row['Address'])
                   and isinstance(row['Value'], str) and len(row['Value']) <= 1024**2)
            address = int(row['Address'], 16)
            _check(0 < address < 1 << 32 and address not in self.literals)
            self.literals[address] = row['Value']
        self.cache = {}
        self.graph_cache = {}
        self.scopes = {identity: ''.join(lines) for identity, lines in self.scopes.items()}

    def offset(self, start, length):
        _check(type(start) is int and type(length) is int and 0 < length <= 16 * 1024**2)
        matches = [offset + start - rva for rva, size, offset in self.sections if rva <= start < start + length <= rva + size]
        _check(len(matches) == 1)
        return matches[0]

    def read(self, start, length):
        with self.native.open('rb') as stream:
            stream.seek(self.offset(start, length)); value = stream.read(length)
        _check(len(value) == length)
        return value

    def extent(self, address):
        index = bisect.bisect_right(self.ordered, address)
        _check(address in self.methods and index < len(self.ordered))
        end = self.ordered[index]
        _check(0 < end - address <= 65536)
        return end

    def method(self, owner, signature, *, include_nested=False):
        _check(owner in self.blocks)
        _check(len(self.owners[owner]) == 1)
        identity = self.owners[owner][0]
        scopes = [name for name in self.owner_methods if name == identity or include_nested and name.startswith(identity + '/')]
        matches = [address for scope in scopes for address, value in self.owner_methods[scope] if re.fullmatch(signature, value)]
        _check(len(matches) == 1)
        return matches[0]

    def bodies(self, addresses):
        missing = list(dict.fromkeys(address for address in addresses if address not in self.cache))
        if missing:
            _check(len(missing) <= 4096)
            ranges = [{'offset': self.offset(address, self.extent(address) - address),
                       'address': self.base + address, 'bytes': self.extent(address) - address} for address in missing]
            decoded = self.prepared.disassemble(ranges)
            for address, instructions, descriptor in zip(missing, decoded, ranges):
                _check(isinstance(instructions, list) and 0 < len(instructions) <= 8192)
                normalized = []
                for at, op, args in instructions:
                    _check(type(at) is int and self.base + address <= at < self.base + address + descriptor['bytes'])
                    normalized.append((at - self.base, op, args))
                self.cache[address] = normalized, hashlib.sha256(self.read(address, descriptor['bytes'])).hexdigest()
        return [self.cache[address] for address in addresses]

    def body(self, address):
        return self.bodies([address])[0]

    def graph(self, address):
        """A static direct-branch graph; never decode unreachable tail data."""
        if address not in self.graph_cache:
            end = self.extent(address)
            ranges = [{'offset': self.offset(address, end - address), 'address': self.base + address,
                       'bytes': end - address, 'control_flow': True}]
            decoded, = self.prepared.disassemble(ranges)
            result = [(at - self.base, op, args) for at, op, args in decoded]
            _check(result and len(result) <= 8192 and all(address <= at < end for at, _, _ in result))
            for _, operation, args in result:
                if operation == 'jmp' and re.fullmatch('0x[0-9a-f]+', args):
                    target = int(args, 16) - self.base
                    _check(address <= target < end or target in self.methods)
            self.graph_cache[address] = result, hashlib.sha256(self.read(address, end - address)).hexdigest()
        return self.graph_cache[address]

    def instruction_sizes(self, address):
        instructions, _ = self.body(address)
        following = [row[0] for row in instructions[1:]] + [self.extent(address)]
        return {row[0]: end - row[0] for row, end in zip(instructions, following)}
