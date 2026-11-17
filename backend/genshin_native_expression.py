"""Bounded arithmetic expressions from owned native metadata table suffixes."""
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, register, _check


def constant(value):
    return ('constant', value)


def operation(kind, width, *args):
    _check(kind in {'add', 'sub', 'xor', 'imul', 'shr', 'cast'} and width in (8, 16, 32, 64))
    return (kind, width, *args)


def leaves(node, depth=0):
    _check(isinstance(node, tuple) and depth <= 64)
    if node[0] in ('constant', 'input', 'field'):
        return [node]
    _check(node[0] in {'add', 'sub', 'xor', 'imul', 'shr', 'cast'})
    return [leaf for child in node[2:] for leaf in leaves(child, depth + 1)]


def evaluate(node, inputs, fields=None, depth=0):
    _check(isinstance(node, tuple) and depth <= 64)
    if node[0] == 'constant':
        return node[1]
    if node[0] == 'input':
        return inputs[node[1]]
    if node[0] == 'field':
        _check(isinstance(fields, dict))
        return fields[node[1]]
    kind, width, *children = node
    _check(kind in {'add', 'sub', 'xor', 'imul', 'shr', 'cast'} and width in (8, 16, 32, 64))
    values = [evaluate(child, inputs, fields, depth + 1) for child in children]
    _check(len(values) == (1 if kind == 'cast' else 2))
    if kind == 'shr':
        _check(0 <= values[1] < width)
    value = (values[0] if kind == 'cast' else values[0] + values[1] if kind == 'add'
             else values[0] - values[1] if kind == 'sub' else values[0] ^ values[1]
             if kind == 'xor' else values[0] * values[1] if kind == 'imul'
             else values[0] >> values[1])
    return value & ((1 << width) - 1)


def _affine(node, index_limit, depth=0):
    """Exact table/index/constant coefficients; do not fit sampled addresses."""
    _check(depth <= 64)
    if node[0] == 'constant':
        return {}, node[1]
    if node[0] == 'input':
        return {node[1]: 1}, 0
    kind, width, *children = node
    _check(kind in {'add', 'sub', 'imul', 'cast'})
    parts = [_affine(child, index_limit, depth + 1) for child in children]
    if kind == 'cast':
        coefficients, value = parts[0]
    elif kind in ('add', 'sub'):
        left, right = parts
        sign = -1 if kind == 'sub' else 1
        coefficients = {key: left[0].get(key, 0) + sign * right[0].get(key, 0)
                        for key in left[0].keys() | right[0].keys()}
        value = left[1] + sign * right[1]
    else:
        left, right = parts
        _check(not left[0] or not right[0], 'A native table address is nonlinear.')
        variable, scalar = (left, right[1]) if not right[0] else (right, left[1])
        coefficients = {key: coefficient * scalar for key, coefficient in variable[0].items()}
        value = variable[1] * scalar
    coefficients = {key: coefficient for key, coefficient in coefficients.items() if coefficient}
    if width < 64:
        # Truncating an address-bearing table pointer is never equivalent. The
        # separate nonnegative index computation may use a bounded 32-bit lane.
        _check('table' not in coefficients)
        lower, upper = value, value
        for coefficient in coefficients.values():
            delta = coefficient * (index_limit - 1)
            lower += min(0, delta)
            upper += max(0, delta)
        _check(0 <= lower <= upper < 1 << width, 'A native table index can wrap.')
    return coefficients, value


def extract(seq, table_register, stride, allowed_fields, *, image_base, index_limit, initial=None):
    _check(seq and len(seq) <= 4096 and type(stride) is int and 0 < stride <= 1024
           and isinstance(allowed_fields, dict) and 0 < len(allowed_fields) <= 32
           and type(index_limit) is int and 0 < index_limit <= 16_000_000)
    registers = {table_register: ('input', 'table')} if initial is None else dict(initial)
    fields = []

    def reg(name):
        name = register(name)[0]
        return registers.get(name, ('input', name))

    def address(ins, memory):
        value = constant(memory.disp)
        if memory.base:
            value = operation('add', 64, value, reg(ins.reg_name(memory.base)))
        if memory.index:
            value = operation('add', 64, value, operation('imul', 64,
                              reg(ins.reg_name(memory.index)), constant(memory.scale)))
        return value

    for ins in seq:
        ops = ins.operands
        if ins.mnemonic == 'nop':
            continue
        if ins.mnemonic == 'call':
            for name in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                registers.pop(name, None)
            continue
        _check(ops and ops[0].type == CS_OP_REG, 'Unsupported native expression instruction.')
        target, width = register(ins.reg_name(ops[0].reg))[0], ops[0].size * 8
        if target == 'rsp':
            continue

        def source(operand):
            if operand.type == CS_OP_IMM:
                return constant(operand.imm)
            if operand.type == CS_OP_REG:
                return operation('cast', operand.size * 8, reg(ins.reg_name(operand.reg)))
            _check(operand.type == CS_OP_MEM and operand.size in (1, 2, 4))
            coefficients, offset = _affine(address(ins, operand.mem), index_limit)
            indices = set(coefficients) - {'table'}
            _check(coefficients.get('table') == 1 and len(indices) == 1
                   and coefficients[next(iter(indices))] == stride
                   and offset in allowed_fields and allowed_fields[offset] == operand.size,
                   'The raw metadata word has no exact typed table address.')
            index_register = next(iter(indices))
            fields.append({'read_rva': ins.address - image_base, 'index_register': index_register,
                           'field_offset': offset, 'field_width_bytes': operand.size, 'stride': stride})
            return ('field', offset)

        previous = reg(target)
        if ins.mnemonic in ('mov', 'movabs', 'movzx'):
            value = source(ops[1])
        elif ins.mnemonic == 'lea':
            value = address(ins, ops[1].mem)
        elif ins.mnemonic == 'imul':
            value = operation('imul', width, source(ops[1]) if len(ops) == 3 else previous,
                              source(ops[2]) if len(ops) == 3 else source(ops[1]))
        elif ins.mnemonic in ('add', 'sub', 'xor', 'shr'):
            value = operation(ins.mnemonic, width, previous, source(ops[1]))
        elif ins.mnemonic == 'inc':
            value = operation('add', width, previous, constant(1))
        else:
            raise ValueError('Unsupported native metadata expression instruction.')
        registers[target] = operation('cast', width, value)
    return registers, fields
