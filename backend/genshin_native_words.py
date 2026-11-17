"""Bounded unary stream-word contracts from typed original native readers."""
from collections import deque

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, Definitions, VOLATILE, register, _check
from .genshin_native_metadata import root


class Context:
    def __init__(self, image, rva):
        self.image, self.rva = image, rva
        self.seq = image.instructions(rva)
        self.by_address = {i.address: i for i in self.seq}
        self.noreturn = set()
        for ins in self.seq:
            if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM:
                continue
            try:
                body = image.window(ins.operands[0].imm - image.base)
                if len(body) > 256:
                    continue
                target = image.instructions(ins.operands[0].imm - image.base)
            except ValueError:
                continue
            if (target[-1].mnemonic == 'int3' and all(not i.mnemonic.startswith('j')
                    and i.mnemonic not in ('ret', 'retf', 'iret') for i in target)):
                self.noreturn.add(ins.operands[0].imm)
        self.constants = Constants(self.seq, self.noreturn)

    def reads(self, width=None):
        return tuple(i for i in self.seq if i.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd', 'add', 'sub', 'xor', 'test', 'cmp')
                     and any(op.type == CS_OP_MEM and op.mem.index and op.mem.disp == 0x20
                             and op.access & 1 and (width is None or op.size == width) for op in i.operands))

    def operations(self, rva, bits, mode, endpoint=None, setters=None, argument=None):
        _check(bits in (8, 16, 32, 64) and mode in ('length', 'count', 'root_count', 'scalar', 'element', 'protected_scalar', 'argument'))
        _check((mode == 'argument' and endpoint is not None and argument in ('rcx', 'rdx', 'r8', 'r9'))
               or mode != 'argument' and argument is None)
        address, end_address = self.image.base + rva, None if endpoint is None else self.image.base + endpoint
        _check(address in self.by_address)
        first = self.by_address[address]
        _check(first.operands[0].type == CS_OP_REG)
        name, mask = root(first, first.operands[0]), (1 << bits) - 1
        initial = ()
        if first.mnemonic in ('add', 'xor', 'sub'):
            seed = self.constants.value_before(address, name, bits)
            initial = ((first.mnemonic, seed),) if first.mnemonic != 'sub' else (('xor', mask), ('add', (seed + 1) & mask))
        else:
            _check(first.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd'))

        def location(ins, op):
            if op.type == CS_OP_REG:
                return ('reg', root(ins, op))
            if op.type == CS_OP_MEM and not op.mem.index:
                base = register(ins.reg_name(op.mem.base))[0]
                if base in ('rsp', 'rbp'):
                    return ('stack', base, op.mem.disp)
            return None

        def value(ins, op, state):
            return state.get(location(ins, op))

        def constant(ins, op):
            if op.type == CS_OP_IMM:
                return op.imm & mask
            _check(op.type == CS_OP_REG)
            return self.constants.value_before(ins.address, root(ins, op), bits) & mask

        def terminal(ins, state):
            ops = ins.operands
            if mode == 'argument' and ins.address == end_address:
                _check(ins.mnemonic == 'call' and ops[0].type == CS_OP_IMM)
                return state.get(('reg', argument))
            if mode == 'scalar' and ins.address == end_address:
                _check(ins.mnemonic in ('mov', 'movss') and ops[0].type == CS_OP_MEM)
                return value(ins, ops[1], state)
            if (mode == 'element' and ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == CS_OP_MEM
                    and ops[0].mem.index and ops[0].mem.disp == 0x20 and ops[0].mem.scale == bits // 8
                    and ops[0].size == bits // 8):
                return value(ins, ops[1], state)
            if ins.mnemonic == 'call' and ops[0].type == CS_OP_IMM:
                if mode == 'count':
                    return state.get(('reg', 'rdx'))
                if mode == 'protected_scalar' and setters and ops[0].imm - self.image.base in setters:
                    return state.get(('reg', setters[ops[0].imm - self.image.base]))
            if mode == 'length' and ins.mnemonic.startswith('j') and ins.mnemonic != 'jmp':
                return state.get(('condition',))
            if mode == 'root_count' and ins.mnemonic in ('cmp', 'test') and all(op.type == CS_OP_REG for op in ops):
                candidates = {value(ins, op, state) for op in ops} - {None}
                _check(len(candidates) <= 1)
                return next(iter(candidates)) if candidates else None
            return None

        def transfer(ins, state):
            result = dict(state)
            ops, mnemonic = ins.operands, ins.mnemonic
            if mnemonic == 'call':
                for key in list(result):
                    if key[0] in ('stack', 'condition') or key[0] == 'reg' and key[1] in VOLATILE:
                        result.pop(key)
                return result
            if mnemonic.startswith('j') or mnemonic in ('nop', 'ret', 'int3'):
                return result
            if mnemonic in ('test', 'cmp'):
                candidates = {value(ins, op, state) for op in ops} - {None}
                result.pop(('condition',), None)
                if len(candidates) == 1:
                    result[('condition',)] = candidates.pop()
                return result
            if not ops:
                return result
            destination = location(ins, ops[0])
            output = None
            if mnemonic in ('mov', 'movzx', 'movsx', 'movsxd', 'movss', 'movd', 'movaps') and len(ops) == 2:
                output = value(ins, ops[1], state)
            elif mnemonic in ('inc', 'dec') and destination in state:
                output = state[destination] + (('add' if mnemonic == 'inc' else 'sub', 1),)
            elif mnemonic in ('add', 'sub', 'xor') and len(ops) == 2:
                a, b = value(ins, ops[0], state), value(ins, ops[1], state)
                try:
                    if a is not None and b is None:
                        output = a + ((mnemonic, constant(ins, ops[1])),)
                    elif a is None and b is not None:
                        seed = constant(ins, ops[0])
                        output = b + ((mnemonic, seed),) if mnemonic != 'sub' else b + (('xor', mask), ('add', (seed + 1) & mask))
                except ValueError:
                    pass
            elif mnemonic == 'lea' and len(ops) == 2 and ops[1].type == CS_OP_MEM:
                memory = ops[1].mem
                source = ('reg', register(ins.reg_name(memory.base))[0])
                if not memory.index and source in state:
                    output = state[source] + (('add', memory.disp & mask),)
            writes = {('reg', register(ins.reg_name(r))[0]) for r in ins.regs_access()[1]}
            for key in writes:
                result.pop(key, None)
            if destination is not None:
                result.pop(destination, None)
                if output is not None:
                    result[destination] = output
            # MOV/LEA preserve flags. Arithmetic may own the tested length.
            if mnemonic in ('add', 'sub', 'xor', 'inc', 'dec', 'and', 'or', 'shl', 'shr', 'sar'):
                result.pop(('condition',), None)
                if output is not None:
                    result[('condition',)] = output
            return result

        children = self.constants.successors(first)
        _check(children)
        initial_state = {('reg', name): initial}
        if first.mnemonic in ('add', 'sub', 'xor'):
            initial_state[('condition',)] = initial
        states, queue, iterations = {child: dict(initial_state) for child in children}, deque(children), 0
        while queue:
            at = queue.popleft()
            iterations += 1
            _check(iterations <= 200000 and len(states) <= 4096, 'The native stream-word slice exceeds its bound.')
            ins, state = self.by_address[at], states[at]
            if terminal(ins, state) is not None:
                continue
            outgoing = transfer(ins, state)
            for child in self.constants.successors(ins):
                previous = states.get(child)
                merged = outgoing if previous is None else {key: val for key, val in previous.items() if outgoing.get(key) == val}
                if previous is None or merged != previous:
                    states[child] = dict(merged)
                    queue.append(child)
        answers = {answer for at, state in states.items() if (answer := terminal(self.by_address[at], state)) is not None}
        _check(len(answers) == 1, ('The native stream-word result is missing or ambiguous.', rva, bits, mode, len(answers)))
        return answers.pop()

    def false_value(self, rva):
        at = next(n for n, ins in enumerate(self.seq) if ins.address - self.image.base == rva)
        first = self.seq[at]
        if (first.mnemonic == 'cmp' and first.operands[0].type == CS_OP_MEM and first.operands[0].size == 1
                and first.operands[1].type == CS_OP_IMM):
            return first.operands[1].imm & 255
        name = root(first, first.operands[0])
        matches = [ins.operands[1].imm & 255 for ins in self.seq[at + 1:at + 8]
                   if ins.mnemonic == 'cmp' and ins.operands[0].type == CS_OP_REG
                   and root(ins, ins.operands[0]) == name and ins.operands[1].type == CS_OP_IMM]
        _check(len(matches) == 1, 'The original boolean false encoding is ambiguous.')
        return matches[0]

    def completed_scalar(self, endpoint, steps, bits=32):
        """Include proved in-place writes before the next control boundary."""
        position = next(n for n, ins in enumerate(self.seq) if ins.address - self.image.base == endpoint)
        store = self.seq[position]
        _check(bits in (32, 64) and store.mnemonic in ('mov', 'movss') and store.operands[0].type == CS_OP_MEM
               and store.operands[0].size == bits // 8 and store.operands[1].type == CS_OP_REG
               and store.operands[1].size == bits // 8)
        memory = store.operands[0].mem
        state = {root(store, store.operands[1]): tuple(steps)}
        value, mask = tuple(steps), (1 << bits) - 1

        def same(op):
            return (op.type == CS_OP_MEM and op.size == bits // 8 and op.mem.base == memory.base
                    and op.mem.index == memory.index and op.mem.scale == memory.scale and op.mem.disp == memory.disp)

        for ins in self.seq[position + 1:position + 34]:
            ops = ins.operands
            if ins.mnemonic in ('cmp', 'test', 'bt', 'call', 'ret', 'int3') or ins.mnemonic.startswith('j'):
                return value
            if not ops:
                continue
            for op in ops:
                if (op.type == CS_OP_MEM and op.access & 2 and op.mem.base == memory.base
                        and op.mem.index == memory.index and op.mem.scale == memory.scale
                        and op.mem.disp < memory.disp + bits // 8 and memory.disp < op.mem.disp + op.size):
                    _check(same(op), 'A partial post-store scalar write has no whole-word contract.')
            if ins.mnemonic in ('mov', 'movss') and len(ops) == 2:
                destination, source = ops
                if same(destination):
                    _check(source.type == CS_OP_REG and root(ins, source) in state)
                    value = state[root(ins, source)]
                elif destination.type == CS_OP_REG:
                    target = root(ins, destination)
                    old = (state.get(root(ins, source)) if source.type == CS_OP_REG else value if same(source) else None)
                    if destination.size != bits // 8 or source.size != bits // 8:
                        old = None
                    state.pop(target, None)
                    if old is not None:
                        state[target] = old
                continue
            if ins.mnemonic in ('add', 'sub', 'xor') and len(ops) == 2:
                destination, source = ops
                if same(destination):
                    _check(source.type == CS_OP_IMM)
                    value += ((ins.mnemonic, source.imm & mask),)
                    continue
                if destination.type == CS_OP_REG:
                    target = root(ins, destination)
                    previous = state.pop(target, None)
                    if destination.size != bits // 8:
                        continue
                    if previous is not None:
                        try:
                            operand = source.imm & mask if source.type == CS_OP_IMM else self.constants.value_before(ins.address, root(ins, source), bits)
                        except (ValueError, AttributeError):
                            continue
                        state[target] = previous + ((ins.mnemonic, operand),)
                    elif same(source):
                        seed = self.constants.value_before(ins.address, target, bits)
                        state[target] = (value + ((ins.mnemonic, seed),) if ins.mnemonic != 'sub'
                                         else value + (('xor', mask), ('add', (seed + 1) & mask)))
                    continue
            if any(same(op) and op.access & 2 for op in ops):
                raise ValueError('The native post-store scalar transformation is unsupported.')
            for written in ins.regs_access()[1]:
                state.pop(register(ins.reg_name(written))[0], None)
        raise ValueError('The native post-store scalar has no bounded control endpoint.')

    def cipher(self, nodes):
        definitions = Definitions(self.seq, self.noreturn)
        candidates = set()
        for ins in self.seq:
            if not (ins.address in nodes and ins.mnemonic in ('add', 'xor') and len(ins.operands) == 2
                    and all(op.type == CS_OP_REG and op.size == 8 for op in ins.operands)):
                continue
            incoming = definitions.before(ins.address, root(ins, ins.operands[0]))
            if None in incoming or not incoming:
                continue
            loads = [self.by_address[at] for at in incoming]
            if not all(load.mnemonic == 'mov' and len(load.operands) == 2
                       and load.operands[1].type == CS_OP_MEM and load.operands[1].size == 8
                       and not load.operands[1].mem.index and load.operands[1].mem.disp in (0, 8, 16, 24)
                       and load.reg_name(load.operands[1].mem.base) not in ('rip', 'rbp', 'rsp') for load in loads):
                continue
            try:
                key = self.constants.value_before(ins.address, root(ins, ins.operands[1]), 64)
            except ValueError:
                continue
            candidates.add((key, ins.mnemonic))
        _check(len(candidates) == 1, 'The original string cipher operands are missing or ambiguous.')
        return candidates.pop()
