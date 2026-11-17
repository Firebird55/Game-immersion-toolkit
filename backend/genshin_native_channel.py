"""Current original ChannelConfig source and object-ID consumer contract.

The contract owns an inert profile input, never an active dispatch descriptor.
No current basename, object ID, field index, address or RSA value is pinned.
"""
import hashlib
import re

from .genshin_native_dispatch import _derive_static_string, _environment, _register_source, derive_initial_seed
from .genshin_native_metadata import root
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, Definitions, _check


SCHEMA = 'genshin-original-channel-loader-v1'


def _context(image, method):
    sequence = image.instructions(method['rva'])
    body = image.window(method['rva'])
    _check(0 < len(sequence) <= 8192 and sum(ins.size for ins in sequence) == len(body)
           and sequence[-1].address + sequence[-1].size == image.base + method['rva'] + len(body))
    return {'image': image, 'sequence': sequence, 'definitions': Definitions(sequence),
            'instructions': {ins.address: ins for ins in sequence}, 'constants': Constants(sequence)}


def _leaf(context, address, name, depth=0):
    _check(depth < 32)
    definitions = context['definitions'].before(address, name)
    _check(len(definitions) == 1 and None not in definitions)
    definition, = definitions
    ins = context['instructions'][definition]
    if (ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == CS_OP_REG
            and ins.operands[0].size == 8 and ins.operands[1].type == CS_OP_REG and ins.operands[1].size == 8):
        return _leaf(context, ins.address, root(ins, ins.operands[1]), depth + 1)
    return ins


def _calls(context, rva=None):
    base = context['image'].base
    return [ins for ins in context['sequence'] if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
            and (rva is None or ins.operands[0].imm - base == rva)]


def _method(view, definition, name, returned, parameters=()):
    methods = [row for row in view.methods(definition) if row['name'] == name and row['rva']
               and row['return_type'].get('definition') == returned
               and tuple(parameter['type']['kind'] for parameter in row['parameters']) == parameters]
    _check(len(methods) == 1, 'The original typed channel loader is missing or ambiguous.')
    return methods[0]


def _slot(ins):
    _check(ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[1].type == CS_OP_MEM)
    source = ins.operands[1]
    _check(source.size == 8 and not source.mem.index and ins.reg_name(source.mem.base) in ('rsp', 'rbp'))
    return ins.reg_name(source.mem.base), source.mem.disp


def _object_candidates(context, combine_call):
    """Paired size/read IDs on the same handle opened from the authored path.

    Complete original map/JSON validation must select one ID and codec contract.
    These bounded ABI candidates do not name or execute the native child APIs.
    """
    sequence = context['sequence']
    positions = {ins.address: index for index, ins in enumerate(sequence)}
    grouped = {}
    for call in _calls(context):
        try:
            value = context['constants'].value_before(call.address, 'rdx', 32)
            _check(type(value) is int and 0 <= value < 1 << 32)
            handle = _leaf(context, call.address, 'rcx')
            slot = _slot(handle)
            frame = context['definitions'].before(handle.address, slot[0])
            _check(len(frame) == 1 and None not in frame)
            grouped.setdefault((value, slot, tuple(frame)), []).append(call)
        except ValueError:
            continue
    candidates = []
    for (value, slot, _frame), calls in grouped.items():
        if len(calls) != 2 or calls[0].operands[0].imm == calls[1].operands[0].imm:
            continue
        first, second = calls
        at = positions[first.address]
        if at + 2 >= len(sequence):
            continue
        test, branch = sequence[at + 1:at + 3]
        if not (test.mnemonic == 'test' and len(test.operands) == 2
                and all(op.type == CS_OP_REG and test.reg_name(op.reg) == 'eax' for op in test.operands)
                and branch.mnemonic == 'jle'):
            continue
        writes = [ins for ins in sequence[:positions[second.address]] if ins.operands
                  and ins.operands[0].type == CS_OP_MEM and ins.operands[0].access & 2
                  and not ins.operands[0].mem.index and ins.reg_name(ins.operands[0].mem.base) == slot[0]
                  and ins.operands[0].mem.disp == slot[1]]
        if len(writes) != 1:
            continue
        store, = writes
        try:
            _check(store.address < first.address and store.mnemonic == 'mov' and store.operands[0].size == 8
                   and store.operands[1].type == CS_OP_REG and store.operands[1].size == 8)
            opened = _leaf(context, store.address, root(store, store.operands[1]))
            _check(opened in _calls(context))
            path = _leaf(context, opened.address, 'rcx')
            _check(path.address == combine_call.address)
            buffer = _leaf(context, second.address, 'r8')
            _check(buffer in _calls(context) and first.address < buffer.address < second.address)
        except ValueError:
            continue
        candidates.append({'id': value, 'size_call_rva': first.address - context['image'].base,
                           'read_call_rva': second.address - context['image'].base,
                           'open_call_rva': opened.address - context['image'].base,
                           'handle_slot': list(slot)})
    _check(candidates and len(candidates) <= 16, 'The original channel object-ID consumer is unsupported or ambiguous.')
    return candidates


def derive_channel_loader(view, usages, arrays, literals):
    source = _derive_static_string(view, usages, arrays, literals, 'channelConfigBlkName')
    _check(re.fullmatch('[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}', source.value),
           'The original channel source basename is unsupported.')
    image = view.image
    owner = view.named('MoleMole', 'Miscs')
    channel = view.named('MoleMole', 'ConfigChannel')
    dispatch = view.named('MoleMole', 'ConfigDispatchUrl')
    fields = [row for row in view.field_offsets(owner['definition']) if row['name'] == '_configChannel'
              and row['type'].get('definition') == channel['definition']]
    _check(len(fields) == 1)
    cache, = fields
    attributes = int.from_bytes(view.bindings.type_record(cache['type']['index'])[8:10], 'little')
    _check(attributes & 0x10 and not attributes & 0x40 and cache['authored_offset_word'] >> 24 == 4)
    cache_offset = cache['authored_offset_word'] & 0xffffff
    getter = _method(view, owner['definition'], 'GetConfigChannel', channel['definition'])
    loader = _method(view, owner['definition'], 'LoadChannelConfigBlk', channel['definition'])
    gc, lc = _context(image, getter), _context(image, loader)
    getter_calls = _calls(gc, loader['rva'])
    _check(len(getter_calls) == 1)
    reads, writes = [], []
    for ins in gc['sequence']:
        if ins.mnemonic != 'mov' or len(ins.operands) != 2:
            continue
        for index, op in enumerate(ins.operands):
            if (op.type != CS_OP_MEM or op.size != 8 or op.mem.index or op.mem.disp != cache_offset
                    or ins.reg_name(op.mem.base) in ('rip', 'rsp', 'rbp')):
                continue
            global_rva, _chain = _register_source(gc, ins.address, ins.reg_name(op.mem.base))
            _check(global_rva == source.proof['storage_global_rva'])
            (reads if index == 1 else writes).append(ins)
    _check(len(reads) == len(writes) == 1)
    _check(_leaf(gc, writes[0].address, root(writes[0], writes[0].operands[1])).address == getter_calls[0].address)
    path_owner = view.named('System.IO', 'Path')
    path_methods = [row for row in view.methods(path_owner['definition']) if row['name'] == 'Combine'
                    and row['rva'] and row['return_type']['kind'] == 14
                    and tuple(p['type']['kind'] for p in row['parameters']) == (14, 14)]
    combine_calls = [call for row in path_methods for call in _calls(lc, row['rva'])]
    _check(len(combine_calls) == 1)
    combine, = combine_calls
    filename = _leaf(lc, combine.address, 'rdx')
    _check(filename.mnemonic == 'mov' and filename.operands[1].type == CS_OP_MEM
           and filename.operands[1].size == 8 and not filename.operands[1].mem.index
           and filename.operands[1].mem.disp == source.proof['field']['packed_offset_word'] & 0xffffff)
    global_rva, _chain = _register_source(lc, filename.address, filename.reg_name(filename.operands[1].mem.base))
    _check(global_rva == source.proof['storage_global_rva'])
    config_fields = sorted(row['name'] for row in view.fields(channel['definition']))
    dispatch_fields = sorted(row['name'] for row in view.fields(dispatch['definition']))
    _check({'ChannelName', 'DispatchConfigs'} <= set(config_fields)
           and {'DispatchName', 'DispatchUrls'} <= set(dispatch_fields)
           and len(config_fields) == len(set(config_fields)) and len(dispatch_fields) == len(set(dispatch_fields)))
    return {'schema': SCHEMA, 'source_basename': source.value, 'source_field': source.proof,
            'cache_field': cache, 'config_declaration': channel, 'dispatch_declaration': dispatch,
            'config_fields': config_fields, 'dispatch_fields': dispatch_fields,
            'object_candidates': _object_candidates(lc, combine),
            'methods': [{'name': row['name'], 'index': row['index'], 'rva': row['rva'],
                         'sha256': hashlib.sha256(image.window(row['rva'])).hexdigest()} for row in (getter, loader)],
            'profile_only': True, 'complete_dispatch_bootstrap': False, 'later_override_excluded': False}


def read_bootstrap_inputs(executable, metadata, *, expected_owner):
    view, _anchor, usages, arrays, literals = _environment(executable, metadata, expected_owner)
    result = derive_initial_seed(view, usages, arrays, literals)
    result.proof['channel_loader'] = derive_channel_loader(view, usages, arrays, literals)
    _check(all(result.proof[key] == value for key, value in expected_owner.items()))
    return result
