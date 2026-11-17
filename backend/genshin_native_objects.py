"""Original allocation/type-slot ownership of nested authored object fields."""
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Definitions, register, _check
from .genshin_native_metadata import pointer, root
from .genshin_native_fields import pointer_states


def nested_calls(view, context, fields, stream, usages, arrays):
    children = {}
    for field in fields:
        typed = field['type']
        if typed['kind'] == 18 and 'definition' in typed:
            matches = [m for m in view.methods(typed['definition']) if m['return_type']['kind'] == 1 and m['rva']
                       and len(m['parameters']) == 1 and m['parameters'][0]['type']['index'] == stream]
            if matches:
                _check(len(matches) == 1)
                children.setdefault(matches[0]['rva'], []).append((field, matches[0]))
    if not children:
        return {}, {}
    _check(usages is not None and arrays is not None, 'Nested original objects require their owned class-slot bindings.')
    slots = {}
    for kind, typed, slot in usages.pairs:
        if kind == 1:
            slots.setdefault(slot, set()).add(typed)
    definitions = Definitions(context.seq, context.noreturn)
    pointers = pointer_states(context)
    image = view.image

    def allocation(at):
        ins = context.by_address[at]
        if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM:
            return None
        owners = definitions.before(at, 'rcx')
        if not owners or None in owners:
            return None
        types = set()
        for owner in owners:
            load = context.by_address[owner]
            if not (load.mnemonic == 'mov' and load.operands[1].type == CS_OP_MEM
                    and load.reg_name(load.operands[1].mem.base) == 'rip'):
                return None
            delta = pointer(load, load.operands[1], image) - arrays[1]['array_rva']
            if delta < 0 or delta % 8 or delta // 8 not in slots:
                return None
            types.update(view.bindings.describe(typed).get('definition') for typed in slots[delta // 8])
        return types

    def receiver(at, name, depth=0):
        _check(depth < 16)
        incoming = definitions.before(at, name)
        _check(incoming and None not in incoming)
        result = set()
        for owner in incoming:
            ins = context.by_address[owner]
            if ins.mnemonic == 'call' and name == 'rax':
                types = allocation(owner)
                _check(types is not None)
                result.update(('allocation', definition) for definition in types)
            elif ins.mnemonic == 'mov' and ins.operands[0].size == ins.operands[1].size == 8:
                source = ins.operands[1]
                if source.type == CS_OP_REG:
                    result.update(receiver(ins.address, root(ins, source), depth + 1))
                elif source.type == CS_OP_MEM and not source.mem.index:
                    base = pointers.get(ins.address, {}).get(('reg', register(ins.reg_name(source.mem.base))[0]))
                    _check(base is not None and base[0] == 'this')
                    result.add(('field', base[1] + source.mem.disp))
                else:
                    raise ValueError('The original nested receiver has no owned source.')
            else:
                raise ValueError('The original nested receiver has no owned allocation or field.')
        return result

    calls, readers = {}, {}
    for ins in context.seq:
        if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM or ins.operands[0].imm - image.base not in children:
            continue
        _check(pointers.get(ins.address, {}).get(('reg', 'rdx')) == ('stream', 0))
        sources = receiver(ins.address, 'rcx')
        matches = []
        for field, reader in children[ins.operands[0].imm - image.base]:
            offset, definition = field['authored_offset_word'], field['type']['definition']
            if sources == {('field', offset)}:
                matches.append((offset, reader, ()))
            elif sources == {('allocation', definition)}:
                stores = []
                position = context.seq.index(ins)
                for store in context.seq[max(0, position - 16):position]:
                    if not (store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM
                            and store.operands[0].size == 8 and not store.operands[0].mem.index
                            and store.operands[1].type == CS_OP_REG):
                        continue
                    memory = store.operands[0].mem
                    base = pointers.get(store.address, {}).get(('reg', register(store.reg_name(memory.base))[0]))
                    if base is not None and base[0] == 'this' and base[1] + memory.disp == offset:
                        if receiver(store.address, root(store, store.operands[1])) == sources:
                            stores.append(store.address)
                _check(len(stores) == 1)
                matches.append((offset, reader, tuple(stores)))
        _check(len(matches) == 1, 'The actual nested stream call has ambiguous authored field ownership.')
        offset, reader, stores = matches[0]
        calls[ins.address], readers[offset] = offset, reader
        for store in stores:
            calls[store] = offset
    _check(calls)
    return calls, readers
