"""Original metadata literals from their actual native constructor and slots."""
import bisect
import struct

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, VOLATILE, register, _check
from .genshin_native_metadata import HEADER_SIZE, pointer, rip_references, root, word
from .genshin_native_usage import header_role
from . import genshin_native_expression as e

MASK64 = (1 << 64) - 1


def _preserves(image, call, name):
    if call.operands[0].type != CS_OP_IMM:
        return False
    try:
        seq = image.instructions(call.operands[0].imm - image.base)
    except ValueError:
        return False
    if len(seq) > 128 or not any(i.mnemonic == 'ret' for i in seq):
        return False
    positions = {i.address for i in seq}
    for ins in seq:
        if ins.mnemonic == 'call' or name in {register(ins.reg_name(r))[0] for r in ins.regs_access()[1]}:
            return False
        if ins.mnemonic.startswith('j') and not (ins.operands[0].type == CS_OP_IMM and ins.operands[0].imm in positions):
            return False
    return True


def _index_aliases(image, prefix):
    aliases = {'rcx'}
    for ins in prefix:
        if ins.mnemonic == 'call':
            aliases = {name for name in aliases if name not in VOLATILE or _preserves(image, ins, name)}
            continue
        previous = set(aliases)
        aliases -= {register(ins.reg_name(r))[0] for r in ins.regs_access()[1]}
        if (ins.mnemonic == 'mov' and len(ins.operands) == 2 and all(op.type == CS_OP_REG for op in ins.operands)
                and root(ins, ins.operands[1]) in previous and ins.operands[0].size >= 4):
            aliases.add(root(ins, ins.operands[0]))
    return aliases


def seed_profile(image, seq):
    candidates = []
    constants = Constants(seq)
    for at in range(len(seq) - 5):
        pairs, pos = [], at
        while pos + 1 < len(seq):
            literal, use = seq[pos:pos + 2]
            if not (literal.mnemonic == 'movabs' and literal.operands[0].type == CS_OP_REG
                    and literal.operands[1].type == CS_OP_IMM and literal.operands[0].size == 8
                    and use.mnemonic in ('imul', 'xor', 'add') and len(use.operands) == 2
                    and all(op.type == CS_OP_REG and op.size == 8 for op in use.operands)
                    and use.operands[0].reg == literal.operands[0].reg):
                break
            pairs.append((literal, use))
            pos += 2
        if len(pairs) < 3 or pairs[0][1].mnemonic != 'imul':
            continue
        aliases = _index_aliases(image, seq[:at])
        if root(pairs[0][1], pairs[0][1].operands[1]) not in aliases:
            continue
        expr = ('input', 'index')
        previous = None
        valid = True
        for literal, use in pairs:
            if previous is not None and root(use, use.operands[1]) != previous:
                valid = False
                break
            expr = e.operation(use.mnemonic, 64, expr, e.constant(literal.operands[1].imm & MASK64))
            previous = root(use, use.operands[0])
        if not valid:
            continue
        loops = []
        for n, ins in enumerate(seq[:-4]):
            use, increment, store = seq[n + 1:n + 4]
            if not (ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_MEM and ins.operands[1].size == 8
                    and ins.operands[1].mem.scale == 8 and ins.operands[1].mem.index
                    and use.mnemonic == 'xor' and root(use, use.operands[0]) == root(ins, ins.operands[0])
                    and root(use, use.operands[1]) == previous
                    and increment.mnemonic == 'add' and root(increment, increment.operands[0]) == previous
                    and increment.operands[1].type == CS_OP_REG
                    and store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM
                    and store.operands[0].size == 8 and store.operands[1].reg == ins.operands[0].reg
                    and any(i.mnemonic.startswith('j') and i.operands[0].type == CS_OP_IMM
                            and i.operands[0].imm == ins.address for i in seq[n + 4:n + 9])):
                continue
            step = constants.value_before(increment.address, root(increment, increment.operands[1]), 64)
            loops.append((step, ins.address - image.base))
        if len(loops) != 1:
            continue
        step, scalar_loop = loops[0]
        lanes = set()
        for ins in seq:
            if (ins.mnemonic in ('paddq', 'movdqa') and len(ins.operands) == 2
                    and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rip'):
                raw = image.offset(pointer(ins, ins.operands[1], image), 16)
                lanes.add(struct.unpack_from('<QQ', image.data, raw))
        _check(lanes == {(0, step)} | {(step * k & MASK64,) * 2 for k in (2, 4, 6, 8)},
               'The original literal vector lanes disagree with its scalar stream.')
        candidates.append({'expression': expr, 'step': step, 'scalar_loop_rva': scalar_loop})
    _check(len(candidates) == 1, 'The original literal seed constructor is missing or ambiguous.')
    return candidates[0]


def literal_profile(view, dispatch):
    image = view.image
    seq = image.instructions(dispatch['rva'])
    begin = next(n for n, i in enumerate(seq) if i.address - image.base == dispatch['cases'][5])
    end = next(n for n in range(begin, len(seq)) if seq[n].mnemonic == 'call')
    call = seq[end]
    _check(call.operands[0].type == CS_OP_IMM)
    constructor = call.operands[0].imm - image.base
    seed = seed_profile(image, image.instructions(constructor))
    jumps = {image.base + dispatch['jump_rva']: tuple(image.base + rva for rva in dispatch['cases'])}
    table, data = (header_role(view, seq, field, jump_targets=jumps) for field in (0x1ec, 0x12c))
    read = next(n for n, i in enumerate(seq) if i.address - image.base == table['read_rva'])
    starts = [n for n in range(read + 1, min(read + 8, end))
              if seq[n].mnemonic == 'add' and seq[n].operands[1].type == CS_OP_REG
              and root(seq[n], seq[n].operands[1]) in {
                  root(i, i.operands[0]) for i in seq[:begin]
                  if i.mnemonic == 'mov' and i.operands[1].type == CS_OP_MEM
                  and i.reg_name(i.operands[1].mem.base) == 'rip'
                  and pointer(i, i.operands[1], image) == view.bindings.identifiers.profile.body_global_rva}]
    _check(len(starts) == 1)
    start = starts[0]
    stop = next(n for n in range(start + 1, end) if seq[n].mnemonic == 'cdqe')
    initial = {name: ('input', 'index') for name in _index_aliases(image, seq[begin:start])}
    table_reg = root(seq[start], seq[start].operands[0])
    initial[table_reg] = ('input', 'table')
    state, fields = e.extract(seq[start + 1:stop], table_reg, 4, {0: 4, 4: 4},
                             image_base=image.base, index_limit=1_000_000, initial=initial)
    _check({field['field_offset'] for field in fields} == {0, 4})
    expression = state['rax']
    _check({leaf[1] for leaf in e.leaves(expression) if leaf[0] == 'field'} == {0}
           and {leaf[1] for leaf in e.leaves(expression) if leaf[0] == 'input'} == {'index'})
    return {'table': table, 'data': data, 'table_expression': expression,
            'constructor_rva': constructor, 'seed': seed}


class Literals:
    def __init__(self, view, usages, profile):
        # A complete native usage inventory, rather than scan-until-invalid,
        # owns the literal denominator. Sparse/ambiguous formats fail closed.
        slots = {}
        for kind, identity, slot in usages.pairs:
            if kind == 5:
                slots.setdefault(identity, set()).add(slot)
        _check(slots and max(slots) < 1_000_000 and sorted(slots) == list(range(max(slots) + 1)))
        count = len(slots)
        table_at = HEADER_SIZE + profile['table']['body_offset']
        data_at = HEADER_SIZE + profile['data']['body_offset']
        _check(table_at + 4 * (count + 1) <= len(view.metadata))
        bounds = [e.evaluate(profile['table_expression'], {'index': index},
                             {0: word(view.metadata, table_at + 4 * index, ())}) for index in range(count + 1)]
        _check(bounds[0] == 0 and all(a <= b and b - a <= 1024**2 for a, b in zip(bounds, bounds[1:]))
               and data_at + bounds[-1] <= len(view.metadata))
        rows, invalid = [], []
        for index, (start, end) in enumerate(zip(bounds, bounds[1:])):
            cipher = view.metadata[data_at + start:data_at + end]
            key = e.evaluate(profile['seed']['expression'], {'index': index})
            decoded = bytearray()
            for pos in range(0, len(cipher), 8):
                decoded.extend((int.from_bytes(cipher[pos:pos + 8].ljust(8, b'\0'), 'little') ^ key).to_bytes(8, 'little'))
                key = (key + profile['seed']['step']) & MASK64
            raw = bytes(decoded[:len(cipher)])
            try:
                rows.append(raw.decode('utf-8', errors='strict'))
            except UnicodeDecodeError:
                rows.append(None)
                invalid.append(index)
        self.rows, self.invalid_utf8, self.slots, self.profile = tuple(rows), tuple(invalid), slots, profile

    def text(self, index):
        _check(type(index) is int and 0 <= index < len(self.rows) and self.rows[index] is not None,
               'The original literal is unavailable or is not strict UTF-8.')
        return self.rows[index]


def path_callers(view, literals, arrays, *, roles=None):
    """Original path -> real usage slots -> decoded native references -> owners."""
    targets = {}
    array = arrays[5]['array_rva']
    roles = roles if roles is not None else ('_BinOutput/Voice/', '_BinOutput/Talk/', 'Config_TextMap', 'TalkExcelConfigData')
    _check(isinstance(roles, tuple) and roles and len(roles) <= 32
           and all(isinstance(role, str) and role and len(role) <= 128 for role in roles))
    for index, value in enumerate(literals.rows):
        if value is None or not any(role in value for role in roles):
            continue
        for slot in literals.slots[index]:
            targets.setdefault(array + 8 * slot, []).append({'literal': index, 'slot': slot, 'path': value})
    _check(targets and len(targets) <= 128)
    references = rip_references(view.image, set(targets))
    decoded = {}
    native_starts = sorted(set(view.bindings.method_rvas) - {0})
    for row in references:
        if row['function'] is not None:
            continue
        position = bisect.bisect_right(native_starts, row['rva']) - 1
        if position < 0 or row['rva'] - native_starts[position] >= 256:
            continue
        start = native_starts[position]
        if start not in decoded:
            try:
                # Some real getters have no unwind entry. Their original
                # metadata method pointer and complete straight-line return
                # jointly own this bounded window; a raw RIP hit alone cannot.
                decoded[start] = {i.address - view.image.base: i for i in view.image.leaf(start, 256)}
            except ValueError:
                decoded[start] = {}
        if row['rva'] in decoded[start]:
            row['function'] = start
    needed = {row['function'] for row in references if row['function'] is not None}
    methods = {}
    for definition, (start, end) in view._methods.items():
        for index in range(start, end):
            rva = view.bindings.method_rvas[index]
            if rva in needed:
                methods.setdefault(rva, []).append((definition, index))
    hits = []
    for candidate in references:
        owner = candidate['function']
        if owner is None:
            continue
        if owner not in decoded:
            try:
                decoded[owner] = {i.address - view.image.base: i for i in view.image.instructions(owner)}
            except ValueError:
                decoded[owner] = {}
        ins = decoded[owner].get(candidate['rva'])
        if not (ins and ins.mnemonic in ('mov', 'lea') and len(ins.operands) == 2
                and ins.operands[1].type == CS_OP_MEM and ins.reg_name(ins.operands[1].mem.base) == 'rip'
                and pointer(ins, ins.operands[1], view.image) == candidate['target']):
            continue
        hits.append({'reference_rva': candidate['rva'], 'method_rva': owner,
                     'literals': tuple(targets[candidate['target']]),
                     'owners': tuple({'type': view.bindings.rows[definition], 'method_index': index,
                                      'method_name': view.bindings.methods[index][1]}
                                     for definition, index in methods.get(owner, ()))})
    return tuple(hits)
