"""Bounded Android DATA-IR adapter for the Star Rail reader contracts.

Original bytes are data. This adapter implements no metadata codec, runtime
build, client execution or provider activation.
"""
import hashlib
import json
from pathlib import Path
import re
import struct

from .android_x64_decoder import Instruction, PackagedX64Decoder
from . import starrail_metadata as metadata

U64 = (1 << 64) - 1
MEMORY = {1: 'byte', 2: 'word', 4: 'dword', 8: 'qword', 10: 'tbyte',
          16: 'xmmword', 32: 'ymmword', 64: 'zmmword'}
ALIASES = {'jz': 'je', 'jnz': 'jne', 'cmovz': 'cmove', 'cmovnz': 'cmovne',
           'setz': 'sete', 'setnz': 'setne', 'sal': 'shl'}
PREFIXES = {'lock', 'rep', 'repe', 'repne', 'bnd'}


class IRUnavailable(ValueError):
    """Missing runtime/operand semantics; never a publisher-format diagnosis."""
    code = 'starrail_ir_contract_unresolved'

    def __init__(self, component):
        self.component = component
        super().__init__('The Star Rail DATA-IR contract is unavailable: ' + component)


class IRInputError(ValueError):
    code = 'starrail_ir_input_invalid'


def _check(value):
    if not value:
        raise IRInputError('The bounded Star Rail DATA request did not validate.')


def _contract(value, component):
    if not value:
        raise IRUnavailable(component)


def _integer(value, low, high):
    _check(type(value) is int and low <= value <= high)
    return value


def _keys(value, names):
    _check(isinstance(value, dict) and set(value) == set(names))


def _register(instruction, value):
    name = instruction.reg_name(value)
    _contract(isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9]{0,15}', name), 'register-name')
    return name


def _full(name):
    aliases = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx',
               'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp'}
    return aliases.get(name, name[:-1] if re.fullmatch(r'r(?:[89]|1[0-5])d', name) else name)


def _encoding_prefixes(data):
    at = 0
    while at < len(data) and (data[at] in {0xf0, 0xf2, 0xf3, 0x2e, 0x36, 0x3e, 0x26, 0x64, 0x65, 0x66, 0x67}
                              or 0x40 <= data[at] <= 0x4f):
        at += 1
    return data[:at], data[at:]


def _mnemonic(instruction):
    _contract(type(instruction) is Instruction, 'instruction-type')
    words = instruction.mnemonic.split()
    if len(words) == 2 and words[0] in {'repz', 'repnz'}:
        words[0] = ('rep' if words[-1] == 'ret' else 'repe') if words[0] == 'repz' else 'repne'
    _contract(1 <= len(words) <= 2 and (len(words) == 1 or words[0] in PREFIXES)
              and re.fullmatch('[a-z][a-z0-9]{0,23}', words[-1]), 'mnemonic')
    operation = ALIASES.get(words[-1], words[-1])
    if operation in {'mov', 'movabs'}:
        operation = 'mov'
        if len(instruction.operands) == 2 and instruction.operands[1].type == 2 and instruction.operands[1].size == 8:
            prefixes, encoding = _encoding_prefixes(instruction.bytes)
            _contract(encoding and any(0x48 <= value <= 0x4f for value in prefixes)
                      and (0xb8 <= encoding[0] <= 0xbf and len(encoding) == 9 or encoding[0] == 0xc7),
                      'mov-immediate-encoding')
            operation = 'movabs' if 0xb8 <= encoding[0] <= 0xbf else 'mov'
    return ' '.join([*words[:-1], operation])


def _branch_operation(instruction):
    return _mnemonic(instruction).split()[-1]


def _memory(instruction, operand, operation):
    memory = operand.mem
    base = _register(instruction, memory.base) if memory.base else ''
    index = _register(instruction, memory.index) if memory.index else ''
    _contract(memory.scale in {0, 1, 2, 4, 8} and (not index or memory.scale in {1, 2, 4, 8}), 'memory-scale')
    terms = [base] if base else []
    if index:
        terms.append(index + ('*' + str(memory.scale) if memory.scale != 1 else ''))
    value = ' + '.join(terms)
    if not value:
        # The structured memory register determines RIP/EIP when present.
        # Absolute addresses need address-size semantics; a 67 prefix is
        # supported only when the actual supplied DATA has that prefix.
        prefixes, _ = _encoding_prefixes(instruction.bytes)
        value = hex(memory.disp & ((1 << (32 if 0x67 in prefixes else 64)) - 1))
    elif memory.disp:
        value += (' + ' if memory.disp > 0 else ' - ') + hex(abs(memory.disp))
    segment = _register(instruction, memory.segment) if memory.segment else ''
    _contract(not segment or segment in {'cs', 'ds', 'es', 'ss', 'fs', 'gs'}, 'memory-segment')
    segment = segment + ':' if segment in {'fs', 'gs'} else ''
    _contract(operand.size in MEMORY or operation == 'lea', 'memory-width')
    size = '' if operation == 'lea' else MEMORY[operand.size] + ' ptr '
    return size + segment + '[' + value + ']'


def normalize(instruction):
    """Render structured, typed operands; never consume decoder op_str."""
    mnemonic = _mnemonic(instruction); operation = mnemonic.split()[-1]
    _contract(type(instruction.size) is int and 1 <= instruction.size <= 15
              and len(instruction.bytes) == instruction.size, 'instruction-size')
    _, encoding = _encoding_prefixes(instruction.bytes)
    _contract(encoding and encoding[0] not in {0x62, 0xc4, 0xc5}, 'vector-encoding-not-represented')
    operands = []
    for operand in instruction.operands:
        if operand.type == 1:
            operands.append(_register(instruction, operand.reg))
        elif operand.type == 2:
            _contract(operand.size in {1, 2, 4, 8} and type(operand.imm) is int, 'immediate-width')
            bits = 64 if operation.startswith(('j', 'loop')) or operation == 'call' else operand.size * 8
            operands.append(hex(operand.imm & ((1 << bits) - 1)))
        elif operand.type == 3:
            operands.append(_memory(instruction, operand, operation))
        else:
            raise IRUnavailable('operand-kind')
    # Iced's default formatter emits this exact IMUL pseudo-operation.
    if operation == 'imul' and len(instruction.operands) == 3 and all(
            op.type == 1 for op in instruction.operands[:2]) and instruction.operands[0].reg == instruction.operands[1].reg:
        operands.pop(1)
    if re.fullmatch(r'(?:stos|lods|scas)[bwdq]', operation):
        memory_operands = [text for text, op in zip(operands, instruction.operands) if op.type == 3]
        _contract(len(memory_operands) == 1, 'implicit-operand-format')
        operands = memory_operands
    return [instruction.address, mnemonic, ', '.join(operands)]


def _flow(instruction):
    operation = _branch_operation(instruction)
    groups = set(instruction.groups)
    if operation in {'xbegin', 'xabort', 'xend'}:
        raise IRUnavailable('transactional-control-flow')
    if operation in {'int', 'int1', 'int3', 'ud0', 'ud1', 'ud2', 'hlt', 'syscall', 'sysenter', 'sysret', 'sysexit'} or groups & {4, 5, 6}:
        return 'trap'
    if operation.startswith('ret'):
        _contract(operation == 'ret' and 3 in groups, 'return-flow')
        return 'return'
    if operation == 'call':
        _contract(2 in groups and len(instruction.operands) == 1, 'call-flow')
        return 'call' if instruction.operands[0].type == 2 else 'indirect-call'
    if operation.startswith(('j', 'loop')):
        _contract(bool(groups & {1, 7}) and len(instruction.operands) == 1, 'branch-flow')
        if instruction.operands[0].type != 2:
            _contract(operation == 'jmp', 'indirect-conditional-flow')
            return 'indirect-branch'
        return 'branch' if operation == 'jmp' else 'conditional'
    _contract(not groups & {1, 2, 3, 7}, 'unclassified-control-flow')
    return 'next'


def _target(instruction):
    _contract(len(instruction.operands) == 1 and instruction.operands[0].type == 2, 'direct-target')
    return instruction.operands[0].imm & U64


def _decode(decoder, data, address, count=0):
    try:
        result = list(decoder.disasm(data, address, count))
    except (ValueError, AttributeError, TypeError) as error:
        raise IRUnavailable('decoder-response') from error
    offset = 0
    for instruction in result:
        _contract(type(instruction) is Instruction and instruction._decoder is decoder, 'decoder-source-binding')
        normalize(instruction)
        _contract(instruction.address == address + offset and instruction.bytes == data[offset:offset + instruction.size], 'decoded-byte-binding')
        offset += instruction.size
    _check(result and (count == 1 and len(result) == 1
                      or count != 1 and len(result) <= 8192 and offset == len(data)))
    return result


def _switch(path, data, address):
    _contract(len(path) >= 6, 'indirect-branch-shape')
    guard, fallback, pointer, load, add, jump = path[-6:]
    g, p, l, a, j = (item.operands for item in (guard, pointer, load, add, jump))
    _contract([_branch_operation(v) for v in path[-6:]] == ['cmp', 'ja', 'lea', 'movsxd', 'add', 'jmp']
        and len(g) == 2 and g[0].type == 1 and g[0].size == 4 and g[1].type == 2
        and len(p) == 2 and p[0].type == 1 and p[0].size == 8 and p[1].type == 3
        and _register(pointer, p[1].mem.base) == 'rip' and not p[1].mem.index
        and len(l) == 2 and l[0].type == 1 and l[0].size == 8 and l[1].type == 3
        and _register(load, l[1].mem.base) == _register(pointer, p[0].reg)
        and _register(load, l[1].mem.index) == _full(_register(guard, g[0].reg))
        and l[1].mem.scale == 4 and l[1].mem.disp == 0
        and len(a) == 2 and all(op.type == 1 for op in a)
        and a[0].reg == l[0].reg and a[1].reg == p[0].reg
        and len(j) == 1 and j[0].type == 1 and j[0].reg == l[0].reg,
        'indirect-branch-shape')
    maximum = g[1].imm; table = pointer.address + pointer.size + p[1].mem.disp
    _check(0 <= maximum <= 255 and address <= table <= address + len(data)
           and (maximum + 1) * 4 <= address + len(data) - table)
    targets = []
    for index in range(maximum + 1):
        relative, = struct.unpack_from('<i', data, table - address + index * 4)
        target = table + relative
        _check(address <= target < address + len(data)); targets.append(target)
    return targets, (pointer.address, jump.address)


def _range(decoder, data, address, flow):
    if not flow:
        # One sentinel establishes an over-limit range without requesting all
        # 65,536 possible one-byte instructions/operand records from JNI.
        return _decode(decoder, data, address, 8193)
    pending, decoded, occupied, branch_targets, guarded = [address], {}, set(), set(), []
    end = address + len(data)
    while pending:
        at = pending.pop(); path = []
        while at not in decoded:
            _check(address <= at < end and at not in occupied and len(decoded) < 8192)
            instruction, = _decode(decoder, data[at-address:], at, 1)
            following = at + instruction.size
            positions = set(range(at, following)); _check(not positions & occupied)
            occupied.update(positions); decoded[at] = instruction; path.append(instruction)
            kind = _flow(instruction)
            if kind == 'indirect-branch':
                targets, region = _switch(path, data, address)
                pending.extend(targets); branch_targets.update(targets); guarded.append(region); break
            if kind in {'return', 'trap'}:
                break
            if kind in {'branch', 'conditional'}:
                target = _target(instruction); branch_targets.add(target)
                if address <= target < end:
                    pending.append(target)
                else:
                    _check(kind == 'branch')
                if kind == 'branch':
                    break
            _check(following < end); at = following
    _check(all(not any(first <= target <= last for target in branch_targets) for first, last in guarded))
    return [decoded[at] for at in sorted(decoded)]


def _ranges(source, values, decoder):
    _keys(values, {'ranges'}); ranges = values['ranges']
    _check(isinstance(ranges, list) and 1 <= len(ranges) <= 4096)
    size = source.seek(0, 2); _check(0 < size <= 1024**3)
    specs, total = [], 0
    for value in ranges:
        _check(isinstance(value, dict))
        _keys(value, {'offset', 'address', 'bytes'} | ({'control_flow'} if 'control_flow' in value else set()))
        offset = _integer(value['offset'], 0, size); count = _integer(value['bytes'], 1, 65536)
        address = _integer(value['address'], 0, U64)
        _check(count <= size - offset and count <= U64 - address)
        flow = value.get('control_flow', False); _check(type(flow) is bool and ('control_flow' not in value or flow))
        total += count; _check(total <= 16 * 1024**2); specs.append((offset, count, address, flow))
    result, instructions = [], 0
    for offset, count, address, flow in specs:
        source.seek(offset); data = source.read(count); _check(len(data) == count)
        rows = _range(decoder, data, address, flow)
        instructions += len(rows); _check(instructions <= 262144)
        result.append([normalize(row) for row in rows])
    return result


def _graph(source, entry, decoder):
    base, sections, table, count = metadata._graph_pe(source)
    _check(base <= U64 - ((1 << 32) - 1))
    previous = -1
    for at in range(0, count, 4096):
        source.seek(table + at * 12); rows = source.read(min(4096, count-at) * 12)
        _check(len(rows) == min(4096, count-at) * 12)
        for first, last, unwind in struct.iter_unpack('<III', rows):
            _check(previous < first < last and unwind > 0); previous = first
    def mapping(rva, length, code=False):
        matches = [off + rva - first for first, size, off, executable in sections
                   if first <= rva < rva + length <= first + size and (not code or executable)]
        _check(len(matches) == 1); return matches[0]
    def owner(at):
        lo, hi = 0, count
        while lo < hi:
            middle = (lo + hi) // 2; source.seek(table + middle * 12)
            first, = struct.unpack('<I', source.read(4))
            if first <= at: lo = middle + 1
            else: hi = middle
        _check(lo > 0); source.seek(table + (lo - 1) * 12)
        first, last, unwind = struct.unpack('<III', source.read(12))
        _check(first <= at < last and last - first <= 32768 and unwind > 0)
        return first, last, unwind
    _check(owner(entry)[0] == entry)
    regions, decoded, occupied, links, calls, returns = {}, {}, set(), {}, {}, set()
    pending, total = [entry], 0
    while pending:
        at = pending.pop()
        if at in decoded: continue
        _check(at not in occupied and len(decoded) < 8192)
        first, last, unwind = owner(at)
        if first not in regions:
            length = last - first
            _check(at == first and len(regions) < 16 and length <= 32768 - total
                and not any(start < last and first < row[0] for start, row in regions.items()))
            offset = mapping(first, length, True); mapping(unwind, 1)
            source.seek(offset); data = source.read(length); _check(len(data) == length)
            regions[first] = last, unwind, offset, data; total += length
        data = regions[first][3]
        instruction, = _decode(decoder, data[at-first:], base + at, 1)
        following = at + instruction.size; positions = set(range(at, following))
        _check(following <= last and not positions & occupied); occupied.update(positions)
        decoded[at] = instruction; kind = _flow(instruction); successors = set()
        if kind == 'return': returns.add(at)
        elif kind in {'branch', 'conditional'}:
            target = _target(instruction) - base; _check(0 <= target < 1 << 32); successors.add(target)
        elif kind in {'call', 'indirect-call'}:
            calls[at] = ('direct', _target(instruction)) if kind == 'call' else ('indirect', None)
        elif kind != 'next': raise IRUnavailable('native-graph-control-flow')
        if kind in {'next', 'call', 'indirect-call', 'conditional'}:
            _check(following < last); successors.add(following)
        links[at] = successors; pending.extend(sorted(successors, reverse=True))
    _check(returns and all(target in decoded for values in links.values() for target in values))
    return {'schema': 'proxy-starrail-native-graph-v1', 'image_base': base, 'entry_rva': entry,
        'regions': [{'rva': start, 'bytes': len(data), 'offset': offset, 'unwind_rva': unwind,
                     'sha256': hashlib.sha256(data).hexdigest()} for start, (last, unwind, offset, data) in sorted(regions.items())],
        'instructions': [normalize(row) + [row.size] for at, row in sorted(decoded.items())],
        'edges': [[base + at, [base + target for target in sorted(values)]] for at, values in sorted(links.items())],
        'calls': [[base + at, kind, target] for at, (kind, target) in sorted(calls.items())],
        'returns': [base + at for at in sorted(returns)]}


class AndroidIR:
    """Helper.run-compatible IR operations; metadata remains unavailable."""
    def __init__(self, decoder):
        self._require_decoder(decoder)
        self._decoder = decoder
        try:
            metadata._no_links(Path(__file__))
            logic = metadata._hash(Path(__file__))
        except (OSError, ValueError) as error:
            raise IRUnavailable('adapter-source-binding') from error
        self.identity = metadata._identity({'schema': 'starrail-android-data-ir-v1',
            'decoder': decoder.proof(), 'logic': logic})

    @staticmethod
    def _require_decoder(decoder):
        _contract(type(decoder) is PackagedX64Decoder and decoder.verified, 'verified-Android-provider')
        try: decoder.require_android()
        except (ValueError, ImportError, AttributeError, TypeError) as error:
            raise IRUnavailable('verified-Android-provider') from error

    @classmethod
    def from_native(cls, native):
        try: return cls(PackagedX64Decoder.from_native(native))
        except (ValueError, ImportError, AttributeError, TypeError) as error:
            if isinstance(error, IRUnavailable): raise
            raise IRUnavailable('verified-Android-provider') from error

    def run(self, operation, *paths, work):
        if operation not in {'disassemble', 'native-graph'}:
            raise IRUnavailable('metadata-reader-not-implemented')
        self._require_decoder(self._decoder)
        _check(len(paths) == 3 and all(Path(path).is_absolute() for path in paths) and Path(work).is_absolute())
        source, request, output = map(Path, paths); work = Path(work)
        for path in (source, request, output, work): metadata._no_links(path)
        _check(source.is_file() and request.is_file() and work.is_dir() and request.parent == work
               and output.parent == work and not output.exists() and request.stat().st_size <= 1024**2)
        def unique(pairs):
            value = {}
            for key, item in pairs:
                _check(key not in value); value[key] = item
            return value
        values = json.loads(request.read_bytes(), object_pairs_hook=unique,
                            parse_constant=lambda _: _check(False))
        with source.open('rb') as stream:
            if operation == 'disassemble': result = _ranges(stream, values, self._decoder)
            else:
                _keys(values, {'entry_rva'}); entry = _integer(values['entry_rva'], 0, (1 << 32) - 1)
                result = _graph(stream, entry, self._decoder)
        if operation == 'native-graph': metadata._native_graph(result, source, entry)
        encoded = json.dumps(result, separators=(',', ':')).encode()
        _check(len(encoded) <= (8 if operation == 'native-graph' else 128) * 1024**2)
        with output.open('xb') as stream: stream.write(encoded)
