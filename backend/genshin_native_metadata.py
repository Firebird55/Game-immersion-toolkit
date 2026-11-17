"""Current-input metadata ownership; no game addresses or arithmetic keys are pinned.

The retained MHY header, packed identifier and record layouts are format roles.
Their current pointer owners and read operands must come from the supplied
original PE. This module never executes client code or imports a game library.
"""
from dataclasses import dataclass
import hashlib
import re
import struct

from .genshin_native_x64 import Image, Constants, Definitions, decoder, register, _check
from .genshin_native_x64 import CS_OP_REG, CS_OP_IMM, CS_OP_MEM
from . import genshin_native_expression as indexed

HEADER_SIZE = 0x210
MAX_METADATA = 256 * 1024**2
MASK64 = (1 << 64) - 1
# Positions and strides describe this metadata format, not a game revision.
HEADER_ROLES = {0x34: 'type_offset', 0x188: 'type_byte_length', 0x48: 'method_offset',
                0x1c8: 'field_offset', 0xc0: 'parameter_offset'}
TYPE_STRIDE = 70


def root(instruction, operand):
    return register(instruction.reg_name(operand.reg))[0]


def pointer(instruction, operand, image):
    _check(operand.type == CS_OP_MEM and instruction.reg_name(operand.mem.base) == 'rip'
           and not operand.mem.index)
    return instruction.address + instruction.size + operand.mem.disp - image.base


def owns_global_pointer(image, seq, instruction, memory, global_rva, definitions=None):
    """All reaching definitions of a native memory base own the same global."""
    if memory.index or not memory.base:
        return False
    definitions = definitions or Definitions(seq)
    by_address = {i.address: i for i in seq}

    def owned(address, name, active, depth):
        _check(depth <= 16, 'Native pointer provenance exceeds its bound.')
        key = address, name
        if key in active:
            return False
        incoming = definitions.before(address, name)
        if not incoming or None in incoming:
            return False
        for at in incoming:
            ins = by_address[at]
            if not (ins.mnemonic == 'mov' and len(ins.operands) == 2
                    and ins.operands[0].type == CS_OP_REG and ins.operands[0].size == 8):
                return False
            source = ins.operands[1]
            if source.type == CS_OP_MEM:
                if not (ins.reg_name(source.mem.base) == 'rip' and source.size == 8
                        and pointer(ins, source, image) == global_rva):
                    return False
            elif source.type == CS_OP_REG and source.size == 8:
                if not owned(ins.address, root(ins, source), active | {key}, depth + 1):
                    return False
            else:
                return False
        return True

    return owned(instruction.address, register(instruction.reg_name(memory.base))[0], set(), 0)


def rip_references(image, targets):
    """Candidate RIP references, subsequently decoded and owned by callers."""
    _check(isinstance(targets, (set, frozenset)) and 0 < len(targets) <= 128)
    results = []
    for name in image.executable_sections:
        rva, _virtual, raw, size = image.sections[name]
        for match in re.finditer(rb'[\x48\x4c][\x8b\x8d][\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)',
                                 image.data[raw:raw + size], re.S):
            at = rva + match.start()
            target = at + 7 + struct.unpack('<i', match[1])[0]
            if target in targets:
                results.append({'rva': at, 'target': target, 'function': image.function_start(at)})
                _check(len(results) <= 100_000)
    return results


@dataclass(frozen=True)
class HeaderOwner:
    header_offset: int
    header_rva: int
    global_rva: int
    initializer_rva: int
    initializer_sha256: str


def header_owner(image, metadata):
    _check(isinstance(image, Image) and isinstance(metadata, bytes)
           and HEADER_SIZE < len(metadata) <= MAX_METADATA and metadata[:4] == b'MHY\0')
    candidates = {}
    for match in re.finditer(b'MHY\0', image.data):
        _check(len(candidates) < 128, 'Too many native metadata header candidates.')
        at = match.start()
        sections = [(rva + at - raw) for rva, _virtual, raw, size in image.sections.values()
                    if raw <= at and at + HEADER_SIZE <= raw + size]
        if len(sections) == 1:
            candidates[sections[0]] = at
    _check(candidates)
    owners = []
    for ref in rip_references(image, set(candidates)):
        try:
            seq = image.leaf(ref['rva'], 32)
        except ValueError:
            continue
        if len(seq) != 3 or [i.mnemonic for i in seq] != ['lea', 'mov', 'ret']:
            continue
        a, b, c = seq
        if not (a.operands[0].type == CS_OP_REG and a.operands[1].type == CS_OP_MEM
                and a.reg_name(a.operands[1].mem.base) == 'rip'
                and b.operands[0].type == CS_OP_MEM
                and b.reg_name(b.operands[0].mem.base) == 'rip'
                and b.operands[1].type == CS_OP_REG
                and b.operands[1].reg == a.operands[0].reg):
            continue
        target = pointer(a, a.operands[1], image)
        _check(target == ref['target'])
        size = c.address + c.size - a.address
        start = image.offset(ref['rva'], size)
        owners.append(HeaderOwner(candidates[target], target, pointer(b, b.operands[0], image),
                                  ref['rva'], hashlib.sha256(image.data[start:start + size]).hexdigest()))
    _check(len(owners) == 1, 'The native metadata header owner is missing or ambiguous.')
    return owners[0]


def _expression(node, offset, depth=0):
    _check(depth <= 64 and isinstance(node, tuple) and node)
    if node[0] == 'offset':
        return offset
    if node[0] == 'constant':
        return node[1]
    kind, width, *children = node
    _check(kind in {'add', 'sub', 'xor', 'imul', 'cast'} and width in (8, 16, 32, 64))
    values = [_expression(child, offset, depth + 1) for child in children]
    _check(len(values) == (1 if kind == 'cast' else 2))
    result = (values[0] if kind == 'cast' else values[0] + values[1] if kind == 'add'
              else values[0] - values[1] if kind == 'sub' else values[0] ^ values[1]
              if kind == 'xor' else values[0] * values[1])
    return result & ((1 << width) - 1)


def _depends(node):
    return node == ('offset',) or any(_depends(part) for part in node[1:] if isinstance(part, tuple))


@dataclass(frozen=True)
class IdentifierProfile:
    method_rva: int
    method_sha256: str
    section_field: int
    section_add: int
    body_global_rva: int
    key: tuple
    step: int


def identifier_profile(image, owner):
    references = rip_references(image, {owner.global_rva})
    candidates = []
    for method in sorted({r['function'] for r in references if r['function'] is not None}):
        try:
            seq = image.instructions(method)
        except ValueError:
            continue
        masks = [i for i in seq if i.mnemonic == 'and' and len(i.operands) == 2
                 and i.operands[1].type == CS_OP_IMM and i.operands[1].imm == 0xffffff]
        shifts = [i for i in seq if i.mnemonic == 'shr' and len(i.operands) == 2
                  and i.operands[1].type == CS_OP_IMM and i.operands[1].imm == 24]
        if not masks or not shifts:
            continue
        byaddr = {i.address - image.base: k for k, i in enumerate(seq)}
        fields = []
        for ref in references:
            if ref['function'] != method:
                continue
            at = byaddr[ref['rva']]
            ins = seq[at]
            if ins.mnemonic != 'mov' or ins.operands[0].type != CS_OP_REG:
                continue
            name = root(ins, ins.operands[0])
            for use in seq[at + 1:at + 9]:
                fields.extend((use, op) for op in use.operands if op.type == CS_OP_MEM
                              and register(use.reg_name(op.mem.base))[0] == name and not op.mem.index)
                if any(register(use.reg_name(r))[0] == name for r in use.regs_access()[1]):
                    break
        muls = sum(i.mnemonic in ('imul', 'mul') and i.operands[0].size == 8 for i in seq)
        xors = sum(i.mnemonic == 'xor' and any(op.type == CS_OP_MEM and op.size == 8
                                              for op in i.operands) for i in seq)
        if len({op.mem.disp for _, op in fields}) == 1 and muls >= 2 and xors:
            candidates.append((method, seq, masks, shifts, fields))
    _check(len(candidates) == 1, 'The packed identifier reader is missing or ambiguous.')
    method, seq, masks, shifts, fields = candidates[0]
    _check(len(masks) == len(shifts) == 1 and len(fields) == 1)
    constants = Constants(seq)
    first = seq.index(masks[0])
    state = {root(masks[0], masks[0].operands[0]): ('offset',)}
    header_load = None
    for ins in seq[first + 1:first + 65]:
        ops = ins.operands
        if (ins.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == CS_OP_MEM
                and ins.reg_name(ops[1].mem.base) == 'rip'
                and pointer(ins, ops[1], image) == owner.global_rva):
            header_load = ins
            break
        _check(not ins.mnemonic.startswith('j') and ins.mnemonic not in ('call', 'ret'))
        _check(len(ops) == 2 and ops[0].type == CS_OP_REG)
        target = root(ins, ops[0])
        if ins.mnemonic in ('mov', 'movabs'):
            value = (('constant', ops[1].imm & ((1 << (ops[0].size * 8)) - 1))
                     if ops[1].type == CS_OP_IMM else state[root(ins, ops[1])])
        else:
            _check(ins.mnemonic in ('add', 'sub', 'xor', 'imul') and ops[1].type == CS_OP_REG)
            value = (ins.mnemonic, ops[0].size * 8, state[target], state[root(ins, ops[1])])
        state[target] = ('cast', ops[0].size * 8, value)
    _check(header_load is not None)
    loops = []
    for at, ins in enumerate(seq[:-10]):
        ops = ins.operands
        if not (ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == CS_OP_REG
                and ops[1].type == CS_OP_MEM and ops[1].size == 8 and not ops[1].mem.index
                and not ops[1].mem.disp and ins.reg_name(ops[1].mem.base) not in ('rip', 'rsp', 'rbp')):
            continue
        use = seq[at + 1]
        if not (use.mnemonic == 'xor' and all(op.type == CS_OP_REG for op in use.operands)
                and root(use, use.operands[0]) == root(ins, ops[0])):
            continue
        keyreg = root(use, use.operands[1])
        expression = state.get(keyreg)
        if expression is None or not _depends(expression):
            continue
        increments = [i for i in seq[at + 2:at + 8] if i.mnemonic == 'add'
                      and i.operands[0].type == CS_OP_REG and root(i, i.operands[0]) == keyreg]
        back = [i for i in seq[at + 2:at + 12] if i.mnemonic.startswith('j')
                and i.operands[0].type == CS_OP_IMM and i.operands[0].imm == ins.address]
        if len(increments) == 1 and back:
            increment = increments[0]
            source = increment.operands[1]
            step = source.imm & MASK64 if source.type == CS_OP_IMM else constants.value_before(
                increment.address, increment.reg_name(source.reg), 64)
            loops.append((keyreg, expression, step))
    _check(len(loops) == 1)
    keyreg, expression, step = loops[0]
    unrolled = []
    for at, ins in enumerate(seq[:-17]):
        ops = ins.operands
        if not (ins.mnemonic == 'mov' and len(ops) == 2 and ops[1].type == CS_OP_MEM
                and ops[1].size == 8 and ops[1].mem.index and ops[1].mem.scale == 8
                and not ops[1].mem.disp):
            continue
        body = seq[at:at + 17]
        if not (body[1].mnemonic == 'xor' and body[1].operands[1].type == CS_OP_REG
                and root(body[1], body[1].operands[1]) == keyreg):
            continue
        leas = [i for i in body if i.mnemonic == 'lea' and i.operands[1].type == CS_OP_MEM
                and register(i.reg_name(i.operands[1].mem.base))[0] == keyreg and i.operands[1].mem.index]
        adds = [i for i in body if i.mnemonic == 'add' and i.operands[0].type == CS_OP_REG
                and root(i, i.operands[0]) == keyreg and i.operands[1].type == CS_OP_REG]
        if len(leas) != 3 or len(adds) != 1:
            continue
        values = [constants.value_before(i.address, i.reg_name(i.operands[1].mem.index)
                  if i.mnemonic == 'lea' else i.reg_name(i.operands[1].reg), 64) for i in (*leas, *adds)]
        offsets = [op.mem.disp for i in body if i.mnemonic == 'xor' for op in i.operands
                   if op.type == CS_OP_MEM and op.size == 8]
        if offsets == [8, 16, 24] and values == [step * k & MASK64 for k in (1, 2, 3, 4)]:
            unrolled.append(ins.address)
    _check(len(unrolled) == 1)
    field, operand = fields[0]
    _check(field.mnemonic == 'add' and field.operands[0].type == CS_OP_REG and operand.size == 4
           and 0 <= operand.mem.disp <= HEADER_SIZE - 4)
    seed = constants.value_before(field.address, field.reg_name(field.operands[0].reg), 32)
    position = seq.index(field)
    bodies = [pointer(i, i.operands[1], image) for i in seq[position + 1:position + 7]
              if i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[0].type == CS_OP_REG
              and i.operands[1].type == CS_OP_MEM and i.operands[1].size == 8
              and i.reg_name(i.operands[1].mem.base) == 'rip']
    _check(len(bodies) == 1)
    lanes = set()
    for ins in seq:
        if (ins.mnemonic in ('paddq', 'movdqa') and len(ins.operands) == 2
                and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rip'):
            at = image.offset(pointer(ins, ins.operands[1], image), 16)
            lanes.add(struct.unpack_from('<QQ', image.data, at))
    _check(lanes == {(0, step), (step * 2 & MASK64,) * 2, (step * 4 & MASK64,) * 2})
    return IdentifierProfile(method, hashlib.sha256(image.window(method)).hexdigest(),
                             operand.mem.disp, seed, bodies[0], expression, step)


class Identifiers:
    def __init__(self, image, metadata):
        self.image, self.metadata = image, metadata
        self.owner = header_owner(image, metadata)
        self.profile = identifier_profile(image, self.owner)
        self.header = image.data[self.owner.header_offset:self.owner.header_offset + HEADER_SIZE]
        section, = struct.unpack_from('<I', self.header, self.profile.section_field)
        self.section = (section + self.profile.section_add) & 0xffffffff
        _check(self.section <= len(metadata) - HEADER_SIZE)
        self.decoded = {}

    def text(self, index):
        _check(type(index) is int and 0 <= index <= 0xffffffff)
        if index == 0xffffffff:
            return '<unnamed>'
        if index in self.decoded:
            return self.decoded[index]
        offset, length = index & 0xffffff, index >> 24
        size = (length + 7) // 8 * 8
        at = HEADER_SIZE + self.section + offset
        _check(0 <= at <= len(self.metadata) - size and len(self.decoded) <= 2_000_000)
        key = _expression(self.profile.key, offset)
        output = bytearray()
        for start in range(at, at + size, 8):
            word, = struct.unpack_from('<Q', self.metadata, start)
            output.extend((word ^ key).to_bytes(8, 'little'))
            key = (key + self.profile.step) & MASK64
        value = output[:length].split(b'\0', 1)[0].decode('utf-8', errors='strict')
        self.decoded[index] = value
        return value


def word(data, offset, operations, bits=32):
    _check(bits in (8, 16, 32, 64) and 0 <= offset <= len(data) - bits // 8
           and isinstance(operations, tuple) and len(operations) <= 8)
    value = int.from_bytes(data[offset:offset + bits // 8], 'little')
    for kind, operand in operations:
        _check(kind in ('add', 'sub', 'xor') and type(operand) is int and 0 <= operand < 1 << bits)
        value = value + operand if kind == 'add' else value - operand if kind == 'sub' else value ^ operand
        value &= (1 << bits) - 1
    return value


def table_roles(identifiers):
    image, owner = identifiers.image, identifiers.owner
    methods, reads = {}, []
    for ref in rip_references(image, {owner.global_rva}):
        method = ref['function']
        if method is None:
            continue
        if method not in methods:
            try:
                methods[method] = image.instructions(method)
            except ValueError:
                methods[method] = []
        seq = methods[method]
        positions = {i.address - image.base: at for at, i in enumerate(seq)}
        if ref['rva'] not in positions:
            continue
        at = positions[ref['rva']]
        first = seq[at]
        if first.mnemonic != 'mov' or first.operands[0].type != CS_OP_REG:
            continue
        pointer_reg = root(first, first.operands[0])
        for ins in seq[at + 1:at + 13]:
            for operand in ins.operands:
                if (operand.type == CS_OP_MEM and not operand.mem.index
                        and register(ins.reg_name(operand.mem.base))[0] == pointer_reg
                        and operand.mem.disp in HEADER_ROLES and operand.size == 4):
                    reads.append((method, seq, ins, HEADER_ROLES[operand.mem.disp], operand.mem.disp))
            if (any(register(ins.reg_name(r))[0] == pointer_reg for r in ins.regs_access()[1])
                    or ins.mnemonic in ('call', 'ret') or ins.mnemonic.startswith('j')):
                break
    groups, constants = {}, {}
    for method, seq, ins, role, field in reads:
        try:
            if method not in constants:
                constants[method] = Constants(seq)
            values = constants[method]
            target, ops = root(ins, ins.operands[0]), ins.operands
            if ins.mnemonic in ('mov', 'movsxd'):
                initial = ()
            else:
                _check(ins.mnemonic in ('add', 'xor'))
                initial = ((ins.mnemonic, values.value_before(ins.address, target, 32)),)
            state, endpoint = {target: initial}, None
            at = seq.index(ins)
            for use in seq[at + 1:at + 25]:
                parts = use.operands
                if role == 'type_byte_length' and use.mnemonic == 'cdqe' and 'rax' in state:
                    position = seq.index(use)
                    chain = seq[position + 1:position + 4]
                    _check(len(chain) == 3 and [i.mnemonic for i in chain] == ['movabs', 'mul', 'shr']
                           and chain[0].operands[1].type == CS_OP_IMM
                           and chain[2].operands[1].type == CS_OP_IMM)
                    multiplier = chain[0].operands[1].imm & MASK64
                    shift = chain[2].operands[1].imm
                    _check(0 <= shift <= 16 and multiplier == ((1 << (64 + shift)) + TYPE_STRIDE - 1) // TYPE_STRIDE)
                    endpoint = state['rax']
                    break
                if (use.mnemonic == 'add' and len(parts) == 2 and parts[0].type == CS_OP_REG
                        and parts[1].type == CS_OP_MEM and use.reg_name(parts[1].mem.base) == 'rip'
                        and pointer(use, parts[1], image) == identifiers.profile.body_global_rva):
                    endpoint = state[root(use, parts[0])]
                    break
                if (use.mnemonic in ('mov', 'movsxd', 'movsx', 'movzx') and len(parts) == 2
                        and parts[0].type == CS_OP_REG):
                    destination = root(use, parts[0])
                    source = root(use, parts[1]) if parts[1].type == CS_OP_REG else None
                    if source in state:
                        state[destination] = state[source]
                    else:
                        state.pop(destination, None)
                    continue
                if (use.mnemonic in ('add', 'sub', 'xor') and len(parts) == 2
                        and parts[0].type == CS_OP_REG and root(use, parts[0]) in state):
                    literal = (parts[1].imm & 0xffffffff if parts[1].type == CS_OP_IMM else
                               values.value_before(use.address, use.reg_name(parts[1].reg), 32)
                               if parts[1].type == CS_OP_REG else None)
                    if literal is not None:
                        destination = root(use, parts[0])
                        state[destination] += ((use.mnemonic, literal),)
                        continue
                if use.mnemonic in ('nop', 'cmp', 'test', 'cdqe'):
                    continue
                _check(use.mnemonic != 'call' and not use.mnemonic.startswith('j'))
                for written in use.regs_access()[1]:
                    state.pop(register(use.reg_name(written))[0], None)
            _check(endpoint is not None)
            groups.setdefault(role, []).append({'method_rva': method, 'read_rva': ins.address - image.base,
                                               'field': field, 'operations': endpoint})
        except (ValueError, KeyError):
            continue
    result = {}
    for role in HEADER_ROLES.values():
        rows = groups.get(role, [])
        _check(rows and len({row['operations'] for row in rows}) == 1,
               'Native metadata table consumers are missing or disagree.')
        result[role] = {'field': rows[0]['field'], 'operations': rows[0]['operations'], 'owners': tuple(rows)}
    count = word(identifiers.header, result['type_byte_length']['field'], result['type_byte_length']['operations'])
    offset = word(identifiers.header, result['type_offset']['field'], result['type_offset']['operations'])
    _check(count % TYPE_STRIDE == 0 and 0 < count // TYPE_STRIDE <= 1_000_000
           and HEADER_SIZE + offset + count <= len(identifiers.metadata))
    for role, row in result.items():
        if role != 'type_byte_length':
            _check(word(identifiers.header, row['field'], row['operations']) < len(identifiers.metadata) - HEADER_SIZE)
    return result


def type_name_fields(identifiers, roles):
    image, groups = identifiers.image, {}
    methods = {row['method_rva'] for row in roles['type_offset']['owners']}
    for method in sorted(methods):
        seq = image.instructions(method)
        if not (any(i.mnemonic == 'imul' and any(op.type == CS_OP_IMM and op.imm == TYPE_STRIDE
                                                for op in i.operands) for i in seq)
                and any(op.type == CS_OP_MEM and i.reg_name(op.mem.base) == 'rip'
                        and pointer(i, op, image) == identifiers.profile.body_global_rva
                        for i in seq for op in i.operands)):
            continue
        definitions, constants = Definitions(seq), Constants(seq)
        byaddr = {i.address: i for i in seq}

        def expression(name, before, budget):
            budget[0] += 1
            _check(budget[0] <= 100)
            try:
                return ('constant', constants.value_before(before, name, 32))
            except ValueError:
                pass
            writers = definitions.before(before, name)
            _check(len(writers) == 1 and None not in writers, 'Ambiguous native metadata word definition.')
            ins = byaddr[next(iter(writers))]
            ops = ins.operands
            _check(ins.mnemonic != 'call' and ops and ops[0].type == CS_OP_REG
                   and root(ins, ops[0]) == register(name)[0] and ops[0].size >= 4)

            def source(operand):
                if operand.type == CS_OP_IMM:
                    return ('constant', operand.imm & 0xffffffff)
                if operand.type == CS_OP_REG:
                    return expression(root(ins, operand), ins.address, budget)
                _check(operand.type == CS_OP_MEM and operand.size == 4 and not operand.mem.index
                       and operand.mem.disp in (0x10, 0x18)
                       and ins.reg_name(operand.mem.base) not in ('rip', 'rsp', 'rbp'))
                name = register(ins.reg_name(operand.mem.base))[0]
                origins = definitions.before(ins.address, name)
                _check(len(origins) == 1)
                return ('field', operand.mem.disp, name, next(iter(origins)))

            if ins.mnemonic in ('mov', 'movzx', 'movsxd'):
                return source(ops[1])
            _check(ins.mnemonic in ('add', 'sub', 'xor') and len(ops) == 2)
            return (ins.mnemonic, expression(name, ins.address, budget), source(ops[1]))

        def flatten(node):
            if node[0] == 'field':
                return node, ()
            _check(node[0] in ('add', 'sub', 'xor'))
            if node[2][0] == 'constant':
                field, steps = flatten(node[1])
                return field, steps + ((node[0], node[2][1]),)
            _check(node[0] in ('add', 'xor') and node[1][0] == 'constant')
            field, steps = flatten(node[2])
            return field, steps + ((node[0], node[1][1]),)

        for ins in seq:
            if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                    and ins.operands[0].imm == image.base + identifiers.profile.method_rva):
                continue
            try:
                field, operations = flatten(expression('rcx', ins.address, [0]))
                groups.setdefault((method, field[2], field[3]), {})[field[1]] = operations
            except (ValueError, KeyError):
                continue
    complete = [row for row in groups.values() if set(row) == {0x10, 0x18}]
    _check(complete, 'No paired original TypeDefinition name/namespace consumer.')
    result = {}
    for offset, role in ((0x10, 'namespace'), (0x18, 'name')):
        operations = {row[offset] for row in complete}
        _check(len(operations) == 1, 'Native TypeDefinition name consumers disagree.')
        result[role] = {'field': offset, 'operations': operations.pop()}
    return result


class Types:
    def __init__(self, image, metadata):
        self.identifiers = Identifiers(image, metadata)
        self.roles = table_roles(self.identifiers)
        self.names = type_name_fields(self.identifiers, self.roles)
        self.offset = self.role('type_offset')
        self.count = self.role('type_byte_length') // TYPE_STRIDE
        self.rows = []
        for index in range(self.count):
            at = HEADER_SIZE + self.offset + TYPE_STRIDE * index
            record = metadata[at:at + TYPE_STRIDE]
            self.rows.append({'definition': index, **{
                role: self.type_name(word(record, spec['field'], spec['operations']))
                for role, spec in self.names.items()}})

    def role(self, name):
        row = self.roles[name]
        return word(self.identifiers.header, row['field'], row['operations'])

    def type_name(self, packed):
        # Absent type names are null metadata fields, not a printable identifier.
        return '' if packed == 0xffffffff else self.identifiers.text(packed)


def method_name_profile(types):
    image, ids = types.identifiers.image, types.identifiers
    candidates = []
    for method in sorted({row['method_rva'] for row in types.roles['method_offset']['owners']}):
        seq = image.instructions(method)
        for tail_at, tail in enumerate(seq):
            if not (tail.mnemonic == 'jmp' and tail.operands[0].type == CS_OP_IMM
                    and tail.operands[0].imm == image.base + ids.profile.method_rva):
                continue
            try:
                begins = [at for at, ins in enumerate(seq[:tail_at]) if ins.mnemonic == 'add'
                          and ins.operands[0].type == CS_OP_REG and ins.operands[1].type == CS_OP_MEM
                          and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                          and pointer(ins, ins.operands[1], image) == ids.profile.body_global_rva]
                _check(len(begins) == 1)
                begin = begins[0]
                registers, fields = indexed.extract(seq[begin + 1:tail_at], root(seq[begin], seq[begin].operands[0]),
                    26, {4: 4}, image_base=image.base, index_limit=MAX_METADATA // 26)
                expression = registers['rcx']
                _check(len(fields) == 1 and {leaf[1] for leaf in indexed.leaves(expression)
                       if leaf[0] == 'input'} == {fields[0]['index_register']})
                candidates.append({'method_rva': method, 'raw_field': fields[0], 'expression': expression})
            except (ValueError, KeyError):
                continue
    _check(len(candidates) == 1, 'The native method-name reader is missing or ambiguous.')
    return candidates[0]


def method_ranges(types):
    image, rows = types.identifiers.image, []
    for method in sorted({row['method_rva'] for row in types.roles['type_offset']['owners']}):
        seq = image.instructions(method)
        for at, ins in enumerate(seq[:-3]):
            ops = ins.operands
            if not (ins.mnemonic == 'movzx' and len(ops) == 2 and ops[1].type == CS_OP_MEM
                    and ops[1].size == 2 and ops[1].mem.disp == 0x3c and not ops[1].mem.index
                    and ins.reg_name(ops[1].mem.base) not in ('rip', 'rsp', 'rbp')):
                continue
            xor, compare = seq[at + 1:at + 3]
            if not (xor.mnemonic == 'xor' and xor.operands[0].reg == ops[0].reg
                    and xor.operands[1].type == CS_OP_IMM and compare.mnemonic == 'cmp'):
                continue
            for position in range(at + 3, min(len(seq) - 9, at + 16)):
                raw, lea, add, global_, array, signed, selected = seq[position:position + 7]
                if not (raw.mnemonic == 'mov' and raw.operands[1].type == CS_OP_MEM
                        and raw.operands[1].size == 4 and raw.operands[1].mem.disp == 4
                        and raw.operands[1].mem.base == ops[1].mem.base and lea.mnemonic == 'lea'
                        and lea.operands[1].type == CS_OP_MEM and add.mnemonic == 'add'
                        and add.operands[1].type == CS_OP_IMM and global_.mnemonic == 'mov'
                        and global_.operands[1].type == CS_OP_MEM
                        and global_.reg_name(global_.operands[1].mem.base) == 'rip'
                        and array.mnemonic == 'mov' and array.operands[1].type == CS_OP_MEM
                        and array.operands[1].mem.disp == 0x18 and selected.mnemonic == 'mov'
                        and selected.operands[1].type == CS_OP_MEM and selected.operands[1].mem.scale == 8):
                    continue
                source_reg = root(raw, raw.operands[0])
                _check(source_reg in {register(lea.reg_name(lea.operands[1].mem.base))[0],
                                     register(lea.reg_name(lea.operands[1].mem.index))[0]})
                _check(root(global_, global_.operands[0])
                       == register(array.reg_name(array.operands[1].mem.base))[0]
                       and root(array, array.operands[0])
                       == register(selected.reg_name(selected.operands[1].mem.base))[0])
                rows.append({'method_rva': method, 'count_field': 0x3c,
                    'count_operations': (('xor', xor.operands[1].imm & 0xffff),),
                    'start_field': 4, 'start_operations': (('add', add.operands[1].imm & 0xffffffff),),
                    'code_registration_global_rva': pointer(global_, global_.operands[1], image),
                    'method_pointer_registration_field': array.operands[1].mem.disp})
    _check(rows and len({(r['count_operations'], r['start_operations'],
        r['code_registration_global_rva'], r['method_pointer_registration_field']) for r in rows}) == 1,
        'Native method member-range consumers are missing or disagree.')
    description = rows[0]
    data = types.identifiers.metadata
    ranges = []
    for definition in range(types.count):
        at = HEADER_SIZE + types.offset + TYPE_STRIDE * definition
        record = data[at:at + TYPE_STRIDE]
        start = word(record, description['start_field'], description['start_operations'])
        count = word(record, description['count_field'], description['count_operations'], 16)
        if count:
            _check(start + count <= MAX_METADATA // 26)
            ranges.append((start, start + count, definition))
    ranges.sort()
    total = 0
    for start, end, _definition in ranges:
        _check(start == total, 'Native method ranges overlap or leave an unowned gap.')
        total = end
    _check(total > 0 and HEADER_SIZE + types.role('method_offset') + 26 * total <= len(data))
    return description, ranges, total


class Methods(Types):
    def __init__(self, image, metadata):
        super().__init__(image, metadata)
        self.method_names = method_name_profile(self)
        self.method_range_description, self.method_ranges, count = method_ranges(self)
        self.methods = []
        offset = self.role('method_offset')
        spec = self.method_names
        for index in range(count):
            at = HEADER_SIZE + offset + 26 * index + 4
            raw = word(metadata, at, ())
            packed = indexed.evaluate(spec['expression'], {spec['raw_field']['index_register']: index}, {4: raw})
            self.methods.append((index, self.identifiers.text(packed)))


def direct_calls(image, targets):
    """Only calls to already-owned metadata accessors, decoded by consumers."""
    _check(isinstance(targets, set) and 0 < len(targets) <= 64)
    results = []
    for name in image.executable_sections:
        rva, _virtual, raw, size = image.sections[name]
        body = image.data[raw:raw + size]
        for match in re.finditer(b'\xe8', body):
            at = match.start()
            if at + 5 > len(body):
                continue
            target = rva + at + 5 + struct.unpack_from('<i', body, at + 1)[0]
            if target in targets:
                results.append((rva + at, target, image.function_start(rva + at)))
                _check(len(results) <= 100_000)
    return results


def member_name_profiles(types):
    image, ids = types.identifiers.image, types.identifiers
    profiles = {}
    for role, field_offset in (('field_offset', 0), ('parameter_offset', 4)):
        found = []
        for method in sorted({row['method_rva'] for row in types.roles[role]['owners']}):
            seq = image.instructions(method)
            for at, ins in enumerate(seq):
                if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                        and ins.operands[0].imm == image.base + ids.profile.method_rva):
                    continue
                try:
                    begins = [k for k, i in enumerate(seq[:at]) if i.mnemonic == 'add'
                              and i.operands[0].type == CS_OP_REG and i.operands[1].type == CS_OP_MEM
                              and i.reg_name(i.operands[1].mem.base) == 'rip'
                              and pointer(i, i.operands[1], image) == ids.profile.body_global_rva]
                    _check(begins)
                    begin = begins[-1]
                    table_register = root(seq[begin], seq[begin].operands[0])
                    registers, fields = indexed.extract(seq[begin + 1:at], table_register, 8,
                        {field_offset: 4}, image_base=image.base, index_limit=min(len(ids.metadata) // 8, 16_000_000))
                    _check(len(fields) == 1)
                    expression = registers['rcx']
                    _check({leaf[1] for leaf in indexed.leaves(expression) if leaf[0] == 'input'}
                           == {fields[0]['index_register']})
                    row = {'method_rva': method, 'raw_field': fields[0], 'expression': expression}
                    if role == 'parameter_offset':
                        tail = []
                        for use in seq[at + 1:at + 10]:
                            if use.mnemonic == 'cmp':
                                break
                            if use.mnemonic == 'mov' and use.operands[0].type == CS_OP_MEM:
                                continue
                            tail.append(use)
                        _check(tail)
                        state, extra = indexed.extract([ins, *tail], table_register, 8, {0: 4, 4: 4},
                            image_base=image.base, index_limit=min(len(ids.metadata) // 8, 16_000_000), initial=registers)
                        _check(len(extra) == 1 and extra[0]['field_offset'] == 0)
                        output = root(tail[-1], tail[-1].operands[0])
                        row['type_expression'], row['type_field'] = state[output], extra[0]
                        _check({leaf[1] for leaf in indexed.leaves(row['type_expression']) if leaf[0] == 'input'}
                               == {fields[0]['index_register']})
                        following = seq[at + 1:at + 18]
                        bindings = []
                        for k, use in enumerate(following[:-3]):
                            add = following[k + 3]
                            if (use.mnemonic == 'mov' and use.operands[1].type == CS_OP_MEM
                                    and use.reg_name(use.operands[1].mem.base) == 'rip'
                                    and add.mnemonic == 'add' and add.operands[1].type == CS_OP_MEM
                                    and add.operands[1].mem.disp == 0x58):
                                bindings.append((pointer(use, use.operands[1], image), add.operands[1].mem.disp))
                        _check(len(set(bindings)) == 1)
                        row['type_registration_global_rva'], row['type_array_registration_field'] = bindings[0]
                    found.append(row)
                except (ValueError, KeyError):
                    continue
        _check(len(found) == 1, 'The native field or parameter reader is missing or ambiguous.')
        profiles[role] = found[0]
    return profiles


def field_ranges(types):
    image, starts, counts = types.identifiers.image, [], []
    count_owners = set()
    owners = {row['method_rva'] for row in types.roles['field_offset']['owners']}
    for method in sorted(owners):
        seq = image.instructions(method)
        constants = Constants(seq)
        for ins in seq:
            if (ins.mnemonic == 'xor' and len(ins.operands) == 2
                    and ins.operands[1].type == CS_OP_MEM and ins.operands[1].size == 4
                    and ins.operands[1].mem.disp == 0x2c and not ins.operands[1].mem.index
                    and ins.reg_name(ins.operands[1].mem.base) not in ('rip', 'rsp', 'rbp')):
                starts.append((('xor', constants.value_before(ins.address, root(ins, ins.operands[0]), 32)),))
    callers = {owner for _at, _target, owner in direct_calls(image, owners) if owner is not None}
    for method in sorted(callers):
        try:
            seq = image.instructions(method)
        except ValueError:
            continue
        for at, ins in enumerate(seq[:-4]):
            if not (at > 0 and ins.mnemonic == 'movzx' and ins.operands[1].type == CS_OP_MEM
                    and ins.operands[1].size == 2 and ins.operands[1].mem.disp == 0x38):
                continue
            previous = seq[at - 1]
            xor, shift, add = seq[at + 1:at + 4]
            if not (previous.mnemonic == 'mov' and previous.operands[1].type == CS_OP_MEM
                    and previous.operands[1].mem.disp == 0x40 and xor.mnemonic == 'xor'
                    and xor.operands[1].type == CS_OP_IMM and shift.mnemonic == 'shl'
                    and shift.operands[1].type == CS_OP_IMM and shift.operands[1].imm == 5
                    and add.mnemonic == 'add' and add.operands[1].type == CS_OP_MEM
                    and add.operands[1].mem.disp == 0x50
                    and previous.operands[0].reg == ins.operands[1].mem.base
                    and previous.operands[1].mem.base == add.operands[1].mem.base):
                continue
            counts.append((('xor', xor.operands[1].imm & 0xffff),))
            count_owners.add(method)
    _check(starts and counts and len(set(starts)) == len(set(counts)) == 1,
           'Native field member ranges are missing or disagree.')
    description = {'start_field': 0x2c, 'start_operations': starts[0],
                   'count_field': 0x38, 'count_operations': counts[0],
                   'count_owner_rvas': tuple(sorted(count_owners))}
    data, ranges = types.identifiers.metadata, []
    for definition in range(types.count):
        at = HEADER_SIZE + types.offset + TYPE_STRIDE * definition
        record = data[at:at + TYPE_STRIDE]
        start = word(record, 0x2c, starts[0])
        count = word(record, 0x38, counts[0], 16)
        if count:
            _check(start + count <= len(data) // 8)
            ranges.append((start, start + count, definition))
    ranges.sort()
    total = 0
    for start, end, _definition in ranges:
        _check(start == total, 'Native field ranges overlap or leave an unowned gap.')
        total = end
    _check(total > 0 and HEADER_SIZE + types.role('field_offset') + 8 * total <= len(data))
    return description, ranges, total


def parameter_ranges(types, profile):
    image, ids = types.identifiers.image, types.identifiers
    seq = image.instructions(profile['method_rva'])
    profiles = []
    for at, ins in enumerate(seq):
        if not (ins.mnemonic == 'movzx' and ins.operands[1].type == CS_OP_MEM
                and ins.operands[1].size == 1 and ins.operands[1].mem.disp == 0x18
                and ins.operands[1].mem.index):
            continue
        begins = [k for k, i in enumerate(seq[:at]) if i.mnemonic == 'add'
                  and i.operands[0].type == CS_OP_REG and i.operands[1].type == CS_OP_MEM
                  and i.reg_name(i.operands[1].mem.base) == 'rip'
                  and pointer(i, i.operands[1], image) == ids.profile.body_global_rva]
        _check(begins and at + 4 < len(seq))
        begin, count_end = begins[-1], at + 4
        table_register = root(seq[begin], seq[begin].operands[0])
        final = seq[count_end]
        _check(final.mnemonic == 'movzx' and final.operands[1].type == CS_OP_REG
               and final.operands[1].size == 1)
        registers, fields = indexed.extract(seq[begin + 1:count_end + 1], table_register, 26,
            {0x18: 1}, image_base=image.base, index_limit=MAX_METADATA // 26)
        _check(len(fields) == 1)
        count_expression = registers[root(final, final.operands[0])]
        _check({leaf[1] for leaf in indexed.leaves(count_expression) if leaf[0] == 'input'}
               == {fields[0]['index_register']})
        starts = []
        for position in range(count_end + 1, len(seq) - 6):
            literal, sub, store, zero = seq[position:position + 4]
            if not (literal.mnemonic == 'mov' and literal.operands[0].type == CS_OP_REG
                    and literal.operands[1].type == CS_OP_IMM and sub.mnemonic == 'sub'
                    and sub.operands[0].reg == literal.operands[0].reg and sub.operands[1].type == CS_OP_REG
                    and store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM
                    and zero.mnemonic == 'xor' and zero.operands[0].reg == zero.operands[1].reg):
                continue
            key_register = root(sub, sub.operands[1])
            _check(key_register in registers)
            bias = indexed.operation('sub', 32, indexed.constant(literal.operands[1].imm), registers[key_register])
            saved = store.operands[0].mem
            for k in range(position + 4, len(seq) - 4):
                load, lea, raw = seq[k:k + 3]
                if not (load.mnemonic == 'mov' and load.operands[1].type == CS_OP_MEM
                        and load.operands[1].mem.base == saved.base and load.operands[1].mem.disp == saved.disp
                        and lea.mnemonic == 'lea' and raw.mnemonic == 'add'
                        and raw.operands[1].type == CS_OP_MEM and raw.operands[1].mem.disp == 8):
                    continue
                _check(register(lea.reg_name(lea.operands[1].mem.base))[0] == root(load, load.operands[0])
                       and register(lea.reg_name(lea.operands[1].mem.index))[0] == root(zero, zero.operands[0])
                       and lea.operands[0].reg == raw.operands[0].reg)
                starts.append(indexed.operation('add', 32, ('field', 8), bias))
        _check(len(starts) == 1)
        profiles.append({'method_rva': profile['method_rva'], 'index_register': fields[0]['index_register'],
                         'count_expression': count_expression, 'start_expression': starts[0]})
    _check(len(profiles) == 1, 'Native parameter member ranges are missing or ambiguous.')
    return profiles[0]


class Members(Methods):
    def __init__(self, image, metadata):
        super().__init__(image, metadata)
        self.member_names = member_name_profiles(self)
        self.field_range_description, self.field_ranges, count = field_ranges(self)
        self.fields = []
        spec, offset = self.member_names['field_offset'], self.role('field_offset')
        for index in range(count):
            raw = word(metadata, HEADER_SIZE + offset + 8 * index, ())
            packed = indexed.evaluate(spec['expression'], {spec['raw_field']['index_register']: index}, {0: raw})
            self.fields.append((index, self.identifiers.text(packed)))
        spec = self.member_names['parameter_offset']
        self.parameter_range_description = parameter_ranges(self, spec)
        ranges = []
        method_offset = self.role('method_offset')
        for index in range(len(self.methods)):
            at = HEADER_SIZE + method_offset + 26 * index
            fields = {8: word(metadata, at + 8, ()), 0x18: metadata[at + 0x18]}
            description = self.parameter_range_description
            inputs = {description['index_register']: index}
            start = indexed.evaluate(description['start_expression'], inputs, fields)
            count = indexed.evaluate(description['count_expression'], inputs, fields)
            if count:
                _check(start + count <= len(metadata) // 8)
                ranges.append((start, start + count, index))
        ranges.sort()
        total = 0
        for start, end, _method in ranges:
            _check(start == total, 'Native parameter ranges overlap or leave an unowned gap.')
            total = end
        _check(total > 0 and HEADER_SIZE + self.role('parameter_offset') + 8 * total <= len(metadata))
        self.parameter_ranges, self.parameters = ranges, []
        parameter_offset = self.role('parameter_offset')
        for index in range(total):
            at = HEADER_SIZE + parameter_offset + 8 * index
            fields = {0: word(metadata, at, ()), 4: word(metadata, at + 4, ())}
            inputs = {spec['raw_field']['index_register']: index}
            packed = indexed.evaluate(spec['expression'], inputs, fields)
            typed = indexed.evaluate(spec['type_expression'], inputs, fields)
            self.parameters.append((index, self.identifiers.text(packed), typed))
