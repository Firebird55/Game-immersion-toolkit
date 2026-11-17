"""Original localized asset paths and their complete native wire ownership."""
import hashlib
import json
import re

from .genshin_native_locale_slots import ALIASES


PATH = 'Data/_ExcelBinOutput/LocalizationExcelConfigData'
SCHEMA = 'genshin-original-localization-table-v1'
CODES = frozenset(ALIASES.values())


def check(value):
    if not value:
        raise ValueError('The original Genshin localized asset inventory is incomplete or ambiguous.')


def canonical_digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _path(value):
    check(isinstance(value, str) and len(value) <= 4096 and '\\' not in value and ':' not in value
          and all(ord(character) >= 32 for character in value)
          and (not value or not value.startswith('/') and all(part not in ('', '.', '..') for part in value.split('/'))))
    check(value.isascii())


def validate_rows(rows):
    check(isinstance(rows, list) and 0 < len(rows) <= 1_000_000)
    seen = set()
    for row in rows:
        check(isinstance(row, dict) and set(row) == {'id', 'paths', 'default'}
              and type(row['id']) is int and 0 <= row['id'] < 1 << 32 and row['id'] not in seen
              and isinstance(row['paths'], dict) and set(row['paths']) == CODES)
        seen.add(row['id'])
        for path in [row['default'], *row['paths'].values()]:
            _path(path)
    return rows


def validate_proof(proof, rows, payload):
    check(isinstance(proof, dict) and proof.get('schema') == SCHEMA
          and type(proof.get('rows')) is int and proof['rows'] == len(rows)
          and type(proof.get('payload_bytes')) is int and proof['payload_bytes'] == len(payload)
          and proof.get('payload_sha256') == hashlib.sha256(payload).hexdigest()
          and proof.get('canonical_sha256') == canonical_digest(rows)
          and isinstance(proof.get('contract_sha256'), str) and re.fullmatch('[a-f0-9]{64}', proof['contract_sha256'])
          and proof.get('strict_eof') is True and proof.get('source_kind') == 'original-publisher'
          and proof.get('all_locales') == sorted(CODES) and proof.get('complete_native_storage') is True)
    methods = proof.get('method_sha256s')
    check(isinstance(methods, list) and 4 <= len(methods) <= 128
          and all(isinstance(method, str) and re.fullmatch('[a-f0-9]{64}', method) for method in methods)
          and methods == sorted(set(methods)))
    return proof


def read_owned(view, anchor, usages, arrays, literals, payload):
    """The environment is current original input, never a saved RVA profile."""
    from .genshin_native_literals import path_callers
    from .genshin_native_slots import derive as derive_slots
    from .genshin_native_locale_slots import derive as derive_locales
    from .genshin_native_words import Context
    from . import genshin_original_dialogue as binary

    check(isinstance(payload, bytes) and 4 <= len(payload) <= 64 * 1024**2)
    paths = path_callers(view, literals, arrays, roles=(PATH,))
    definitions = {owner['type']['definition'] for row in paths
                   if any(literal['path'] == PATH for literal in row['literals']) for owner in row['owners']}
    check(len(definitions) == 1)
    definition, = definitions
    methods = view.methods(definition)
    getters = [m for m in methods if m['rva'] and len(m['parameters']) == 1
               and m['parameters'][0]['type']['kind'] == 9 and m['return_type'].get('definition') is not None]
    loaders = [m for m in methods if m['rva'] and m['return_type']['kind'] == 1 and len(m['parameters']) == 1
               and m['parameters'][0]['type']['index'] == anchor['stream']]
    check(len(getters) == len(loaders) == 1)
    getter, loader = getters[0], loaders[0]
    row_definition = getter['return_type']['definition']
    readers = [m for m in view.methods(row_definition) if m['rva'] and m['return_type']['kind'] == 1
               and len(m['parameters']) == 2 and m['parameters'][0]['type']['index'] == anchor['stream']
               and m['parameters'][1]['type'].get('name') == 'INativeAllocator']
    check(len(readers) == 1)
    reader = readers[0]
    slots = derive_slots(view, row_definition, reader, anchor['stream'])
    locales = derive_locales(view, row_definition, slots, literals, arrays)
    context = Context(view.image, loader['rva'])
    reads = context.reads(4)
    check(len(reads) == 1)
    count = binary.Word(32, context.operations(reads[0].address - view.image.base, 32, 'root_count'))
    contract = binary.Array(count, slots.record)
    original = binary.decode_original(payload, contract)
    rows = validate_rows([{'id': row['slot_' + str(slots.identity_slot)],
        'paths': {code: row.get('slot_' + str(offset)) or '' for code, offset in locales.slots},
        'default': row.get('slot_' + str(locales.default)) or ''} for row in original])
    method_hashes = set(slots.method_sha256s) | set(locales.method_sha256s)
    method_hashes.update(hashlib.sha256(view.image.window(m['rva'])).hexdigest() for m in (getter, loader))
    proof = {'schema': SCHEMA, 'rows': len(rows), 'payload_sha256': hashlib.sha256(payload).hexdigest(),
             'payload_bytes': len(payload), 'canonical_sha256': canonical_digest(rows),
             'contract_sha256': hashlib.sha256(json.dumps(binary._source_contract(contract), sort_keys=True).encode()).hexdigest(),
             'method_sha256s': sorted(method_hashes), 'strict_eof': True, 'source_kind': 'original-publisher',
             'all_locales': sorted(CODES), 'complete_native_storage': True}
    return rows, validate_proof(proof, rows, payload)


def read_localization(executable, metadata, payload):
    from .genshin_original_excel import native_environment
    return read_owned(*native_environment(executable, metadata), payload)
