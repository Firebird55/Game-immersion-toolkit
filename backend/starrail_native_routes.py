"""Derive bootstrap and resource protocol descriptions from original metadata."""
import re

from . import starrail_native_description as descriptions
from .starrail_metadata import _check

NUMBER = r'(0x[0-9a-f]+|[0-9]+)'
REGISTER = r'r[a-z0-9]+'


def _one(values):
    values = list(values); _check(len(values) == 1); return values[0]


def _offset(block, name):
    return int(_one(re.findall(r'(?<![A-Za-z0-9_])' + re.escape(name) + r' // Offset: (0x[0-9A-Fa-f]+)', block)), 16)


def _copies(instructions):
    result = []
    for first, second in zip(instructions, instructions[1:]):
        a = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\]', first[2])
        b = re.fullmatch(r'qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\], (' + REGISTER + r')', second[2])
        if first[1] == second[1] == 'mov' and a and b and a[1] == b[3]:
            result.append((a[2], int(a[3], 0), b[1], int(b[2], 0)))
    return result


def _string_tag(instructions, offset):
    positions = [i for i, (_, op, args) in enumerate(instructions)
                 if op == 'mov' and re.fullmatch(r'rdx, qword ptr \[' + REGISTER + r' \+ ' + hex(offset) + r'\]', args)]
    at = _one(positions); values = []
    for _, op, args in instructions[max(0, at - 8):at]:
        direct = re.fullmatch(r'byte ptr \[' + REGISTER + r' \+ ' + REGISTER + r' \+ 0x20\], ' + NUMBER, args)
        if op == 'mov' and direct:
            values = [int(direct[1], 0)]
    if not values:
        for register in ('dl', 'r8b', 'r9b'):
            tags = [int(match[1], 0) for _, op, args in instructions[max(0, at - 8):at]
                    if op == 'mov' and (match := re.fullmatch(register + ', ' + NUMBER, args))]
            if tags:
                values.append(tags[-1])
    _check(values and all(value & 128 for value in values[:-1]) and values[-1] < 128)
    tag = sum((value & 127) << (7 * i) for i, value in enumerate(values))
    _check(tag & 7 == 2 and 0 < tag >> 3 < 1 << 29)
    return tag >> 3


def _enum_converter(index, address, enum_type):
    """Prove original label/constant assignments reaching an enum return.

    This follows static definitions and branch edges, never evaluates native
    instructions. Opaque patch/exception returns cannot establish a label.
    """
    block = index.blocks.get(enum_type, '')
    _check(re.search(r'^public enum ', block, re.M))
    labels = dict((label, int(number)) for label, number in re.findall(
        r'^    public const [A-Za-z0-9_.]+ ([A-Za-z_][A-Za-z0-9_]*) = (-?[0-9]+) // Offset:', block, re.M))
    _check(labels and len(labels) <= 256)
    body, _ = index.graph(address); pairs = {}; literal_loads = {}; registers = set(); sizes = {}
    for first, following in zip(body, body[1:]):
        sizes[first[0]] = following[0] - first[0]
    for i, (at, operation, args) in enumerate(body[:-1]):
        load = re.fullmatch(r'rdx, qword ptr \[rip ([+-]) ' + NUMBER + r'\]', args)
        if operation != 'mov' or not load:
            continue
        target = at + sizes[at] + (1 if load[1] == '+' else -1) * int(load[2], 0)
        label = index.literals.get(target)
        if label not in labels:
            continue
        literal_loads[i] = label
        _, op, operands = body[i + 1]
        value = re.fullmatch(r'([a-z0-9]+), ' + NUMBER, operands)
        zero = re.fullmatch(r'([a-z0-9]+), \1', operands)
        _check(op == 'mov' and value or op == 'xor' and zero)
        register = value[1] if op == 'mov' else zero[1]
        number = int(value[2], 0) if op == 'mov' else 0
        _check(number & 0xffffffff == labels[label] & 0xffffffff)
        pairs[i + 1] = label; registers.add(register)
    _check(set(pairs.values()) == set(labels) and len(registers) == 1)
    register = next(iter(registers)); canonical = descriptions._register(register)
    returned = _one(i for i, (_, op, args) in enumerate(body) if op == 'mov' and args == 'eax, ' + register)
    by_address = {row[0]: i for i, row in enumerate(body)}; predecessors = {i: [] for i in range(len(body))}
    equality_calls = []
    for i, (_, operation, args) in enumerate(body):
        edges = []
        if operation == 'call' and re.fullmatch('0x[0-9a-f]+', args):
            equality = any(row['owner'].startswith('System.String#') and re.fullmatch(
                r'(?:public|private) static bool (?:EqualsHelper|op_Equality)\(string, string\)', row['signature'])
                for row in index.methods.get(int(args, 16) - index.base, []))
            if equality:
                equality_calls.append(i)
        if operation.startswith('j'):
            if re.fullmatch('0x[0-9a-f]+', args) and int(args, 16) - index.base in by_address:
                edges.append(by_address[int(args, 16) - index.base])
            elif operation == 'jmp' and not args.startswith('0x'):
                # The managed decoder has already proved this guarded switch.
                # Replay only its authenticated table edges for def/use joins.
                _check(i >= 5)
                pointer, guard = body[i - 3], body[i - 5]
                load = re.fullmatch(REGISTER + r', \[rip ([+-]) ' + NUMBER + r'\]', pointer[2])
                maximum = re.fullmatch(r'[a-z0-9]+, ' + NUMBER, guard[2])
                _check(pointer[1] == 'lea' and load and guard[1] == 'cmp' and maximum)
                count = int(maximum[1], 0) + 1; _check(0 < count <= 256)
                table = body[i - 2][0] + (1 if load[1] == '+' else -1) * int(load[2], 0)
                import struct
                offsets = struct.unpack('<' + 'i' * count, index.read(table, count * 4))
                _check(all(table + offset in by_address for offset in offsets))
                edges.extend(by_address[table + offset] for offset in offsets)
            if operation != 'jmp' and i + 1 < len(body):
                edges.append(i + 1)
        elif operation not in {'ret', 'retf', 'int', 'int1', 'int3', 'ud2'} and i + 1 < len(body):
            edges.append(i + 1)
        for edge in edges:
            predecessors[edge].append(i)
    _check(equality_calls)
    def argument_origins(at, register):
        pending = [(previous, register) for previous in predecessors[at]]
        visited, found = set(), set()
        while pending:
            node, register = pending.pop()
            if (node, register) in visited:
                continue
            visited.add((node, register))
            _, operation, args = body[node]
            if descriptions._writes(operation, args, register):
                copy = re.fullmatch(r'(' + REGISTER + r'), (' + REGISTER + r')', args)
                if operation == 'mov' and copy and copy[1] == register:
                    if predecessors[node]:
                        pending.extend((previous, copy[2]) for previous in predecessors[node])
                    else:
                        _check(copy[2] == 'rcx'); found.add('original-argument')
                elif register == 'rdx' and node in literal_loads:
                    found.add(literal_loads[node])
                else:
                    _check(False)
            elif predecessors[node]:
                pending.extend((previous, register) for previous in predecessors[node])
            else:
                _check(register == 'rcx'); found.add('original-argument')
        return found
    for call in equality_calls:
        _check(argument_origins(call, 'rcx') == {'original-argument'}
               and argument_origins(call, 'rdx') and argument_origins(call, 'rdx') <= set(labels))
    pending, visited, origins = list(predecessors[returned]), set(), set()
    while pending:
        at = pending.pop()
        if at in visited:
            continue
        visited.add(at)
        _, operation, args = body[at]
        if descriptions._writes(operation, args, canonical):
            _check(at in pairs); origins.add(pairs[at])
        else:
            _check(predecessors[at]); pending.extend(predecessors[at])
    _check(origins == set(labels))
    return enum_type


def _version_schema(index, instructions, readers):
    fields, field_types = {}, {}
    for line in index.blocks['RPG.GameCore.VersionData'].splitlines():
        match = re.fullmatch(r'    (?:private|public) ([A-Za-z0-9_.]+) (<[^>]+>k__BackingField|[A-Za-z0-9_]+) // Offset: (0x[0-9A-Fa-f]+), Token: .*', line)
        if match:
            name = match[2]
            fields[int(match[3], 16)] = name[1:name.index('>')] if name.startswith('<') else name
            field_types[int(match[3], 16)] = match[1]
    schema, state = [], {'rcx': ('receiver', None)}
    for _, operation, args in instructions:
        call = operation == 'call' and re.fullmatch('0x[0-9a-f]+', args)
        if call:
            source = state.get('rcx'); conversion = None; target = int(args, 16) - index.base
            if source and source[0] == 'value' and schema[source[1]]['kind'] == 'string':
                candidates = [match[1] for row in getattr(index, 'methods', {}).get(target, [])
                              if (match := re.fullmatch(r'public static ([A-Za-z0-9_.]+) [A-Za-z0-9_]+\(string\)', row['signature']))
                              and match[1] in index.blocks and re.search(r'^public enum ', index.blocks[match[1]], re.M)]
                if candidates:
                    enum_type = _one(candidates); _enum_converter(index, target, enum_type)
                    conversion = ('converted', source[1], enum_type)
            for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                state.pop(register, None)
            kind = readers.get(int(args, 16))
            if kind:
                state['rax'] = ('value', len(schema))
                schema.append({'kind': kind, 'semantic': None})
            elif conversion:
                state['rax'] = conversion
            continue
        store = re.fullmatch(r'(qword|dword|byte) ptr \[(' + REGISTER + r') \+ (0x[0-9a-f]+)\], ([a-z0-9]+)', args)
        if operation == 'mov' and store:
            source = state.get(descriptions._register(store[4])); receiver = state.get(store[2])
            if source and source[0] in {'value', 'converted'} and receiver == ('receiver', None) and int(store[3], 16) in fields:
                field = schema[source[1]]
                widths = {'string': {'qword'}, 'u32': {'dword', 'qword'}, 'bool': {'byte'}}
                valid = (store[1] == 'dword' and field_types[int(store[3], 16)] == source[2]) if source[0] == 'converted' else store[1] in widths[field['kind']]
                if valid:
                    semantic = fields[int(store[3], 16)]
                    _check(field['semantic'] in (None, semantic)); field['semantic'] = semantic
            continue
        copy = re.fullmatch(r'([a-z0-9]+), ([a-z0-9]+)', args)
        if operation == 'mov' and copy:
            source = state.get(descriptions._register(copy[2])); target = descriptions._register(copy[1])
            if source:
                kind = 'string' if source[0] == 'receiver' else 'u32' if source[0] == 'converted' else schema[source[1]]['kind']
                full = all(descriptions._register(register) == register and register.startswith('r') for register in (copy[1], copy[2]))
                wide = all(re.fullmatch(r'r(?:ax|bx|cx|dx|si|di|bp|sp|[89]|1[0-5])|e(?:ax|bx|cx|dx|si|di|bp|sp)|r(?:[89]|1[0-5])d', register)
                           for register in (copy[1], copy[2]))
                low = all(re.fullmatch(r'[abcd]l|[sd]il|[bs]pl|r(?:[89]|1[0-5])b', register)
                          for register in (copy[1], copy[2]))
                if full or kind == 'u32' and wide or kind == 'bool' and (wide or low):
                    state[target] = source
                else:
                    state.pop(target, None)
            else:
                state.pop(target, None)
            continue
        for register in list(state):
            if descriptions._writes(operation, args, register):
                state.pop(register, None)
    return schema


def derive(index, files):
    """Return a description accepted by starrail_original_discovery.

    Managed semantic names establish ownership. Field offsets, method addresses,
    serialization order, protobuf tags and bootstrap filenames come from these
    original inputs; no game release or address/tag lists select a description.
    """
    client = index.method('RPG.Client.ClientStartupConfig', r'public static RPG\.Client\.ClientStartupConfig Deserialize\(byte\[\]\)')
    version = index.method('RPG.GameCore.VersionData', r'public void Deserialize\(byte\[\]\)')
    client_body, version_body = index.bodies([client, version])
    readers = descriptions.primitive_readers(version_body[0], index.methods, index.base)
    client_schema = descriptions.client_schema(index.blocks['RPG.Client.ClientStartupConfig'], client_body[0], readers)
    parser_pattern = r'public static RPG\.Client\.ServerDispatchData _ParseServerDispatchData\([^(),]+\)'
    parser = index.method('RPG.Client.ServerDispatchData', parser_pattern)
    parser_signature = _one([row['signature'] for row in index.methods[parser]
                             if re.fullmatch(parser_pattern, row['signature'])])
    protocol = re.search(r'\(([^(),]+)\)', parser_signature)[1]
    writer = index.method(protocol, r'public void WriteTo\(Google\.Protobuf\.CodedOutputStream\)')
    parser_body, writer_body = index.bodies([parser, writer]); routes = []
    semantic = {'design': '_DesignDataBundleVersionUpdateUrl', 'asb': '_AssetBundleVersionUpdateUrl',
                'base': '<BaseAssetBundleVersionUpdateUrl>k__BackingField', 'lua': '_LuaBundleVersionUpdateUrl'}
    copies = _copies(parser_body[0])
    destinations = {role: _offset(index.blocks['RPG.Client.ServerDispatchData'], field) for role, field in semantic.items()}
    string_fields = {int(offset, 16) for offset in re.findall(
        r'^    (?:public|private) string [^\n]+ // Offset: (0x[0-9A-Fa-f]+)', index.blocks[protocol], re.M)}
    groups = {}
    for source, source_offset, destination, destination_offset in copies:
        if source_offset in string_fields and destination_offset in destinations.values():
            groups.setdefault((source, destination), {}).setdefault(destination_offset, set()).add(source_offset)
    selected = _one(group for group in groups.values() if set(group) == set(destinations.values())
                    and all(len(offsets) == 1 for offsets in group.values()))
    for role, destination in destinations.items():
        source_offset = next(iter(selected[destination]))
        routes.append({'route': role, 'field': _string_tag(writer_body[0], source_offset), 'wire_type': 2})

    setter = index.method('RPG.Client.GlobalDispatchData', r'public void SetDispatchUrls\(string\[\]\)', include_nested=True)
    setter_scope = _one(record['owner'] for record in index.methods[setter]
                        if re.fullmatch(r'public void SetDispatchUrls\(string\[\]\)', record['signature']))
    candidates = []
    for line in index.blocks['RPG.Client.NetworkManager'].splitlines():
        signature = re.fullmatch(r'    (?:private|public) RPG.Client.GlobalDispatchData [A-Za-z0-9_]+\(([A-Za-z0-9_]+)\) \{\} // VA: 0x[0-9A-Fa-f]+, RVA: (0x[0-9A-Fa-f]+), Token: .*', line)
        if signature:
            address = int(signature[2], 16); body, digest = index.body(address)
            if any(op == 'call' and args == hex(index.base + setter) for _, op, args in body):
                candidates.append((signature[1], body, digest))
    global_type, global_parser, global_parser_sha = _one(candidates)
    region_type, list_offset = _one(re.findall(r'private (?:readonly )?Google.Protobuf.Collections.RepeatedField<([A-Za-z0-9_]+)> [A-Za-z0-9_]+ // Offset: (0x[0-9A-Fa-f]+)', index.blocks[global_type]))
    list_offset = int(list_offset, 16)
    _check(any(op == 'mov' and re.fullmatch(REGISTER + r', qword ptr \[' + REGISTER + r' \+ ' + hex(list_offset) + r'\]', args)
               for _, op, args in global_parser))
    name_offset = _offset(index.scopes[setter_scope], 'Name')
    name_field = _one(row[1] for row in _copies(global_parser) if row[3] == name_offset)
    setter_at = _one(i for i, (_, op, args) in enumerate(global_parser) if op == 'call' and args == hex(index.base + setter))
    pairs = [(row[3], row[1]) for row in _copies(global_parser[max(0, setter_at - 18):setter_at])]
    _check(len(pairs) == 2 and pairs[1][0] - pairs[0][0] == 8)
    region_writer = index.method(region_type, r'public void WriteTo\(Google\.Protobuf\.CodedOutputStream\)')
    region_body, region_sha = index.body(region_writer)
    region_fields = {key: _string_tag(region_body, offset) for key, offset in (
        ('name', name_field), ('primary_gateway', pairs[0][1]), ('alternate_gateway', pairs[1][1]))}
    global_writer = index.method(global_type, r'public void WriteTo\(Google\.Protobuf\.CodedOutputStream\)')
    global_ctor = index.method(global_type, r'(?:private|public) (?:static )?void \.cctor\(\)')
    (write, write_sha), (ctor, ctor_sha) = index.bodies([global_writer, global_ctor])
    read_at = _one(i for i, (_, op, args) in enumerate(write) if op == 'mov' and re.fullmatch(
        REGISTER + r', qword ptr \[' + REGISTER + r' \+ ' + hex(list_offset) + r'\]', args))
    slot = _one(int(match[1], 16) for _, op, args in write[read_at:read_at + 12]
                if op == 'mov' and (match := re.fullmatch(r'r8, qword ptr \[rax \+ (0x[0-9a-f]+)\]', args)))
    store_at = _one(i for i, (_, op, args) in enumerate(ctor) if op == 'mov' and re.fullmatch(
        r'qword ptr \[' + REGISTER + r' \+ ' + hex(slot) + r'\], rax', args))
    tag = _one(int(match[1], 0) for _, op, args in ctor[max(0, store_at - 10):store_at]
               if op == 'mov' and (match := re.fullmatch(r'ecx, ' + NUMBER, args)))
    _check(tag & 7 == 2 and tag > 0)

    bootstrap = {'native': index.prepared.receipt['identity']['files']['native']['name']}
    for role, owner, signature in [('config', 'RPG.Client.ClientStartupConfig', r'public static void Load\(\)'),
                                    ('version', 'RPG.GameCore.VersionData', r'public void LoadVersionDataFromBinary\(\)')]:
        method = index.method(owner, signature); body, _ = index.body(method); sizes = index.instruction_sizes(method); names = []
        for address, op, args in body:
            match = re.fullmatch(REGISTER + r', qword ptr \[rip ([+-]) (0x[0-9a-f]+)\]', args)
            if op == 'mov' and match:
                target = address + sizes[address] + (1 if match[1] == '+' else -1) * int(match[2], 16)
                value = index.literals.get(target, '')
                if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*\.bytes', value):
                    names.append(value)
        name = _one(set(names)); bootstrap[role] = _one(path for path in files if path == name or path.endswith('/' + name))
    result = {'native_file_md5': index.prepared.receipt['identity']['files']['native']['md5'],
              'bootstrap_files': bootstrap, 'client_schema': client_schema,
              'version_schema': _version_schema(index, version_body[0], readers), 'routes': routes,
              'global_dispatch': {'region_list_field': tag >> 3, 'region_fields': region_fields}}
    from .starrail_original_discovery import _description
    return _description(result)
