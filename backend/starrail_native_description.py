"""Bounded, data-only description derivation from original native evidence.

The caller supplies decoded x64 instructions and matching managed metadata.
Acquiring, authenticating and disassembling those inputs is a separate helper
contract; importing this module never loads a game library or executes code.
There are no release numbers, native addresses, field offsets or key constants
here. Unsupported or ambiguous evidence raises ValueError before publication.
"""
from collections import Counter
import re


def _check(condition):
    if not condition:
        raise ValueError('Unsupported or ambiguous original native description.')


def _instructions(value):
    _check(isinstance(value, (list, tuple)) and 0 < len(value) <= 8192)
    previous = -1
    for row in value:
        _check(isinstance(row, (list, tuple)) and len(row) == 3)
        address, operation, operands = row
        _check(type(address) is int and previous < address < 1 << 64
               and isinstance(operation, str)
               and re.fullmatch(r'(?:(?:lock|rep|repe|repne|bnd) )?[a-z][a-z0-9]{0,23}', operation)
               and isinstance(operands, str) and len(operands) <= 512)
        previous = address
    _check(value[-1][0] - value[0][0] <= 65536)
    return value


def _register(value):
    aliases = {'eax': 'rax', 'ax': 'rax', 'al': 'rax', 'ah': 'rax',
               'ebx': 'rbx', 'bx': 'rbx', 'bl': 'rbx', 'bh': 'rbx',
               'ecx': 'rcx', 'cx': 'rcx', 'cl': 'rcx', 'ch': 'rcx',
               'edx': 'rdx', 'dx': 'rdx', 'dl': 'rdx', 'dh': 'rdx',
               'esi': 'rsi', 'si': 'rsi', 'sil': 'rsi', 'edi': 'rdi', 'di': 'rdi', 'dil': 'rdi',
               'ebp': 'rbp', 'bp': 'rbp', 'bpl': 'rbp', 'esp': 'rsp', 'sp': 'rsp', 'spl': 'rsp'}
    match = re.fullmatch(r'(r(?:[89]|1[0-5]))[dwb]', value)
    return aliases.get(value, match[1] if match else value)


def _writes(operation, operands, register):
    """Conservative x64 register effects for supported read/store joins."""
    operation = operation.split()[-1]
    register = _register(register)
    parts = [part.strip() for part in operands.split(',')]
    if operation == 'call':
        return register in {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}
    if operation in {'div', 'idiv', 'mul', 'cmpxchg8b', 'cmpxchg16b'} or operation == 'imul' and len(parts) == 1:
        return register in {'rax', 'rdx'}
    if operation in {'cpuid', 'rdtscp'}:
        return register in {'rax', 'rbx', 'rcx', 'rdx'}
    if operation in {'rdtsc', 'rdmsr', 'cqo', 'cdq', 'cwd'}:
        return register in {'rax', 'rdx'}
    if operation in {'syscall', 'sysenter', 'int', 'int1', 'int3'}:
        return True
    if operation in {'enter', 'leave'}:
        return register in {'rsp', 'rbp'}
    if operation in {'cbw', 'cwde', 'cdqe', 'lahf'} or operation.startswith('lods'):
        return register == 'rax'
    if operation.startswith('cmpxchg') and register == 'rax':
        return True
    if operation in {'xchg', 'xadd'}:
        return any(_register(part) == register for part in parts)
    if operation in {'cmp', 'test', 'bt', 'push', 'nop', 'ret', 'sahf'} or operation.startswith('j'):
        return False
    if operation.startswith('loop'):
        return register == 'rcx'
    if operation.startswith(('stos', 'scas')):
        return register == 'rdi'
    if operation in {'movsb', 'movsw', 'movsq', 'cmpsb', 'cmpsw', 'cmpsq'} or (
            operation in {'movsd', 'cmpsd'} and not operands.startswith('xmm')):
        return register in {'rsi', 'rdi'}
    return bool(parts) and _register(parts[0]) == register


def primitive_readers(instructions, methods, image_base):
    """Join direct calls to no-argument string/uint/bool metadata signatures.

    ``methods`` maps RVAs to lists of {owner, signature} records. The unique
    most-used owner supplies the binary reader; ties and mixed signatures fail.
    Returned call targets use the absolute addresses in decoded instructions.
    """
    _check(isinstance(methods, dict) and type(image_base) is int and 0 <= image_base < 1 << 64)
    calls = []
    for _, operation, operands in _instructions(instructions):
        if operation != 'call' or not re.fullmatch('0x[0-9a-f]+', operands):
            continue
        target = int(operands, 16)
        records = methods.get(target - image_base, [])
        _check(isinstance(records, list) and len(records) <= 64)
        candidates = set()
        for record in records:
            _check(isinstance(record, dict) and set(record) == {'owner', 'signature'}
                   and all(isinstance(v, str) and len(v) <= 2048 for v in record.values()))
            match = re.fullmatch(r'public (string|uint|bool) [A-Za-z0-9_]+\(\)', record['signature'])
            if match:
                candidates.add((record['owner'], target,
                                {'string': 'string', 'uint': 'u32', 'bool': 'bool'}[match[1]]))
        _check(len(candidates) <= 1)
        calls.extend(candidates)
    counts = Counter(owner for owner, _, _ in calls)
    _check(bool(counts))
    owner, count = counts.most_common(1)[0]
    _check(count > 1 and sum(n == count for n in counts.values()) == 1)
    result = {}
    for candidate, target, kind in calls:
        if candidate == owner:
            _check(target not in result or result[target] == kind)
            result[target] = kind
    _check({'string', 'u32'} <= set(result.values()))
    return result


def client_schema(metadata_block, instructions, readers):
    """Derive every public ClientStartupConfig field in serialization order.

    Offsets/types/names come from the matching metadata block; call/store order
    comes from its native Deserialize method. Arrays require a count read,
    allocation call, and subsequent string-reader loop evidence. This recognizes
    the evidenced x64 family only, not arbitrary native control flow.
    """
    _check(isinstance(metadata_block, str) and 0 < len(metadata_block) <= 1024**2)
    _check(isinstance(readers, dict) and 0 < len(readers) <= 64
           and all(type(k) is int and 0 <= k < 1 << 64
                   and isinstance(v, str) and v in {'string', 'u32', 'bool'} for k, v in readers.items()))
    fields = {}
    for line in metadata_block.splitlines():
        if not line.startswith('    public ') or ' // Offset:' not in line:
            continue
        match = re.fullmatch(r'    public (string\[\]|string|int|uint|bool) '
                             r'([A-Za-z][A-Za-z0-9_]*) // Offset: (0x[0-9A-Fa-f]+), Token: 0x[0-9A-Fa-f]+', line)
        _check(match is not None)
        offset = int(match[3], 16)
        _check(offset not in fields and 0 < offset <= 65536 and len(fields) < 256
               and match[2] not in {name for _, name in fields.values()})
        fields[offset] = (match[1], match[2])
    _check(bool(fields))
    instructions = _instructions(instructions)
    calls = [(i, readers[int(operands, 16)]) for i, (_, operation, operands) in enumerate(instructions)
             if operation == 'call' and re.fullmatch('0x[0-9a-f]+', operands)
             and int(operands, 16) in readers]
    stores = []
    for i, (_, operation, operands) in enumerate(instructions):
        match = re.fullmatch(r'(qword|dword|byte) ptr \[(r[a-z0-9]+) \+ (0x[0-9a-f]+)\], (rax|eax|al)', operands)
        if operation != 'mov' or not match or int(match[3], 16) not in fields:
            continue
        dtype, name = fields[int(match[3], 16)]
        preceding = [(j, kind) for j, kind in calls if j < i]
        _check(bool(preceding))
        last, kind = preceding[-1]
        if dtype == 'string[]':
            _check(kind == 'u32' and match[1] == 'qword' and match[4] == 'rax')
            _check(any(op == 'call' for _, op, _ in instructions[last + 1:i]))
            following = [(j, k) for j, k in calls if j > i]
            _check(bool(following) and following[0][1] == 'string')
            end = next((j for j, k in following if k == 'u32'), len(instructions))
            loop = instructions[following[0][0]:end]
            _check(any(op == 'mov' and re.fullmatch(
                r'qword ptr \[r[a-z0-9]+ \+ r[a-z0-9]+\*8 \+ 0x[0-9a-f]+\], rax', args)
                       for _, op, args in loop)
                   and any(op in {'jne', 'jb', 'jl'} and re.fullmatch('0x[0-9a-f]+', args)
                           for _, op, args in loop))
            kind = 'string_array'
        else:
            _check(kind == {'string': 'string', 'int': 'u32', 'uint': 'u32', 'bool': 'bool'}[dtype])
            width, register = {'string': ('qword', 'rax'), 'int': ('dword', 'eax'),
                               'uint': ('dword', 'eax'), 'bool': ('byte', 'al')}[dtype]
            _check((match[1], match[4]) == (width, register))
            _check(not any(_writes(op, args, 'rax') for _, op, args in instructions[last + 1:i]))
        stores.append((int(match[3], 16), match[2], {'kind': kind, 'semantic': name}, i))
    _check(len(stores) == len(fields) and {offset for offset, _, _, _ in stores} == set(fields)
           and len({register for _, register, _, _ in stores}) == 1)
    receiver = stores[0][1]
    _check(calls and not any(_writes(op, args, receiver)
                            for _, op, args in instructions[calls[0][0] + 1:stores[-1][3]]))
    return [field for _, _, field, _ in stores]


def string_key(instructions):
    """Describe the evidenced masked-index scalar string codec, data only.

    The caller must establish this function's ownership through original native
    references. This recognizes a strict instruction/data-flow shape and returns
    its operands, without a known-key list or a claim of general decompilation.
    Metadata header/record layouts and helper lifecycle remain separate inputs.
    """
    instructions = _instructions(instructions)
    registers = {'r' + name for name in ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp')}
    registers.update(f'r{i}' for i in range(8, 16))
    aliases = dict(zip(('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'),
                       ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp')))
    aliases.update({f'r{i}d': f'r{i}' for i in range(8, 16)})

    def literal(row):
        _, operation, operands = row
        match = re.fullmatch(r'([a-z0-9]+), (0x[0-9a-f]+|[0-9]+)', operands)
        if operation in {'mov', 'movabs'} and match:
            value = int(match[2], 0)
            _check(value < 1 << 64)
            return match[1], value
        return None

    seeds, steps = [], []
    for i in range(len(instructions) - 3):
        multiplier = literal(instructions[i])
        if multiplier is None or multiplier[0] not in registers:
            continue
        _, operation, operands = instructions[i + 1]
        multiply = re.fullmatch(multiplier[0] + r', ([a-z0-9]+)', operands)
        if operation != 'imul' or not multiply or multiply[1] not in registers:
            continue
        addition = literal(instructions[i + 2])
        if addition and addition[0] in registers and tuple(instructions[i + 3][1:]) == (
                'add', f'{addition[0]}, {multiplier[0]}'):
            seeds.append((i, multiplier[1], addition[1], addition[0], multiply[1]))
        # Scalar tail advances the same seed by step * already-read blocks.
        _, operation, operands = instructions[i + 2]
        advance = re.fullmatch(r'([a-z0-9]+), ' + multiplier[0], operands)
        if operation == 'add' and advance and advance[1] in registers:
            steps.append((multiplier[1], advance[1]))
    _check(len(seeds) == 1)
    at, multiplier, addition, key_register, index_register = seeds[0]
    step_values = {value for value, target in steps if target == key_register}
    _check(len(step_values) == 1 and at >= 5)
    prefix = instructions[at - 5:at]
    negative, positive = literal(prefix[1]), literal(prefix[2])
    _check(negative is not None and positive is not None
           and negative[0] in aliases and positive[0] in aliases)
    index = re.fullmatch(r'([a-z0-9]+), \1', prefix[0][2])
    _check(prefix[0][1] == 'test' and index is not None and index[1] in aliases
           and aliases[positive[0]] == index_register)
    _check(tuple(prefix[3][1:]) == ('cmovs', f'{positive[0]}, {negative[0]}')
           and tuple(prefix[4][1:]) == ('and', f'{positive[0]}, {index[1]}'))
    for mask in (negative[1], positive[1]):
        _check(0 < mask < 1 << 31 and mask & (mask + 1) == 0)
        _check(any(operation == 'shr' and re.fullmatch(
            r'[a-z0-9]+, (?:' + hex(mask.bit_length()) + '|' + str(mask.bit_length()) + ')', operands)
                   for _, operation, operands in instructions))
    _check(negative[1] < positive[1] and multiplier != 0 and next(iter(step_values)) != 0)
    return {'negative_index_mask': negative[1], 'positive_index_mask': positive[1],
            'multiply': multiplier, 'add': addition, 'step': next(iter(step_values))}
