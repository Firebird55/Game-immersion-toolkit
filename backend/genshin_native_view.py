"""Semantic access to members whose identities come from original metadata."""
from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, Constants, Definitions, _check
from .genshin_native_metadata import HEADER_SIZE, owns_global_pointer, root, word


def field_offset_roles(bindings):
    """Read the native field-info indirection, including its current operands."""
    ids = bindings.identifiers
    image = ids.image
    owner = bindings.type_profiles['field_type']['method_rva']
    seq = image.instructions(owner)
    constants = Constants(seq)
    definitions = Definitions(seq)
    # These positions are metadata format roles, never current decoded values.
    roles = {0xfc: 'type_to_field_info', 0x108: 'field_info_records', 0x1ac: 'field_offsets'}
    found = {}
    for at, ins in enumerate(seq):
        if len(ins.operands) != 2:
            continue
        destination, source = ins.operands
        if not (destination.type == CS_OP_REG and source.type == CS_OP_MEM
                and source.size == 4 and source.mem.disp in roles):
            continue
        # The actual member-type owner must load this header from the same
        # original bootstrap global; unrelated similarly sized records fail.
        if not owns_global_pointer(image, seq, ins, source.mem, ids.owner.global_rva, definitions):
            continue
        steps = None
        if ins.mnemonic == 'add':
            steps = (('add', constants.value_before(ins.address, root(ins, destination), 32)),)
        elif ins.mnemonic in ('mov', 'movsxd') and at + 2 < len(seq):
            a, b = seq[at + 1:at + 3]
            if (a.mnemonic == 'xor' and a.operands[0].reg == destination.reg
                    and a.operands[1].type == CS_OP_IMM):
                steps = (('xor', a.operands[1].imm & 0xffffffff),)
            elif (a.mnemonic == 'mov' and a.operands[1].type == CS_OP_IMM
                  and b.mnemonic == 'add' and b.operands[0].reg == destination.reg
                  and b.operands[1].reg == a.operands[0].reg):
                steps = (('add', constants.value_before(b.address, root(a, a.operands[0]), 32)),)
        if steps is None:
            continue
        value = word(ids.header, source.mem.disp, steps)
        _check(0 <= value < len(ids.metadata) - HEADER_SIZE)
        name = roles[source.mem.disp]
        row = {'field': source.mem.disp, 'operations': steps, 'body_offset': value,
               'method_rva': owner, 'read_rva': ins.address - image.base}
        if name in found:
            _check(found[name]['operations'] == steps and found[name]['body_offset'] == value)
        found[name] = row
    _check(set(found) == set(roles.values()), 'Original field-offset indirection is incomplete.')
    return found


class View:
    """No frozen inventories, member indices, addresses or game operands."""
    def __init__(self, bindings):
        self.bindings = bindings
        self.image = bindings.identifiers.image
        self.metadata = bindings.identifiers.metadata
        self._named = {}
        for row in bindings.rows:
            self._named.setdefault((row['namespace'], row['name']), []).append(row)
        self._fields = {definition: (start, end) for start, end, definition in bindings.field_ranges}
        self._methods = {definition: (start, end) for start, end, definition in bindings.method_ranges}
        self._parameters = {method: (start, end) for start, end, method in bindings.parameter_ranges}
        self.offset_roles = field_offset_roles(bindings)
        self._at = {}

    def named(self, namespace, name):
        rows = self._named.get((namespace, name), ())
        _check(len(rows) == 1, 'Original named metadata owner is missing or ambiguous.')
        return rows[0]

    def methods_at(self, rva):
        _check(type(rva) is int and rva > 0)
        if rva not in self._at:
            indices = {index for index, native in enumerate(self.bindings.method_rvas) if native == rva}
            matches = []
            for definition, (start, end) in self._methods.items():
                if any(start <= index < end for index in indices):
                    matches.extend({'owner': self.bindings.rows[definition], 'method': method}
                                   for method in self.methods(definition) if method['index'] in indices)
            self._at[rva] = tuple(matches)
        return self._at[rva]

    def fields(self, definition):
        _check(type(definition) is int and 0 <= definition < len(self.bindings.rows))
        begin, end = self._fields.get(definition, (0, 0))
        return [{'index': index, 'name': self.bindings.fields[index][1],
                 'type': self.bindings.describe(self.bindings.field_types[index])}
                for index in range(begin, end)]

    def field_offsets(self, definition):
        fields = self.fields(definition)
        role = lambda name: self.offset_roles[name]['body_offset']
        index = word(self.metadata, HEADER_SIZE + role('type_to_field_info') + 4 * definition, ())
        _check(index < 0x80000000)
        start = word(self.metadata, HEADER_SIZE + role('field_info_records') + 12 * index + 8, ())
        _check(start < 0x80000000)
        # Preserve flag bits. They are not an ordinary instance offset.
        return [{**field, 'authored_offset_word': word(self.metadata,
                 HEADER_SIZE + role('field_offsets') + 4 * (start + ordinal), ())}
                for ordinal, field in enumerate(fields)]

    def methods(self, definition):
        _check(type(definition) is int and 0 <= definition < len(self.bindings.rows))
        begin, end = self._methods.get(definition, (0, 0))
        result = []
        for index in range(begin, end):
            ps, pe = self._parameters.get(index, (0, 0))
            result.append({'index': index, 'name': self.bindings.methods[index][1],
                           'rva': self.bindings.method_rvas[index],
                           'return_type': self.bindings.describe(self.bindings.return_types[index]),
                           'parameters': [{'name': self.bindings.parameters[p][1],
                                           'type': self.bindings.describe(self.bindings.parameters[p][2])}
                                          for p in range(ps, pe)]})
        return result

    def inner_reader(self, definition, stream_type):
        matches = [m for m in self.methods(definition)
                   if m['return_type']['kind'] == 1 and m['rva'] and len(m['parameters']) == 1
                   and m['parameters'][0]['type']['index'] == stream_type]
        named = [m for m in matches if m['name'] == 'FromBinaryInner']
        matches = named or matches
        _check(len(matches) == 1, 'Original typed inner reader is missing or ambiguous.')
        return matches[0]

    def array_reader(self, definition, stream_type, inner=False):
        matches = [m for m in self.methods(definition)
                   if m['return_type']['kind'] == (1 if inner else 2) and m['rva']
                   and len(m['parameters']) == 2
                   and m['parameters'][0]['type']['index'] == stream_type
                   and m['parameters'][1]['type'].get('element', {}).get('definition') == definition]
        named = [m for m in matches if m['name'] == ('FromBinaryInner' if inner else 'FromBinary')]
        matches = named or matches
        _check(len(matches) == 1, 'Original typed array reader is missing or ambiguous.')
        return matches[0]
