"""Original ManualTextMap input behind its existing authored table consumer.

Logical names and the canonical string-ID/UInt32-text-key schema are format
descriptions. Current metadata, literal slots, getters and native stream readers
must independently own that table. No community rows are parser input.
"""
import hashlib
import json
import re


MANUAL_PATH = 'Data/_ExcelBinOutput/ManualTextMapConfigData'
MANUAL_RELATIVE = 'ExcelBinOutput/ManualTextMapConfigData.json'
MAX_METADATA = 256 * 1024**2


def check(value):
    if not value:
        raise ValueError('The official Genshin ManualTextMap generation is incomplete or ambiguous.')


def metadata_name(channel):
    check(channel in {'genshin-global', 'genshin-cn'})
    return ('GenshinImpact_Data' if channel == 'genshin-global' else 'YuanShen_Data') + '/Native/Data/Metadata/global-metadata.dat'


def validate_rows(rows):
    check(isinstance(rows, list) and 0 < len(rows) <= 1_000_000)
    for row in rows:
        check(isinstance(row, dict) and set(row) == {'textMapId', 'textMapContentTextMapHash'}
              and isinstance(row['textMapId'], str) and 0 < len(row['textMapId']) <= 4096
              and type(row['textMapContentTextMapHash']) is int and 0 <= row['textMapContentTextMapHash'] < 1 << 32)
    return rows


def validate_proof(proof, rows, payload):
    check(isinstance(proof, dict) and proof.get('schema') == 'genshin-original-manual-table-v1'
          and type(proof.get('rows')) is int and proof['rows'] == len(rows)
          and type(proof.get('payload_bytes')) is int and proof['payload_bytes'] == len(payload)
          and proof.get('payload_sha256') == hashlib.sha256(payload).hexdigest()
          and proof.get('canonical_sha256') == hashlib.sha256(json.dumps(rows, ensure_ascii=False,
              sort_keys=True, separators=(',', ':')).encode()).hexdigest()
          and isinstance(proof.get('contract_sha256'), str) and re.fullmatch('[a-f0-9]{64}', proof['contract_sha256'])
          and proof.get('strict_eof') is True and proof.get('source_kind') == 'original-publisher')
    methods = proof.get('method_sha256s')
    check(isinstance(methods, list) and 1 <= len(methods) <= 3
          and all(isinstance(method, str) and re.fullmatch('[a-f0-9]{64}', method) for method in methods)
          and methods == sorted(set(methods)))
    return proof


def read_manual(executable, metadata, payload):
    """Derive and strictly decode the complete currently owned original table."""
    from .genshin_native_x64 import Image
    from .genshin_native_registration import Bindings
    from .genshin_native_view import View
    from .genshin_native_usage import table_reader, dispatcher, usage_profile, Usages, slot_arrays
    from .genshin_native_literals import literal_profile, Literals, path_callers
    from .genshin_native_contracts import Contracts
    from .genshin_native_words import Context
    from . import genshin_original_dialogue as binary

    check(isinstance(metadata, bytes) and 512 <= len(metadata) <= MAX_METADATA
          and isinstance(payload, bytes) and 4 <= len(payload) <= 64 * 1024**2)
    view = View(Bindings(Image(executable), metadata))
    anchor = table_reader(view, 'MoleMole.Config', 'TalkExcelConfig')
    dispatch = dispatcher(view, anchor)
    usages = Usages(view, usage_profile(view, dispatch))
    arrays = slot_arrays(view, dispatch, usages)
    literals = Literals(view, usages, literal_profile(view, dispatch))
    paths = path_callers(view, literals, arrays, roles=(MANUAL_PATH,))
    definitions = {declared['type']['definition'] for row in paths
                   if any(literal['path'] == MANUAL_PATH for literal in row['literals'])
                   for declared in row['owners']}
    check(len(definitions) == 1)
    definition, = definitions
    methods = view.methods(definition)
    getters = [method for method in methods if method['rva'] and len(method['parameters']) == 1
               and method['parameters'][0]['type']['kind'] == 14
               and method['return_type'].get('definition') is not None]
    loaders = [method for method in methods if method['rva'] and method['return_type']['kind'] == 1
               and len(method['parameters']) == 1 and method['parameters'][0]['type']['index'] == anchor['stream']]
    check(len(getters) == len(loaders) == 1)
    getter, loader = getters[0], loaders[0]
    record_definition = getter['return_type']['definition']
    fields = view.fields(record_definition)
    identities = [field['name'] for field in fields if field['type']['kind'] == 14]
    hashes = [field['name'] for field in fields if field['type']['kind'] == 9]
    check(len(identities) == len(hashes) == 1)
    reader = view.inner_reader(record_definition, anchor['stream'])
    contracts = Contracts(view, anchor['stream'], usages=usages, arrays=arrays)
    record = contracts.record(record_definition, reader['rva'])
    context = Context(view.image, loader['rva'])
    reads = context.reads(4)
    check(reads)
    count = binary.Word(32, context.operations(reads[0].address - view.image.base, 32, 'root_count'))
    contract = binary.Array(count, record)
    original = binary.decode_original(payload, contract)  # Strict whole EOF.
    rows = validate_rows([{'textMapId': row.get(identities[0]), 'textMapContentTextMapHash': row.get(hashes[0], 0)}
                          for row in original])
    proof = {'schema': 'genshin-original-manual-table-v1', 'rows': len(rows),
             'payload_sha256': hashlib.sha256(payload).hexdigest(), 'payload_bytes': len(payload),
             'canonical_sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                                          separators=(',', ':')).encode()).hexdigest(),
             'contract_sha256': hashlib.sha256(json.dumps(binary._source_contract(contract), sort_keys=True).encode()).hexdigest(),
             'method_sha256s': sorted({hashlib.sha256(view.image.window(method['rva'])).hexdigest()
                                      for method in (getter, loader, reader)}),
             'strict_eof': True, 'source_kind': 'original-publisher'}
    return rows, validate_proof(proof, rows, payload)
