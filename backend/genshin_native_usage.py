"""Native-owned metadata usage dispatch and complete original usage tables."""
import struct

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, Definitions, _check
from .genshin_native_metadata import HEADER_SIZE, owns_global_pointer, pointer, rip_references, root, word
from . import genshin_native_expression as e


def table_reader(view, namespace, name):
    owner = view.named(namespace, name)
    readers = [m for m in view.methods(owner['definition']) if m['name'] == 'FromBinaryInner'
               and len(m['parameters']) == 1 and m['return_type']['kind'] == 1 and m['rva']]
    _check(len(readers) == 1, 'The original named table reader is ambiguous.')
    reader = readers[0]
    stream = reader['parameters'][0]['type']['index']
    returns = {index for index in set(view.bindings.return_types)
               if view.bindings.describe(index).get('definition') == owner['definition']}
    methods = {index for index, typed in enumerate(view.bindings.return_types) if typed in returns}
    candidates = []
    for definition, (start, end) in view._methods.items():
        if not any(start <= index < end for index in methods):
            continue
        rows = view.methods(definition)
        getters = [m for m in rows if m['index'] in methods and len(m['parameters']) == 1
                   and m['parameters'][0]['type']['kind'] == 9]
        loaders = [m for m in rows if m['return_type']['kind'] == 1 and m['rva']
                   and len(m['parameters']) == 1 and m['parameters'][0]['type']['index'] == stream]
        if getters and len(loaders) == 1:
            candidates.append({'owner': view.bindings.rows[definition], 'getters': getters, 'loader': loaders[0]})
    _check(len(candidates) == 1, 'The original typed table container is missing or ambiguous.')
    return {'owner': owner, 'reader': reader, 'stream': stream, 'container': candidates[0]}


def dispatcher(view, table):
    image = view.image
    targets = {i.operands[0].imm - image.base
               for i in image.instructions(table['container']['loader']['rva'])
               if i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM}
    found = []
    for target in sorted(targets):
        try:
            seq = image.instructions(target)
        except ValueError:
            continue
        if (any(i.mnemonic == 'shr' and i.operands[1].type == CS_OP_IMM
                and i.operands[1].imm == 29 for i in seq)
            and any(i.mnemonic == 'and' and i.operands[1].type == CS_OP_IMM
                    and i.operands[1].imm == 0x1fffffff for i in seq)
            and any(i.mnemonic == 'mov' and len(i.operands) == 2 and i.operands[1].type == CS_OP_MEM
                    and i.reg_name(i.operands[1].mem.base) == 'rip'
                    and pointer(i, i.operands[1], image) == view.bindings.identifiers.owner.global_rva
                    for i in seq)):
            found.append((target, seq))
    _check(len(found) == 1, 'The original table usage initializer is missing or ambiguous.')
    owner, seq = found[0]
    tables = []
    for at, ins in enumerate(seq[:-3]):
        load, add, jump = seq[at + 1:at + 4]
        if not (ins.mnemonic == 'lea' and ins.operands[1].type == CS_OP_MEM
                and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                and load.mnemonic == 'movsxd' and load.operands[1].type == CS_OP_MEM
                and load.operands[1].mem.scale == 4 and load.operands[1].mem.index
                and load.operands[1].mem.base == ins.operands[0].reg
                and add.mnemonic == 'add' and add.operands[0].reg == load.operands[0].reg
                and add.operands[1].reg == ins.operands[0].reg
                and jump.mnemonic == 'jmp' and jump.operands[0].type == CS_OP_REG
                and jump.operands[0].reg == add.operands[0].reg):
            continue
        table_rva = pointer(ins, ins.operands[1], image)
        raw = image.offset(table_rva, 32)
        cases = tuple(table_rva + struct.unpack_from('<i', image.data, raw + 4 * kind)[0]
                      for kind in range(8))
        positions = {i.address - image.base for i in seq}
        _check(all(case in positions for case in cases))
        tables.append((table_rva, cases, jump.address - image.base))
    _check(len(tables) == 1, 'The original typed usage dispatch is ambiguous.')
    return {'rva': owner, 'jump_table_rva': tables[0][0], 'cases': tables[0][1], 'jump_rva': tables[0][2]}


def slot_arrays(view, dispatch, usages, kinds=(1, 3, 5)):
    """Own actual class/method/literal slot arrays through typed dispatch cases."""
    image = view.image
    seq = image.instructions(dispatch['rva'])
    stores = dict(view.bindings.registration.stores)
    result = {}
    _check(kinds and len(set(kinds)) == len(kinds) and all(kind in range(8) for kind in kinds))
    for kind in kinds:
        target = dispatch['cases'][kind]
        at = next(n for n, ins in enumerate(seq) if ins.address - image.base == target)
        found = []
        for n in range(at, min(at + 9, len(seq) - 1)):
            ins, following = seq[n:n + 2]
            if not (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_REG
                    and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                    and following.mnemonic == 'mov' and following.operands[1].type == CS_OP_MEM
                    and following.operands[1].size == 8 and not following.operands[1].mem.index
                    and following.operands[1].mem.base == ins.operands[0].reg):
                continue
            global_rva = pointer(ins, ins.operands[1], image)
            _check(global_rva in stores)
            field = following.operands[1].mem.disp
            _check(0 <= field <= 4096 and field % 8 == 0)
            raw = image.offset(stores[global_rva] + field, 8)
            address, = struct.unpack_from('<Q', image.data, raw)
            _check(address >= image.base)
            array = address - image.base
            slots = [slot for actual, _identity, slot in usages.pairs if actual == kind]
            _check(slots and max(slots) < 16_000_000)
            span = 8 * (max(slots) + 1)
            _check(sum(start <= array and array + span <= start + max(virtual, size)
                       for start, virtual, _raw, size in image.sections.values()) == 1,
                   'The native slot array exceeds its original image section.')
            found.append((global_rva, field, array))
        _check(found and len(set(found)) == 1, 'The original typed slot-array owner is ambiguous.')
        global_rva, field, array = found[0]
        result[kind] = {'registration_global_rva': global_rva, 'field': field, 'array_rva': array,
                        'case_rva': target}
    return result


def header_role(view, seq, field, *, jump_targets=None):
    """Native arithmetic for a format header role, with CFG-owned constants."""
    constants = Constants(seq, jump_targets=jump_targets)
    definitions = Definitions(seq, jump_targets=jump_targets)
    candidates = []
    for at, ins in enumerate(seq[:-2]):
        if not (len(ins.operands) == 2 and ins.operands[0].type == CS_OP_REG
                and ins.operands[1].type == CS_OP_MEM and ins.operands[1].mem.disp == field
                and ins.operands[1].size == 4):
            continue
        if not owns_global_pointer(view.image, seq, ins, ins.operands[1].mem,
                                   view.bindings.identifiers.owner.global_rva, definitions):
            continue
        steps = None
        if ins.mnemonic == 'add':
            steps = (('add', constants.value_before(ins.address, root(ins, ins.operands[0]), 32)),)
        elif ins.mnemonic == 'mov':
            a, b = seq[at + 1:at + 3]
            if (a.mnemonic == 'mov' and a.operands[1].type == CS_OP_IMM
                    and b.mnemonic == 'add' and b.operands[0].reg == ins.operands[0].reg
                    and b.operands[1].reg == a.operands[0].reg):
                steps = (('add', constants.value_before(b.address, root(a, a.operands[0]), 32)),)
        if steps is not None:
            offset = word(view.bindings.identifiers.header, field, steps)
            _check(offset < len(view.metadata) - HEADER_SIZE)
            candidates.append({'field': field, 'operations': steps, 'body_offset': offset,
                               'read_rva': ins.address - view.image.base})
    _check(len(candidates) == 1, 'The original metadata header role is missing or ambiguous.')
    return candidates[0]


def usage_profile(view, dispatch):
    image, ids = view.image, view.bindings.identifiers
    seq = image.instructions(dispatch['rva'])
    list_header, pair_header = header_role(view, seq, 0x1a0), header_role(view, seq, 0x78)
    body_registers = {root(i, i.operands[0]) for i in seq
                      if i.mnemonic == 'mov' and i.operands[1].type == CS_OP_MEM
                      and i.reg_name(i.operands[1].mem.base) == 'rip'
                      and pointer(i, i.operands[1], image) == ids.profile.body_global_rva}
    _check(body_registers)

    def table_begin(profile):
        read = next(n for n, i in enumerate(seq) if i.address - image.base == profile['read_rva'])
        positions = [n for n in range(read + 1, min(read + 8, len(seq)))
                     if seq[n].mnemonic == 'add' and seq[n].operands[1].type == CS_OP_REG
                     and root(seq[n], seq[n].operands[1]) in body_registers]
        _check(len(positions) == 1)
        return positions[0]

    begin = table_begin(list_header)
    table_register = root(seq[begin], seq[begin].operands[0])
    initial = {table_register: ('input', 'table')}
    for ins in seq[:begin]:
        if (ins.mnemonic == 'mov' and ins.operands[0].type == CS_OP_REG
                and ins.operands[1].type == CS_OP_REG and root(ins, ins.operands[1]) == 'rcx'):
            initial[root(ins, ins.operands[0])] = e.operation('cast', ins.operands[1].size * 8, ('input', 'rcx'))
    end = next(n for n in range(begin + 1, len(seq)) if seq[n].mnemonic == 'cmp')
    state, fields = e.extract(seq[begin + 1:end], table_register, 4, {0: 4, 4: 4},
                             image_base=image.base, index_limit=1_000_000, initial=initial)
    _check(len(fields) == 2 and seq[end + 1].mnemonic == 'jne')
    target = seq[end + 1].operands[0].imm
    tail = next(n for n, i in enumerate(seq) if i.address == target)
    bounds = {}
    for ins in seq[tail:tail + 2]:
        _check(ins.mnemonic == 'xor' and ins.operands[1].type == CS_OP_IMM)
        expr = e.operation('xor', 32, state[root(ins, ins.operands[0])], e.constant(ins.operands[1].imm & 0xffffffff))
        raw = {leaf[1] for leaf in e.leaves(expr) if leaf[0] == 'field'}
        _check(len(raw) == 1)
        bounds[raw.pop()] = expr
    _check(set(bounds) == {0, 4})
    _check({leaf[1] for leaf in e.leaves(bounds[0]) if leaf[0] == 'input'} == {'rcx'})

    # Exact loop consumer owns the denominator, including the sentinel boundary.
    count_candidates = []
    owners = {r['function'] for r in rip_references(image, {ids.owner.global_rva}) if r['function'] is not None}
    for owner in sorted(owners):
        try:
            instructions = image.instructions(owner)
        except ValueError:
            continue
        for at, ins in enumerate(instructions[:-5]):
            cmp, branch, shift, dec = instructions[at + 1:at + 5]
            if not (ins.mnemonic == 'add' and ins.operands[1].type == CS_OP_MEM
                    and ins.operands[1].mem.disp == 0x88 and ins.operands[1].size == 4
                    and cmp.mnemonic == 'cmp' and branch.mnemonic.startswith('j')
                    and shift.mnemonic == 'shr' and shift.operands[1].type == CS_OP_IMM
                    and shift.operands[1].imm == 2 and dec.mnemonic == 'dec'
                    and root(ins, ins.operands[0]) == root(shift, shift.operands[0]) == root(dec, dec.operands[0])
                    and any(i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM
                            and i.operands[0].imm - image.base == dispatch['rva'] for i in instructions)):
                continue
            steps = (('add', Constants(instructions).value_before(ins.address, root(ins, ins.operands[0]), 32)),)
            if not owns_global_pointer(image, instructions, ins, ins.operands[1].mem, ids.owner.global_rva):
                continue
            length = word(ids.header, 0x88, steps)
            _check(length % 4 == 0 and 8 <= length <= 4_000_004)
            count_candidates.append({'count': length // 4 - 1, 'operations': steps, 'method_rva': owner})
    _check(len(count_candidates) == 1, 'The complete original usage denominator is ambiguous.')
    count = count_candidates[0]

    pair_begin = table_begin(pair_header)
    pair_table = root(seq[pair_begin], seq[pair_begin].operands[0])
    pair_end = next(n for n in range(pair_begin + 1, len(seq) - 1)
                    if seq[n].mnemonic == 'mov' and seq[n + 1].mnemonic == 'and'
                    and seq[n + 1].operands[1].type == CS_OP_IMM and seq[n + 1].operands[1].imm == 0x1fffffff)
    pair_read = next(n for n, i in enumerate(seq) if i.address - image.base == pair_header['read_rva'])
    producers = []
    for at in range(tail, pair_read - 1):
        ins, following = seq[at:at + 2]
        if not (ins.mnemonic == 'imul' and len(ins.operands) == 3 and ins.operands[1].type == CS_OP_REG
                and ins.operands[2].type == CS_OP_IMM and following.mnemonic == 'add'
                and following.operands[0].reg == ins.operands[0].reg and following.operands[1].type == CS_OP_IMM):
            continue
        key, index = root(ins, ins.operands[0]), root(ins, ins.operands[1])
        mul, add = ins.operands[2].imm & 0xffffffff, following.operands[1].imm & 0xffffffff
        increments = [i for i in seq[at + 2:pair_read] if i.mnemonic == 'add'
                      and i.operands[0].type == CS_OP_REG and root(i, i.operands[0]) == key
                      and i.operands[1].type == CS_OP_IMM]
        _check(len(increments) == 1 and increments[0].operands[1].imm & 0xffffffff == mul)
        producers.append((key, index, e.operation('add', 32,
                         e.operation('imul', 32, ('input', index), e.constant(mul)), e.constant(add))))
    _check(len(producers) == 1)
    key, index, expr = producers[0]
    pure = [i for i in seq[pair_begin + 1:pair_end] if i.mnemonic != 'cmp' and not i.mnemonic.startswith('j')]
    state, fields = e.extract(pure, pair_table, 8, {0: 4, 4: 4}, image_base=image.base,
                             index_limit=16_000_000, initial={pair_table: ('input', 'table'), key: expr})
    _check(len(fields) == 2)
    source = state[root(seq[pair_end], seq[pair_end].operands[1])]
    slot = state[root(pure[-1], pure[-1].operands[0])]
    _check({leaf[1] for node in (source, slot) for leaf in e.leaves(node) if leaf[0] == 'input'} == {index})
    return {'list_header': list_header, 'pair_header': pair_header, 'count': count,
            'first': bounds[0], 'next': bounds[4], 'pair_index': index, 'source': source, 'slot': slot}


class Usages:
    def __init__(self, view, profile):
        data, count = view.metadata, profile['count']['count']
        list_at = HEADER_SIZE + profile['list_header']['body_offset']
        pair_at = HEADER_SIZE + profile['pair_header']['body_offset']
        _check(0 < count <= 1_000_000 and list_at + 4 * (count + 1) <= len(data))
        bounds = [e.evaluate(profile['first'], {'rcx': index}, {0: word(data, list_at + 4 * index, ())})
                  for index in range(count + 1)]
        _check(bounds[0] == 0 and all(a <= b for a, b in zip(bounds, bounds[1:])))
        _check(bounds[-1] <= 16_000_000 and pair_at + 8 * bounds[-1] <= len(data))
        for index in range(count):
            fields = {0: word(data, list_at + 4 * index, ()), 4: word(data, list_at + 4 * (index + 1), ())}
            _check(e.evaluate(profile['next'], {'rcx': index}, fields) == bounds[index + 1])
        pairs = []
        for index in range(bounds[-1]):
            fields = {0: word(data, pair_at + 8 * index, ()), 4: word(data, pair_at + 8 * index + 4, ())}
            inputs = {profile['pair_index']: index}
            source, slot = e.evaluate(profile['source'], inputs, fields), e.evaluate(profile['slot'], inputs, fields)
            pairs.append((source >> 29, source & 0x1fffffff, slot))
        self.profile, self.bounds, self.pairs = profile, tuple(bounds), tuple(pairs)

    def entries(self, index):
        _check(type(index) is int and 0 <= index < len(self.bounds) - 1)
        return self.pairs[self.bounds[index]:self.bounds[index + 1]]
