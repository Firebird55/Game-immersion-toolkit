"""Native-owned original dialogue contracts consumed by the original decoder."""
from . import genshin_original_dialogue as o
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, _check
from .genshin_native_metadata import root
from .genshin_native_fields import ordered_fields
from .genshin_native_words import Context
from .genshin_native_objects import nested_calls


def alias(name):
    return {'_loadType': 'resourceKind', '_param': 'params'}.get(name, name.lstrip('_'))


class Contracts:
    def __init__(self, view, stream, *, usages=None, arrays=None):
        self.view, self.stream = view, stream
        self.usages, self.arrays = usages, arrays
        self.contexts, self.records, self.pending = {}, {}, set()

    def context(self, rva):
        if rva not in self.contexts:
            _check(len(self.contexts) < 2048)
            self.contexts[rva] = Context(self.view.image, rva)
        return self.contexts[rva]

    def count(self, rva):
        context = self.context(rva)
        reads = context.reads(4)
        _check(reads)
        return o.Word(32, context.operations(reads[0].address - self.view.image.base, 32, 'count'))

    def wrappers(self, fields):
        primitives, setters = {}, {}
        for definition in {field['type']['definition'] for field in fields if field['type']['kind'] == 17}:
            members = self.view.fields(definition)
            if len(members) != 1 or members[0]['type']['kind'] not in (8, 9, 10, 11, 12):
                continue
            methods = self.view.methods(definition)
            kinds = {m['return_type']['kind'] for m in methods if not m['parameters']
                     and m['return_type']['kind'] in (8, 9, 10, 11, 12) and m['name'] != 'get_size'}
            writes = [m for m in methods if m['name'] != '.ctor' and m['return_type']['kind'] == 1 and m['rva']
                      and len(m['parameters']) == 1 and m['parameters'][0]['type']['kind'] in kinds]
            if not writes:
                continue
            written = {m['parameters'][0]['type']['kind'] for m in writes}
            _check(len(written) == 1)
            primitive = written.pop()
            primitives[definition] = primitive
            for method in writes:
                setters[method['rva']] = 'xmm1' if primitive == 12 else 'rdx'
        return primitives, setters

    def numeric_dictionary(self, rva, setters):
        context = self.context(rva)
        reads = context.reads(4)
        _check(len(reads) == 3)
        count, key, value = (ins.address - self.view.image.base for ins in reads)
        integer = {target: argument for target, argument in setters.items() if argument == 'rdx'}
        floating = {target: argument for target, argument in setters.items() if argument == 'xmm1'}
        _check(integer and floating)
        return o.Dictionary(o.Word(32, context.operations(count, 32, 'length')),
                            o.Word(32, context.operations(key, 32, 'protected_scalar', setters=integer)),
                            o.Word(32, context.operations(value, 32, 'protected_scalar', setters=floating), interpretation='float'))

    def record(self, definition, rva, depth=0):
        _check(depth < 32)
        key = definition, rva
        if key in self.records:
            return self.records[key]
        _check(key not in self.pending, 'A recursive original record has no bounded concrete schema.')
        self.pending.add(key)
        try:
            fields = self.view.field_offsets(definition)
            helpers = {}
            for field in fields:
                typed = field['type']
                if typed['kind'] == 29 and 'definition' in typed['element']:
                    child = typed['element']['definition']
                    readers = [m for m in self.view.methods(child) if m['return_type']['kind'] == 1 and len(m['parameters']) == 1
                               and m['parameters'][0]['type']['index'] == self.stream and m['rva']]
                    if readers:
                        helpers[field['authored_offset_word']] = self.view.array_reader(child, self.stream, True)
            context = self.context(rva)
            wrappers, setters = self.wrappers(fields)
            object_calls, objects = nested_calls(self.view, context, fields, self.stream, self.usages, self.arrays)
            header, rows = ordered_fields(context, fields, {m['rva'] for m in helpers.values()}, setters, object_calls)
            offsets = {field['authored_offset_word']: field for field in fields}
            result = []
            for row in rows:
                field = offsets[row['offset']]
                typed, default = field['type'], None
                first = row['representative'] - self.view.image.base
                stores = row['stores']
                width = stores[0]['bits'] if stores else None
                if typed.get('definition') in wrappers:
                    primitive = wrappers[typed['definition']]
                    bits = 64 if primitive in (10, 11) else 32
                    steps = context.operations(first, bits, 'protected_scalar', setters=setters)
                    value = o.Word(bits, steps, interpretation='float' if primitive == 12 else 'unsigned')
                    default = 0
                elif width == 8:
                    _check(not stores[0]['mnemonic'].startswith('set') or stores[0]['mnemonic'] in ('setne', 'setnz'),
                           'The original boolean comparison has unsupported polarity.')
                    value = o.Word(8, interpretation='bool', false_value=context.false_value(first))
                    default = False
                elif width in (32, 64) and typed['kind'] in (8, 9, 10, 11, 12, 17):
                    _check(stores)
                    endpoint = stores[0]['address'] - self.view.image.base
                    steps = context.operations(first, width, 'scalar', endpoint)
                    steps = context.completed_scalar(endpoint, steps, width)
                    value = o.Word(width, steps, interpretation='float' if typed['kind'] == 12 else 'unsigned')
                    default = 0
                elif typed['kind'] == 14:
                    length = context.operations(first, 16, 'length')
                    cipher, operation = context.cipher(set(row['nodes']))
                    value = o.Text(o.Word(16, length), cipher, operation)
                elif row['offset'] in objects:
                    child = objects[row['offset']]
                    value = self.record(typed['definition'], child['rva'], depth + 1)
                elif typed['kind'] == 21:
                    calls = [context.by_address[at] for at in row['ref_calls'] if context.by_address[at].mnemonic == 'call']
                    targets = {ins.operands[0].imm - self.view.image.base for ins in calls if ins.operands[0].type == CS_OP_IMM}
                    _check(len(targets) == 1)
                    value = self.numeric_dictionary(targets.pop(), setters)
                elif typed['kind'] == 29:
                    element = typed['element']
                    if row['offset'] in helpers:
                        helper = helpers[row['offset']]
                        calls = [context.by_address[at] for at in row['ref_calls']]
                        _check(any(ins.operands[0].imm - self.view.image.base == helper['rva'] for ins in calls))
                        inner = self.view.inner_reader(element['definition'], self.stream)
                        value = o.Array(self.count(helper['rva']), self.record(element['definition'], inner['rva'], depth + 1))
                    elif element['kind'] in (8, 9, 10, 11, 14, 17):
                        primitive = element['kind']
                        if element['kind'] == 17:
                            underlying = [f for f in self.view.fields(element['definition']) if f['name'] == 'value__']
                            _check(len(underlying) == 1 and underlying[0]['type']['kind'] in (8, 9, 10, 11),
                                   'The native enum array has no owned integer underlying field.')
                            primitive = underlying[0]['type']['kind']
                        _check(len(row['reads']) == 2)
                        count, item = (at - self.view.image.base for at in row['reads'])
                        count = o.Word(32, context.operations(count, 32, 'count'))
                        if element['kind'] == 14:
                            length = context.operations(item, 16, 'length')
                            cipher, operation = context.cipher(set(row['nodes']))
                            item = o.Text(o.Word(16, length), cipher, operation)
                        else:
                            bits = 64 if primitive in (10, 11) else 32
                            item = o.Word(bits, context.operations(item, bits, 'element'))
                        value = o.Array(count, item)
                    else:
                        raise ValueError('The original typed array element has no supported native contract.')
                else:
                    raise ValueError('The original typed field has no supported native contract.')
                result.append(o.Field(alias(field['name']), value, 1 << row['bit'], raw_flag=row['raw_flag'],
                                      present_when_set=row['present_when_set'], default=default))
            value = o.Record(tuple(result), o.Word(header['bits'], header['operations']))
            self.records[key] = value
            return value
        finally:
            self.pending.remove(key)

    def inventory(self, table):
        owner, loader = table['owner'], table['container']['loader']
        record = self.record(owner['definition'], table['reader']['rva'])
        context = self.context(loader['rva'])
        reads = context.reads(4)
        _check(reads)
        counter = root(reads[0], reads[0].operands[0])
        loops = []
        for at, ins in enumerate(context.seq[:-1]):
            following = context.seq[at + 1]
            if (ins.mnemonic == 'dec' and root(ins, ins.operands[0]) == counter
                    and following.mnemonic == 'jne' and following.operands[0].type == CS_OP_IMM
                    and self.view.image.base + loader['rva'] <= following.operands[0].imm < ins.address):
                loops.append(ins.address)
        _check(len(loops) == 1, 'The original table has no unique owned count-down loop.')
        id_fields = [field for field in self.view.field_offsets(owner['definition']) if field['name'] == '_id']
        _check(len(id_fields) == 1)
        offset = id_fields[0]['authored_offset_word']
        loads = [ins for ins in context.seq if ins.mnemonic == 'mov' and ins.operands[1].type == CS_OP_MEM
                 and ins.operands[1].size == 4 and ins.operands[1].mem.disp == offset and not ins.operands[1].mem.index]
        _check(len(loads) == 1, 'The original table row identity is ambiguous.')
        count = o.Word(32, context.operations(reads[0].address - self.view.image.base, 32, 'root_count'))
        return o.Array(count, record)
