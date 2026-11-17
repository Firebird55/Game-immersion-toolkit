"""Original method attributes from the actual native MethodInfo constructor."""
import struct

from . import genshin_native_expression as e
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, _check
from .genshin_native_metadata import HEADER_SIZE, root
from .genshin_native_words import Context
from .genshin_native_sources import _out_states
from .genshin_native_talk import class_method_initializer


def attribute_profile(view, initializer):
    """Recover current operands; retained record fields describe the format."""
    context = Context(view.image, initializer)
    seq, constants = context.seq, context.constants
    from .genshin_native_x64 import Definitions
    definitions = Definitions(seq, context.noreturn)
    states = _out_states(context, {})
    field, headers = view.bindings.roles['method_offset']['field'], []
    for at, ins in enumerate(seq[:-2]):
        if not (ins.mnemonic == 'movsxd' and ins.operands[1].type == CS_OP_MEM
                and ins.operands[1].size == 4 and ins.operands[1].mem.disp == field):
            continue
        _check(states[ins.address].get(('reg', ins.reg_name(ins.operands[1].mem.base)))
               == ('arena', view.bindings.identifiers.owner.global_rva))
        xor, add = seq[at + 1:at + 3]
        _check(xor.mnemonic == 'xor' and xor.operands[1].type == CS_OP_IMM
               and xor.operands[0].reg == ins.operands[0].reg and add.mnemonic == 'add'
               and add.operands[1].type == CS_OP_REG and add.operands[0].reg == ins.operands[0].reg)
        _check(states[add.address].get(('reg', root(add, add.operands[1])))
               == ('arena', view.bindings.identifiers.profile.body_global_rva))
        raw = struct.unpack_from('<I', view.bindings.identifiers.header, field)[0]
        offset = raw ^ (xor.operands[1].imm & 0xffffffff)
        _check(offset == view.bindings.role('method_offset'))
        headers.append({'body_offset': offset, 'read_rva': ins.address - view.image.base,
                        'field': field, 'operations': (('xor', xor.operands[1].imm & 0xffffffff),),
                        'table_position': at + 2})
    _check(len(headers) == 1, 'The native MethodInfo table ownership is ambiguous.')
    header = headers[0]
    table_position = header['table_position']
    table_register = root(seq[table_position], seq[table_position].operands[0])
    profiles = []
    for at, ins in enumerate(seq[:-3]):
        # The retained MethodDefinition format stores attributes at +0x16.
        if not (ins.mnemonic == 'movzx' and ins.operands[1].type == CS_OP_MEM
                and ins.operands[1].size == 2 and ins.operands[1].mem.disp == 0x16):
            continue
        sub, add, store = seq[at + 1:at + 4]
        if not (sub.mnemonic == 'sub' and sub.operands[1].type == CS_OP_REG
                and add.mnemonic == 'add' and add.operands[1].type == CS_OP_IMM
                and store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM
                and store.operands[0].size == 2
                and root(sub, sub.operands[0]) == root(add, add.operands[0])
                == root(store, store.operands[1]) == root(ins, ins.operands[0])):
            continue
        rows = definitions.before(ins.address, ins.reg_name(ins.operands[1].mem.base))
        keys = definitions.before(sub.address, root(sub, sub.operands[1]))
        _check(len(rows) == len(keys) == 1 and None not in rows and None not in keys)
        row_position = next(k for k, current in enumerate(seq) if current.address in rows)
        prefix = seq[table_position + 1:row_position + 1]
        _check(prefix and all(not current.mnemonic.startswith('j') and current.mnemonic != 'call' for current in prefix))
        initial = {table_register: ('input', 'table')}
        for name in ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15'):
            if name == table_register:
                continue
            try:
                initial[name] = e.constant(constants.value_before(prefix[0].address, name, 64))
            except ValueError:
                pass
        registers, raw = e.extract(prefix, table_register, 26, {0x16: 2}, image_base=view.image.base,
                                   index_limit=len(view.bindings.methods), initial=initial)
        _check(not raw and next(iter(keys)) in {current.address for current in prefix})
        expressions, fields = e.extract(seq[at:at + 3], table_register, 26, {0x16: 2}, image_base=view.image.base,
                                        index_limit=len(view.bindings.methods), initial=registers)
        _check(len(fields) == 1)
        expression = e.operation('cast', 16, expressions[root(ins, ins.operands[0])])
        _check({leaf[1] for leaf in e.leaves(expression) if leaf[0] == 'input'} == {fields[0]['index_register']})
        # The same native MethodInfo object receives this exact metadata row
        # index. Its current store offset is not a pinned runtime ABI value.
        indices = [current for current in seq[row_position + 1:at] if current.mnemonic == 'mov'
                   and current.operands[0].type == CS_OP_MEM and current.operands[0].size == 4
                   and current.operands[0].mem.base == store.operands[0].mem.base
                   and not current.operands[0].mem.index and current.operands[0].mem.disp >= 0
                   and current.operands[1].type == CS_OP_REG and current.operands[1].size == 4
                   and root(current, current.operands[1]) == fields[0]['index_register']]
        _check(len(indices) == 1, 'The native attribute row has no agreeing MethodInfo index store.')
        profiles.append({'method_rva': initializer, 'header': header, 'field': fields[0], 'expression': expression,
                         'runtime_flags_store_rva': store.address - view.image.base,
                         'runtime_index_store_rva': indices[0].address - view.image.base,
                         'runtime_index_offset': indices[0].operands[0].mem.disp})
    _check(len(profiles) == 1, 'The original native method attribute reader is ambiguous.')
    return profiles[0]


class Attributes:
    def __init__(self, view, dispatch):
        self.view = view
        self.profile = attribute_profile(view, class_method_initializer(view, dispatch))

    def flags(self, index):
        _check(type(index) is int and 0 <= index < len(self.view.bindings.methods))
        profile = self.profile
        at = HEADER_SIZE + profile['header']['body_offset'] + 26 * index + profile['field']['field_offset']
        _check(0 <= at <= len(self.view.metadata) - 2)
        raw = struct.unpack_from('<H', self.view.metadata, at)[0]
        return e.evaluate(profile['expression'], {profile['field']['index_register']: index},
                          {profile['field']['field_offset']: raw})

    def argument_register(self, method, position):
        """The x64 integer/object ABI position, including a real instance this."""
        _check(type(position) is int and 0 <= position < len(method['parameters']))
        supported = set(range(2, 12)) | {14, 15, 16, 18, 24, 25, 28, 29}
        _check(method['parameters'][position]['type']['kind'] in supported
               and method['return_type']['kind'] in supported | {1},
               'The original signature needs an unsupported native argument or return ABI.')
        slot = position + (0 if self.flags(method['index']) & 0x10 else 1)
        _check(slot < 4, 'The original parameter lies outside the supported native argument registers.')
        return ('rcx', 'rdx', 'r8', 'r9')[slot]
