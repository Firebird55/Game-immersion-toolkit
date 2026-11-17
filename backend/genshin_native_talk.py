"""Own the actual Talk object and virtual stream reader from its source loader."""
from collections import Counter, deque

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Definitions, VOLATILE, register, _check
from .genshin_native_metadata import HEADER_SIZE, owns_global_pointer, pointer, root, word


def class_method_initializer(view, dispatch):
    image = view.image
    seq = image.instructions(dispatch['rva'])
    begin = next(n for n, i in enumerate(seq) if i.address - image.base == dispatch['cases'][3])
    by_address = {i.address: i for i in seq}
    lookups = {by_address[i.operands[0].imm].operands[0].imm - image.base
               for i in seq[begin:begin + 15] if i.mnemonic == 'jne' and i.operands[0].type == CS_OP_IMM
               and i.operands[0].imm < image.base + dispatch['cases'][3]
               and i.operands[0].imm in by_address and by_address[i.operands[0].imm].mnemonic == 'call'
               and by_address[i.operands[0].imm].operands[0].type == CS_OP_IMM}
    _check(len(lookups) == 1)
    lookup = image.instructions(lookups.pop())
    candidates = []
    for target in {i.operands[0].imm - image.base for i in lookup if i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM}:
        try:
            body = image.instructions(target)
        except ValueError:
            continue
        if (any(i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM and i.operands[0].imm - image.base == target for i in body)
                and any(i.mnemonic == 'mov' and i.operands[0].type == CS_OP_MEM and i.operands[0].mem.disp == 0x98 for i in body)):
            candidates.append(target)
    _check(len(candidates) == 1, 'The original class method initializer is ambiguous.')
    return candidates[0]


def root_owner(view, table, usages, arrays, paths):
    image = view.image
    source = 'Data/_BinOutput/Talk/Quest/GlobalDialog'
    owners = {row['method_rva'] for row in paths if any(literal['path'] == source for literal in row['literals'])}
    slots = {}
    for kind, identity, slot in usages.pairs:
        if kind == 1:
            slots.setdefault(slot, set()).add(identity)
    candidates = []
    for owner in sorted(owners):
        try:
            seq = image.instructions(owner)
        except ValueError:
            continue
        for at, ins in enumerate(seq[:-1]):
            call = seq[at + 1]
            if not (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_REG and ins.reg_name(ins.operands[0].reg) == 'rcx'
                    and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                    and call.mnemonic == 'call' and call.operands[0].type == CS_OP_IMM):
                continue
            delta = pointer(ins, ins.operands[1], image) - arrays[1]['array_rva']
            if delta < 0 or delta % 8 or delta // 8 not in slots:
                continue
            for typed in slots[delta // 8]:
                kind = view.bindings.describe(typed)
                if 'definition' not in kind:
                    continue
                readers = [m for m in view.methods(kind['definition']) if m['return_type']['kind'] == 2
                           and any(p['type']['index'] == table['stream'] for p in m['parameters']) and m['rva']]
                if readers:
                    _check(len(readers) == 1)
                    candidates.append({'path': source, 'loader_rva': owner, 'type': kind,
                                       'allocation_rva': call.address - image.base,
                                       'allocator_rva': call.operands[0].imm - image.base,
                                       'wrapper_reader': readers[0]})
    _check(len(candidates) == 1, 'The original Talk allocation and typed stream owner are ambiguous.')
    return candidates[0]


def _object_dispatches(image, seq, allocation_rva, vtable_base):
    """All reaching object/class aliases must originate at this allocation."""
    from .genshin_native_x64 import Constants
    cfg = Constants(seq)
    initial = image.base + allocation_rva
    children = cfg.successors(next(i for i in seq if i.address == initial))
    by_address = {i.address: i for i in seq}
    states = {at: {('reg', 'rax'): 'object'} for at in children}
    queue, iterations = deque(children), 0

    def key(ins, op):
        if op.type == CS_OP_REG:
            return ('reg', root(ins, op))
        if op.type == CS_OP_MEM and not op.mem.index:
            base = register(ins.reg_name(op.mem.base))[0]
            if base in ('rsp', 'rbp'):
                return ('stack', op.mem.disp + (cfg.frame if base == 'rbp' else 0))
        return None

    while queue:
        at = queue.popleft()
        iterations += 1
        _check(iterations <= 200000)
        ins, state = by_address[at], states[at]
        outgoing, ops = dict(state), ins.operands
        if ins.mnemonic == 'call':
            for name in VOLATILE:
                outgoing.pop(('reg', name), None)
        else:
            output, destination = None, key(ins, ops[0]) if ops else None
            if ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].size == ops[1].size == 8:
                output = state.get(key(ins, ops[1]))
                if ops[1].type == CS_OP_MEM and not ops[1].mem.index and not ops[1].mem.disp:
                    if state.get(('reg', register(ins.reg_name(ops[1].mem.base))[0])) == 'object':
                        output = 'class'
            for written in ins.regs_access()[1]:
                outgoing.pop(('reg', register(ins.reg_name(written))[0]), None)
            if destination is not None and ops[0].access & 2:
                outgoing.pop(destination, None)
                if output is not None:
                    outgoing[destination] = output
        for child in cfg.successors(ins):
            previous = states.get(child)
            merged = outgoing if previous is None else {key: val for key, val in previous.items() if outgoing.get(key) == val}
            if previous is None or previous != merged:
                states[child] = dict(merged)
                queue.append(child)
    dispatches = []
    for ins in seq:
        state = states.get(ins.address, {})
        if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_MEM
                and not ins.operands[0].mem.index and ins.operands[0].mem.disp >= vtable_base
                and (ins.operands[0].mem.disp - vtable_base) % 8 == 0
                and state.get(('reg', 'rcx')) == 'object'
                and state.get(('reg', register(ins.reg_name(ins.operands[0].mem.base))[0])) == 'class'):
            continue
        dispatches.append({'rva': ins.address - image.base, 'slot': (ins.operands[0].mem.disp - vtable_base) // 8})
    _check(len(dispatches) == 1, 'The allocated original Talk object has no unique owned virtual dispatch.')
    return dispatches[0]


def exact_reader(view, table, dispatch, owner):
    image = view.image
    initializer = class_method_initializer(view, dispatch)
    allocator = image.instructions(owner['allocator_rva'])
    setups = []
    for target in {i.operands[0].imm - image.base for i in allocator if i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM}:
        try:
            body = image.instructions(target)
        except ValueError:
            continue
        if (any(i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM and i.operands[0].imm - image.base == initializer for i in body)
                and any(i.mnemonic == 'mov' and i.operands[0].type == CS_OP_MEM and i.operands[0].mem.index
                        and i.operands[0].mem.scale == 8 and i.operands[0].size == 8 for i in body)):
            setups.append((target, body))
    _check(len(setups) == 1)
    setup_rva, setup = setups[0]
    stores = Counter(i.operands[0].mem.disp for i in setup if i.mnemonic == 'mov' and i.operands[0].type == CS_OP_MEM
                     and i.operands[0].mem.index and i.operands[0].mem.scale == 8
                     and i.operands[0].size == 8 and i.operands[0].mem.disp > 0)
    ranked = stores.most_common()
    _check(ranked and ranked[0][1] >= 3 and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]))
    vtable_base = ranked[0][0]
    actual = _object_dispatches(image, image.instructions(owner['loader_rva']), owner['allocation_rva'], vtable_base)
    definitions = Definitions(setup)
    routes = []
    for at, ins in enumerate(setup):
        if not (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_REG
                and ins.operands[1].type == CS_OP_MEM and ins.operands[1].mem.index
                and ins.operands[1].mem.scale == 4 and ins.operands[1].size == 4
                and any(i.mnemonic == 'and' and i.operands[1].type == CS_OP_IMM
                        and i.operands[1].imm == 0x1fffffff for i in setup[at + 1:at + 5])):
            continue
        reads = [n for n in range(max(0, at - 11), at) if setup[n].mnemonic == 'movsxd'
                 and setup[n].operands[1].type == CS_OP_MEM and not setup[n].operands[1].mem.index]
        if len(reads) != 1:
            continue
        n = reads[0]
        read, transform, add = setup[n:n + 3]
        if not (transform.mnemonic == 'xor' and transform.operands[1].type == CS_OP_IMM and add.mnemonic == 'add'
                and add.operands[1].type == CS_OP_REG and owns_global_pointer(image, setup, read, read.operands[1].mem,
                    view.bindings.identifiers.owner.global_rva, definitions)):
            continue
        body_defs = definitions.before(add.address, root(add, add.operands[1]))
        if not body_defs or None in body_defs:
            continue
        bodies = [next(i for i in setup if i.address == definition) for definition in body_defs]
        if not all(i.mnemonic == 'mov' and i.operands[1].type == CS_OP_MEM
                   and i.reg_name(i.operands[1].mem.base) == 'rip'
                   and pointer(i, i.operands[1], image) == view.bindings.identifiers.profile.body_global_rva for i in bodies):
            continue
        for pos in range(max(0, at - 18), at - 3):
            lea = setup[pos]
            if not (lea.mnemonic == 'lea' and lea.operands[1].type == CS_OP_MEM and not lea.operands[1].mem.index):
                continue
            following = setup[pos + 1:pos + 4]
            loads = [i for i in following if i.mnemonic == 'mov' and i.operands[1].type == CS_OP_MEM
                     and i.operands[1].size == 4 and not i.operands[1].mem.index]
            adds = [i for i in following if i.mnemonic == 'add' and i.operands[1].type == CS_OP_REG
                    and root(i, i.operands[1]) == root(lea, lea.operands[0])]
            if len(loads) != 1 or len(adds) != 1 or loads[0].operands[0].reg != adds[0].operands[0].reg:
                continue
            load = loads[0]
            type_defs = definitions.before(load.address, register(load.reg_name(load.operands[1].mem.base))[0])
            if len(type_defs) != 1 or None in type_defs:
                continue
            type_load = next(i for i in setup if i.address in type_defs)
            if not (type_load.mnemonic == 'mov' and type_load.operands[1].type == CS_OP_MEM and type_load.operands[1].mem.disp == 0x40):
                continue
            routes.append({'header_field': read.operands[1].mem.disp, 'operations': (('xor', transform.operands[1].imm & 0xffffffff),),
                           'typedef_start_field': load.operands[1].mem.disp, 'slot_addend': lea.operands[1].mem.disp})
    unique = {(r['header_field'], r['operations'], r['typedef_start_field'], r['slot_addend']) for r in routes}
    _check(routes and len(unique) == 1, 'The original encoded virtual-method route is ambiguous.')
    route = routes[0]
    section = word(view.bindings.identifiers.header, route['header_field'], route['operations'])
    td = HEADER_SIZE + view.bindings.role('type_offset') + 70 * owner['type']['definition']
    start = word(view.metadata, td + route['typedef_start_field'], ())
    index = (start + actual['slot'] + route['slot_addend']) & 0xffffffff
    encoded = word(view.metadata, HEADER_SIZE + section + 4 * index, ())
    _check(encoded >> 29 == 3)
    methods = [m for m in view.methods(owner['type']['definition']) if m['index'] == encoded & 0x1fffffff]
    _check(len(methods) == 1)
    target = methods[0]
    _check(target['rva'] and target['return_type']['kind'] == 1 and len(target['parameters']) == 1
           and target['parameters'][0]['type']['index'] == table['stream'])
    return {'owner': owner, 'reader': target, 'class_setup_rva': setup_rva, 'virtual_dispatch': actual,
            'vtable_base': vtable_base, 'table_route': route}


def dialogue_roles(view, owner, stream, usages, arrays):
    """Own node identity through actual root-array/config-cache registration."""
    from .genshin_native_voice import call_origin, _definition, _field_load, _pointer_origin
    from .genshin_native_words import Context
    root_fields = view.field_offsets(owner['type']['definition'])
    array_fields = [field for field in root_fields if field['type']['kind'] == 29 and field['type']['element'].get('kind') == 18]
    _check(len(array_fields) == 1)
    array = array_fields[0]
    node = array['type']['element']['definition']
    fields = view.field_offsets(node)
    loader = Context(view.image, owner['loader_rva'])
    definitions = Definitions(loader.seq, loader.noreturn)
    registrations = []
    class_slots = {}
    for kind, index, slot in usages.pairs:
        if kind == 1:
            class_slots.setdefault(slot, set()).add(index)
    for ins in loader.seq:
        if ins.mnemonic != 'jmp' or ins.operands[0].type != CS_OP_IMM:
            continue
        try:
            methods = [row for row in view.methods_at(ins.operands[0].imm - view.image.base)
                       if row['method']['return_type']['kind'] == 1 and len(row['method']['parameters']) == 2
                       and row['method']['parameters'][0]['type'].get('namespace') == 'System'
                       and row['method']['parameters'][0]['type'].get('name') == 'Object'
                       and row['method']['parameters'][1]['type']['kind'] == 11]
            _check(len(methods) == 1)
            # The loader also forwards null and separately typed runtime
            # alternatives. The receiver's actual root-class guard owns its
            # field namespace; a single allocation-return path is not assumed.
            body = view.image.instructions(methods[0]['method']['rva'])
            guarded = []
            for current in body:
                if not (current.mnemonic == 'mov' and current.operands[1].type == CS_OP_MEM
                        and current.reg_name(current.operands[1].mem.base) == 'rip'):
                    continue
                difference = pointer(current, current.operands[1], view.image) - arrays[1]['array_rva']
                if difference >= 0 and difference % 8 == 0 and difference // 8 in class_slots:
                    types = {view.bindings.describe(typed).get('definition') for typed in class_slots[difference // 8]}
                    if types == {owner['type']['definition']}:
                        guarded.append(current.address)
            _check(guarded and any(current.mnemonic == 'cmp' and any(op.type == CS_OP_MEM and op.mem.index
                         and op.mem.scale == 8 and op.mem.disp == -8 for op in current.operands) for current in body))
            registrations.append(methods[0])
        except ValueError:
            continue
    _check(len(registrations) == 1, 'The original Talk root registration receiver is ambiguous.')
    registration = Context(view.image, registrations[0]['method']['rva'])
    definitions = Definitions(registration.seq, registration.noreturn)
    nodes = []
    for ins in registration.seq:
        if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM:
            continue
        methods = [row for row in view.methods_at(ins.operands[0].imm - view.image.base)
                   if row['method']['return_type']['kind'] == 1 and len(row['method']['parameters']) == 1
                   and row['method']['parameters'][0]['type'].get('definition') == node]
        if not methods:
            continue
        try:
            source = _definition(registration, definitions, ins.address, 'rcx')
            _check(source.mnemonic == 'mov' and source.operands[1].type == CS_OP_REG)
            load = _definition(registration, definitions, source.address, root(source, source.operands[1]))
            _check(load.mnemonic == 'mov' and load.operands[1].type == CS_OP_MEM
                   and load.operands[1].mem.scale == 8 and load.operands[1].mem.index
                   and load.operands[1].mem.disp == 0x20 and load.operands[1].size == 8)
            origin = _pointer_origin(registration, definitions, load.address, load.reg_name(load.operands[1].mem.base))
            _check(origin == ('field', ('input', 'rcx'), array['authored_offset_word']))
            _check(len(methods) == 1)
            nodes.append(methods[0])
        except ValueError:
            continue
    _check(len(nodes) == 1, 'The actual typed root-array node registration is ambiguous.')
    context = Context(view.image, nodes[0]['method']['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    identities = []
    for ins in context.seq:
        if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM:
            continue
        try:
            _check(_pointer_origin(context, definitions, ins.address, 'r8') == ('input', 'rcx'))
            key = _field_load(context, definitions, ins.address, 'rdx')
            _check(_pointer_origin(context, definitions, key.address, key.reg_name(key.operands[1].mem.base)) == ('input', 'rcx'))
            metadata = [field for field in fields if field['authored_offset_word'] == key.operands[1].mem.disp
                        and field['type']['kind'] == 9]
            _check(len(metadata) == 1)
            tag = context.constants.value_before(ins.address, 'r9', 8)
            identities.append({'offset': key.operands[1].mem.disp, 'type_tag': tag,
                               'native_key_read_rva': key.address - view.image.base,
                               'native_registration_rva': ins.address - view.image.base})
        except ValueError:
            continue
    _check(len(identities) == 1, 'The actual node/UInt32 cache identity field is ambiguous.')
    # The ordinary key accessor and its UInt32 accessor must own exactly the
    # same original field. No table-value matching selects this field.
    number = view.named('System', 'NumberFormatter')
    formatters = [method for method in view.methods(number['definition']) if method['name'] == 'NumberToString'
                  and method['return_type']['kind'] == 14 and len(method['parameters']) == 3
                  and [p['type']['kind'] for p in method['parameters'][:2]] == [14, 9] and method['rva']]
    _check(len(formatters) == 1)
    formatted = []
    methods = view.methods(node)
    for method in methods:
        if method['parameters'] or method['return_type']['kind'] != 14 or not method['rva']:
            continue
        current = Context(view.image, method['rva'])
        defs = Definitions(current.seq, current.noreturn)
        for ins in current.seq:
            if not (ins.mnemonic in ('call', 'jmp') and ins.operands[0].type == CS_OP_IMM
                    and ins.operands[0].imm - view.image.base == formatters[0]['rva']):
                continue
            _check(current.constants.value_before(ins.address, 'rcx', 64) == 0)
            field = _field_load(current, defs, ins.address, 'rdx')
            _check(_pointer_origin(current, defs, field.address, field.reg_name(field.operands[1].mem.base)) == ('input', 'rcx'))
            formatted.append((method, field.operands[1].mem.disp))
    _check(len(formatted) == 1)
    text_offset = formatted[0][1]
    unsigned = []
    for method in methods:
        if method['parameters'] or method['return_type']['kind'] != 9 or not method['rva']:
            continue
        try:
            seq = view.image.leaf(method['rva'], 32)
        except ValueError:
            continue
        if (len(seq) == 2 and seq[0].mnemonic == 'mov' and seq[0].reg_name(seq[0].operands[0].reg) == 'eax'
                and seq[0].operands[1].type == CS_OP_MEM and seq[0].reg_name(seq[0].operands[1].mem.base) == 'rcx'
                and seq[0].operands[1].mem.disp == text_offset):
            unsigned.append(method)
    _check(len(unsigned) == 1 and any(field['authored_offset_word'] == text_offset and field['type']['kind'] == 9 for field in fields))
    _check(text_offset != identities[0]['offset'])
    next_fields = [field for field in fields if field['type']['kind'] == 29 and field['type']['element']['kind'] == 9]
    roles = [field for field in fields if field['type'].get('namespace') == 'MoleMole.Config'
             and field['type'].get('name') == 'TalkRoleEx']
    _check(len(next_fields) == len(roles) == 1)
    return {'root_array_offset': array['authored_offset_word'], 'node_definition': node,
            'root_registration': registrations[0], 'node_registration': nodes[0], 'node_identity': identities[0],
            'text_key_offset': text_offset, 'text_key_accessor': formatted[0][0], 'unsigned_text_key_accessor': unsigned[0],
            'next_dialogues_offset': next_fields[0]['authored_offset_word'],
            'role_offset': roles[0]['authored_offset_word'], 'role_definition': roles[0]['type']['definition']}
