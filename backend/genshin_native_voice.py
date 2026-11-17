"""Voice source paths, resource wrappers and original dictionary reader owners."""
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Definitions, _check
from .genshin_native_metadata import pointer, root
from .genshin_native_fields import pointer_states
from .genshin_native_words import Context


def source_manager(view, paths):
    owners = {owner['type']['definition'] for row in paths
              if any(literal['path'].startswith('Data/_BinOutput/Voice/') for literal in row['literals'])
              for owner in row['owners'] if owner['method_name'] == '.cctor'}
    _check(len(owners) == 1, 'The original Voice source manager is missing or ambiguous.')
    definition = owners.pop()
    methods = view.methods(definition)
    constructors = [method for method in methods if method['name'] == '.cctor' and method['rva']]
    _check(len(constructors) == 1)
    return {'owner': view.bindings.rows[definition], 'methods': methods, 'constructor': constructors[0]}


def call_origin(context, address, name, definitions=None, depth=0):
    _check(depth < 16)
    definitions = definitions or Definitions(context.seq, context.noreturn)
    incoming = definitions.before(address, name)
    _check(incoming and None not in incoming)
    result = set()
    for at in incoming:
        ins = context.by_address[at]
        if ins.mnemonic == 'call' and name == 'rax' and ins.operands[0].type == CS_OP_IMM:
            result.add(at)
        elif (ins.mnemonic == 'mov' and len(ins.operands) == 2
              and all(op.type == CS_OP_REG and op.size == 8 for op in ins.operands)):
            result.add(call_origin(context, at, root(ins, ins.operands[1]), definitions, depth + 1))
        else:
            raise ValueError('The native value has no owned call-return origin.')
    _check(len(result) == 1)
    return result.pop()


def class_of_call(view, context, address, usages, arrays):
    definitions = Definitions(context.seq, context.noreturn)
    incoming = definitions.before(address, 'rcx')
    _check(incoming and None not in incoming)
    slots = {}
    for kind, identity, slot in usages.pairs:
        if kind == 1:
            slots.setdefault(slot, set()).add(identity)
    types = {}
    for at in incoming:
        load = context.by_address[at]
        _check(load.mnemonic == 'mov' and load.operands[1].type == CS_OP_MEM
               and load.reg_name(load.operands[1].mem.base) == 'rip')
        difference = pointer(load, load.operands[1], view.image) - arrays[1]['array_rva']
        _check(difference >= 0 and difference % 8 == 0 and difference // 8 in slots)
        for typed in slots[difference // 8]:
            row = view.bindings.describe(typed)
            _check('definition' in row)
            types[row['definition']] = row
    _check(len(types) == 1, 'The native allocation/resource class is ambiguous.')
    return next(iter(types.values()))


def path_hashes(view, manager, paths):
    context = Context(view.image, manager['constructor']['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    result = {}
    for row in paths:
        if row['method_rva'] != manager['constructor']['rva']:
            continue
        values = {literal['path'] for literal in row['literals'] if literal['path'] in (
            'Data/_BinOutput/Voice/Lut/Lut', 'Data/_BinOutput/Voice/Emo/Emo',
            'Data/_BinOutput/Voice/Items/Inner', 'Data/_BinOutput/Voice/ExternalVoices')}
        if not values:
            continue
        _check(len(values) == 1)
        position = next(n for n, ins in enumerate(context.seq) if ins.address - view.image.base == row['reference_rva'])
        calls = [n for n in range(position + 1, min(position + 6, len(context.seq)))
                 if context.seq[n].mnemonic == 'call']
        _check(calls)
        call_at = calls[0]
        call = context.seq[call_at]
        _check(definitions.before(call.address, 'rcx') == frozenset({context.seq[position].address}))
        stores = [ins for ins in context.seq[call_at + 1:call_at + 5]
                  if ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_MEM
                  and ins.reg_name(ins.operands[0].mem.base) == 'rip' and ins.operands[0].size == 8
                  and ins.operands[1].type == CS_OP_REG]
        _check(len(stores) == 2)
        globals_ = sorted(pointer(ins, ins.operands[0], view.image) for ins in stores)
        _check(globals_[1] - globals_[0] == 8)
        returned = [ins for ins in stores if root(ins, ins.operands[1]) == 'rax'
                    and definitions.before(ins.address, 'rax') == frozenset({call.address})]
        _check(len(returned) == 1 and pointer(returned[0], returned[0].operands[0], view.image) == globals_[1])
        path = values.pop()
        _check(path not in result)
        result[path] = {'pair_rva': globals_[0], 'path_component_rva': globals_[1],
                        'literal_reference_rva': row['reference_rva'], 'constructor_call_rva': call.address - view.image.base}
    _check('Data/_BinOutput/Voice/Lut/Lut' in result)
    return result


def lut_wrapper(view, manager, hashes, usages, arrays, stream):
    path = 'Data/_BinOutput/Voice/Lut/Lut'
    pair = hashes[path]['pair_rva']
    candidates = []
    for method in manager['methods']:
        if method['parameters'] or method['return_type']['kind'] != 1 or method['name'] == '.cctor' or not method['rva']:
            continue
        context = Context(view.image, method['rva'])
        definitions = Definitions(context.seq, context.noreturn)
        for at, ins in enumerate(context.seq):
            if not (ins.mnemonic in ('movups', 'movaps') and len(ins.operands) == 2
                    and ins.operands[1].type == CS_OP_MEM and ins.operands[1].size == 16
                    and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                    and pointer(ins, ins.operands[1], view.image) == pair):
                continue
            following = context.seq[at + 1:at + 10]
            _check(len(following) >= 4)
            store, address = following[:2]
            _check(store.mnemonic == 'movaps' and store.operands[0].type == CS_OP_MEM
                   and store.operands[0].size == 16 and store.operands[1].reg == ins.operands[0].reg
                   and address.mnemonic == 'lea' and address.reg_name(address.operands[0].reg) == 'rdx'
                   and address.operands[1].type == CS_OP_MEM
                   and address.operands[1].mem.base == store.operands[0].mem.base
                   and address.operands[1].mem.disp == store.operands[0].mem.disp)
            calls = [i for i in following[2:] if i.mnemonic == 'call']
            _check(calls)
            call = calls[0]
            _check(call.operands[0].type == CS_OP_IMM
                   and definitions.before(call.address, 'rdx') == frozenset({address.address}))
            singleton = call_origin(context, call.address, 'rcx', definitions)
            source_type = class_of_call(view, context, singleton, usages, arrays)
            wrappers = [m for m in view.methods(source_type['definition']) if m['name'] == 'DictionaryFromBinary'
                        and m['return_type']['kind'] == 1 and len(m['parameters']) == 2
                        and m['parameters'][0]['type']['index'] == stream and m['parameters'][1]['type']['kind'] == 21 and m['rva']]
            _check(len(wrappers) == 1, 'The source-owned resource has no unique typed binary dictionary method.')
            candidates.append({'path': path, 'sync_method': method, 'source_type': source_type, 'wrapper': wrappers[0],
                               'resource_call_rva': call.address - view.image.base, 'singleton_call_rva': singleton - view.image.base})
    _check(len(candidates) == 1, 'The original Lut path/resource wrapper binding is ambiguous.')
    return candidates[0]


def dictionary_decoder(view, wrapper):
    context = Context(view.image, wrapper['rva'])
    if len(context.reads()) >= 2:
        return wrapper['rva']
    targets = {ins.operands[0].imm - view.image.base for ins in context.seq
               if ins.mnemonic in ('call', 'jmp') and ins.operands[0].type == CS_OP_IMM}
    candidates = []
    for target in targets:
        try:
            child = Context(view.image, target)
        except ValueError:
            continue
        if len(child.reads()) >= 2:
            candidates.append(target)
    _check(len(candidates) == 1, 'The owned binary dictionary has no unique native decoder.')
    return candidates[0]


def dictionary_value(view, decoder, stream, usages, arrays):
    context = Context(view.image, decoder)
    pointers = pointer_states(context, {'rcx': ('stream', 0)})
    definitions = Definitions(context.seq, context.noreturn)
    candidates = []
    for ins in context.seq:
        if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                and pointers.get(ins.address, {}).get(('reg', 'rdx')) == ('stream', 0)):
            continue
        try:
            allocation = call_origin(context, ins.address, 'rcx', definitions)
            typed = class_of_call(view, context, allocation, usages, arrays)
        except ValueError:
            continue
        readers = [m for m in view.methods(typed['definition']) if m['rva'] == ins.operands[0].imm - view.image.base
                   and m['return_type']['kind'] == 1 and len(m['parameters']) == 1
                   and m['parameters'][0]['type']['index'] == stream]
        if readers:
            _check(len(readers) == 1)
            candidates.append({'type': typed, 'reader': readers[0], 'allocation_rva': allocation - view.image.base})
    _check(len(candidates) == 1, 'The original dictionary value allocation/reader is ambiguous.')
    return candidates[0]


def items_callback(view, manager, stream, usages, arrays):
    callbacks = [m for m in manager['methods'] if m['return_type'].get('namespace') == 'System'
                 and m['return_type'].get('name') == 'Object' and m['rva'] and len(m['parameters']) == 1
                 and m['parameters'][0]['type']['index'] == stream]
    _check(len(callbacks) == 1, 'The original Voice source stream callback is ambiguous.')
    callback = callbacks[0]
    slots = {slot for kind, index, slot in usages.pairs if kind == 3 and index == callback['index']}
    _check(slots)
    registrations = []
    for method in manager['methods']:
        if not method['rva']:
            continue
        try:
            context = Context(view.image, method['rva'])
        except ValueError:
            continue
        for ins in context.seq:
            if any(op.type == CS_OP_MEM and ins.reg_name(op.mem.base) == 'rip'
                   and pointer(ins, op, view.image) in {arrays[3]['array_rva'] + 8 * slot for slot in slots}
                   for op in ins.operands):
                registrations.append(method['index'])
    _check(len(set(registrations)) == 1, 'The original stream callback registration is ambiguous.')
    context = Context(view.image, callback['rva'])
    pointers = pointer_states(context, {'rcx': ('stream', 0)})
    definitions = Definitions(context.seq, context.noreturn)
    candidates = []
    for ins in context.seq:
        if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                and pointers.get(ins.address, {}).get(('reg', 'rcx')) == ('stream', 0)):
            continue
        incoming = definitions.before(ins.address, 'rdx')
        if not incoming or None in incoming:
            continue
        addresses = [context.by_address[at] for at in incoming]
        if all(i.mnemonic == 'lea' and i.operands[1].type == CS_OP_MEM
               and i.reg_name(i.operands[1].mem.base) in ('rbp', 'rsp') and not i.operands[1].mem.index for i in addresses):
            candidates.append(ins.operands[0].imm - view.image.base)
    _check(len(candidates) == 1, 'The actual source callback has no unique stream/out dictionary decoder.')
    return {'callback': callback, 'registered_by_method': registrations[0], 'decoder_rva': candidates[0]}


def _definition(context, definitions, address, name):
    incoming = definitions.before(address, name)
    _check(len(incoming) == 1 and None not in incoming, 'A native semantic role has ambiguous reaching definitions.')
    return context.by_address[next(iter(incoming))]


def _pointer_origin(context, definitions, address, name, depth=0):
    _check(depth < 16)
    incoming = definitions.before(address, name)
    if incoming == frozenset({None}):
        return 'input', name
    _check(incoming and None not in incoming)
    origins = set()
    for at in incoming:
        ins = context.by_address[at]
        if ins.mnemonic == 'mov' and ins.operands[0].size == ins.operands[1].size == 8:
            source = ins.operands[1]
            if source.type == CS_OP_REG:
                origins.add(_pointer_origin(context, definitions, at, root(ins, source), depth + 1))
            elif source.type == CS_OP_MEM and not source.mem.index:
                base = ins.reg_name(source.mem.base)
                if base == 'rip':
                    origins.add(('global', pointer(ins, source, context.image)))
                elif base in ('rsp', 'rbp'):
                    origins.add(('stack_value', _stack_location(context, ins, source)))
                else:
                    origins.add(('field', _pointer_origin(context, definitions, at, base, depth + 1), source.mem.disp))
            else:
                raise ValueError('The native pointer source is unsupported.')
        elif ins.mnemonic == 'call' and name == 'rax' and ins.operands[0].type == CS_OP_IMM:
            origins.add(('call', ins.operands[0].imm - context.image.base,
                         _pointer_origin(context, definitions, at, 'rcx', depth + 1)))
        elif ins.mnemonic == 'lea' and ins.operands[1].type == CS_OP_MEM and not ins.operands[1].mem.index:
            source = ins.operands[1]
            base = ins.reg_name(source.mem.base)
            if base in ('rsp', 'rbp'):
                origins.add(('stack_address', _stack_location(context, ins, source)))
            else:
                origins.add(('address', _pointer_origin(context, definitions, at, base, depth + 1), source.mem.disp))
        else:
            raise ValueError('The native pointer has no bounded owned source.')
    _check(len(origins) == 1, 'Native pointer paths disagree on their source.')
    return origins.pop()


def _field_load(context, definitions, address, name, width=4, depth=0):
    _check(depth < 16)
    incoming = definitions.before(address, name)
    _check(incoming and None not in incoming)
    loads, origins = [], set()
    for at in incoming:
        ins = context.by_address[at]
        _check(ins.mnemonic == 'mov' and len(ins.operands) == 2)
        source = ins.operands[1]
        if source.type == CS_OP_REG:
            load = _field_load(context, definitions, ins.address, root(ins, source), width, depth + 1)
        else:
            _check(source.type == CS_OP_MEM and source.size == width and not source.mem.index)
            load = ins
        memory = load.operands[1]
        base = load.reg_name(memory.mem.base)
        origin = (('stack', _stack_location(context, load, memory)) if base in ('rsp', 'rbp')
                  else ('global', pointer(load, memory, context.image)) if base == 'rip'
                  else ('field', _pointer_origin(context, definitions, load.address, base), memory.mem.disp))
        origins.add(origin)
        loads.append(load)
    _check(len(origins) == 1, 'Native field loads disagree on their authored source.')
    return loads[0]


def _stack_location(context, ins, operand):
    _check(operand.type == CS_OP_MEM and not operand.mem.index)
    base = ins.reg_name(operand.mem.base)
    _check(base in ('rbp', 'rsp'))
    return operand.mem.disp + (context.constants.frame if base == 'rbp' else 0)


def _stack_address(context, definitions, address, name, depth=0):
    _check(depth < 16)
    ins = _definition(context, definitions, address, name)
    if ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_REG and ins.operands[1].size == 8:
        return _stack_address(context, definitions, ins.address, root(ins, ins.operands[1]), depth + 1)
    _check(ins.mnemonic == 'lea')
    return _stack_location(context, ins, ins.operands[1])


def _getter_field(context, definitions, call):
    slot = _stack_address(context, definitions, call.address, 'rcx')
    position = context.seq.index(call)
    spills = []
    for at in range(max(0, position - 12), position):
        ins = context.seq[at]
        if not (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_MEM and ins.operands[0].size == 4
                and ins.operands[1].type == CS_OP_REG):
            continue
        try:
            location = _stack_location(context, ins, ins.operands[0])
        except ValueError:
            continue
        if location == slot and all(not other.mnemonic.startswith('j') and other.mnemonic != 'call'
                                    for other in context.seq[at + 1:position]):
            spills.append(ins)
    _check(len(spills) == 1)
    spill = spills[0]
    load = _field_load(context, definitions, spill.address, root(spill, spill.operands[1]))
    base = load.reg_name(load.operands[1].mem.base)
    row = _field_load(context, definitions, load.address, base, 8)
    origin = _stack_location(context, row, row.operands[1])
    return load.operands[1].mem.disp, origin, load.address - context.image.base


def lut_event_roles(view, manager, wrapper, value):
    """The actual argument<<32|trigger consumer owns both original field roles."""
    fields = {field['authored_offset_word']: field for field in view.field_offsets(value['type']['definition'])}
    getters = {}
    for field in fields.values():
        typed = field['type']
        if typed['kind'] != 17:
            continue
        members = view.fields(typed['definition'])
        if len(members) == 1 and members[0]['type']['kind'] == 9:
            for method in view.methods(typed['definition']):
                if method['return_type']['kind'] == 9 and not method['parameters'] and method['rva']:
                    getters[method['rva']] = typed['definition']
    _check(getters)
    sync = Context(view.image, wrapper['sync_method']['rva'])
    calls = {ins.operands[0].imm - view.image.base for ins in sync.seq if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM}
    # Select the actual sync loader's typed dictionary handlers. Their generic
    # instantiation indices are not an ABI identity between serialized and
    # runtime caches; field roles below need their own actual consumer proof.
    handlers = [method for method in manager['methods'] if method['rva'] in calls and method['return_type']['kind'] == 1
                and len(method['parameters']) == 1 and method['parameters'][0]['type']['kind'] == 21]
    _check(handlers)
    results = []
    for handler in handlers:
        context = Context(view.image, handler['rva'])
        definitions = Definitions(context.seq, context.noreturn)
        for at, shift in enumerate(context.seq[:-1]):
            combine = context.seq[at + 1]
            if not (shift.mnemonic == 'shl' and shift.operands[0].size == 8 and shift.operands[1].type == CS_OP_IMM
                    and shift.operands[1].imm == 32 and combine.mnemonic == 'or'
                    and combine.operands[0].reg == shift.operands[0].reg and combine.operands[1].type == CS_OP_REG):
                continue
            try:
                high = _definition(context, definitions, shift.address, root(shift, shift.operands[0]))
                _check(high.mnemonic == 'mov' and high.operands[1].type == CS_OP_REG and high.reg_name(high.operands[1].reg) == 'eax')
                call = _definition(context, definitions, high.address, 'rax')
                _check(call.mnemonic == 'call' and call.operands[0].type == CS_OP_IMM
                       and call.operands[0].imm - view.image.base in getters)
                argument, origin, read_rva = _getter_field(context, definitions, call)
                low = _field_load(context, definitions, combine.address, root(combine, combine.operands[1]))
                row = _field_load(context, definitions, low.address, low.reg_name(low.operands[1].mem.base), 8)
                _check(_stack_location(context, row, row.operands[1]) == origin)
                trigger = low.operands[1].mem.disp
                _check(argument in fields and trigger in fields and argument != trigger)
                getter = call.operands[0].imm - view.image.base
                _check(fields[argument]['type'].get('definition') == getters[getter])
                enum = fields[trigger]['type']
                _check(enum['kind'] == 17 and {'value__', 'Dialog'} <= {f['name'] for f in view.fields(enum['definition'])})
                remaining = set(fields) - {argument, trigger}
                _check(len(remaining) == 1)
                results.append({'handler': handler, 'argument': argument, 'trigger': trigger,
                                'group_candidate': remaining.pop(), 'row_stack_origin': origin,
                                'argument_read_rva': read_rva, 'packed_key_rva': shift.address - view.image.base,
                                'argument_getter_rva': getter, 'trigger_type': enum})
            except ValueError:
                continue
    _check(len(results) == 1, 'The original Lut event-field roles are missing or ambiguous.')
    return results[0]


def _word_call_origin(context, definitions, address, name, depth=0):
    _check(depth < 16)
    ins = _definition(context, definitions, address, name)
    if ins.mnemonic == 'call' and name == 'rax' and ins.operands[0].type == CS_OP_IMM:
        return ins.address
    _check(ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_REG and ins.operands[1].size in (4, 8))
    return _word_call_origin(context, definitions, ins.address, root(ins, ins.operands[1]), depth + 1)


def _static_field(view, manager, offset, kind):
    # The offset word retains its storage flags. Its low 24 bits describe the
    # static storage location in this metadata layout; the native store/load
    # and declared owner/type must independently select the same unique field.
    fields = [field for field in view.field_offsets(manager['owner']['definition'])
              if field['authored_offset_word'] & 0xffffff == offset and field['type']['kind'] == kind]
    _check(len(fields) == 1, 'The native static field has ambiguous metadata ownership.')
    return fields[0]


def lut_group_cache(view, manager, roles):
    context = Context(view.image, roles['handler']['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    results = []
    for at, ins in enumerate(context.seq):
        if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                and ins.operands[0].imm - view.image.base == roles['argument_getter_rva']):
            continue
        try:
            offset, origin, read = _getter_field(context, definitions, ins)
            if offset != roles['group_candidate'] or origin != roles['row_stack_origin']:
                continue
            consumers = []
            for call in context.seq[at + 1:at + 101]:
                if call.mnemonic != 'call':
                    continue
                try:
                    _check(_word_call_origin(context, definitions, call.address, 'r8') == ins.address)
                    argument = _definition(context, definitions, call.address, 'r8')
                    key = _definition(context, definitions, call.address, 'rdx')
                    _check(argument.operands[0].size == key.operands[0].size == 4)
                    cache = _field_load(context, definitions, call.address, 'rcx', 8)
                    cache_offset = cache.operands[1].mem.disp
                    field = _static_field(view, manager, cache_offset, 21)
                    consumers.append({'cache_offset': cache_offset, 'cache_field': field,
                                      'native_consumer_rva': call.address - view.image.base})
                except ValueError:
                    continue
            _check(len(consumers) == 1)
            results.append({'field_offset': offset, 'field_read_rva': read,
                            'plain_group_getter_rva': ins.address - view.image.base, **consumers[0]})
        except ValueError:
            continue
    _check(len(results) == 1, 'The original UUID/group cache consumer is missing or ambiguous.')
    return results[0]


def items_prefix_field(view, manager, paths):
    prefix = 'Data/_BinOutput/Voice/Items/'
    hits = [row for row in paths if row['method_rva'] == manager['constructor']['rva']
            and any(literal['path'] == prefix for literal in row['literals'])]
    _check(len(hits) == 1)
    seq = view.image.instructions(manager['constructor']['rva'])
    at = next(n for n, ins in enumerate(seq) if ins.address - view.image.base == hits[0]['reference_rva'])
    load, store = seq[at:at + 2]
    _check(store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM and store.operands[0].size == 8
           and store.operands[1].type == CS_OP_REG and store.operands[1].reg == load.operands[0].reg)
    offset = store.operands[0].mem.disp
    return {'prefix': prefix, 'offset': offset, 'field': _static_field(view, manager, offset, 14),
            'native_store_rva': store.address - view.image.base}


def group_filename(view, manager, group, prefix):
    strings = view.named('System', 'String')
    concat = [m for m in view.methods(strings['definition']) if m['name'] == 'Concat' and m['rva']
              and m['return_type']['kind'] == 14 and len(m['parameters']) == 2
              and all(p['type']['kind'] == 14 for p in m['parameters'])]
    numbers = view.named('System', 'NumberFormatter')
    formatter = [m for m in view.methods(numbers['definition']) if m['name'] == 'NumberToString' and m['rva']
                 and m['return_type']['kind'] == 14 and len(m['parameters']) == 3
                 and [p['type']['kind'] for p in m['parameters'][:2]] == [14, 9]
                 and m['parameters'][2]['type'].get('namespace') == 'System'
                 and m['parameters'][2]['type'].get('name') == 'IFormatProvider']
    _check(len(concat) == len(formatter) == 1)
    formatting_info = view.named('System.Globalization', 'NumberFormatInfo')
    current_info = [m for m in view.methods(formatting_info['definition']) if m['name'] == 'get_CurrentInfo'
                    and m['rva'] and not m['parameters'] and m['return_type'].get('definition') == formatting_info['definition']]
    _check(len(current_info) == 1)
    results, rejected = [], []
    for method in manager['methods']:
        if not method['rva'] or method['name'] == '.cctor':
            continue
        try:
            context = Context(view.image, method['rva'])
        except ValueError:
            continue
        offsets = {op.mem.disp for ins in context.seq for op in ins.operands if op.type == CS_OP_MEM and op.access & 1}
        if not {group['cache_offset'], prefix['offset']} <= offsets:
            continue
        definitions = Definitions(context.seq, context.noreturn)
        for ins in context.seq:
            if not (ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
                    and ins.operands[0].imm - view.image.base == concat[0]['rva']):
                continue
            try:
                stage = 'prefix receiver'
                left = _field_load(context, definitions, ins.address, 'rcx', 8)
                _check(left.operands[1].mem.disp == prefix['offset'])
                stage = 'formatter return'
                formatting = call_origin(context, ins.address, 'rdx', definitions)
                format_call = context.by_address[formatting]
                _check(format_call.operands[0].imm - view.image.base == formatter[0]['rva'])
                stage = 'default format/provider'
                _check(context.constants.value_before(formatting, 'rcx', 64) == 0)
                provider = call_origin(context, formatting, 'r8', definitions)
                _check(context.by_address[provider].operands[0].imm - view.image.base == current_info[0]['rva'])
                stage = 'mapped group stack'
                source = _field_load(context, definitions, formatting, 'rdx')
                slot = _stack_location(context, source, source.operands[1])
                lookups = []
                for call in context.seq:
                    if call.address >= source.address or call.mnemonic != 'call':
                        continue
                    try:
                        _check(_stack_address(context, definitions, call.address, 'r8') == slot)
                        cache = _field_load(context, definitions, call.address, 'rcx', 8)
                        _check(cache.operands[1].mem.disp == group['cache_offset'])
                        lookups.append(call.address - view.image.base)
                    except ValueError:
                        continue
                stage = 'native cache/out lookup'
                _check(len(lookups) == 1)
                results.append({'method': method, 'lookup_rva': lookups[0], 'group_out_stack': slot,
                                'format_rva': formatting - view.image.base,
                                'concat_rva': ins.address - view.image.base,
                                'formatter': formatter[0], 'current_format_provider': current_info[0],
                                'concat': concat[0], 'prefix': prefix['prefix']})
            except ValueError as error:
                rejected.append((method['index'], stage, str(error)))
                continue
    _check(results, ('The original mapped group/default-decimal Items filename is unavailable.', rejected))
    # Several real entry points may implement the same proven construction.
    # Retain every consumer rather than selecting a current method by address.
    agreement = {(row['prefix'], row['formatter']['rva'], row['concat']['rva'],
                  row['current_format_provider']['rva']) for row in results}
    _check(len(agreement) == 1, 'The original group filename consumers disagree.')
    return {'prefix': prefix['prefix'], 'group_cache_offset': group['cache_offset'], 'consumers': tuple(results)}


def _value_origin(context, definitions, address, name, depth=0):
    _check(depth < 20)
    incoming = definitions.before(address, name)
    if incoming == frozenset({None}):
        return 'input', name
    _check(incoming and None not in incoming)
    result = set()
    for at in incoming:
        ins = context.by_address[at]
        if ins.mnemonic == 'call' and name == 'rax' and ins.operands[0].type == CS_OP_IMM:
            result.add(('call', ins.address, ins.operands[0].imm - context.image.base))
        elif ins.mnemonic in ('mov', 'movzx') and ins.operands[1].type == CS_OP_REG:
            result.add(_value_origin(context, definitions, ins.address, root(ins, ins.operands[1]), depth + 1))
        elif ins.mnemonic in ('mov', 'movzx') and ins.operands[1].type == CS_OP_MEM and not ins.operands[1].mem.index:
            source = ins.operands[1]
            base = ins.reg_name(source.mem.base)
            if base in ('rsp', 'rbp'):
                result.add(('stack_value', _stack_location(context, ins, source)))
            else:
                result.add(('field', _pointer_origin(context, definitions, ins.address, base), source.mem.disp, source.size))
        elif ins.mnemonic == 'lea' and ins.operands[1].type == CS_OP_MEM:
            result.add(('stack_address', _stack_location(context, ins, ins.operands[1])))
        else:
            raise ValueError('The native value origin is unsupported.')
    _check(len(result) == 1, 'Native value paths disagree on their origin.')
    return result.pop()


def items_event_roles(view, manager, value):
    fields = {field['authored_offset_word']: field for field in view.field_offsets(value['type']['definition'])}
    lookups = [method for method in manager['methods'] if method['return_type']['kind'] == 2 and method['rva']
               and len(method['parameters']) == 3 and method['parameters'][0]['type']['kind'] == 17
               and method['parameters'][1]['type']['kind'] == 9
               and method['parameters'][2]['type'].get('definition') == value['type']['definition']]
    _check(len(lookups) == 1)
    lookup = lookups[0]
    enum = lookup['parameters'][0]['type']['definition']
    _check('Dialog' in {field['name'] for field in view.fields(enum)})
    context = Context(view.image, lookup['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    roles = {}
    for ins in context.seq:
        if not (ins.mnemonic == 'cmp' and len(ins.operands) == 2 and all(op.type == CS_OP_REG for op in ins.operands)):
            continue
        try:
            left, right = (_value_origin(context, definitions, ins.address, root(ins, operand)) for operand in ins.operands)
            if right[0] == 'call' and left[0] == 'input':
                left, right = right, left
            if left[0] != 'call' or right not in (('input', 'rcx'), ('input', 'rdx')):
                continue
            role = 'trigger' if right[1] == 'rcx' else 'argument'
            methods = view.methods_at(left[2])
            if role == 'trigger':
                methods = [row for row in methods if row['method']['return_type'].get('definition') == enum
                           and len(row['method']['parameters']) == 1 and row['method']['parameters'][0]['type']['kind'] == 14]
                _check(len(methods) == 1)
                field = _value_origin(context, definitions, left[1], 'rcx')
                _check(field[0] == 'field' and field[2] in fields and fields[field[2]]['type']['kind'] == 14)
                offset, origin = field[2], field[1]
            else:
                methods = [row for row in methods if row['method']['return_type']['kind'] == 9 and not row['method']['parameters']]
                _check(len(methods) == 1)
                offset, stack_origin, _read = _getter_field(context, definitions, context.by_address[left[1]])
                _check(offset in fields and fields[offset]['type'].get('definition') == methods[0]['owner']['definition'])
                origin = 'stack_value', stack_origin
            _check(role not in roles)
            roles[role] = {'field_offset': offset, 'item_origin': origin, 'typed_consumer': methods[0],
                           'comparison_rva': ins.address - view.image.base, 'input_argument': right[1]}
        except ValueError:
            continue
    _check(set(roles) == {'trigger', 'argument'} and roles['trigger']['item_origin'] == roles['argument']['item_origin'],
           'The original Item trigger/argument input comparisons are missing or ambiguous.')
    return {'lookup': lookup, 'fields': roles}


def items_source_roles(view, manager, value):
    item = value['type']['definition']
    fields = view.field_offsets(item)
    arrays = {field['type']['element']['definition']: field for field in fields
              if field['type']['kind'] == 29 and 'definition' in field['type']['element']}
    array_methods = [(method, parameter['type']['element']['definition'])
                     for method in manager['methods'] for parameter in method['parameters']
                     if method['return_type']['kind'] == 1 and len(method['parameters']) == 3
                     and method['parameters'][0]['type']['kind'] == 18 and method['parameters'][2]['type']['kind'] == 21
                     and parameter is method['parameters'][1]
                     and parameter['type']['kind'] == 29 and parameter['type']['element'].get('definition') in arrays]
    _check(len(array_methods) == 1, ('The original source-array consumers are ambiguous.', [(m['index'], d) for m, d in array_methods]))
    array_method, source = array_methods[0]
    elements = [method for method in manager['methods']
                if any(parameter['type'].get('definition') == source for parameter in method['parameters'])]
    converters = [method for method in manager['methods'] if method['return_type']['kind'] == 1
                  and len(method['parameters']) == 2 and method['parameters'][0]['type'].get('definition') == item]
    _check(len(elements) == len(converters) == 1)
    element, converter = elements[0], converters[0]
    _check(len(element['parameters']) == 2 and element['parameters'][0]['type'].get('definition') == source)
    runtime_source = element['parameters'][1]['type']['definition']
    runtime_entry = array_method['parameters'][0]['type']['definition']
    context = Context(view.image, converter['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    forwarding = []
    for ins in context.seq:
        if ins.mnemonic in ('call', 'jmp') and ins.operands[0].type == CS_OP_IMM and ins.operands[0].imm - view.image.base == array_method['rva']:
            origin = _value_origin(context, definitions, ins.address, 'rdx')
            _check(origin[0] == 'field' and origin[1] == ('input', 'rcx') and origin[3] == 8)
            _check(origin[2] == arrays[source]['authored_offset_word'])
            forwarding.append(ins.address - view.image.base)
    _check(len(forwarding) == 1)
    selectors = [method for method in view.methods(runtime_entry) if method['return_type']['kind'] == 14
                 and len(method['parameters']) == 1 and method['rva']]
    _check(len(selectors) == 1)
    selector = Context(view.image, selectors[0]['rva'])
    returned = []
    for at, ins in enumerate(selector.seq[:-2]):
        add, ret = selector.seq[at + 1:at + 3]
        if not (ins.mnemonic == 'mov' and ins.reg_name(ins.operands[0].reg) == 'rax'
                and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rsp'
                and add.mnemonic == 'add' and ret.mnemonic == 'ret'):
            continue
        references = [i for i in selector.seq[:at] if i.mnemonic == 'lea'
                      and i.reg_name(i.operands[0].reg) == 'r8' and i.operands[1].type == CS_OP_MEM
                      and i.reg_name(i.operands[1].mem.base) == 'rsp']
        _check(len(references) == 1)
        returned.append(ins.operands[1].mem.disp - references[0].operands[1].mem.disp)
    _check(len(returned) == 1)
    returned_offset = returned[0]
    # Boxed metadata offsets include the retained 16-byte value-type header;
    # the actual out-pointer and native copy use the unboxed struct layout.
    runtime_fields = [field for field in view.field_offsets(runtime_source)
                      if field['authored_offset_word'] - 16 == returned_offset and field['type']['kind'] == 14]
    _check(len(runtime_fields) == 1)
    context = Context(view.image, element['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    copies = []
    for ins in context.seq:
        if not (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_MEM and ins.operands[0].size == 8
                and not ins.operands[0].mem.index and ins.operands[0].mem.disp == returned_offset
                and ins.operands[1].type == CS_OP_REG):
            continue
        memory = ins.operands[0].mem
        try:
            _check(_pointer_origin(context, definitions, ins.address, ins.reg_name(memory.base)) == ('input', 'rdx'))
            origin = _value_origin(context, definitions, ins.address, root(ins, ins.operands[1]))
            _check(origin[0] == 'field' and origin[1] == ('input', 'rcx') and origin[3] == 8)
            original = [field for field in view.field_offsets(source) if field['authored_offset_word'] == origin[2] and field['type']['kind'] == 14]
            _check(len(original) == 1)
            copies.append((ins.address - view.image.base, origin[2]))
        except ValueError:
            continue
    _check(len(copies) == 1, 'The original source filename/runtime selected string copy is ambiguous.')
    return {'source_array_offset': arrays[source]['authored_offset_word'], 'source_definition': source,
            'source_filename_offset': copies[0][1], 'source_filename_copy_rva': copies[0][0],
            'converter': converter, 'array_consumer': array_method, 'element_consumer': element,
            'runtime_selector': selectors[0], 'runtime_string_field': runtime_fields[0],
            'native_return_offset': returned_offset}


def item_uuid_role(view, value, source_roles, usages, arrays):
    """Own the string hashed by the converter's standard ASCII Wwise FNV-1."""
    context = Context(view.image, source_roles['converter']['rva'])
    definitions = Definitions(context.seq, context.noreturn)
    fields = {field['authored_offset_word']: field for field in view.field_offsets(value['type']['definition'])}
    runtime = source_roles['array_consumer']['parameters'][0]['type']['definition']
    results = []
    for position, load in enumerate(context.seq):
        if not (load.mnemonic == 'mov' and load.operands[0].type == CS_OP_REG
                and load.operands[1].type == CS_OP_MEM and load.operands[1].size == 8
                and not load.operands[1].mem.index and load.operands[1].mem.disp in fields
                and fields[load.operands[1].mem.disp]['type']['kind'] == 14):
            continue
        try:
            _check(_pointer_origin(context, definitions, load.address, load.reg_name(load.operands[1].mem.base)) == ('input', 'rcx'))
            string = root(load, load.operands[0])
            following = context.seq[position + 1:position + 97]
            advances = [n for n, ins in enumerate(following[:32]) if ins.mnemonic == 'add'
                        and ins.operands[0].type == CS_OP_REG and root(ins, ins.operands[0]) == string
                        and ins.operands[1].type == CS_OP_IMM and ins.operands[1].imm == 20]
            _check(len(advances) == 1)
            advance = advances[0]
            lengths = [ins for ins in following[:advance] if ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_MEM
                       and ins.operands[1].size == 4 and ins.operands[1].mem.disp == 16
                       and ins.reg_name(ins.operands[1].mem.base) == string]
            _check(len(lengths) == 1)
            stores = [n for n, ins in enumerate(following[advance + 1:], advance + 1)
                      if ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_MEM
                      and ins.operands[0].size == 4 and ins.operands[1].type == CS_OP_REG]
            _check(stores)
            end = stores[0]
            region = following[advance + 1:end]
            # These are the retained public FNV-1 algorithm constants, rather
            # than revision-specific codec parameters or game identifiers.
            literals = {ins.operands[1].imm & 0xffffffff for ins in region
                        if ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_IMM}
            _check({0x811c9dc5, 0x811c9dc5 * 0x1000193 & 0xffffffff} <= literals)
            multiplications = [ins for ins in region if ins.mnemonic == 'imul' and len(ins.operands) == 3
                               and ins.operands[2].type == CS_OP_IMM and ins.operands[2].imm & 0xffffffff == 0x1000193]
            _check(len(multiplications) >= 3)
            normalizers = []
            for at, ins in enumerate(region[:-6]):
                if not (ins.mnemonic == 'movzx' and ins.operands[1].type == CS_OP_MEM and ins.operands[1].size == 2
                        and ins.reg_name(ins.operands[1].mem.base) == string and not ins.operands[1].mem.index
                        and ins.operands[1].mem.disp in (0, 2)):
                    continue
                minus, plus, compare, select = region[at + 1:at + 5]
                char = root(ins, ins.operands[0])
                _check(minus.mnemonic == plus.mnemonic == 'lea'
                       and all(i.operands[1].type == CS_OP_MEM and not i.operands[1].mem.index
                               and i.reg_name(i.operands[1].mem.base) == char for i in (minus, plus))
                       and minus.operands[1].mem.disp == -0x5b and plus.operands[1].mem.disp == 0x20
                       and compare.mnemonic == 'cmp' and compare.operands[1].type == CS_OP_IMM
                       and compare.operands[1].imm & 0xffff == (-26) & 0xffff
                       and root(compare, compare.operands[0]) == root(minus, minus.operands[0])
                       and select.mnemonic == 'cmovb' and root(select, select.operands[0]) == root(plus, plus.operands[0])
                       and root(select, select.operands[1]) == char)
                low = [i for i in region[at + 5:at + 10] if i.mnemonic == 'movzx' and i.operands[1].type == CS_OP_REG
                       and i.operands[1].size == 1 and root(i, i.operands[1]) == root(plus, plus.operands[0])]
                _check(len(low) == 1)
                normalizers.append(ins.address - view.image.base)
            _check(len(normalizers) == 3)
            store = following[end]
            allocation = call_origin(context, store.address, store.reg_name(store.operands[0].mem.base), definitions)
            typed = class_of_call(view, context, allocation, usages, arrays)
            _check(typed['definition'] == runtime)
            targets = [field for field in view.field_offsets(runtime)
                       if field['authored_offset_word'] == store.operands[0].mem.disp and field['type']['kind'] == 9]
            _check(len(targets) == 1)
            results.append({'uuid_offset': load.operands[1].mem.disp, 'field_load_rva': load.address - view.image.base,
                            'hash_store_rva': store.address - view.image.base, 'runtime_identifier_field': targets[0],
                            'native_ascii_normalizers': tuple(normalizers), 'identifier_encoding': 'ASCII-lowercase-FNV1-32'})
        except ValueError:
            continue
    _check(len(results) == 1, 'The native Item UUID/ASCII Wwise hash input is missing or ambiguous.')
    return results[0]
