"""Owned, bounded joins from original runtime-usage records to method identities.

Only a supported native arithmetic shape supplies codec parameters. Original
libraries remain authenticated data; no client instruction is executed. Numeric
parameters and addresses belong to the private preparation cache, never a
release/version list in this module.
"""
import hashlib
import mmap
import re
import struct

from .starrail_metadata import _check, CANONICAL
from .starrail_native_routes import NUMBER, REGISTER, _one
from .starrail_native_description import _instructions, _writes

U32 = (1 << 32) - 1
U64 = (1 << 64) - 1

PARAMETERS = frozenset(('list_add', 'list_slot', 'list_mul', 'list_shift', 'list_key_add',
    'list_key_xor', 'list_bias', 'mul1', 'xor1', 'mul2', 'add1', 'shift1', 'mul3',
    'add2', 'shift2', 'pair_slot', 'pair_add', 'source_add', 'kind_shift', 'kind_max',
    'destination_xor', 'index_mask'))


def _parameters(value):
    _check(isinstance(value, dict) and set(value) == PARAMETERS
           and all(type(number) is int and 0 <= number <= U64 for number in value.values()))
    _check(all(value[name] <= U32 for name in ('list_add', 'list_key_add', 'list_key_xor',
        'list_bias', 'pair_add', 'source_add', 'destination_xor'))
        and all(0 < value[name] < 64 for name in ('list_shift', 'shift1', 'shift2'))
        and 0 < value['kind_shift'] < 32
        and value['kind_max'] == (1 << (32 - value['kind_shift'])) - 1
        and value['index_mask'] == (1 << value['kind_shift']) - 1
        and all(0 <= value[name] <= 0x204 and value[name] % 4 == 0 for name in ('list_slot', 'pair_slot')))
    return value


def _number(name):
    return '(?P<' + name + '>' + NUMBER[1:-1] + ')'


def _capture(rows, patterns):
    text = '\n'.join(op + ' ' + args for _, op, args in rows)
    matches = list(re.finditer('(?m)^' + '\n'.join(patterns) + '$', text))
    match = _one(matches)
    return {key: int(value, 0) for key, value in match.groupdict().items()}


def codec_parameters(rows):
    """Extract both index expressions and record joins, rejecting clobbers."""
    rows = _instructions(rows)
    n = _number
    lists = _capture(rows, [
        'mov eax, ' + n('list_add'),
        r'add eax, dword ptr \[rdx \+ ' + n('list_slot') + r'\]',
        r'mov esi, ecx', r'cdqe ',
        r'mov r14, qword ptr \[rip [+-] ' + NUMBER + r'\]', r'add rax, r14',
        r'movabs r12, ' + n('list_mul'), r'mov edi, dword ptr \[rax \+ rsi\*4\]',
        r'imul rsi, r12', 'shr rsi, ' + n('list_shift'), r'inc ecx', r'imul r12, rcx',
        'shr r12, ' + n('end_shift'), 'add esi, ' + n('list_key_add'),
        'xor esi, ' + n('list_key_xor'), r'lea ebx, \[rdi \+ rsi\]',
        'add r12d, ' + n('end_key_add'), 'xor r12d, ' + n('end_key_xor'),
        r'add r12d, dword ptr \[rax \+ rcx\*4\]', r'sub r12d, ebx'])
    bias = _capture(rows, [r'lea r13d, \[rdi \+ rsi\]', 'add r13d, ' + n('list_bias')])
    pairs = _capture(rows, [
        r'mov ecx, r13d', 'imul rax, rcx, ' + n('mul1'), 'xor rax, ' + n('xor1'),
        'imul rax, ' + n('mul2'), 'movabs rbx, ' + n('add1'), r'add rax, rbx',
        'shr rax, ' + n('shift1'), 'imul rdi, rax, ' + n('mul3'),
        'movabs rax, ' + n('add2'), r'add rdi, rax', 'shr rdi, ' + n('shift2'),
        r'mov eax, dword ptr \[rdx \+ ' + n('pair_slot') + r'\]',
        'mov ebx, ' + n('pair_add'), r'add eax, ebx', r'movsxd rsi, eax', r'add rsi, r14',
        r'mov eax, dword ptr \[rsi \+ rcx\*8 \+ 0x4\]', r'sub eax, edi',
        'add eax, ' + n('source_add'), r'mov ebx, eax', 'shr ebx, ' + n('kind_shift'),
        'cmp ebx, ' + n('kind_max'), 'ja ' + NUMBER,
        r'mov esi, dword ptr \[rsi \+ rcx\*8\]', 'mov ecx, ' + n('destination_xor'),
        r'xor esi, ecx', r'sub esi, edi', r'mov ecx, eax', 'and ecx, ' + n('index_mask')])
    _check(lists['list_shift'] == lists.pop('end_shift')
           and lists['list_key_add'] == lists.pop('end_key_add')
           and lists['list_key_xor'] == lists.pop('end_key_xor'))
    _check(all(0 < shift < 64 for shift in (lists['list_shift'], pairs['shift1'], pairs['shift2']))
           and 0 < pairs['kind_shift'] < 32
           and pairs['kind_max'] == (1 << (32 - pairs['kind_shift'])) - 1
           and pairs['index_mask'] == (1 << pairs['kind_shift']) - 1
           and all(0 <= value <= U64 for value in (lists | bias | pairs).values()))
    return _parameters(lists | bias | pairs)


def _rip(rows, at):
    address, _, args = rows[at]
    match = re.search(r'\[rip ([+-]) ' + NUMBER + r'\]', args)
    _check(match and at + 1 < len(rows))
    return rows[at + 1][0] + (1 if match[1] == '+' else -1) * int(match[2], 0)


def _file_rva(index, offset):
    return _one(start + offset - raw for start, size, raw in index.sections if raw <= offset < raw + size)


def registration(index):
    """Select the original registration through its fresh literal-table join.

    The instruction shape is the frozen software's registration description.
    Matching an opcode pattern alone never establishes the registration owner.
    """
    pattern = re.compile(rb'\x48\x8d\x05....\x48\x89\x05....\x48\x8d\x05....\x48\x89\x05....'
                         rb'\x48\x8d\x05....\x48\x89\x05....\x48\x8d\x05....\x48\x89\x05', re.S)
    selected = []
    _check(index.literals)
    literal_base = index.base + min(index.literals)
    with index.native.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for match in pattern.finditer(data):
            offset = match.start()
            try:
                table = _file_rva(index, offset + 35) + struct.unpack_from('<i', data, offset + 31)[0]
                global_slot = _file_rva(index, offset + 42) + struct.unpack_from('<i', data, offset + 38)[0]
                raw = index.read(table, 0x100)
            except (ValueError, struct.error):
                continue
            if literal_base in struct.unpack('<32Q', raw):
                selected.append({'rva': table, 'global': global_slot, 'bytes': raw,
                                 'sha256': hashlib.sha256(raw).hexdigest()})
    return _one(selected)


def _references(index, global_slot):
    pattern = re.compile(rb'[\x48-\x4f]\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', re.S)
    found = set()
    with index.native.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for start, size, raw in index.sections:
            for match in pattern.finditer(data, raw, raw + size):
                address = start + match.start() - raw
                if address + 7 + struct.unpack_from('<i', data, match.start() + 3)[0] == global_slot:
                    found.add(address)
    _check(0 < len(found) <= 4096)
    return sorted(found)


def _last_list(index, registration, initializer):
    found, visited = [], set()
    for address in _references(index, registration['global']):
        first, _ = index.native_bounds(address)
        if first in visited:
            continue
        visited.add(first)
        rows, _ = index.linear_body(first, unmanaged=True)
        for i in range(len(rows) - 5):
            if rows[i][1] != 'mov' or not rows[i][2].startswith('rax, qword ptr [rip '):
                continue
            if _rip(rows, i) != registration['global']:
                continue
            value = re.fullmatch('ecx, ' + NUMBER, rows[i + 1][2])
            slot = re.fullmatch(r'ecx, dword ptr \[rax \+ ' + NUMBER + r'\]', rows[i + 2][2])
            if (rows[i + 1][1] == 'mov' and value and rows[i + 2][1] == 'add' and slot
                    and rows[i + 3][1:] == ('cmp', 'ecx, 0xffffffff') and rows[i + 4][1] == 'je'
                    and rows[i + 5][1:] == ('call', hex(index.base + initializer))):
                offset, add = int(slot[1], 0), int(value[1], 0)
                _check(0 <= offset <= len(registration['bytes']) - 4 and offset % 4 == 0)
                found.append((struct.unpack_from('<I', registration['bytes'], offset)[0] + add) & U32)
    return _one(found)


def constructor(index, owner):
    """Bind every initialized IntPtr element, including explicit empty slots."""
    address = index.method(owner, r'private static void \.cctor\(\)')
    rows, digest = index.linear_body(address)
    candidates = []
    for i in range(1, len(rows) - 2):
        value = re.fullmatch('ecx, ' + NUMBER, rows[i - 1][2])
        if (rows[i - 1][1] == 'mov' and value and rows[i][1] == 'call'
                and re.fullmatch('0x[0-9a-f]+', rows[i][2])
                and rows[i + 1][1] == 'mov' and re.fullmatch(r'byte ptr \[rip [+-] ' + NUMBER + r'\], 0x1', rows[i + 1][2])
                and rows[i + 2][1] == 'jmp'):
            candidates.append((i, int(value[1], 0), int(rows[i][2], 16) - index.base))
    at, list_id, initializer = _one(candidates)
    flag = _rip(rows, at + 1)
    guard = _one(i for i in range(min(12, len(rows) - 1)) if rows[i][1] == 'cmp'
                 and re.fullmatch(r'byte ptr \[rip [+-] ' + NUMBER + r'\], 0x0', rows[i][2])
                 and rows[i + 1][1:] == ('je', hex(index.base + rows[at - 1][0])))
    _check(_rip(rows, guard) == flag and rows[0][0] <= int(rows[at + 2][2], 16) - index.base < rows[at - 1][0])
    allocation = _one(i for i in range(min(30, len(rows) - 1)) if rows[i][1] == 'mov'
                      and re.fullmatch('edx, ' + NUMBER, rows[i][2]) and rows[i + 1][1] == 'call')
    count = int(rows[allocation][2].split(', ')[1], 0)
    _check(0 < count <= 65536)
    elements = {}
    end = _one(i for i in range(allocation + 2, at) if rows[i][1] == 'ret')
    _check(all(not _writes(op, args, 'rax') and (op in {'cmp', 'test', 'bt'} or not re.fullmatch(REGISTER + r', rax', args))
               for _, op, args in rows[allocation + 2:end]))
    storage = []
    for i in range(allocation + 2, end):
        store = re.fullmatch(r'qword ptr \[rax \+ ' + NUMBER + r'\], (' + REGISTER + '|0x0)', rows[i][2])
        if rows[i][1] != 'mov' or not store:
            _check(not re.match(r'(?:byte|word|dword|qword|xmmword) ptr \[rax(?: \+|\])', rows[i][2]))
            final = re.fullmatch(r'qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\], rax', rows[i][2])
            if rows[i][1] == 'mov' and final:
                _check(i > 0 and rows[i - 1][1] == 'mov' and re.fullmatch(
                    re.escape(final[1]) + r', qword ptr \[rip [+-] ' + NUMBER + r'\]', rows[i - 1][2]))
                storage.append((_rip(rows, i - 1), int(final[2], 0)))
            continue
        offset = int(store[1], 0)
        _check(offset >= 0x20 and offset % 8 == 0 and (offset - 0x20) // 8 < count)
        element = (offset - 0x20) // 8
        _check(element not in elements)
        if store[2] == '0x0':
            elements[element] = None
        else:
            _check(i > 0 and rows[i - 1][1] == 'mov' and re.fullmatch(
                re.escape(store[2]) + r', qword ptr \[rip [+-] ' + NUMBER + r'\]', rows[i - 1][2]))
            elements[element] = index.base + _rip(rows, i - 1)
    _check(set(elements) == set(range(count)))
    return {'owner': owner, 'rva': address, 'sha256': digest, 'elements': elements,
            'list_id': list_id, 'initializer': initializer, 'storage': _one(storage)}


def method_usages(index, constructors):
    """Resolve required factory globals through original usage pairs only."""
    _check(constructors and len(constructors) <= 64)
    initializer = _one(set(value['initializer'] for value in constructors))
    rows, digest = index.linear_body(initializer, unmanaged=True)
    parameters = codec_parameters(rows)
    tables = registration(index)
    last = _last_list(index, tables, initializer)
    _check(0 <= last <= 2_000_000)
    caches = []
    for i in range(len(rows) - 3):
        slot = re.fullmatch(r'rcx, qword ptr \[rcx \+ ' + NUMBER + r'\]', rows[i + 2][2])
        if (rows[i][1] == 'call' and re.fullmatch('0x[0-9a-f]+', rows[i][2])
                and rows[i + 1][1] == 'mov' and rows[i + 1][2].startswith('rcx, qword ptr [rip ')
                and _rip(rows, i + 1) == tables['global'] and rows[i + 2][1] == 'mov' and slot
                and rows[i + 3][1:] == ('mov', 'qword ptr [rcx + rsi*8], rax')):
            offset = int(slot[1], 0)
            _check(0 <= offset <= len(tables['bytes']) - 8 and offset % 8 == 0)
            caches.append(struct.unpack_from('<Q', tables['bytes'], offset)[0])
    cache_base = _one(caches)
    wanted = {value for constructor in constructors for value in constructor['elements'].values() if value is not None}
    metadata = (index.prepared.inputs / CANONICAL['metadata']).read_bytes()
    _check(len(metadata) > 0x208)
    body = metadata[0x208:]
    prefix = metadata[:8]
    matches = []
    with index.native.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        begin = data.find(prefix); candidates = 0
        while begin >= 0:
            candidates += 1; _check(candidates <= 64)
            header = data[begin:begin + 0x208]
            try:
                mapping = decode_usages(header, body, parameters, last, cache_base, wanted, index.method_definitions)
                matches.append((mapping, _file_rva(index, begin)))
            except (ValueError, struct.error, IndexError):
                pass
            begin = data.find(prefix, begin + 1)
    mapping, header_rva = _one(matches)
    return mapping, {'initializer_sha256': digest, 'registration_sha256': tables['sha256'],
                     'header_rva': header_rva, 'parameters': parameters, 'last_list': last}


def decode_usages(header, body, p, last_list, cache_base, wanted, definitions):
    """Apply the described scalar expressions with explicit integer widths."""
    p = _parameters(p)
    _check(isinstance(header, bytes) and len(header) == 0x208 and isinstance(body, bytes)
           and len(body) <= 512 * 1024**2 and isinstance(wanted, (set, frozenset))
           and wanted and len(wanted) <= 65536
           and all(type(address) is int and 0 <= address <= U64 for address in wanted)
           and type(last_list) is int and 0 <= last_list <= 2_000_000
           and type(cache_base) is int and 0 <= cache_base <= U64
           and isinstance(definitions, dict))
    def u32(data, at):
        _check(0 <= at <= len(data) - 4)
        return struct.unpack_from('<I', data, at)[0]
    lists = (u32(header, p['list_slot']) + p['list_add']) & U32
    pairs = (u32(header, p['pair_slot']) + p['pair_add']) & U32
    _check(0 < lists <= len(body) - (last_list + 2) * 4 and 0 < pairs < len(body))
    def start(i):
        key = ((((i * p['list_mul']) & U64) >> p['list_shift']) + p['list_key_add']) & U32
        key ^= p['list_key_xor']
        return (u32(body, lists + i * 4) + key + p['list_bias']) & U32
    count = start(last_list + 1)
    _check(start(0) == 0 and 0 < count <= 2_000_000 and pairs + count * 8 <= len(body))
    previous = 0
    for i in range(1, last_list + 2):
        current = start(i)
        _check(previous <= current <= count)
        previous = current
    mapping = {}
    for i in range(count):
        value = (((i * p['mul1']) & U64) ^ p['xor1']) & U64
        value = (value * p['mul2'] + p['add1']) & U64
        value >>= p['shift1']
        key = ((value * p['mul3'] + p['add2']) & U64) >> p['shift2']
        key &= U32
        raw_destination, raw_source = struct.unpack_from('<II', body, pairs + i * 8)
        source = (raw_source - key + p['source_add']) & U32
        destination = ((raw_destination ^ p['destination_xor']) - key) & U32
        kind = source >> p['kind_shift']
        if kind not in (3, 6):
            continue
        address = cache_base + destination * 8
        if address not in wanted:
            continue
        # The normal method-definition usage kind is the frozen IL2CPP format
        # enum. A generic-method spec needs a separate proved binding contract.
        _check(kind == 3)
        method = source & p['index_mask']
        _check(method in definitions and (address not in mapping or mapping[address] == method))
        mapping[address] = method
    _check(set(mapping) == wanted)
    return mapping

def derive(index, bases=('RPG.GameCore.TaskConfig', 'RPG.GameCore.PredicateConfig')):
    """Discover typed registries without an obfuscated owner or reader name."""
    _check(isinstance(bases, (tuple, list)) and 0 < len(bases) <= 64 and len(set(bases)) == len(bases))
    root = index.blocks['RPG.GameCore.LevelGraphConfig']
    reader = _one(set(re.findall(r'public static void FromBinary\(([A-Za-z0-9_.]+), RPG\.GameCore\.LevelGraphConfig\)', root)))
    root_address = index.method('RPG.GameCore.LevelGraphConfig', r'public static void FromBinary\('
        + re.escape(reader) + r', RPG\.GameCore\.LevelGraphConfig\)')
    root_rows, _ = index.body(root_address)
    varuint = _one(set(int(args, 16) - index.base for _, operation, args in root_rows
        if operation == 'call' and re.fullmatch('0x[0-9a-f]+', args) and any(
            re.fullmatch(r'public static ulong [A-Za-z0-9_]+\(' + re.escape(reader) + r'\)', row['signature'])
            for row in index.methods.get(int(args, 16) - index.base, []))))
    values = {}
    for base in bases:
        _check(base in index.blocks)
        owners = set()
        pattern = r'internal static void [A-Za-z0-9_]+\(' + re.escape(reader) + ', ' + re.escape(base) + r'\)'
        for records in index.methods.values():
            for record in records:
                if re.fullmatch(pattern, record['signature']):
                    owner = record['owner'].split('#')[0]
                    if owner in index.blocks and re.search(r'^    private static IntPtr\[\] ', index.blocks[owner], re.M):
                        owners.add(owner)
        owner = _one(owners)
        values[base] = constructor(index, owner)
        _dispatcher(index, owner, reader, base, values[base]['storage'], varuint)
    mapping, evidence = method_usages(index, list(values.values()))
    registries = {}
    for base, value in values.items():
        entries = {}
        for number, address in value['elements'].items():
            if address is None:
                entries[number] = None
                continue
            method = mapping[address]
            _, record = index.method_definitions[method]
            _check(record['owner'] == _one(index.owners[value['owner']])
                   and re.fullmatch(r'private static ' + re.escape(base) + r' [A-Za-z0-9_]+\('
                                    + re.escape(reader) + r'\)', record['signature']))
            entries[number] = method
        registries[base] = entries
    return {'reader': reader, 'registries': registries, 'evidence': evidence,
            'constructors': {base: {'sha256': value['sha256'], 'entries': len(value['elements'])}
                             for base, value in values.items()}}

def _nonreturning(index, address):
    """Prove a callee traps on every reachable exit, without a symbol allowlist."""
    cache = getattr(index, '_usage_trap_functions', None)
    if cache is None:
        cache = index._usage_trap_functions = {}
    if address in cache:
        return cache[address]
    try:
        rows, _ = index.linear_body(address, unmanaged=True)
    except (AttributeError, ValueError):
        cache[address] = False
        return False
    by_address = {row[0]: i for i, row in enumerate(rows)}
    pending, visited, trapped = [0], set(), False
    while pending:
        at = pending.pop()
        if at in visited:
            continue
        visited.add(at)
        _check(len(visited) <= 8192)
        _, operation, args = rows[at]
        if operation in {'int3', 'ud2', 'hlt'} or operation == 'int' and args == '0x3':
            trapped = True
            continue
        if operation in {'ret', 'retf'}:
            cache[address] = False
            return False
        if operation.startswith('j') or operation.startswith('loop'):
            if not re.fullmatch('0x[0-9a-f]+', args) or int(args, 16) - index.base not in by_address:
                cache[address] = False
                return False
            pending.append(by_address[int(args, 16) - index.base])
        if operation != 'jmp':
            if at + 1 == len(rows):
                cache[address] = False
                return False
            pending.append(at + 1)
    cache[address] = trapped
    return trapped


def _dispatcher(index, owner, reader, base, storage, varuint):
    """Prove the original indexed factory call on every reaching CFG path."""
    from .starrail_native_description import _register
    signature = r'internal static void [A-Za-z0-9_]+\(' + re.escape(reader) + ', ' + re.escape(base) + r'\)'
    address = index.method(owner, signature)
    rows, _ = index.graph(address)
    positions = {row[0]: i for i, row in enumerate(rows)}
    edges = []
    for i, (_, operation, args) in enumerate(rows):
        successors = []
        if operation == 'call' and re.fullmatch('0x[0-9a-f]+', args) and _nonreturning(index, int(args, 16) - index.base):
            edges.append(successors)
            continue
        if operation.startswith('j') or operation.startswith('loop'):
            _check(re.fullmatch('0x[0-9a-f]+', args))
            target = int(args, 16) - index.base
            _check(target in positions)
            successors.append(positions[target])
        if operation not in {'jmp', 'ret', 'retf', 'int', 'int1', 'int3', 'ud2'} and i + 1 < len(rows):
            successors.append(i + 1)
        edges.append(successors)

    def transfer(at, incoming):
        state = dict(incoming)
        position, operation, args = rows[at]
        if operation == 'call':
            result = None
            if state.get('rcx') == ('reader',) and args == hex(index.base + varuint):
                result = ('index', position)
            elif state.get('rcx') == ('reader',) and args == 'qword ptr [rax + 0x8]' and state.get('rax', (None,))[0] == 'factory':
                result = ('object', position)
            for register in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                state.pop(register, None)
            if result:
                state['rax'] = result
            return state
        target = args.split(',')[0]
        value = None
        copy = re.fullmatch(r'([a-z0-9]+), ([a-z0-9]+)', args)
        if operation == 'mov' and copy:
            value = state.get(_register(copy[2]))
            if value and value[0] != 'index' and any(_register(register) != register for register in (copy[1], copy[2])):
                value = None
        load = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[rip [+-] ' + NUMBER + r'\]', args)
        if operation == 'mov' and load:
            value = ('global', _rip(rows, at))
        member = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[(' + REGISTER + r') \+ ' + NUMBER + r'\]', args)
        if operation == 'mov' and member:
            source = state.get(member[2])
            if source and source[0] == 'global' and (source[1], int(member[3], 0)) == storage:
                value = ('array', storage)
        element = re.fullmatch(r'(' + REGISTER + r'), qword ptr \[(' + REGISTER + r') \+ (' + REGISTER + r')\*8 \+ 0x20\]', args)
        if operation == 'mov' and element and state.get(element[2]) == ('array', storage) and state.get(element[3], (None,))[0] == 'index':
            value = ('factory', storage)
        for register in list(state):
            if _writes(operation, args, register):
                state.pop(register, None)
        if value:
            state[_register(target)] = value
        return state

    states = {0: {'rcx': ('reader',), 'rdx': ('output',)}}
    pending, iterations = [0], 0
    while pending:
        at = pending.pop(); iterations += 1; _check(iterations <= 262144)
        outgoing = transfer(at, states[at])
        for successor in edges[at]:
            joined = outgoing if successor not in states else {key: value for key, value in outgoing.items() if states[successor].get(key) == value}
            if successor not in states or states[successor] != joined:
                states[successor] = joined; pending.append(successor)
    calls, stores = [], []
    for at, (_, operation, args) in enumerate(rows):
        state = states.get(at, {})
        if operation == 'call' and not re.fullmatch('0x[0-9a-f]+', args):
            _check(args == 'qword ptr [rax + 0x8]' and state.get('rax') == ('factory', storage) and state.get('rcx') == ('reader',))
            calls.append(at)
        store = re.fullmatch(r'qword ptr \[(' + REGISTER + r')\], rax', args)
        if operation == 'mov' and store and state.get(store[1]) == ('output',):
            _check(state.get('rax', (None,))[0] == 'object')
            stores.append(at)
    _check(len(calls) == len(stores) == 1)
    return address
