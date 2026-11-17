"""Authored field ownership and serialization order in typed native readers."""
from collections import deque

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, VOLATILE, register, _check
from .genshin_native_metadata import root


def pointer_states(context, arguments=None, *, output_pointers=None):
    frame = context.constants.frame
    outputs = {} if output_pointers is None else output_pointers
    _check(isinstance(outputs, dict) and len(outputs) <= 16)
    for target, (size, pointers) in outputs.items():
        _check(type(target) is int and target > 0 and type(size) is int and 8 <= size <= 4096
               and isinstance(pointers, dict) and 1 <= len(pointers) <= 16)
        _check(all(type(at) is int and 0 <= at <= size - 8 and at % 8 == 0
                   and isinstance(value, tuple) and len(value) == 2
                   and isinstance(value[0], str) and type(value[1]) is int
                   for at, value in pointers.items()))

    def key(ins, op):
        if op.type == CS_OP_REG:
            return ('reg', root(ins, op))
        if op.type == CS_OP_MEM and not op.mem.index:
            name = register(ins.reg_name(op.mem.base))[0]
            if name in ('rbp', 'rsp'):
                return ('stack', op.mem.disp + (frame if name == 'rbp' else 0))
        return None

    entry = context.seq[0].address
    initial = {'rcx': ('this', 0), 'rdx': ('stream', 0)} if arguments is None else dict(arguments)
    states = {entry: {('reg', name): value for name, value in initial.items()}}
    queue, iterations = deque([entry]), 0
    while queue:
        at = queue.popleft()
        iterations += 1
        _check(iterations <= 200000)
        ins, outgoing = context.by_address[at], dict(states[at])
        ops, handled = ins.operands, False
        if outputs and ops and ops[0].type == CS_OP_MEM and ops[0].access & 2:
            destination = key(ins, ops[0])
            if destination is not None and destination[0] == 'stack':
                low, high = destination[1], destination[1] + ops[0].size
                for stored in list(outgoing):
                    if stored[0] == 'stack' and stored[1] < high and stored[1] + 8 > low:
                        outgoing.pop(stored)
        if ins.mnemonic in ('mov', 'movabs', 'movzx', 'movsxd') and len(ops) == 2:
            destination = key(ins, ops[0])
            value = outgoing.get(key(ins, ops[1]))
            if destination:
                outgoing.pop(destination, None)
                if value is not None and ops[0].size == ops[1].size == 8:
                    outgoing[destination] = value
            handled = True
        elif ins.mnemonic == 'lea' and len(ops) == 2 and ops[0].type == CS_OP_REG and ops[1].type == CS_OP_MEM:
            memory = ops[1].mem
            value = outgoing.get(('reg', register(ins.reg_name(memory.base))[0]))
            destination = key(ins, ops[0])
            outgoing.pop(destination, None)
            if value is not None and not memory.index and ops[0].size == 8:
                outgoing[destination] = (value[0], value[1] + memory.disp)
            elif outputs and not memory.index and ins.reg_name(memory.base) in ('rbp', 'rsp'):
                outgoing[destination] = ('stack-address', memory.disp + (frame if ins.reg_name(memory.base) == 'rbp' else 0))
            handled = True
        elif ins.mnemonic in ('add', 'sub') and len(ops) == 2 and ops[0].type == CS_OP_REG and ops[1].type == CS_OP_IMM:
            destination = key(ins, ops[0])
            value = outgoing.pop(destination, None)
            if value is not None and ops[0].size == 8:
                outgoing[destination] = (value[0], value[1] + (ops[1].imm if ins.mnemonic == 'add' else -ops[1].imm))
            handled = True
        elif ins.mnemonic == 'call':
            output = (outputs.get(ops[0].imm - context.image.base)
                      if ops and ops[0].type == CS_OP_IMM else None)
            if output is not None:
                size, values = output
                address = outgoing.get(('reg', 'rcx'))
                _check(address is not None and address[0] == 'stack-address',
                       'The owned native output has no unambiguous stack destination.')
                for stored in list(outgoing):
                    if stored[0] == 'stack' and stored[1] < address[1] + size and stored[1] + 8 > address[1]:
                        outgoing.pop(stored)
                outgoing.update({('stack', address[1] + offset): value for offset, value in values.items()})
            for name in VOLATILE:
                outgoing.pop(('reg', name), None)
            handled = True
        elif ins.mnemonic in ('cmp', 'test', 'bt', 'nop') or ins.mnemonic.startswith('j'):
            handled = True
        if not handled:
            for name in ins.regs_access()[1]:
                outgoing.pop(('reg', register(ins.reg_name(name))[0]), None)
        for child in context.constants.successors(ins):
            previous = states.get(child)
            merged = outgoing if previous is None else {key: value for key, value in previous.items() if outgoing.get(key) == value}
            if previous is None or merged != previous:
                states[child] = dict(merged)
                queue.append(child)
    return states


def header_profile(context):
    first = context.reads()[0]
    inputs = [op for op in first.operands if op.type == CS_OP_MEM and op.mem.index and op.mem.disp == 0x20 and op.access & 1]
    _check(len(inputs) == 1 and first.operands[0].type == CS_OP_REG)
    bits, name = inputs[0].size * 8, root(first, first.operands[0])
    mask, operations = (1 << bits) - 1, []
    if first.mnemonic in ('add', 'xor', 'sub'):
        seed = context.constants.value_before(first.address, name, bits)
        operations = [(first.mnemonic, seed)] if first.mnemonic != 'sub' else [('xor', mask), ('add', (seed + 1) & mask)]
    else:
        _check(first.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd'))
    return {'read_rva': first.address - context.image.base, 'bits': bits, 'operations': tuple(operations),
            'seed_address': first.address, 'register': name}


def ordered_fields(context, authored_fields, reference_readers=(), scalar_setters=(), object_calls=None):
    header = header_profile(context)
    frame = context.constants.frame
    pointers = pointer_states(context)
    offsets = {field['authored_offset_word'] for field in authored_fields}

    def key(ins, op):
        if op.type == CS_OP_REG:
            return ('reg', root(ins, op))
        if op.type == CS_OP_MEM and not op.mem.index:
            base = register(ins.reg_name(op.mem.base))[0]
            if base in ('rsp', 'rbp'):
                return ('stack', op.mem.disp + (frame if base == 'rbp' else 0))
        return None

    def value(ins, op, state):
        result = state.get(key(ins, op))
        if result is None:
            return None
        operations, shift, width, inverted = result
        width = min(width, op.size * 8)
        return operations, shift, width, inverted & ((1 << width) - 1)

    entry = context.seq[0].address
    states, queue, iterations = {entry: {}}, deque([entry]), 0
    while queue:
        at = queue.popleft()
        iterations += 1
        _check(iterations <= 200000)
        ins, outgoing = context.by_address[at], dict(states[at])
        ops, handled = ins.operands, False
        mnemonic = ins.mnemonic
        if at == header['seed_address']:
            outgoing[('reg', header['register'])] = (header['operations'], 0, header['bits'], 0)
            handled = True
        elif mnemonic in ('mov', 'movabs', 'movzx', 'movsx', 'movsxd') and len(ops) == 2:
            destination, source = key(ins, ops[0]), value(ins, ops[1], outgoing)
            if destination:
                outgoing.pop(destination, None)
                if source is not None:
                    outgoing[destination] = source
            handled = True
        elif mnemonic == 'shr' and ops[1].type == CS_OP_IMM:
            destination, source = key(ins, ops[0]), value(ins, ops[0], outgoing)
            outgoing.pop(destination, None)
            if source is not None and 0 <= ops[1].imm < source[2]:
                outgoing[destination] = source[0], source[1] + ops[1].imm, source[2] - ops[1].imm, source[3] >> ops[1].imm
            handled = True
        elif mnemonic in ('bt', 'test', 'cmp') and len(ops) == 2:
            source = value(ins, ops[0], outgoing)
            outgoing.pop(('condition',), None)
            if source is not None:
                operations, shift, width, inverted = source
                if mnemonic == 'bt' and ops[1].type == CS_OP_IMM and 0 <= ops[1].imm < width:
                    outgoing[('condition',)] = (operations, shift + ops[1].imm, 'carry', bool(inverted >> ops[1].imm & 1))
                elif mnemonic == 'test' and ops[1].type == CS_OP_IMM:
                    mask = ops[1].imm
                    if mask > 0 and mask & (mask - 1) == 0 and mask.bit_length() <= width:
                        outgoing[('condition',)] = (operations, shift + mask.bit_length() - 1, 'zero', bool(inverted & mask))
                elif mnemonic == 'test' and key(ins, ops[1]) == key(ins, ops[0]):
                    outgoing[('condition',)] = (operations, shift + width - 1, 'sign', bool(inverted >> (width - 1) & 1))
                elif mnemonic == 'cmp' and ops[1].type == CS_OP_IMM and ops[1].imm == 0:
                    # Subtracting zero preserves the sign bit, including when
                    # the authored header was spilled to a stack slot.
                    outgoing[('condition',)] = (operations, shift + width - 1, 'sign', bool(inverted >> (width - 1) & 1))
            handled = True
        elif mnemonic.startswith('j'):
            handled = True
        elif mnemonic == 'call':
            for name in VOLATILE:
                outgoing.pop(('reg', name), None)
            outgoing.pop(('condition',), None)
            handled = True
        elif mnemonic == 'xor' and len(ops) == 2:
            source, amount = value(ins, ops[0], outgoing), None
            if source is not None and ops[1].type == CS_OP_IMM:
                amount = ops[1].imm
            elif ops[0].type == ops[1].type == CS_OP_REG:
                other = value(ins, ops[1], outgoing)
                if (source is None) != (other is None):
                    symbolic, constant = (source, ops[1]) if source is not None else (other, ops[0])
                    try:
                        amount = context.constants.value_before(ins.address, root(ins, constant), ops[0].size * 8)
                        source = symbolic
                    except ValueError:
                        pass
            if source is not None and amount is not None:
                width = min(source[2], ops[0].size * 8)
                inverted = (source[3] ^ amount) & ((1 << width) - 1)
                outgoing[key(ins, ops[0])] = source[0], source[1], width, inverted
                outgoing[('condition',)] = source[0], source[1] + width - 1, 'sign', bool(inverted >> (width - 1) & 1)
                handled = True
            else:
                outgoing.pop(('condition',), None)
        elif mnemonic in ('add', 'sub', 'inc', 'dec', 'lea') and ops and ops[0].type == CS_OP_REG:
            source = value(ins, ops[0], outgoing)
            amount, operation = None, mnemonic
            if mnemonic == 'lea' and ops[1].type == CS_OP_MEM and not ops[1].mem.index:
                source = outgoing.get(('reg', register(ins.reg_name(ops[1].mem.base))[0]))
                amount, operation = ops[1].mem.disp, 'add'
            elif mnemonic in ('inc', 'dec'):
                amount, operation = 1, 'add' if mnemonic == 'inc' else 'sub'
            elif len(ops) == 2:
                try:
                    amount = ops[1].imm if ops[1].type == CS_OP_IMM else context.constants.value_before(ins.address, root(ins, ops[1]), header['bits'])
                except ValueError:
                    pass
            if source is not None and source[1] == 0 and source[2] == header['bits'] and amount is not None:
                steps = source[0] + ((('xor', source[3]),) if source[3] else ())
                steps += ((operation, amount & ((1 << header['bits']) - 1)),)
                outgoing[key(ins, ops[0])] = steps, 0, header['bits'], 0
                handled = True
                if mnemonic != 'lea':
                    outgoing[('condition',)] = steps, header['bits'] - 1, 'sign', False
            elif mnemonic != 'lea':
                outgoing.pop(('condition',), None)
        elif mnemonic in ('cmp', 'add', 'sub', 'and', 'or', 'inc', 'dec', 'shl', 'sar'):
            outgoing.pop(('condition',), None)
        if not handled:
            for written in ins.regs_access()[1]:
                outgoing.pop(('reg', register(ins.reg_name(written))[0]), None)
        for child in context.constants.successors(ins):
            previous = states.get(child)
            merged = outgoing if previous is None else {key: val for key, val in previous.items() if outgoing.get(key) == val}
            if previous is None or merged != previous:
                states[child] = dict(merged)
                queue.append(child)

    predicates = {}
    for ins in context.seq:
        condition = states.get(ins.address, {}).get(('condition',))
        if condition is None or not ins.mnemonic.startswith('j') or ins.mnemonic == 'jmp':
            continue
        operations, bit, kind, inverted = condition
        wanted = ({'jb': True, 'jc': True, 'jnae': True, 'jae': False, 'jnb': False, 'jnc': False} if kind == 'carry'
                  else {'jne': True, 'jnz': True, 'je': False, 'jz': False} if kind == 'zero'
                  else {'js': True, 'jns': False}).get(ins.mnemonic)
        if wanted is not None:
            predicates[ins.address] = operations, bit, wanted != inverted

    def reach(start, assignment, stops=None):
        seen, todo = set(), [start]
        while todo:
            at = todo.pop()
            if at in seen or stops and at in stops and at != start:
                continue
            seen.add(at)
            children = context.constants.successors(context.by_address[at])
            if at in predicates and len(children) == 2:
                operations, bit, wanted = predicates[at]
                field_key = operations, bit
                if field_key in assignment:
                    children = [children[0] if assignment[field_key] == wanted else children[1]]
            todo.extend(children)
        return seen

    reads = {ins.address: ins for ins in context.reads() if ins.address - context.image.base != header['read_rva']}
    refs = {} if object_calls is None else dict(object_calls)
    for ins in context.seq:
        if (ins.mnemonic not in ('call', 'jmp') or not ins.operands or ins.operands[0].type != CS_OP_IMM
                or ins.mnemonic == 'jmp' and ins.operands[0].imm - context.image.base not in set(reference_readers) | set(scalar_setters)):
            continue
        state = pointers.get(ins.address, {})
        args = {name: state.get(('reg', name)) for name in ('rcx', 'rdx', 'r8', 'r9')}
        fields = {val[1] for val in args.values() if val is not None and val[0] == 'this' and val[1] in offsets}
        if fields and (('stream', 0) in args.values() or ins.operands[0].imm - context.image.base in scalar_setters):
            _check(len(fields) == 1)
            refs[ins.address] = fields.pop()
        elif ins.operands[0].imm - context.image.base in reference_readers and ('stream', 0) in args.values():
            # A typed array helper can fill a local reference before the
            # shared merge block stores it in the authored object field.
            refs[ins.address] = None
    rows = []
    for domain, bit in sorted({(operations, bit) for operations, bit, _wanted in predicates.values()}):
        field_key = domain, bit
        yes, no = reach(entry, {field_key: True}), reach(entry, {field_key: False})
        exclusive = yes ^ no
        owned_reads = sorted(set(reads) & exclusive)
        owned_refs = sorted(set(refs) & exclusive)
        candidates = owned_reads or owned_refs
        _check(candidates, ('A native presence flag has no owned field input.', bit))
        polarities = {at in yes for at in candidates}
        _check(len(polarities) == 1)
        rows.append({'bit': bit, 'domain': domain, 'key': field_key, 'present_when_set': polarities.pop(), 'representative': min(candidates),
                     'reads': tuple(owned_reads), 'ref_calls': tuple(owned_refs)})
    owned_inputs = {at for row in rows for at in row['reads']}
    _check(set(reads) & context.returning_nodes() <= owned_inputs,
           'An original field input has no owned presence flag.')
    domains = {r['domain'] for r in rows}
    nonraw = domains - {()}
    _check(len(nonraw) <= 1, 'The native reader uses incompatible non-raw header domains.')
    canonical = next(iter(nonraw)) if nonraw else ()
    header['operations'] = canonical
    for row in rows:
        row['raw_flag'] = row['domain'] != canonical
    assignments = {r['key']: r['present_when_set'] for r in rows}
    representatives = {r['representative'] for r in rows}
    _check(len(representatives) == len(rows) and rows)
    reachable = {r['key']: reach(r['representative'], assignments) for r in rows}
    for row in rows:
        row['ancestors'] = tuple(other['key'] for other in rows if other['key'] != row['key']
                                 and row['representative'] in reachable[other['key']])
        nodes = reach(row['representative'], assignments, representatives)
        stores = []
        for at in sorted(nodes):
            ins = context.by_address[at]
            if not (ins.mnemonic in ('mov', 'movss') or ins.mnemonic.startswith('set')) or not ins.operands or ins.operands[0].type != CS_OP_MEM:
                continue
            memory = ins.operands[0].mem
            owner = pointers.get(at, {}).get(('reg', register(ins.reg_name(memory.base))[0]))
            if owner is not None and owner[0] == 'this' and not memory.index and owner[1] + memory.disp in offsets:
                stores.append({'address': at, 'offset': owner[1] + memory.disp,
                               'bits': ins.operands[0].size * 8, 'mnemonic': ins.mnemonic})
        owned_offsets = {store['offset'] for store in stores} | {refs[at] for at in row['ref_calls'] if refs[at] is not None}
        _check(len(owned_offsets) == 1, ('A serialized field has ambiguous authored object ownership.', row['bit'], owned_offsets))
        row.update(nodes=tuple(sorted(nodes)), stores=tuple(stores), offset=owned_offsets.pop())
    rows.sort(key=lambda r: (len(r['ancestors']), r['representative']))
    _check(len({len(row['ancestors']) for row in rows}) == len(rows))
    _check(len({row['offset'] for row in rows}) == len(rows))
    return header, tuple(rows)
