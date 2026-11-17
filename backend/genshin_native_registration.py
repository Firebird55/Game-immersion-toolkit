"""Original static registrations and typed member bindings, derived as data."""
from dataclasses import dataclass
import re
import struct

from .genshin_native_x64 import CS_OP_IMM, CS_OP_MEM, CS_OP_REG, _check, decoder, register
from .genshin_native_metadata import Members, HEADER_SIZE, pointer, root, word
from . import genshin_native_expression as expression


@dataclass(frozen=True)
class Registration:
    initializer_rva: int
    stores: tuple
    code_rva: int
    types_rva: int
    method_array_rva: int
    type_array_rva: int


def registrations(members):
    ids = members.identifiers
    image = ids.image
    method_description = members.method_range_description
    parameter_description = members.member_names['parameter_offset']
    code_global = method_description['code_registration_global_rva']
    types_global = parameter_description['type_registration_global_rva']
    writers = []
    for name in image.executable_sections:
        rva, _virtual, raw, size = image.sections[name]
        for match in re.finditer(rb'[\x48\x4c]\x89[\x05\x0d\x15\x1d\x25\x2d\x35\x3d](....)',
                                 image.data[raw:raw + size], re.S):
            at = rva + match.start()
            if at + 7 + struct.unpack('<i', match[1])[0] == code_global:
                writers.append(at)
                _check(len(writers) <= 128)
    candidates = []
    for writer in writers:
        try:
            start = writer - 7
            seq = image.leaf(start, 256)
            _check(seq[-1].mnemonic == 'ret' and len(seq) % 2 == 1 and 7 <= len(seq) <= 33)
            stores = []
            for at in range(0, len(seq) - 1, 2):
                lea, store = seq[at:at + 2]
                _check(lea.mnemonic == 'lea' and lea.operands[0].type == CS_OP_REG
                       and lea.operands[1].type == CS_OP_MEM and lea.reg_name(lea.operands[1].mem.base) == 'rip'
                       and store.mnemonic == 'mov' and store.operands[0].type == CS_OP_MEM
                       and store.reg_name(store.operands[0].mem.base) == 'rip'
                       and store.operands[1].type == CS_OP_REG and store.operands[1].reg == lea.operands[0].reg)
                stores.append((pointer(store, store.operands[0], image), pointer(lea, lea.operands[1], image)))
            _check(len({target for target, _source in stores}) == len(stores))
            lookup = dict(stores)
            _check(lookup[ids.owner.global_rva] == ids.owner.header_rva)
            code, types = lookup[code_global], lookup[types_global]
            at = image.offset(code + method_description['method_pointer_registration_field'], 8)
            method_array, = struct.unpack_from('<Q', image.data, at)
            at = image.offset(types + parameter_description['type_array_registration_field'], 8)
            type_array, = struct.unpack_from('<Q', image.data, at)
            _check(method_array >= image.base and type_array >= image.base)
            method_array, type_array = method_array - image.base, type_array - image.base
            image.offset(method_array, 8 * len(members.methods))
            image.offset(type_array, 16)
            candidates.append(Registration(start, tuple(stores), code, types, method_array, type_array))
        except (ValueError, KeyError):
            continue
    _check(len(candidates) == 1, 'Original native registration ownership is missing or ambiguous.')
    return candidates[0]


def member_type_profiles(members):
    image, ids = members.identifiers.image, members.identifiers
    field_candidates = set()
    header_field = members.roles['field_offset']['field']
    for caller in members.field_range_description['count_owner_rvas']:
        seq = image.instructions(caller)
        targets = {i.operands[0].imm - image.base for i in seq
                   if i.mnemonic == 'call' and i.operands[0].type == CS_OP_IMM}
        for target in targets:
            try:
                body = image.instructions(target)
            except ValueError:
                continue
            if (any(i.mnemonic == 'movsxd' and i.operands[1].type == CS_OP_MEM
                    and i.operands[1].mem.disp == header_field for i in body)
                    and any(i.mnemonic == 'add' and i.operands[1].type == CS_OP_MEM
                            and i.operands[1].mem.disp == 0x58 for i in body)):
                field_candidates.add(target)
    _check(len(field_candidates) == 1, 'Original field type-array setup is missing or ambiguous.')
    profiles = {}
    for role, owners, stride, field in (
        ('field_type', field_candidates, 8, 4),
        ('return_type', {row['method_rva'] for row in members.roles['method_offset']['owners']}, 26, 0),
    ):
        found = []
        for owner in sorted(owners):
            seq = image.instructions(owner)
            for at, ins in enumerate(seq):
                if not (ins.mnemonic == 'cmp' and ins.operands[0].type == CS_OP_REG
                        and ins.operands[1].type == CS_OP_IMM and ins.operands[1].imm == -1):
                    continue
                following = seq[at + 1:at + 6]
                consumers = [i for i in following if i.mnemonic == 'add' and i.operands[1].type == CS_OP_MEM
                             and i.operands[1].mem.disp == 0x58]
                if len(consumers) != 1:
                    continue
                try:
                    begins = []
                    if role == 'return_type':
                        begins = [k for k, use in enumerate(seq[:at]) if use.mnemonic == 'add'
                                  and use.operands[0].type == CS_OP_REG and use.operands[1].type == CS_OP_MEM
                                  and use.reg_name(use.operands[1].mem.base) == 'rip'
                                  and pointer(use, use.operands[1], image) == ids.profile.body_global_rva]
                    else:
                        for k, use in enumerate(seq[:at - 2]):
                            if not (use.mnemonic == 'movsxd' and use.operands[1].type == CS_OP_MEM
                                    and use.operands[1].mem.disp == header_field):
                                continue
                            xor, add = seq[k + 1:k + 3]
                            if not (xor.mnemonic == 'xor' and xor.operands[1].type == CS_OP_IMM
                                    and add.mnemonic == 'add' and add.operands[1].type == CS_OP_REG):
                                continue
                            _check(members.roles['field_offset']['operations']
                                   == (('xor', xor.operands[1].imm & 0xffffffff),))
                            body_register = add.operands[1].reg
                            _check(any(old.mnemonic == 'mov' and old.operands[0].type == CS_OP_REG
                                and old.operands[0].reg == body_register and old.operands[1].type == CS_OP_MEM
                                and old.reg_name(old.operands[1].mem.base) == 'rip'
                                and pointer(old, old.operands[1], image) == ids.profile.body_global_rva
                                for old in seq[:k]))
                            begins.append(k + 2)
                    _check(begins)
                    begin = begins[-1]
                    state, fields = expression.extract(seq[begin + 1:at], root(seq[begin], seq[begin].operands[0]),
                        stride, {field: 4}, image_base=image.base,
                        index_limit=min(len(ids.metadata) // stride, 16_000_000))
                    _check(len(fields) == 1)
                    result = state[root(ins, ins.operands[0])]
                    _check({leaf[1] for leaf in expression.leaves(result) if leaf[0] == 'input'}
                           == {fields[0]['index_register']})
                    globals_ = [i for i in following if i.mnemonic == 'mov' and i.operands[1].type == CS_OP_MEM
                                and i.reg_name(i.operands[1].mem.base) == 'rip']
                    _check(len(globals_) == 1 and pointer(globals_[0], globals_[0].operands[1], image)
                           == members.member_names['parameter_offset']['type_registration_global_rva'])
                    found.append({'method_rva': owner, 'raw_field': fields[0], 'expression': result})
                except (ValueError, KeyError):
                    continue
        _check(len(found) == 1, 'Original member type-index expressions are missing or ambiguous.')
        profiles[role] = found[0]
    return profiles


class Bindings(Members):
    def __init__(self, image, metadata):
        super().__init__(image, metadata)
        self.registration = registrations(self)
        self.type_profiles = member_type_profiles(self)
        self.field_types, self.return_types = [], []
        for role, count, section, stride, field, result in (
            ('field_type', len(self.fields), self.role('field_offset'), 8, 4, self.field_types),
            ('return_type', len(self.methods), self.role('method_offset'), 26, 0, self.return_types),
        ):
            profile = self.type_profiles[role]
            for index in range(count):
                raw = word(metadata, HEADER_SIZE + section + stride * index + field, ())
                typed = expression.evaluate(profile['expression'], {profile['raw_field']['index_register']: index}, {field: raw})
                _check(typed != 0xffffffff and typed < 16_000_000)
                result.append(typed)
        self.native_types = {}
        for index in sorted(set(self.field_types) | set(self.return_types) | {row[2] for row in self.parameters}):
            self.type_record(index)
        at = image.offset(self.registration.method_array_rva, 8 * len(self.methods))
        self.method_rvas = []
        for index in range(len(self.methods)):
            address, = struct.unpack_from('<Q', image.data, at + 8 * index)
            rva = address - image.base if address else 0
            _check(not address or any(start <= rva < start + size for name in image.executable_sections
                                     for start, _virtual, _raw, size in (image.sections[name],)))
            self.method_rvas.append(rva)

    def type_record(self, index):
        _check(type(index) is int and 0 <= index < 16_000_000)
        if index not in self.native_types:
            image = self.identifiers.image
            at = image.offset(self.registration.type_array_rva + 16 * index, 16)
            raw = image.data[at:at + 16]
            _check(1 <= raw[0xa] <= 0x1f)
            self.native_types[index] = raw
        return self.native_types[index]

    def describe(self, index, depth=0):
        _check(depth < 8)
        raw = self.type_record(index)
        kind = raw[0xa]
        result = {'index': index, 'kind': kind}
        if kind in (0x11, 0x12, 0x1c):
            definition, = struct.unpack_from('<I', raw)
            _check(definition < len(self.rows))
            result.update(self.rows[definition])
        if kind in (0x0f, 0x10, 0x1d):
            address, = struct.unpack_from('<Q', raw)
            difference = address - self.identifiers.image.base - self.registration.type_array_rva
            _check(difference >= 0 and difference % 16 == 0)
            result['element'] = self.describe(difference // 16, depth + 1)
        return result
