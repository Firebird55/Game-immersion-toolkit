"""Original initial dispatch seed from current metadata and its static initializer.

The initial value is private source data. It does not own the RSA material,
request template, later runtime overrides or a complete current descriptor.
"""
from dataclasses import dataclass, field
import hashlib
import re

from .genshin_native_metadata import pointer, root
from .genshin_native_x64 import CS_OP_MEM, CS_OP_REG, Definitions, _check


SCHEMA = 'genshin-original-initial-dispatch-seed-v1'
MAX_METHOD_INSTRUCTIONS = 8192


@dataclass(frozen=True)
class InitialSeed:
    value: str = field(repr=False)
    proof: dict


def _register_source(context, address, name, depth=0):
    """A single reaching full pointer definition, preserving copies and clobbers."""
    _check(depth < 32, 'The original static pointer provenance exceeds its bound.')
    definitions = context['definitions'].before(address, name)
    _check(len(definitions) == 1 and None not in definitions,
           'The original static pointer has conflicting or unknown definitions.')
    definition, = definitions
    ins = context['instructions'][definition]
    _check(ins.mnemonic == 'mov' and len(ins.operands) == 2
           and ins.operands[0].type == CS_OP_REG and ins.operands[0].size == 8
           and root(ins, ins.operands[0]) == name,
           'The original static pointer was clobbered or transformed.')
    source = ins.operands[1]
    if source.type == CS_OP_REG and source.size == 8:
        target, chain = _register_source(context, ins.address, root(ins, source), depth + 1)
        return target, (*chain, ins.address - context['image'].base)
    _check(source.type == CS_OP_MEM and source.size == 8 and not source.mem.index
           and ins.reg_name(source.mem.base) == 'rip',
           'The original static pointer has no owned image-relative source.')
    return pointer(ins, source, context['image']), (ins.address - context['image'].base,)


def derive_initial_seed(view, usages, arrays, literals):
    """Use the maintained original View/usage/literal readers, never saved indices."""
    owner = view.named('MoleMole', 'GlobalVars')
    definition = owner['definition']
    fields = [row for row in view.field_offsets(definition) if row['name'] == 'dispatchSeed']
    _check(len(fields) == 1 and fields[0]['type']['kind'] == 14,
           'The original dispatch seed field is missing or ambiguous.')
    selected, = fields
    raw_type = view.bindings.type_record(selected['type']['index'])
    attributes = int.from_bytes(raw_type[8:10], 'little')
    _check(attributes & 0x10 and not attributes & 0x40,
           'The original dispatch seed is not an owned static field.')
    packed = selected['authored_offset_word']
    # This metadata format stores an offset payload and a separate location tag.
    # Tag four is accepted only with the matching named static cctor store.
    _check(type(packed) is int and packed >> 24 == 4)
    offset = packed & 0xffffff
    _check(offset > 0 and offset % 8 == 0)
    methods = [row for row in view.methods(definition) if row['name'] == '.cctor']
    _check(len(methods) == 1 and methods[0]['rva'] and not methods[0]['parameters']
           and methods[0]['return_type']['kind'] == 1,
           'The original dispatch initializer is missing or ambiguous.')
    method, = methods
    image = view.image
    sequence = image.instructions(method['rva'])
    _check(0 < len(sequence) <= MAX_METHOD_INSTRUCTIONS)
    context = {'image': image, 'definitions': Definitions(sequence),
               'instructions': {ins.address: ins for ins in sequence}}
    stores = [ins for ins in sequence if ins.operands
              and ins.operands[0].type == CS_OP_MEM and ins.operands[0].access & 2
              and not ins.operands[0].mem.index and ins.operands[0].mem.disp == offset
              and ins.reg_name(ins.operands[0].mem.base) not in ('rip', 'rsp', 'rbp')]
    _check(len(stores) == 1, 'The original dispatch field has ambiguous initializer stores.')
    store, = stores
    _check(store.mnemonic == 'mov' and len(store.operands) == 2 and store.operands[0].size == 8
           and store.operands[1].type == CS_OP_REG and store.operands[1].size == 8)
    base, base_chain = _register_source(context, store.address,
                                        store.reg_name(store.operands[0].mem.base))
    literal_pointer, literal_chain = _register_source(context, store.address, root(store, store.operands[1]))
    base_ranges = [row for row in image.sections.values()
                   if row[0] <= base and base + 8 <= row[0] + max(row[1], row[3])]
    _check(len(base_ranges) == 1 and base != literal_pointer,
           'The original static storage pointer leaves its owned image.')
    _check(5 in arrays and type(arrays[5]['array_rva']) is int)
    relative = literal_pointer - arrays[5]['array_rva']
    _check(relative >= 0 and relative % 8 == 0)
    slot = relative // 8
    identities = {identity for kind, identity, usage_slot in usages.pairs
                  if kind == 5 and usage_slot == slot}
    _check(len(identities) == 1, 'The original seed literal slot has ambiguous ownership.')
    identity, = identities
    value = literals.text(identity)
    _check(isinstance(value, str) and re.fullmatch('[0-9a-f]{16,128}', value),
           'The original initial dispatch seed has an unsupported representation.')
    proof = {'schema': SCHEMA, 'source_kind': 'original-publisher-initial-static-value',
             'executable_sha256': hashlib.sha256(image.data).hexdigest(),
             'metadata_sha256': hashlib.sha256(view.metadata).hexdigest(),
             'owner': {'namespace': owner['namespace'], 'name': owner['name'], 'definition': definition},
             'field': {'index': selected['index'], 'name': selected['name'], 'attributes': attributes,
                       'packed_offset_word': packed},
             'initializer': {'index': method['index'], 'rva': method['rva'],
                             'sha256': hashlib.sha256(image.window(method['rva'])).hexdigest()},
             'storage_global_rva': base, 'storage_load_chain': list(base_chain),
             'literal_index': identity, 'literal_slot': slot, 'literal_load_chain': list(literal_chain),
             'store_rva': store.address - image.base, 'characters': len(value),
             'value_sha256': hashlib.sha256(value.encode()).hexdigest(),
             'later_override_excluded': False, 'complete_dispatch_bootstrap': False}
    return InitialSeed(value, proof)


def read_initial_seed(executable, metadata, *, expected_owner):
    """Whole input checks precede maintained parser/literal extraction."""
    _check(isinstance(executable, bytes) and isinstance(metadata, bytes)
           and isinstance(expected_owner, dict) and set(expected_owner) == {'executable_sha256', 'metadata_sha256'})
    _check(expected_owner == {'executable_sha256': hashlib.sha256(executable).hexdigest(),
                              'metadata_sha256': hashlib.sha256(metadata).hexdigest()},
           'The original dispatch seed input owner changed.')
    from .genshin_original_excel import native_environment
    view, _anchor, usages, arrays, literals = native_environment(executable, metadata)
    result = derive_initial_seed(view, usages, arrays, literals)
    _check(all(result.proof[key] == value for key, value in expected_owner.items()))
    return result
