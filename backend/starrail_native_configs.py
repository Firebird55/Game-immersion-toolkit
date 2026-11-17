"""Native-owned mission schemas and literal constructor defaults, data only."""
from functools import lru_cache
import math
import re
import struct

from . import starrail_native_usages as usages, starrail_native_tables as tables
from .starrail_native_description import _register, _writes
from .starrail_native_routes import NUMBER, REGISTER, _one
from .starrail_metadata import _check
from .starrail_original_configs import ROOT


def _bits(register):
    if re.fullmatch(r'xmm[0-9]+', register):
        return 128, 0
    if register in {'ah', 'bh', 'ch', 'dh'}:
        return 8, 8
    if register in {'al', 'bl', 'cl', 'dl', 'sil', 'dil', 'spl', 'bpl'} or re.fullmatch(r'r(?:[89]|1[0-5])b', register):
        return 8, 0
    if register in {'ax', 'bx', 'cx', 'dx', 'si', 'di', 'sp', 'bp'} or re.fullmatch(r'r(?:[89]|1[0-5])w', register):
        return 16, 0
    if register.startswith('e') or re.fullmatch(r'r(?:[89]|1[0-5])d', register):
        return 32, 0
    return 64, 0


def _constant_read(value, register):
    if not value or value[0] != 'constant':
        return value
    bits, shift = _bits(register)
    mask = (1 << bits) - 1
    return ('constant', (value[1] >> shift) & mask, (value[2] >> shift) & mask)


def _constant_write(value, register, previous):
    bits, shift = _bits(register)
    mask = ((1 << bits) - 1) << shift
    old = previous if previous and previous[0] == 'constant' else ('constant', 0, 0)
    number = (old[1] & ~mask) | ((value[1] << shift) & mask)
    known = (old[2] & ~mask) | ((value[2] << shift) & mask)
    if bits == 32:
        number &= (1 << 32) - 1
        known |= ((1 << 64) - 1) ^ ((1 << 32) - 1)
    return ('constant', number, known)


class Descriptions:
    def __init__(self, index):
        self.index = index
        # A persistent preparation service opens successive native generations.
        # Class-wide LRU keys would retain every old index through ``self``.
        for method, limit in (('enum', 4096), ('description', 4096), ('_paths', 1)):
            setattr(self, method, lru_cache(maxsize=limit)(getattr(self, method)))
        self.usages = usages.derive(index)
        self.reader = self.usages['reader']
        self.registries = self.usages['registries']
        self.bindings = {}
        root = index.method(ROOT, r'public static void FromBinary\(' + re.escape(self.reader) + ', ' + re.escape(ROOT) + r'\)')
        rows, _ = index.body(root)
        self.varuint = _one(set(int(args, 16) - index.base for _, op, args in rows
            if op == 'call' and re.fullmatch('0x[0-9a-f]+', args) and any(
                re.fullmatch(r'public static ulong [A-Za-z0-9_]+\(' + re.escape(self.reader) + r'\)', row['signature'])
                for row in index.methods.get(int(args, 16) - index.base, []))))
        allocations = []
        for i in range(1, len(rows) - 1):
            if (rows[i][1] == 'call' and re.fullmatch('0x[0-9a-f]+', rows[i][2])
                    and rows[i - 1][1] == 'mov' and re.fullmatch(r'rcx, qword ptr \[rip [+-] ' + NUMBER + r'\]', rows[i - 1][2])
                    and rows[i + 1][1] == 'mov' and re.fullmatch(r'qword ptr \[' + REGISTER + r'\], rax', rows[i + 1][2])):
                allocations.append(int(rows[i][2], 16) - index.base)
        self.allocator = _one(set(allocations))
        self.bindings[ROOT] = (root, 'FromBinary', 'reference', None)

    def _chain(self, name):
        chain = []
        while name in self.index.blocks:
            _check(name not in chain and len(chain) <= 32)
            chain.append(name)
            block = self.index.blocks[name]
            parent = re.search(r'^public (?:abstract )?class [^ ]+ : ([^ ]+)', block, re.M)
            if not parent:
                break
            name = parent[1]
        return chain

    def enum(self, name):
        block = self.index.blocks.get(name, '')
        if not re.search(r'^public enum ', block, re.M):
            return None
        result = {}
        for label, number in re.findall(r'^    public const [A-Za-z0-9_.]+ ([A-Za-z_][A-Za-z0-9_]*) = (-?[0-9]+) // Offset:', block, re.M):
            number = int(number)
            _check(number not in result and -(1 << 31) <= number < 1 << 31)
            result[number] = label
        _check(result)
        return result

    def _fields(self, name):
        fields = []
        for owner in self._chain(name):
            fields.extend({'type': kind, 'name': field, 'offset': int(offset, 16)} for kind, field, offset in re.findall(
                r'^    public (?!static |const )(.+) ([A-Za-z0-9_]+) // Offset: (0x[0-9A-Fa-f]+),', self.index.blocks[owner], re.M))
        _check(fields and len(fields) <= 64 and len({field['offset'] for field in fields}) == len(fields))
        return fields

    def _flow(self, rows, *, mode, stop, depth=0):
        """Track only pointer provenance and literal field stores, not client code."""
        _check(depth <= 8)
        state = {'rcx': ('reader',), 'rdx': ('outref',)} if mode == 'reference' else {'rcx': ('reader',)} if mode == 'factory' else {'rcx': ('object', 0)}
        objects = {0: []} if mode == 'constructor' else {}
        output, selected, returns = None, None, []
        def get(register):
            return state.get(_register(register))
        for at, (position, operation, args) in enumerate(rows):
            if mode == 'reference' and operation == 'jmp' and args == hex(self.index.base + stop):
                _check(get('rcx') == ('reader',) and output and get('rdx') == output)
                return objects[output[1]]
            if operation == 'ret':
                returns.append(get('rax'))
                if mode in {'factory', 'constructor'}:
                    break
                continue
            _check(not (mode in {'factory', 'constructor'} and (operation.startswith('j') or operation.startswith('loop'))))
            if operation == 'call':
                target = int(args, 16) - self.index.base if re.fullmatch('0x[0-9a-f]+', args) else None
                if target == stop:
                    receiver = get('rdx') if mode == 'factory' else output
                    _check(get('rcx') == ('reader',) and receiver and receiver[0] == 'object')
                    _check(mode != 'reference' or target == self.varuint or get('rdx') == receiver)
                    selected = receiver
                    if mode != 'factory':
                        return objects[receiver[1]]
                result = None
                if target == self.allocator:
                    _check(get('rcx',) and get('rcx')[0] == 'global')
                    result = ('object', position); objects[position] = []
                elif target != stop:
                    instances = [get(register) for register in ('rcx', 'rdx', 'r8', 'r9')]
                    instances = [value for value in instances if value and value[0] == 'object']
                    if instances:
                        records = self.index.methods.get(target, [])
                        _check(len(instances) == 1 and get('rcx') == instances[0] and any(
                            re.fullmatch(r'(?:public|protected|private) void \.ctor\(\)', row['signature']) for row in records))
                        body, _ = self.index.body(target)
                        values = self._flow(body, mode='constructor', stop=None, depth=depth + 1)
                        objects[instances[0][1]].extend(values)
                for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    state.pop(register, None)
                if result:
                    state['rax'] = result
                continue
            store = re.fullmatch(r'(qword|dword|word|byte) ptr \[(' + REGISTER + r')(?: \+ ' + NUMBER + r')?\], (.+)', args)
            if operation in {'mov', 'movss', 'movsd'} and store:
                _check(operation == 'mov' or store[1] == ('dword' if operation == 'movss' else 'qword'))
                receiver = get(store[2]); offset = int(store[3] or '0', 0)
                count = {'byte': 1, 'word': 2, 'dword': 4, 'qword': 8}[store[1]]
                source = ('constant', int(store[4], 0), (1 << 64) - 1) if re.fullmatch(NUMBER, store[4]) else _constant_read(get(store[4]), store[4])
                if receiver == ('outref',) and offset == 0:
                    _check(source and source[0] == 'object'); output = source
                elif receiver and receiver[0] == 'object':
                    _check(source and source[0] in {'constant', 'literal'})
                    if source[0] == 'constant':
                        mask = (1 << (8 * count)) - 1
                        _check(source[2] & mask == mask)
                        source = ('constant', source[1] & mask, mask)
                    objects[receiver[1]].append((offset, store[1], source[1]))
                else:
                    _check(store[2] in {'rsp', 'rbp'})
                continue
            memory = re.match(r'(?:qword|dword|word|byte|xmmword) ptr \[(' + REGISTER + r')', args)
            if memory and operation not in {'cmp', 'test', 'bt', 'nop'}:
                _check(memory[1] in {'rsp', 'rbp'})
            value = None
            destination = args.split(',')[0]
            previous = get(destination)
            copy = re.fullmatch(r'([a-z0-9]+), ([a-z0-9]+)', args)
            if operation == 'mov' and copy:
                value = _constant_read(get(copy[2]), copy[2])
                if value and value[0] in {'reader', 'object', 'outref', 'global', 'literal'} and any(_register(reg) != reg for reg in (copy[1], copy[2])):
                    value = None
            literal = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[rip [+-] ' + NUMBER + r'\]', args)
            if operation == 'mov' and literal:
                address = usages._rip(rows, at)
                value = ('literal', self.index.literals[address]) if address in self.index.literals else ('global', address)
            scalar = re.fullmatch(r'xmm[0-9]+, (dword|qword) ptr \[rip [+-] ' + NUMBER + r'\]', args)
            if operation in {'movss', 'movsd'} and scalar:
                count = 4 if operation == 'movss' else 8
                _check(scalar[1] == ('dword' if count == 4 else 'qword'))
                value = ('constant', int.from_bytes(self.index.read(usages._rip(rows, at), count), 'little'), (1 << (8 * count)) - 1)
            constant = re.fullmatch(r'([a-z0-9]+), ' + NUMBER, args)
            if operation == 'mov' and constant:
                value = ('constant', int(constant[2], 0), (1 << 64) - 1)
            load = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[(' + REGISTER + r')\]', args)
            if operation == 'mov' and load and get(load[2]) == ('outref',):
                value = output
            if operation in {'xor', 'xorps', 'xorpd', 'pxor'} and copy and copy[1] == copy[2]:
                value = ('constant', 0, (1 << 128) - 1)
            for register in list(state):
                if _writes(operation, args, register):
                    state.pop(register, None)
            if value:
                state[_register(destination)] = _constant_write(value, destination, previous) if value[0] == 'constant' else value
        if mode == 'constructor':
            _check(returns)
            return objects[0]
        _check(selected and returns and all(value == selected for value in returns))
        return objects[selected[1]]

    def polymorphic(self, base, number):
        _check(base in self.registries and type(number) is int and number in self.registries[base])
        definition = self.registries[base][number]
        _check(definition is not None)
        address, _ = self.index.method_definitions[definition]
        rows, _ = self.index.body(address)
        candidates = []
        for _, operation, args in rows:
            if operation != 'call' or not re.fullmatch('0x[0-9a-f]+', args):
                continue
            target = int(args, 16) - self.index.base
            for record in self.index.methods.get(target, []):
                match = re.fullmatch(r'public static void ([A-Za-z0-9_]+)\(' + re.escape(self.reader) + r', ([A-Za-z0-9_.]+)\)', record['signature'])
                if match and match[2] in self.index.blocks and record['owner'] == _one(self.index.owners[match[2]]) and base in self._chain(match[2]):
                    candidates.append((match[2], target, match[1]))
        name, target, method = _one(candidates)
        defaults = self._flow(rows, mode='factory', stop=target)
        binding = (target, method, 'object', defaults)
        if name in self.bindings:
            existing = self.bindings[name]
            _check(existing[:3] == binding[:3] and existing[3] is not None
                   and _defaults(self._fields(name), existing[3], self.enum)
                   == _defaults(self._fields(name), defaults, self.enum))
        else:
            self.bindings[name] = binding
        return name

    def description(self, name):
        _check(name in self.index.blocks)
        if name not in self.bindings:
            pattern = r'public static void FromBinary\(' + re.escape(self.reader) + ', ' + re.escape(name) + r'\)'
            identity = _one(self.index.owners[name])
            methods = self.index.owner_methods[identity]
            named = [(address, signature) for address, signature in methods if re.fullmatch(pattern, signature)]
            if named:
                address, _ = _one(named)
                self.bindings[name] = (address, 'FromBinary', 'reference', None)
            else:
                candidates = {}
                for address, signature in methods:
                    match = re.fullmatch(r'public static void ([A-Za-z0-9_]+)\(' + re.escape(self.reader) + ', ' + re.escape(name) + r'\)', signature)
                    if match:
                        candidates[address] = match[1]
                _check(0 < len(candidates) <= 16)
                wrappers = []
                for address in candidates:
                    rows, _ = self.index.body(address)
                    calls = {int(args, 16) - self.index.base for _, op, args in rows if op in {'call', 'jmp'} and re.fullmatch('0x[0-9a-f]+', args)}
                    readers = (calls & candidates.keys()) - {address}
                    if self.allocator in calls and self.varuint in calls:
                        wrappers.append((address, candidates[address], 'reference', None))
                    elif self.allocator in calls and len(readers) == 1:
                        target = next(iter(readers))
                        values = self._flow(rows, mode='reference', stop=target)
                        wrappers.append((target, candidates[target], 'object', values))
                self.bindings[name] = _one(wrappers)
        address, method, receiver, values = self.bindings[name]
        fields = self._fields(name)
        binding = {'fields': fields, 'from_binary': address, 'row_block': self.index.blocks[name],
                   'table_block': '', 'reader_method': method, 'receiver': receiver}
        ordered, prefix = tables._field_order(self.index, binding)
        _check(not prefix)
        if values is None:
            rows, _ = self.index.body(address)
            values = self._flow(rows, mode='reference', stop=self.varuint)
        defaults = _defaults(fields, values, self.enum)
        return {'fields': [[field['name'], field['type']] for field in ordered], 'defaults': defaults}

    def _paths(self):
        candidates = [(address, record) for address, records in self.index.methods.items() for record in records
                      if re.fullmatch(r'(?:public|private) static string JsonToBinaryPath\(string\)', record['signature'])]
        address, _ = _one(candidates)
        rows, _ = self.index.body(address)
        return _path_recipe(self.index, rows)

    def binary_path(self, relative):
        prefix, suffix = self._paths()
        _check(re.fullmatch(r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.json', relative))
        return prefix + relative[:-5] + suffix


def _path_recipe(index, rows):
    """Prove prefix/stem/suffix arguments reaching the original builder result."""
    state, builders, results = {'rcx': ('path',)}, {}, []
    length_offset = int(_one(re.findall(r'^private int m_stringLength // Offset: (0x[0-9A-Fa-f]+),',
                                      index.blocks.get('System.String', ''), re.M)), 16)
    for at, (position, operation, args) in enumerate(rows):
        if operation in {'call', 'jmp'} and re.fullmatch('0x[0-9a-f]+', args):
            records = index.methods.get(int(args, 16) - index.base, [])
            receiver, argument = state.get('rcx'), state.get('rdx')
            value, builder_call = None, False
            for record in records:
                owner, signature = record['owner'].split('#')[0], record['signature']
                if (owner == 'System.String' and signature == 'public int LastIndexOf(char, int, int)'
                        and receiver == ('path',)
                        and _constant_read(argument, 'dx') == ('constant', 0x2e, (1 << 16) - 1)
                        and state.get('r8') == ('last',) and state.get('r9') == ('length',)):
                    value = ('dot',)
                elif (owner == 'System.String' and signature == 'public string Substring(int, int)'
                      and receiver == ('path',)
                      and _constant_read(argument, 'edx') == ('constant', 0, (1 << 32) - 1)
                      and state.get('r8') == ('dot',)):
                    value = ('stem',)
                elif re.fullmatch(r'(?:public|private|internal) static System\.Text\.StringBuilder [A-Za-z0-9_]+\(\)', signature):
                    value = ('builder', position); builders[position] = []
                elif (owner == 'System.Text.StringBuilder' and signature == 'public System.Text.StringBuilder Append(string)'
                      and receiver and receiver[0] == 'builder'):
                    builders[receiver[1]].append(argument or ('unknown',)); value = receiver; builder_call = True
                elif (owner == 'System.Text.StringBuilder' and signature == 'public override string ToString()'
                      and receiver and receiver[0] == 'builder'):
                    results.append(list(builders[receiver[1]])); builder_call = True
            if receiver and receiver[0] == 'builder' and not builder_call:
                builders[receiver[1]].append(('unknown',))
            for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                state.pop(register, None)
            if value:
                state['rax'] = value
            continue
        value = None
        destination = args.split(',')[0]
        previous = state.get(_register(destination))
        copy = re.fullmatch(r'([a-z0-9]+), ([a-z0-9]+)', args)
        if operation == 'mov' and copy:
            value = _constant_read(state.get(_register(copy[2])), copy[2])
            if value and value[0] not in {'dot', 'constant'} and any(_register(reg) != reg for reg in (copy[1], copy[2])):
                value = None
        literal = re.fullmatch(REGISTER + r', qword ptr \[rip [+-] ' + NUMBER + r'\]', args)
        if operation == 'mov' and literal:
            string = index.literals.get(usages._rip(rows, at))
            if string is not None:
                value = ('literal', string)
        constant = re.fullmatch(r'[a-z0-9]+, ' + NUMBER, args)
        if operation == 'mov' and constant:
            value = ('constant', int(constant[1], 0), (1 << 64) - 1)
        if operation == 'xor' and copy and copy[1] == copy[2]:
            value = ('constant', 0, (1 << 64) - 1)
        length = re.fullmatch(r'([a-z0-9]+), dword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\]', args)
        if (operation == 'mov' and length and _bits(length[1]) == (32, 0)
                and state.get(_register(length[2])) == ('path',) and int(length[3], 0) == length_offset):
            value = ('length',)
        last = re.fullmatch(r'([a-z0-9]+), \[(' + REGISTER + r') - (?:0x1|1)\]', args)
        if operation == 'lea' and last and _bits(last[1]) == (32, 0) and state.get(_register(last[2])) == ('length',):
            value = ('last',)
        for register in list(state):
            if _writes(operation, args, register):
                state.pop(register, None)
        if value:
            state[_register(destination)] = _constant_write(value, destination, previous) if value[0] == 'constant' else value
    prefix, suffix = _one((values[0][1], values[2][1]) for values in results
                          if len(values) == 3 and values[0][0] == values[2][0] == 'literal' and values[1] == ('stem',))
    _check(re.fullmatch(r'(?:[A-Za-z0-9_-]+/)+', prefix) and re.fullmatch(r'\.[A-Za-z0-9]{1,16}', suffix))
    return prefix, suffix


def _defaults(fields, stores, enum):
    """Apply literal stores at byte granularity, including combined bool writes."""
    sizes = {'byte': 1, 'word': 2, 'dword': 4, 'qword': 8}
    memory, strings = {}, {}
    maximum = max(field['offset'] for field in fields) + 16
    _check(isinstance(stores, (list, tuple)) and len(stores) <= 4096)
    for offset, width, value in stores:
        _check(width in sizes and 0x10 <= offset < offset + sizes[width] <= maximum)
        if isinstance(value, str):
            _check(width == 'qword' and any(field['offset'] == offset and field['type'] == 'string' for field in fields))
            _check(not any(at in memory for at in range(offset, offset + 8)))
            strings[offset] = value
        else:
            _check(type(value) is int and 0 <= value < 1 << (8 * sizes[width]))
            _check(not any(start <= offset < start + 8 or offset <= start < offset + sizes[width] for start in strings))
            for i, byte in enumerate(value.to_bytes(sizes[width], 'little')):
                memory[offset + i] = byte
    _check(all(not any(at in memory for at in range(offset, offset + 8)) for offset in strings))
    defaults = {}
    for field in fields:
        kind, key, offset = field['type'], field['name'], field['offset']
        labels = enum(kind)
        if offset in strings:
            defaults[key] = strings[offset]
            continue
        count = 1 if kind == 'bool' else 4 if kind in {'uint', 'int', 'float'} or labels is not None else 8
        raw = bytes(memory.get(offset + i, 0) for i in range(count))
        number = int.from_bytes(raw, 'little')
        if kind == 'bool':
            _check(number in (0, 1)); defaults[key] = bool(number)
        elif kind in {'uint', 'int'} or labels is not None:
            if kind != 'uint' and number >= 1 << 31:
                number -= 1 << 32
            defaults[key] = labels.get(number, number) if labels is not None else number
        elif kind == 'float':
            number, = struct.unpack('<f', raw); _check(math.isfinite(number)); defaults[key] = number
        elif any(offset + i in memory for i in range(count)):
            _check(number == 0); defaults[key] = None
    return defaults
