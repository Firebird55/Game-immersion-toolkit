"""Native-owned fieldless configuration storage, read strictly as data.

Current metadata owns the getter/helper types and NativeWrapper layout. Current
instructions own field slots, presence flags and wire operands. No game method
is invoked and no version-specific field address is part of this module.
"""
from dataclasses import dataclass
import bisect
import hashlib

from . import genshin_original_dialogue as binary
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, Definitions, decoder, register, _check
from .genshin_native_metadata import root
from .genshin_native_fields import ordered_fields, pointer_states
from .genshin_native_contracts import Contracts
from .genshin_native_words import Context


@dataclass(frozen=True)
class Slots:
    record: binary.Record
    identity_slot: int
    string_slots: tuple[int, ...]
    getter_owner: int
    string_getter: int
    method_sha256s: tuple[str, ...]


def _typed(view, rva):
    rows = view.methods_at(rva)
    _check(len(rows) == 1, 'The native slot helper has ambiguous metadata ownership.')
    return rows[0]


def _getter(view, method, native_starts):
    """An original metadata-owned tiny getter through its typed tail call."""
    image, rva = view.image, method['rva']
    end = bisect.bisect_right(native_starts, rva)
    _check(end < len(native_starts))
    size = native_starts[end] - rva
    _check(0 < size <= 256)
    at = image.offset(rva, size)
    seq = []
    for instruction in decoder().disasm(image.data[at:at + size], image.base + rva):
        if instruction.mnemonic == 'nop':
            continue
        seq.append(instruction)
        _check(len(seq) <= 16)
        if instruction.mnemonic == 'jmp':
            break
        _check(instruction.mnemonic in {'mov', 'and', 'xor', 'nop'})
    _check(len(seq) == 4)
    load, mask, slot, tail = seq
    _check(load.mnemonic == 'mov' and len(load.operands) == 2
           and root(load, load.operands[0]) == 'rcx' and load.operands[1].type == CS_OP_MEM
           and load.reg_name(load.operands[1].mem.base) == 'rcx' and not load.operands[1].mem.index
           and load.operands[0].size == load.operands[1].size == 8)
    _check(mask.mnemonic == 'and' and root(mask, mask.operands[0]) == 'rcx'
           and mask.operands[1].type == CS_OP_IMM)
    _check(slot.operands[0].type == CS_OP_REG and slot.reg_name(slot.operands[0].reg) == 'edx')
    if slot.mnemonic == 'mov' and slot.operands[1].type == CS_OP_IMM:
        offset = slot.operands[1].imm
    else:
        _check(slot.mnemonic == 'xor' and slot.operands[1].type == CS_OP_REG
               and slot.operands[0].reg == slot.operands[1].reg)
        offset = 0
    _check(tail.mnemonic == 'jmp' and tail.operands[0].type == CS_OP_IMM)
    target = tail.operands[0].imm - image.base
    helper = _typed(view, target)
    parameters = helper['method']['parameters']
    _check(helper['method']['return_type']['kind'] == 14 and len(parameters) == 2
           and [p['type']['kind'] for p in parameters] == [11, 8])
    span = tail.address + tail.size - image.base - rva
    return {'slot': offset, 'helper': helper, 'handle_offset': load.operands[1].mem.disp,
            'handle_mask': mask.operands[1].imm & ((1 << 64) - 1),
            'sha256': hashlib.sha256(image.data[at:at + span]).hexdigest()}


def _handle(context, definitions, pointers, address, name, offset, mask, depth=0):
    _check(depth < 32)
    owners = definitions.before(address, name)
    _check(owners and None not in owners, 'The native slot handle has no complete definition.')
    results = set()
    for owner in owners:
        ins = context.by_address[owner]
        ops = ins.operands
        if ins.mnemonic == 'and' and ops[1].type == CS_OP_IMM and ops[1].imm & ((1 << 64) - 1) == mask:
            source = _handle(context, definitions, pointers, owner, name, offset, mask, depth + 1)
            _check(source in {'raw', 'masked'})
            results.add('masked')
        elif ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].size == ops[1].size == 8:
            source = ops[1]
            if source.type == CS_OP_REG:
                results.add(_handle(context, definitions, pointers, owner, root(ins, source), offset, mask, depth + 1))
            elif source.type == CS_OP_MEM and not source.mem.index:
                base = pointers.get(owner, {}).get(('reg', register(ins.reg_name(source.mem.base))[0]))
                _check(base is not None and base[0] == 'this' and base[1] + source.mem.disp == offset,
                       'The native slot handle belongs to another object.')
                results.add('raw')
            else:
                raise ValueError('The native slot handle has an unsupported source.')
        else:
            raise ValueError('The native slot handle has an unsupported definition.')
    _check(len(results) == 1, 'The native slot handle is ambiguous across successful paths.')
    return results.pop()


def _wrapper(view):
    owner = view.named('MoleMole.NativeConfig', 'NativeDataUtils')
    methods = [m for m in view.methods(owner['definition']) if m['name'] == 'QueryWrapperInternal'
               and m['rva'] and len(m['parameters']) == 1 and m['parameters'][0]['type']['kind'] == 11
               and m['return_type'].get('namespace') == 'MoleMole.NativeConfig'
               and m['return_type'].get('name') == 'NativeWrapper']
    _check(len(methods) == 1)
    method = methods[0]
    fields = [f for f in view.field_offsets(method['return_type']['definition']) if f['authored_offset_word'] < 16_000_000]
    buffers = [f for f in fields if f['name'] == '_buffer' and f['type']['kind'] == 15]
    _check(len(buffers) == 1 and fields)
    ends = []
    for field in fields:
        # IL2CPP's boxed value-type member offsets include the object header;
        # the native hidden return pointer receives the unboxed structure.
        offset = field['authored_offset_word'] - 16
        typed = field['type']
        if typed['kind'] == 17:
            underlying = [f for f in view.fields(typed['definition']) if f['name'] == 'value__']
            _check(len(underlying) == 1)
            typed = underlying[0]['type']
        size = {2: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 4, 9: 4, 10: 8, 11: 8, 15: 8, 18: 8}.get(typed['kind'])
        _check(size is not None and 0 <= offset <= 256)
        ends.append(offset + size)
    size = (max(ends) + 7) & ~7
    return method, size, buffers[0]['authored_offset_word'] - 16


def derive(view, definition, reader, stream):
    """Complete native slot layout plus a strict canonical wire contract."""
    _check(not view.fields(definition), 'A native slot record must have no competing managed storage.')
    image, methods = view.image, view.methods(definition)
    starts = sorted(set(view.bindings.method_rvas) - {0})
    strings = [_getter(view, m, starts) for m in methods
               if m['rva'] and not m['parameters'] and m['return_type']['kind'] == 14]
    _check(strings and len(strings) <= 64)
    helpers = {(r['helper']['owner']['definition'], r['helper']['method']['rva'], r['handle_offset'], r['handle_mask']) for r in strings}
    _check(len(helpers) == 1)
    helper_owner, string_getter, handle_offset, handle_mask = helpers.pop()
    string_slots = tuple(sorted(r['slot'] for r in strings))
    _check(len(set(string_slots)) == len(string_slots))
    cstring = view.named('MoleMole.NativeConfig', 'NativeCString')['definition']
    string_storage = [f for f in view.field_offsets(cstring) if f['authored_offset_word'] < 16_000_000]
    _check(len(string_storage) == 1 and string_storage[0]['authored_offset_word'] == 16
           and string_storage[0]['type']['kind'] == 11,
           'The native string storage no longer has its owned UInt64 representation.')
    context = Context(image, reader['rva'])
    actual_calls = {ins.operands[0].imm - image.base for ins in context.seq
                    if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM}
    setters = [m for m in view.methods(helper_owner) if m['rva'] and m['return_type']['kind'] == 1
               and len(m['parameters']) == 3 and [p['type']['kind'] for p in m['parameters']] == [11, 8, 17]
               and m['parameters'][2]['type'].get('definition') == cstring and m['rva'] in actual_calls]
    _check(len(setters) == 1)
    setter = setters[0]
    identity = [m for m in methods if m['rva'] and not m['parameters'] and m['return_type']['kind'] == 9]
    sizes = [m for m in methods if m['rva'] and not m['parameters'] and m['return_type']['kind'] == 8]
    _check(len(identity) == len(sizes) == 1)
    id_context = Context(image, identity[0]['rva'])
    getters = []
    for ins in id_context.seq:
        if ins.mnemonic != 'call' or ins.operands[0].type != CS_OP_IMM:
            continue
        target = ins.operands[0].imm - image.base
        declared = _typed(view, target)
        params = declared['method']['parameters']
        if declared['owner']['definition'] == helper_owner and len(params) == 2 and [p['type']['kind'] for p in params] == [11, 8]:
            getters.append((ins, declared))
    _check(len(getters) == 1)
    getter_call, getter = getters[0]
    wrapper_definition = getter['method']['return_type'].get('definition')
    _check(getter['method']['return_type']['kind'] == 17 and wrapper_definition is not None)
    _check(_handle(id_context, Definitions(id_context.seq, id_context.noreturn), pointer_states(id_context),
                   getter_call.address, 'rcx', handle_offset, handle_mask) == 'masked')
    id_decoders = [_typed(view, ins.operands[0].imm - image.base) for ins in id_context.seq
                   if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM and ins.address != getter_call.address]
    _check(len(id_decoders) == 1 and id_decoders[0]['owner']['definition'] == wrapper_definition
           and id_decoders[0]['method']['return_type']['kind'] == 9 and not id_decoders[0]['method']['parameters'])
    identity_slot = id_context.constants.value_before(getter_call.address, 'rdx', 32)
    size_code = image.leaf(sizes[0]['rva'])
    _check(len(size_code) == 2 and size_code[0].mnemonic == 'mov' and size_code[0].op_str.startswith('eax, ')
           and size_code[0].operands[1].type == CS_OP_IMM and size_code[1].mnemonic == 'ret')
    native_size = size_code[0].operands[1].imm
    _check(8 <= native_size <= 4096)
    query, wrapper_size, buffer_offset = _wrapper(view)
    _check(reader['return_type']['kind'] == 1 and len(reader['parameters']) == 2
           and reader['parameters'][0]['type']['index'] == stream
           and reader['parameters'][1]['type'].get('name') == 'INativeAllocator')
    pointers = pointer_states(context, output_pointers={query['rva']: (wrapper_size, {buffer_offset: ('native-buffer', 0)})})
    definitions = Definitions(context.seq, context.noreturn)
    refs, scalar_stores, used_slots = {}, {}, set()
    for ins in context.seq:
        if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM:
            target = ins.operands[0].imm - image.base
            if target in {setter['rva'], query['rva']}:
                name = 'rcx' if target == setter['rva'] else 'rdx'
                _check(_handle(context, definitions, pointers, ins.address, name, handle_offset, handle_mask) == 'masked')
            if target == setter['rva']:
                offset = context.constants.value_before(ins.address, 'rdx', 32)
                _check(offset in string_slots)
                refs[ins.address] = offset
                used_slots.add(offset)
        elif ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_MEM and ins.operands[0].size == 4:
            memory = ins.operands[0].mem
            owner = pointers.get(ins.address, {}).get(('reg', register(ins.reg_name(memory.base))[0]))
            if owner is not None and owner[0] == 'native-buffer' and not memory.index:
                offset = owner[1] + memory.disp
                _check(offset not in string_slots)
                refs[ins.address] = offset
                scalar_stores.setdefault(offset, []).append(ins.address)
    _check(used_slots == set(string_slots) and identity_slot in scalar_stores)
    offsets = sorted(set(refs.values()))
    occupied = [byte for offset in offsets for byte in range(offset, offset + (8 if offset in string_slots else 4))]
    _check(sorted(occupied) == list(range(native_size)), 'The native record storage has unknown, overlapping or missing fields.')
    authored = [{'name': f'slot_{offset}', 'authored_offset_word': offset} for offset in offsets]
    header, fields = ordered_fields(context, authored, object_calls=refs)
    _check({r['offset'] for r in fields} == set(offsets))
    contracts = Contracts(view, stream)
    primitives, scalar_setters = contracts.wrappers([{'type': {'kind': 17, 'definition': wrapper_definition}}])
    _check(scalar_setters and primitives.get(wrapper_definition) == 9)
    result = []
    for field in fields:
        offset, first = field['offset'], field['representative'] - image.base
        if offset in string_slots:
            length = context.operations(first, 16, 'length')
            cipher, operation = context.cipher(set(field['nodes']))
            value, default = binary.Text(binary.Word(16, length), cipher, operation), None
        else:
            calls = [ins for ins in context.seq if ins.address in field['nodes'] and ins.mnemonic == 'call'
                     and ins.operands[0].type == CS_OP_IMM and ins.operands[0].imm - image.base in scalar_setters]
            if calls:
                steps = context.operations(first, 32, 'protected_scalar', setters=scalar_setters)
            else:
                stores = set(scalar_stores[offset]) & set(field['nodes'])
                _check(len(stores) == 1)
                steps = context.operations(first, 32, 'scalar', stores.pop() - image.base)
            value, default = binary.Word(32, steps), 0
        result.append(binary.Field(f'slot_{offset}', value, 1 << field['bit'], raw_flag=field['raw_flag'],
                                   present_when_set=field['present_when_set'], default=default))
    hashes = {r['sha256'] for r in strings}
    hashes.update(hashlib.sha256(image.window(m['rva'])).hexdigest()
                  for m in (reader, identity[0], query, setter, getter['method'], id_decoders[0]['method']))
    return Slots(binary.Record(tuple(result), binary.Word(header['bits'], header['operations'])), identity_slot,
                 string_slots, helper_owner, string_getter, tuple(sorted(hashes)))
