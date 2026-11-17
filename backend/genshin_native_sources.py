"""Native-owned original source-index dictionary bootstrap.

Only actual path owners and their typed native calls select a reader. This does
not yet establish source-group schemas or nullable Talk lookup policy.
"""
from . import genshin_original_dialogue as o
from collections import deque

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Definitions, VOLATILE, register, _check
from .genshin_native_metadata import pointer, root, owns_global_pointer
from .genshin_native_words import Context
from .genshin_native_voice import call_origin, class_of_call, _field_load, _pointer_origin


def index_reader(view, paths, stream):
    sources = {}
    owners = set()
    for row in paths:
        selected = {literal['path'] for literal in row['literals'] if '_BinOutput/IndexDic/' in literal['path']}
        if not selected:
            continue
        declared = {owner['type']['definition'] for owner in row['owners']}
        _check(len(declared) == 1, 'An original source-index path has no unique metadata owner.')
        owners.update(declared)
        for path in selected:
            sources.setdefault(path, set()).add(row['method_rva'])
    _check(sources and len(owners) == 1, 'The original source-index manager is ambiguous.')
    definition = owners.pop()
    loaders = [method for method in view.methods(definition) if method['rva']
               and method['return_type']['kind'] == 1 and len(method['parameters']) == 2
               and [parameter['type']['kind'] for parameter in method['parameters']] == [14, 21]]
    _check(len(loaders) == 1, 'The original string-to-index loader is ambiguous.')
    loader = loaders[0]
    context = Context(view.image, loader['rva'])
    calls = {ins.operands[0].imm - view.image.base for ins in context.seq
             if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM}
    readers = []
    for target in calls:
        for declared in view.methods_at(target):
            owner, method = declared['owner'], declared['method']
            if (method['return_type']['kind'] == 1 and len(method['parameters']) == 2
                    and method['parameters'][0]['type']['index'] == stream
                    and method['parameters'][1]['type']['kind'] == 21):
                readers.append((owner, method))
    _check(len(readers) == 1, 'The actual source-index stream decoder is ambiguous.')
    owner, reader = readers[0]
    context = Context(view.image, reader['rva']); reads = context.reads()
    _check(len(reads) == 3)
    widths = [max(op.size for op in ins.operands if op.type == CS_OP_MEM and op.mem.index and op.mem.disp == 0x20)
              for ins in reads]
    _check(widths == [4, 4, 8], 'The source index is not an owned UInt32/UInt64 dictionary.')
    following = context.seq[context.seq.index(reads[-1]) + 1:]
    inserts = [ins for ins in following if ins.mnemonic == 'call']
    _check(inserts and inserts[0].operands[0].type == CS_OP_IMM)
    insert = inserts[0].address - view.image.base
    contract = o.Dictionary(
        o.Word(32, context.operations(reads[0].address - view.image.base, 32, 'length')),
        o.Word(32, context.operations(reads[1].address - view.image.base, 32, 'argument', insert, argument='rdx')),
        o.Word(64, context.operations(reads[2].address - view.image.base, 64, 'argument', insert, argument='r8')),
    )
    return {'manager_definition': definition, 'loader': loader, 'reader_owner': owner, 'reader': reader, 'stream': stream,
            'insert_rva': insert, 'paths': tuple(sorted(sources)),
            'path_methods': {path: tuple(sorted(methods)) for path, methods in sources.items()}, 'contract': contract}


def _argument_load(context, definitions, address, name, depth=0):
    _check(depth < 16)
    incoming = definitions.before(address, name)
    _check(incoming and None not in incoming)
    result = set()
    for at in incoming:
        ins = context.by_address[at]
        if (ins.mnemonic == 'mov' and len(ins.operands) == 2 and all(op.type == CS_OP_REG and op.size == 8 for op in ins.operands)):
            result.add(_argument_load(context, definitions, at, root(ins, ins.operands[1]), depth + 1))
        else:
            result.add(at)
    _check(len(result) == 1, 'The source-index argument has conflicting origins.')
    return result.pop()


def index_caches(view, paths, owned):
    """Exact path argument -> typed loader out-value -> same native cache."""
    candidates = {}
    grouped = {}
    for row in paths:
        if any(literal['path'] in owned['paths'] for literal in row['literals']):
            grouped.setdefault(row['method_rva'], []).append(row)
    for target, references in grouped.items():
        try:
            context = Context(view.image, target)
        except ValueError:
            continue
        definitions = Definitions(context.seq, context.noreturn)
        outputs = {}
        for position, call in enumerate(context.seq):
            if not (call.mnemonic == 'call' and call.operands[0].type == CS_OP_IMM
                    and call.operands[0].imm - view.image.base in {owned['loader']['rva'], owned.get('reader', {}).get('rva')}):
                continue
            try:
                source_call = call.address
                if call.operands[0].imm - view.image.base != owned['loader']['rva']:
                    source_call = call_origin(context, call.address, 'rcx', definitions)
                    opened = context.by_address[source_call]
                    declared = view.methods_at(opened.operands[0].imm - view.image.base)
                    _check(declared and all(row['method']['return_type']['index'] == owned['stream']
                           and row['method']['parameters'] and row['method']['parameters'][0]['type']['kind'] == 14
                           for row in declared), 'The source-index stream is not owned by a typed path opener.')
                source = _argument_load(context, definitions, source_call, 'rcx')
                matches = {literal['path'] for row in references
                           if row['reference_rva'] + view.image.base == source
                           for literal in row['literals'] if literal['path'] in owned['paths']}
                _check(len(matches) == 1)
                output = context.by_address[_argument_load(context, definitions, call.address, 'rdx')]
                _check(output.mnemonic == 'lea' and output.operands[1].type == CS_OP_MEM
                       and not output.operands[1].mem.index)
                location = _stack_location(context, output, output.operands[1])
                _check(location is not None)
                outputs[call.address] = matches.pop(), location
            except ValueError:
                continue
        if not outputs:
            continue
        states = _out_states(context, outputs)
        for at, state in states.items():
            ins = context.by_address[at]
            if not (ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == CS_OP_MEM
                    and ins.operands[1].type == CS_OP_REG and ins.operands[0].size == ins.operands[1].size == 8
                    and not ins.operands[0].mem.index and ins.operands[0].mem.disp >= 0):
                continue
            dst, src = ins.operands
            value, arena = state.get(('reg', root(ins, src))), state.get(('reg', ins.reg_name(dst.mem.base)))
            if value and arena and value[0] == 'out' and arena[0] == 'arena':
                call_at = value[1]; path = outputs[call_at][0]
                candidates.setdefault(path, []).append({'path': path, 'loader_rva': target,
                    'loader_call_rva': call_at - view.image.base, 'store_rva': at - view.image.base,
                    'arena_global_rva': arena[1], 'cache_offset': dst.mem.disp})
    result = []
    for path, rows in sorted(candidates.items()):
        _check(len({(row['arena_global_rva'], row['cache_offset']) for row in rows}) == 1,
               'One source-index path writes conflicting native caches.')
        result.append(rows[0])
    _check(result, 'No original source-index cache has a proved typed path/out-value route.')
    return {'caches': tuple(result), 'unresolved_paths': tuple(sorted(set(owned['paths']) - set(candidates)))}


def _stack_location(context, ins, operand):
    if operand.type != CS_OP_MEM or operand.mem.index:
        return None
    base = ins.reg_name(operand.mem.base)
    if base not in ('rsp', 'rbp'):
        return None
    return operand.mem.disp + (context.constants.frame if base == 'rbp' else 0)


def _out_states(context, outputs):
    """Must-origins across native branches; local out addresses are explicit."""
    first = context.seq[0].address
    states, queue, iterations = {first: {}}, deque((first,)), 0
    while queue:
        at = queue.popleft(); iterations += 1
        _check(iterations <= 200000)
        ins, state = context.by_address[at], states[at]
        result, ops = dict(state), ins.operands
        if ins.mnemonic == 'call':
            for name in VOLATILE:
                result.pop(('reg', name), None)
            # A callee can overwrite our local pointer only when given its
            # address. Other calls may mutate a dictionary but cannot replace
            # the caller's unpassed local pointer through the x64 call ABI.
            for name in ('rcx', 'rdx', 'r8', 'r9'):
                value = state.get(('reg', name))
                if value and value[0] == 'address':
                    result.pop(('stack', value[1]), None)
            if at in outputs:
                result['stack', outputs[at][1]] = ('out', at)
        elif not ins.mnemonic.startswith('j') and ins.mnemonic not in ('cmp', 'test', 'ret', 'nop', 'int3'):
            writes = {register(ins.reg_name(reg))[0] for reg in ins.regs_access()[1]}
            for name in writes:
                result.pop(('reg', name), None)
            if ops and ops[0].type == CS_OP_MEM and ops[0].access & 2:
                offset = _stack_location(context, ins, ops[0])
                address = state.get(('reg', ins.reg_name(ops[0].mem.base)))
                if offset is None and not ops[0].mem.index and address and address[0] == 'address':
                    offset = address[1] + ops[0].mem.disp
                if offset is not None:
                    for key in list(result):
                        if key[0] == 'stack' and key[1] < offset + ops[0].size and offset < key[1] + 8:
                            result.pop(key)
                if len(ops) == 2 and ops[1].type == CS_OP_REG:
                    value = state.get(('reg', root(ins, ops[1])))
                    if value and value[0] == 'address':
                        # An address copied into outgoing arguments or other
                        # memory may escape. It cannot keep a proved local
                        # out-value merely because RCX..R9 omit that address.
                        result.pop(('stack', value[1]), None)
            if len(ops) == 2 and ops[0].type == CS_OP_REG and ops[0].size == 8:
                value, dst, src = None, ('reg', root(ins, ops[0])), ops[1]
                if ins.mnemonic == 'mov' and src.size == 8:
                    if src.type == CS_OP_REG:
                        value = state.get(('reg', root(ins, src)))
                    elif src.type == CS_OP_MEM:
                        offset = _stack_location(context, ins, src)
                        if offset is not None:
                            value = state.get(('stack', offset))
                        elif ins.reg_name(src.mem.base) == 'rip':
                            value = ('arena', pointer(ins, src, context.image))
                elif ins.mnemonic == 'lea':
                    offset = _stack_location(context, ins, src)
                    if offset is not None:
                        value = ('address', offset)
                if value is not None:
                    result[dst] = value
        for successor in context.constants.successors(ins):
            if successor not in states:
                states[successor] = result.copy(); queue.append(successor)
            else:
                common = {key: value for key, value in states[successor].items() if result.get(key) == value}
                if common != states[successor]:
                    states[successor] = common; queue.append(successor)
    return states


def cache_getters(view, caches, resource_definition):
    """Typed UInt32/out-UInt64 lookups that read the proved index arena."""
    result = []
    for method in view.methods(resource_definition):
        if (not method['rva'] or method['return_type']['kind'] != 2
                or [p['type']['kind'] for p in method['parameters']] != [9, 11]):
            continue
        try:
            context = Context(view.image, method['rva'])
        except ValueError:
            continue
        definitions = Definitions(context.seq, context.noreturn)
        reads = []
        for ins in context.seq:
            for operand in ins.operands:
                if operand.type != CS_OP_MEM or not operand.access & 1 or operand.mem.index or operand.size != 8:
                    continue
                for source in caches['caches']:
                    if (operand.mem.disp == source['cache_offset'] and owns_global_pointer(view.image, context.seq, ins,
                            operand.mem, source['arena_global_rva'], definitions)):
                        reads.append({'path': source['path'], 'read_rva': ins.address - view.image.base,
                                      'arena_global_rva': source['arena_global_rva'], 'cache_offset': source['cache_offset']})
        if reads:
            result.append({'method': method, 'reads': tuple(reads)})
    _check(result, 'The original index caches have no typed identity getters.')
    return tuple(result)


def indexed_roots(view, getters, resource_definition, stream, allocator, usages, arrays):
    """Actual getter caller -> native class allocation -> called stream reader."""
    lookup = {row['method']['rva']: row for row in getters}
    result, unresolved = [], []
    for method in view.methods(resource_definition):
        if not method['rva']:
            continue
        try:
            context = Context(view.image, method['rva'])
        except ValueError:
            continue
        calls = [ins for ins in context.seq if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM]
        used = [call for call in calls if call.operands[0].imm - view.image.base in lookup]
        if not used:
            continue
        targets = {call.operands[0].imm - view.image.base for call in calls}
        roots = []
        for call in calls:
            if call.operands[0].imm - view.image.base != allocator:
                continue
            try:
                typed = class_of_call(view, context, call.address, usages, arrays)
            except ValueError:
                continue
            readers = [reader for reader in view.methods(typed['definition']) if reader['rva'] in targets
                       and reader['return_type']['kind'] == 1 and len(reader['parameters']) == 1
                       and reader['parameters'][0]['type']['index'] == stream]
            if not readers:
                continue
            _check(len(readers) == 1, 'An index-owned allocated root calls conflicting typed readers.')
            roots.append({'type': typed, 'allocation_rva': call.address - view.image.base, 'reader': readers[0]})
        source_paths = tuple(sorted({read['path'] for call in used
                                    for read in lookup[call.operands[0].imm - view.image.base]['reads']}))
        item = {'paths': source_paths, 'loader': method, 'roots': tuple(roots),
                'getter_calls': tuple({'call_rva': call.address - view.image.base,
                                      'getter_rva': call.operands[0].imm - view.image.base} for call in used)}
        (result if roots else unresolved).append(item)
    _check(result, 'The native index identity getters have no owned root reader callers.')
    return {'roots': tuple(result), 'other_getter_callers': tuple(unresolved)}


def _integer_origin(context, definitions, address, name, depth=0):
    _check(depth < 16)
    incoming = definitions.before(address, name)
    if incoming == frozenset({None}):
        return 'input', name
    _check(incoming and None not in incoming)
    values = set()
    for at in incoming:
        ins = context.by_address[at]
        _check(ins.mnemonic == 'mov' and all(op.type == CS_OP_REG and op.size >= 4 for op in ins.operands))
        values.add(_integer_origin(context, definitions, at, root(ins, ins.operands[1]), depth + 1))
    _check(len(values) == 1)
    return values.pop()


def descriptor_identity(view, collection, attributes):
    """Typed descriptor forwarding -> UInt32 store -> same nullable cache."""
    node = collection['node_definition']
    first = collection['node_registration']
    positions = [index for index, p in enumerate(first['method']['parameters']) if p['type'].get('definition') == node]
    _check(len(positions) == 1 and attributes.argument_register(first['method'], positions[0]) == first['node_argument'])
    queue = deque(((first['method']['rva'], first['node_argument'], ()),))
    seen, results = set(), []
    while queue:
        rva, argument, chain = queue.popleft()
        if (rva, argument) in seen:
            continue
        _check(len(chain) <= 4 and len(seen) < 16)
        seen.add((rva, argument))
        context = Context(view.image, rva); definitions = Definitions(context.seq, context.noreturn)
        for ins in context.seq:
            if ins.mnemonic not in ('call', 'jmp') or ins.operands[0].type != CS_OP_IMM:
                continue
            target = ins.operands[0].imm - view.image.base
            declared = [row for row in view.methods_at(target) if row['method']['return_type']['kind'] == 1
                        and sum(p['type'].get('definition') == node for p in row['method']['parameters']) == 1]
            for row in declared:
                method = row['method']
                if (len(method['parameters']) == 2 and method['parameters'][0]['type']['kind'] == 9
                        and method['parameters'][1]['type'].get('definition') == node):
                    try:
                        key_arg, value_arg = (attributes.argument_register(method, n) for n in (0, 1))
                        _check(_pointer_origin(context, definitions, ins.address, value_arg) == ('input', argument))
                        key = _field_load(context, definitions, ins.address, key_arg)
                        _check(_pointer_origin(context, definitions, key.address, key.reg_name(key.operands[1].mem.base)) == ('input', argument))
                        fields = [f for f in view.field_offsets(node) if f['authored_offset_word'] == key.operands[1].mem.disp
                                  and f['type']['kind'] == 9]
                        _check(len(fields) == 1)
                        store = Context(view.image, target); stores = Definitions(store.seq, store.noreturn)
                        caches = []
                        for write in store.seq:
                            if write.mnemonic not in ('call', 'jmp') or write.operands[0].type != CS_OP_IMM:
                                continue
                            try:
                                _check(_pointer_origin(store, stores, write.address, 'r8') == ('input', value_arg)
                                       and _integer_origin(store, stores, write.address, 'rdx') == ('input', key_arg))
                                receiver = _field_load(store, stores, write.address, 'rcx', 8)
                                origin = _pointer_origin(store, stores, receiver.address, receiver.reg_name(receiver.operands[1].mem.base))
                                _check(origin[0] == 'global')
                                caches.append({'arena_global_rva': origin[1], 'cache_offset': receiver.operands[1].mem.disp,
                                               'insert_rva': write.address - view.image.base})
                            except ValueError:
                                continue
                        _check(len(caches) == 1)
                        cache, getters = caches[0], []
                        for getter in view.methods(row['owner']['definition']):
                            if (not getter['rva'] or getter['return_type'].get('definition') != node
                                    or [p['type']['kind'] for p in getter['parameters']] != [9]):
                                continue
                            current = Context(view.image, getter['rva']); defs = Definitions(current.seq, current.noreturn)
                            reads = [i.address - view.image.base for i in current.seq for op in i.operands
                                     if op.type == CS_OP_MEM and op.access & 1 and op.size == 8 and not op.mem.index
                                     and op.mem.disp == cache['cache_offset'] and owns_global_pointer(view.image, current.seq,
                                         i, op.mem, cache['arena_global_rva'], defs)]
                            lookups = []
                            for lookup in current.seq:
                                if lookup.mnemonic != 'call' or lookup.operands[0].type != CS_OP_IMM:
                                    continue
                                try:
                                    getter_argument = attributes.argument_register(getter, 0)
                                    _check(_integer_origin(current, defs, lookup.address, 'rdx') == ('input', getter_argument))
                                    receiver = _field_load(current, defs, lookup.address, 'rcx', 8)
                                    origin = _pointer_origin(current, defs, receiver.address, receiver.reg_name(receiver.operands[1].mem.base))
                                    _check(origin == ('global', cache['arena_global_rva'])
                                           and receiver.operands[1].mem.disp == cache['cache_offset'])
                                    lookups.append(lookup.address - view.image.base)
                                except ValueError:
                                    continue
                            if reads and lookups:
                                getters.append({'method': getter, 'reads': tuple(reads), 'key_lookups': tuple(lookups)})
                        _check(getters)
                        results.append({'identity_offset': fields[0]['authored_offset_word'], 'cache': cache,
                                        'store_method': row, 'nullable_getters': tuple(getters),
                                        'field_read_rva': key.address - view.image.base, 'chain': chain})
                    except ValueError:
                        pass
                position = next(n for n, p in enumerate(method['parameters']) if p['type'].get('definition') == node)
                try:
                    forwarded = attributes.argument_register(method, position)
                    _check(_pointer_origin(context, definitions, ins.address, forwarded) == ('input', argument))
                    queue.append((target, forwarded, chain + ((rva, ins.address - view.image.base, target, forwarded),)))
                except ValueError:
                    continue
    _check(results and len({(r['identity_offset'], r['cache']['arena_global_rva'], r['cache']['cache_offset'])
                            for r in results}) == 1, 'The original descriptor identity/cache ownership is ambiguous.')
    return {'definition': node, 'identity_offset': results[0]['identity_offset'], 'proofs': tuple(results)}


def descriptor_asset(view, resource_definition, definition, stream, attributes):
    """Exact native signature/field -> original UInt64 stream opening."""
    results, unsupported = [], []
    for method in view.methods(resource_definition):
        positions = [n for n, p in enumerate(method['parameters']) if p['type'].get('definition') == definition]
        if not method['rva'] or len(positions) != 1:
            continue
        try:
            argument = attributes.argument_register(method, positions[0])
        except ValueError:
            unsupported.append(method)
            continue
        context = Context(view.image, method['rva']); definitions = Definitions(context.seq, context.noreturn)
        for ins in context.seq:
            if ins.mnemonic not in ('call', 'jmp') or ins.operands[0].type != CS_OP_IMM:
                continue
            methods = [row for row in view.methods_at(ins.operands[0].imm - view.image.base)
                       if row['method']['return_type']['index'] == stream and row['method']['parameters']
                       and row['method']['parameters'][0]['type']['kind'] == 11]
            for opener in methods:
                try:
                    source_argument = attributes.argument_register(opener['method'], 0)
                    source = _field_load(context, definitions, ins.address, source_argument, 8)
                    _check(_pointer_origin(context, definitions, source.address, source.reg_name(source.operands[1].mem.base)) == ('input', argument))
                    fields = [field for field in view.field_offsets(definition) if field['authored_offset_word'] == source.operands[1].mem.disp
                              and field['type']['kind'] == 11]
                    _check(len(fields) == 1)
                    results.append({'asset_offset': fields[0]['authored_offset_word'], 'method': method,
                                    'descriptor_argument': argument, 'native_method_flags': attributes.flags(method['index']),
                                    'field_read_rva': source.address - view.image.base,
                                    'stream_open_rva': ins.address - view.image.base, 'stream_opener': opener})
                except ValueError:
                    continue
    _check(results and len({row['asset_offset'] for row in results}) == 1,
           'The original descriptor UInt64 asset role has no unique native owner.')
    return {'definition': definition, 'asset_offset': results[0]['asset_offset'], 'proofs': tuple(results),
            'other_unsupported_signature_candidates': tuple(unsupported)}
