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
               and isinstance(operation, str) and re.fullmatch('[a-z][a-z0-9]{0,23}', operation)
               and isinstance(operands, str) and len(operands) <= 512)
        previous = address
    _check(value[-1][0] - value[0][0] <= 65536)
    return value


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
            # A scalar return cannot survive another call before its store.
            _check(not any(op == 'call' for _, op, _ in instructions[last + 1:i]))
        stores.append((int(match[3], 16), match[2], {'kind': kind, 'semantic': name}))
    _check(len(stores) == len(fields) and {offset for offset, _, _ in stores} == set(fields)
           and len({register for _, register, _ in stores}) == 1)
    return [field for _, _, field in stores]
