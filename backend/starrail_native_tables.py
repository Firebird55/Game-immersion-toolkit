"""Original table ownership and serialized field descriptions, data only."""
from collections import defaultdict
import re
import struct

from .starrail_metadata import _check
from .starrail_native_description import _register
from .starrail_native_routes import _one, NUMBER, REGISTER


def bindings(index, names):
    _check(isinstance(names, (set, frozenset)) and 0 < len(names) <= 256
           and all(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,127}', name) for name in names))
    literals = {}
    for address, value in index.literals.items():
        for name in names:
            if value == name or value.endswith('/' + name + '.bytes'):
                literals[address] = name
    _check(set(literals.values()) == names)
    records = []
    prefilter = re.compile(rb'[\x40-\x4f]?[\x8b\x8d][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', re.S)
    total = 0
    for owner, identity, block in index.all_blocks:
        ctor = re.findall(r'^    private static void \.cctor\(\) \{\} // VA: 0x[0-9A-Fa-f]+, RVA: (0x[0-9A-Fa-f]+),', block, re.M)
        arrays = {name: int(offset, 16) for name, offset in re.findall(
            r'^    (?:private|public) static (?:readonly )?string\[\] ([A-Za-z0-9_]+) // Offset: (0x[0-9A-Fa-f]+), Token:', block, re.M)}
        rows = set(re.findall(r'Dictionary<[^,>]+, ([A-Za-z0-9_.]+Row)> [A-Za-z0-9_]+ // Offset:', block))
        if not ctor or not arrays or len(rows) != 1:
            continue
        _check(len(ctor) == 1)
        start = int(ctor[0], 16); end = index.raw_extent(start); raw = index.read(start, end - start)
        total += len(raw); _check(total <= 16 * 1024**2)
        if not any(start + match.start() + len(match.group()) + struct.unpack_from('<i', match.group(), len(match.group()) - 4)[0]
                   in literals for match in prefilter.finditer(raw)):
            continue
        instructions, digest = index.body(start); sizes = index.instruction_sizes(start)
        registers, stores, heap = {}, [], defaultdict(set)
        def get(register):
            return registers.get(_register(register))
        def put(register, value):
            register = _register(register)
            if value is None:
                registers.pop(register, None)
            else:
                registers[register] = value
        for address, operation, args in instructions:
            load = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[rip ([+-]) ' + NUMBER + r'\]', args)
            dereference = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\]', args)
            store = re.fullmatch(r'qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\], (' + REGISTER + r')', args)
            copy = re.fullmatch(r'(' + REGISTER + r'), (' + REGISTER + r')', args)
            if operation == 'call':
                for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    put(register, None)
                put('rax', ('heap', address))
            elif operation == 'mov' and load:
                target = address + sizes[address] + (1 if load[2] == '+' else -1) * int(load[3], 0)
                put(load[1], ('literal', literals[target]) if target in literals else ('global', target))
            elif operation == 'mov' and dereference:
                source = get(dereference[2])
                put(dereference[1], ('member', source, int(dereference[3], 0)) if source and source[0] in {'global', 'member'} else None)
            elif operation == 'mov' and store:
                origin, source, offset = get(store[1]), get(store[3]), int(store[2], 0)
                if origin and origin[0] == 'heap' and source and source[0] == 'literal' and offset >= 0x20 and offset % 8 == 0:
                    heap[origin[1]].add(source[1])
                # A heap element store cannot masquerade as a static field.
                # Static storage must come through original global/member loads.
                if origin and origin[0] in {'global', 'member'} and source and source[0] == 'heap':
                    stores.append((origin, offset, source[1]))
            elif operation == 'mov' and copy:
                put(copy[1], get(copy[2]))
            elif ',' in args and operation not in {'test', 'cmp'}:
                put(args.split(',')[0], None)
        valid = [(origin, offset, pointer) for origin, offset, pointer in stores if heap.get(pointer)]
        if valid:
            records.append((owner, identity, block, arrays, next(iter(rows)), valid, heap, digest))
    bias_sets = [{metadata - offset for metadata in arrays.values() for _, offset, pointer in stores}
                 for _, _, _, arrays, _, stores, _, _ in records]
    _check(len(bias_sets) >= 2 and all(bias_sets))
    biases = set.intersection(*bias_sets); _check(len(biases) == 1); bias = next(iter(biases))
    result = {}
    for owner, identity, block, arrays, row, stores, heap, digest in records:
        joined = {(next(iter(heap[pointer])), origin) for origin, offset, pointer in stores
                  if offset + bias in arrays.values() and len(heap[pointer]) == 1}
        if not joined:
            continue
        table, storage = _one(joined)
        _check(table not in result and row in index.blocks)
        row_block = index.blocks[row]
        from_binary = _one(re.findall(r'^    public static void FromBinary\([^\n]*\) \{\} // VA: 0x[0-9A-Fa-f]+, RVA: (0x[0-9A-Fa-f]+),', row_block, re.M))
        fields = [{'type': kind, 'name': name, 'offset': int(offset, 16)} for kind, name, offset in re.findall(
            r'^    public (.+) ([A-Za-z0-9_]+) // Offset: (0x[0-9A-Fa-f]+),', row_block, re.M)]
        _check(fields and len(fields) <= 64)
        result[table] = {'table_type': owner, 'table_identity': identity, 'table_block': block,
                         'row_type': row, 'row_block': row_block, 'fields': fields,
                         'from_binary': int(from_binary, 16), 'constructor_sha256': digest}
    _check(set(result) == names)
    return result


def _field_order(index, binding):
    fields = {field['offset']: field for field in binding['fields']}
    _check(len(fields) == len(binding['fields']))
    instructions, digest = index.body(binding['from_binary'])
    method = binding.get('reader_method', 'FromBinary')
    receiver = binding.get('receiver', 'reference')
    _check(isinstance(method, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', method)
           and receiver in {'reference', 'object'})
    reader = _one(set(re.findall(r'public static void ' + re.escape(method)
                                + r'\(([A-Za-z0-9_.]+),', binding['row_block'])))
    registers = {'rdx': ('row' if receiver == 'object' else 'rowref', 0), 'rcx': ('reader', 0)}
    mask_found, mask_reader, current, writes = False, None, None, {}
    signed_completions, textids = {}, {}
    dwords = { _register(register): register for register in
              ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp', *(f'r{i}d' for i in range(8, 16))) }
    def get(register):
        return registers.get(_register(register))
    def put(register, value):
        register = _register(register)
        if value is None:
            registers.pop(register, None)
        else:
            registers[register] = value
    def field(value):
        if value and value[0] == 'row' and value[1] in fields and current is not None:
            writes.setdefault(value[1], set()).add(current)
    for at, (address, operation, operands) in enumerate(instructions):
        if at in signed_completions:
            register, value = signed_completions[at]; put(register, value); continue
        test = re.fullmatch(r'([a-z0-9]+), ' + NUMBER, operands)
        if operation == 'test' and test and get(test[1]) and get(test[1])[0] == 'mask':
            value = int(test[2], 0)
            _check(value > 0 and value & (value - 1) == 0)
            current = value.bit_length() - 1 + (8 if test[1] in {'ah', 'bh', 'ch', 'dh'} else 0) + get(test[1])[1]
            continue
        call = operation in {'call', 'jmp'} and re.fullmatch('0x[0-9a-f]+', operands)
        if call:
            target = int(operands, 16) - index.base
            if operation == 'jmp' and instructions[0][0] <= target <= instructions[-1][0]:
                continue
            signatures = []
            for method in index.methods.get(target, []):
                parsed = re.fullmatch(r'public static ([^ ]+) [A-Za-z0-9_]+\((.*)\)', method['signature'])
                if parsed and re.match(re.escape(reader) + r'(?:,|$)', parsed[2]):
                    signatures.append(parsed)
            _check(len(signatures) <= 1)
            signature = signatures[0] if signatures else None
            if signature:
                for register in ('rcx', 'rdx', 'r8', 'r9')[:signature[2].count(',') + 1]:
                    field(get(register))
            elif get('rcx') == ('reader', 0):
                # Concrete generic instantiations are absent from the helper's
                # managed method map. The field type selects the frozen scalar
                # or array codec only after its pointer argument is established.
                for register in ('rdx', 'r8', 'r9'):
                    field(get(register))
            for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                put(register, None)
            if signature and signature[1] in {'ulong', 'uint'} and not mask_found:
                put('rax', ('mask', 0)); mask_found = True; mask_reader = target
            else:
                put('rax', ('return', target, address))
            continue
        store = re.fullmatch(r'(?:qword|dword|word|byte) ptr \[([a-z0-9]+)(?: \+ ' + NUMBER + r')?\], ([a-z0-9]+)', operands)
        if operation == 'mov' and store:
            receiver, offset, source = get(store[1]), int(store[2] or '0', 0), get(store[3])
            if receiver and receiver[0] == 'row' and source and source[0] in {'return', 'zigzag'}:
                destination = receiver[1] + offset
                root = destination if destination in fields else destination - 8
                if root in fields and fields[root]['type'] == 'RPG.Client.TextID':
                    parts = textids.setdefault((root, current), {})
                    if destination == root and source[0] == 'zigzag' and operands.startswith('dword ptr '):
                        parts['legacy'] = source
                    elif destination == root + 8 and source[0] == 'return' and operands.startswith('qword ptr '):
                        parts['current'] = source
                    if set(parts) == {'legacy', 'current'}:
                        _check(parts['legacy'][1] == parts['current'][1] == mask_reader
                               and parts['legacy'][2] < parts['current'][2])
                        field(('row', root))
                    continue
                if destination in fields:
                    kind = fields[destination]['type']
                    width = 'byte' if kind == 'bool' else 'qword' if kind == 'string' or kind.endswith('[]') else 'dword'
                    _check(operands.startswith(width + ' ptr '))
                field(('row', destination))
            continue
        load = re.fullmatch(r'([a-z0-9]+), (?:qword|dword|word|byte) ptr \[([a-z0-9]+)(?: \+ ' + NUMBER + r')?\]', operands)
        if operation == 'mov' and load:
            source, offset = get(load[2]), int(load[3] or '0', 0)
            put(load[1], ('row', 0) if source == ('rowref', 0) and offset == 0 else None)
            continue
        copy = re.fullmatch(r'([a-z0-9]+), ([a-z0-9]+)', operands)
        if operation == 'mov' and copy:
            source = get(copy[2])
            target_register, source_register = _register(copy[1]), _register(copy[2])
            if (source and source[0] == 'return' and target_register in dwords and source_register in dwords
                    and target_register != source_register
                    and copy[1] in {target_register, dwords[target_register]}
                    and copy[2] in {source_register, dwords[source_register]} and at + 4 < len(instructions)):
                destination, original = dwords[target_register], dwords[source_register]
                tail = instructions[at + 1:at + 5]
                results = []
                for shifted, signed, result in ((original, destination, target_register), (destination, original, source_register)):
                    shift = re.fullmatch(re.escape(shifted) + r', ' + NUMBER, tail[0][2])
                    mask = re.fullmatch(re.escape(signed) + r', ' + NUMBER, tail[1][2])
                    if (tail[0][1] == 'shr' and shift and int(shift[1], 0) == 1
                            and tail[1][1] == 'and' and mask and int(mask[1], 0) == 1
                            and tuple(tail[2][1:]) == ('neg', signed)
                            and tuple(tail[3][1:]) == ('xor', signed + ', ' + shifted)):
                        results.append(result)
                if results:
                    _check(len(results) == 1)
                    _check(not any(op.startswith('j') and re.fullmatch('0x[0-9a-f]+', args)
                                   and tail[0][0] <= int(args, 16) - index.base <= tail[-1][0]
                                   for _, op, args in instructions))
                    signed_completions[at + 4] = (results[0], ('zigzag', *source[1:]))
            put(copy[1], get(copy[2])); continue
        add = re.fullmatch(r'([a-z0-9]+), ' + NUMBER, operands)
        if operation == 'add' and add and get(add[1]) and get(add[1])[0] == 'row':
            put(add[1], ('row', get(add[1])[1] + int(add[2], 0))); continue
        lea = re.fullmatch(r'([a-z0-9]+), \[([a-z0-9]+) \+ ' + NUMBER + r'\]', operands)
        if operation == 'lea' and lea and get(lea[2]) and get(lea[2])[0] == 'row':
            put(lea[1], ('row', get(lea[2])[1] + int(lea[3], 0))); continue
        if ',' in operands and operation not in {'test', 'cmp'}:
            put(operands.split(',')[0], None)
    _check(mask_found and set(writes) == set(fields) and all(len(bits) == 1 for bits in writes.values()))
    ordered = sorted(fields.values(), key=lambda field: next(iter(writes[field['offset']])))
    _check([next(iter(writes[field['offset']])) for field in ordered] == list(range(len(fields))))
    prefixed = []
    for loader in re.findall(r'^    (?:public|private) static void [A-Za-z0-9_]+\(string\) \{\} // VA: 0x[0-9A-Fa-f]+, RVA: (0x[0-9A-Fa-f]+), Token:', binding['table_block'], re.M):
        body, _ = index.body(int(loader, 16))
        for at, (_, operation, operands) in enumerate(body):
            if operation != 'call' or not re.fullmatch('0x[0-9a-f]+', operands):
                continue
            target = int(operands, 16) - index.base
            if any(re.fullmatch(r'public static byte [A-Za-z0-9_]+\(string, System.Action<' + re.escape(reader) + r'>, bool, bool\)', method['signature'])
                   for method in index.methods.get(target, [])):
                flags = [int(match[1], 0) for _, op, args in body[max(0, at - 6):at]
                         if op == 'mov' and (match := re.fullmatch(r'r8b, ' + NUMBER, args))]
                _check(flags == [1]); prefixed.append(target)
    _check(len(prefixed) <= 1)
    return ordered, bool(prefixed)


def descriptions(index, table_bindings):
    result = {}
    kinds = {'uint': 'u32', 'int': 's32', 'bool': 'bool', 'string': 'string', 'float': 'f32',
             'uint[]': 'u32[]', 'string[]': 'string[]', 'float[]': 'f32[]', 'RPG.Client.TextID': 'textid'}
    for name, binding in table_bindings.items():
        ordered, prefix = _field_order(index, binding); fields, enums = [], {}
        for field in ordered:
            kind = kinds.get(field['type'])
            if kind is None:
                _check(field['type'] in index.blocks)
                enum = index.blocks[field['type']]
                _check(re.search(r'^public enum [^\n]+', enum, re.M))
                values = re.findall(r'^    public const [A-Za-z0-9_.]+ ([A-Za-z_][A-Za-z0-9_]*) = (-?[0-9]+) // Offset:', enum, re.M)
                _check(values)
                mapping = {}
                for label, number in values:
                    number = int(number)
                    # Alias labels do not establish one canonical presentation.
                    _check(number not in mapping and -(1 << 31) <= number < 1 << 31)
                    mapping[number] = label
                kind = 's32'; enums[field['name']] = mapping
            fields.append([field['name'], kind])
        result[name] = {'fields': fields, 'identity': [], 'hash_byte_prefix': prefix, 'enums': enums}
    return result
