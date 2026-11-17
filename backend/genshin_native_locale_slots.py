"""Owned enum-name and locale-slot switches for original localized assets."""
from dataclasses import dataclass
import bisect
import hashlib
import struct

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Definitions, _check
from .genshin_native_metadata import pointer, root
from .genshin_native_words import Context


ALIASES = {'en': 'EN', 'zh-cn': 'CHS', 'zh-tw': 'CHT', 'fr': 'FR', 'de': 'DE',
           'es': 'ES', 'pt': 'PT', 'ru': 'RU', 'ja': 'JP', 'ko': 'KR', 'th': 'TH',
           'vi': 'VI', 'id': 'ID', 'tr': 'TR', 'it': 'IT'}


@dataclass(frozen=True)
class LocaleSlots:
    slots: tuple[tuple[str, int], ...]
    default: int
    method_sha256s: tuple[str, ...]


def typed_parameters(view, definition):
    """Only methods whose current original parameter types name this owner."""
    aliases = {index for index, raw in view.bindings.native_types.items()
               if raw[10] in (17, 18) and struct.unpack_from('<I', raw)[0] == definition}
    params = sorted(index for index, _name, typed in view.bindings.parameters if typed in aliases)
    methods = []
    for method, (start, end) in view._parameters.items():
        at = bisect.bisect_left(params, start)
        if at < len(params) and params[at] < end:
            methods.append(method)
    methods.sort()
    wanted = set(methods)
    result = []
    for definition, (start, end) in view._methods.items():
        at = bisect.bisect_left(methods, start)
        if at < len(methods) and methods[at] < end:
            result.extend({'owner': view.bindings.rows[definition], 'method': m}
                          for m in view.methods(definition) if m['index'] in wanted)
    _check(len(result) <= 4096)
    return result


def bias(context, address, name, argument, definitions=None, depth=0):
    """A bounded copy/sign-extension plus constant bias of one enum argument."""
    _check(depth < 32)
    definitions = definitions or Definitions(context.seq, context.noreturn)
    origins = definitions.before(address, name)
    _check(origins)
    results = set()
    for at in origins:
        if at is None:
            _check(name == argument, 'The native enum index has another input.')
            results.add(0)
            continue
        ins = context.by_address[at]
        ops = ins.operands
        if ins.mnemonic in ('mov', 'movsxd') and len(ops) == 2 and ops[1].type == CS_OP_REG:
            results.add(bias(context, at, root(ins, ops[1]), argument, definitions, depth + 1))
        elif ins.mnemonic in ('dec', 'inc', 'sub', 'add'):
            amount = -1 if ins.mnemonic == 'dec' else 1
            if ins.mnemonic in ('sub', 'add'):
                _check(ops[1].type == CS_OP_IMM)
                amount = ops[1].imm * (-1 if ins.mnemonic == 'sub' else 1)
            results.add(bias(context, at, name, argument, definitions, depth + 1) + amount)
        else:
            raise ValueError('The original enum index has an unsupported transformation.')
    _check(len(results) == 1 and -64 <= next(iter(results)) <= 64,
           'The original enum index has incompatible native paths.')
    return results.pop()


def _count(context, before, index_bias, argument):
    candidates = []
    for i, ins in enumerate(context.seq[:-1]):
        if (ins.address >= before or ins.mnemonic != 'cmp' or len(ins.operands) != 2
                or ins.operands[0].type != CS_OP_REG or ins.operands[1].type != CS_OP_IMM
                or not 0 <= ins.operands[1].imm < 64 or context.seq[i + 1].mnemonic != 'ja'):
            continue
        try:
            current = bias(context, ins.address, root(ins, ins.operands[0]), argument)
        except ValueError:
            continue
        if current == index_bias:
            candidates.append(ins.operands[1].imm + 1)
    _check(len(candidates) == 1, 'The native locale table has no unique unsigned index bound.')
    return candidates[0]


def named_returns(context, literal_addresses):
    """Every bounded jump-table case must return its own original ISO literal."""
    seq, image = context.seq, context.image
    jumps = [(i, ins) for i, ins in enumerate(seq) if ins.mnemonic == 'jmp' and ins.operands[0].type == CS_OP_REG]
    _check(len(jumps) == 1)
    i, jump = jumps[0]
    _check(i >= 3)
    load, add = seq[i - 2:i]
    _check(load.mnemonic == 'movsxd' and load.operands[1].type == CS_OP_MEM
           and load.operands[1].mem.scale == 4 and load.operands[1].mem.index
           and add.mnemonic == 'add' and add.operands[1].type == CS_OP_REG
           and root(add, add.operands[0]) == root(jump, jump.operands[0]) == root(load, load.operands[0]))
    table = context.constants.value_before(load.address, load.reg_name(load.operands[1].mem.base), 64) - image.base
    _check(context.constants.value_before(add.address, root(add, add.operands[1]), 64) == image.base + table)
    offset = bias(context, load.address, load.reg_name(load.operands[1].mem.index), 'rcx')
    count = _count(context, load.address, offset, 'rcx')
    deltas = struct.unpack_from('<' + 'i' * count, image.data, image.offset(table, count * 4))
    result = {}
    for index, delta in enumerate(deltas):
        address = image.base + table + delta
        _check(address in context.by_address)
        ins = context.by_address[address]
        _check(ins.mnemonic == 'mov' and root(ins, ins.operands[0]) == 'rax' and ins.operands[1].type == CS_OP_MEM
               and ins.reg_name(ins.operands[1].mem.base) == 'rip')
        literal = literal_addresses.get(pointer(ins, ins.operands[1], image))
        _check(literal in ALIASES, 'A native locale case has no owned standard language name.')
        at = seq.index(ins) + 1
        while at < len(seq) and seq[at].mnemonic == 'nop':
            at += 1
        _check(at + 1 < len(seq) and seq[at].mnemonic == 'add' and root(seq[at], seq[at].operands[0]) == 'rsp'
               and seq[at + 1].mnemonic == 'ret')
        result[index - offset] = ALIASES[literal]
    _check(set(result.values()) == set(ALIASES.values()) and len(result) == len(ALIASES))
    return result


def selected_slots(context, string_getter, string_slots):
    image = context.image
    calls = [ins for ins in context.seq if ins.mnemonic == 'call' and ins.operands[0].type == CS_OP_IMM
             and ins.operands[0].imm - image.base == string_getter]
    defaults = [ins for ins in context.seq if ins.mnemonic == 'jmp' and ins.operands[0].type == CS_OP_IMM
                and ins.operands[0].imm - image.base == string_getter]
    _check(len(calls) == len(defaults) == 1)
    # The second declared parameter is the same enum used by the name switch.
    loads = [ins for ins in context.seq if ins.address < calls[0].address and ins.mnemonic == 'mov'
             and ins.operands[0].type == CS_OP_REG and root(ins, ins.operands[0]) == 'rdx'
             and ins.operands[0].size == 4 and ins.operands[1].type == CS_OP_MEM
             and ins.operands[1].mem.scale == 4 and ins.operands[1].mem.index]
    _check(len(loads) == 1)
    load = loads[0]
    memory = load.operands[1].mem
    offset = bias(context, load.address, load.reg_name(memory.index), 'rdx')
    count = _count(context, load.address, offset, 'rdx')
    table = context.constants.value_before(load.address, load.reg_name(memory.base), 64) - image.base + memory.disp
    values = struct.unpack_from('<' + 'I' * count, image.data, image.offset(table, count * 4))
    default = context.constants.value_before(defaults[0].address, 'rdx', 32)
    _check(default in string_slots and len(set(values)) == count and default not in values
           and set(values) | {default} == set(string_slots))
    return {index - offset: value for index, value in enumerate(values)}, default


def derive(view, definition, slots, literals, arrays):
    candidates = []
    for row in typed_parameters(view, definition):
        method = row['method']
        params = method['parameters']
        if (method['rva'] and method['return_type']['kind'] == 14 and len(params) == 2
                and params[0]['type'].get('definition') == definition and params[1]['type']['kind'] == 17):
            candidates.append(method)
    _check(candidates and len(candidates) <= 32)
    addresses = {arrays[5]['array_rva'] + 8 * slot: literals.rows[index]
                 for index, occupied in literals.slots.items() for slot in occupied}
    results = {}
    for candidate in candidates:
        context = Context(view.image, candidate['rva'])
        try:
            values, default = selected_slots(context, slots.string_getter, slots.string_slots)
        except ValueError:
            continue
        enum = candidate['parameters'][1]['type']['definition']
        for named in typed_parameters(view, enum):
            method = named['method']
            if not (method['rva'] and method['return_type']['kind'] == 14 and len(method['parameters']) == 1
                    and method['parameters'][0]['type'].get('definition') == enum):
                continue
            try:
                names = named_returns(Context(view.image, method['rva']), addresses)
            except ValueError:
                continue
            _check(set(names) == set(values))
            contract = tuple(sorted((locale, values[value]) for value, locale in names.items())), default
            hashes = results.setdefault(contract, set())
            hashes.update(hashlib.sha256(view.image.window(m['rva'])).hexdigest() for m in (candidate, method))
    _check(len(results) == 1, 'Original locale routing is missing or has competing complete native contracts.')
    (mapping, default), hashes = next(iter(results.items()))
    return LocaleSlots(mapping, default, tuple(sorted(hashes)))
