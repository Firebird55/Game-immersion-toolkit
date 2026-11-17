"""Original table consumers keep bounded native ambiguity and complete sizing."""
import struct
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.genshin_native_words import Context
from backend.genshin_native_contracts import Contracts, array_element
from backend.genshin_original_excel import validate_rows, metadata_name
from backend.genshin_native_x64 import Image
from backend.tests.test_genshin_native_bootstrap import toy_image, requires_decoder


def image_with_code(code, helper=b'\xc3'):
    raw = bytearray(toy_image(duplicate=True))
    raw[0x200:0x200 + len(code)] = code
    raw[0x220:0x220 + len(helper)] = helper
    struct.pack_into('<I', raw, 0xc04, 0x1000 + len(code))
    struct.pack_into('<I', raw, 0xc10, 0x1020 + len(helper))
    return Image(bytes(raw))


@requires_decoder
@pytest.mark.parametrize('throws', [True, False])
def test_only_proved_nonreturning_error_reads_are_excluded(throws):
    # First read returns normally; the second reaches a real typed helper call.
    code = bytes.fromhex('8b4411204585c07401c38b441120e80d000000c3')
    context = Context(image_with_code(code, b'\xcc' if throws else b'\xc3'), 0x1000)
    first, error = context.reads()
    assert first.address in context.returning_nodes()
    assert (error.address in context.returning_nodes()) is not throws
    assert context.returning_nodes() is context.returning_nodes()


@requires_decoder
@pytest.mark.parametrize('other', [0x55, 0x56])
def test_equivalent_unrolled_native_elements_merge_but_changed_operands_reject(other):
    # Two real stream-read -> XOR -> array-store paths, rather than mock profiles.
    part = lambda operand: bytes.fromhex('8b44112083f0') + bytes([operand]) + bytes.fromhex('8944b320')
    context = Context(image_with_code(part(0x55) + part(other) + b'\xc3'), 0x1000)
    reads = [instruction.address - context.image.base for instruction in context.reads()]
    assert len(reads) == 2
    if other == 0x55:
        assert array_element(context, reads, 32).transform(7) == 7 ^ 0x55
    else:
        with pytest.raises(ValueError, match='conflicting'): array_element(context, reads, 32)


def test_protected_array_wrapper_must_own_its_primitive_and_typed_setter():
    fields = [{'type': {'kind': 29, 'element': {'kind': 17, 'definition': 11}}}]
    view = SimpleNamespace(fields=lambda definition: [{'name': 'value', 'type': {'kind': 9}}],
        methods=lambda definition: [
            {'name': 'get_value', 'parameters': [], 'return_type': {'kind': 9}, 'rva': 0x1000},
            {'name': 'set_value', 'parameters': [{'type': {'kind': 9}}], 'return_type': {'kind': 1}, 'rva': 0x1020}])
    contract = Contracts(view, 1)
    assert contract.wrappers(fields) == ({11: 9}, {0x1020: 'rdx'})
    view.methods = lambda definition: []
    assert contract.wrappers(fields) == ({}, {})


@pytest.mark.parametrize('change', ['missing-id', 'missing-hash', 'bool-hash', 'wide-hash', 'unexpected-field'])
def test_changed_canonical_table_shape_never_becomes_a_silent_empty_table(change):
    row = {'textMapId': 'INFO_MALE_PRONOUN_subject', 'textMapContentTextMapHash': 17}
    if change == 'missing-id': row.pop('textMapId')
    elif change == 'missing-hash': row.pop('textMapContentTextMapHash')
    elif change == 'bool-hash': row['textMapContentTextMapHash'] = True
    elif change == 'wide-hash': row['textMapContentTextMapHash'] = 1 << 32
    else: row['unverified_extra'] = 'value'
    with pytest.raises(ValueError): validate_rows([row])


def test_metadata_path_keeps_regional_editions_distinct():
    assert metadata_name('genshin-global').startswith('GenshinImpact_Data/Native/Data/')
    assert metadata_name('genshin-cn').startswith('YuanShen_Data/Native/Data/')
    with pytest.raises(ValueError): metadata_name('unknown')


def manual_source(tmp_path, monkeypatch):
    from backend import genshin_official_source as source, genshin_original_excel as excel
    from backend.genshin_original_containers import DesignCatalog, asset_identity
    from backend.tests.test_genshin_original_containers import catalog
    from backend.tests.test_genshin_official_text import Objects
    from backend.tests.test_genshin_official_source import build
    directory = tmp_path / 'source'; directory.mkdir(exist_ok=True)
    native = directory / 'original-native'; native.write_bytes(b'N' * 1024)
    metadata = directory / 'original-metadata'; metadata.write_bytes(b'M' * 1024)
    info = lambda path: {'name': metadata_name('genshin-global'), 'bytes': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'publisher_md5': hashlib.md5(path.read_bytes()).hexdigest()}
    calls = []
    def official(directory, selected, publisher, name, *args):
        assert name == metadata_name(selected['channel'])
        return metadata, info(metadata)
    monkeypatch.setattr(source, '_official_file', official)
    rows = [{'textMapId': 'INFO_MALE_PRONOUN_subject', 'textMapContentTextMapHash': 1},
            {'textMapId': 'INFO_FEMALE_PRONOUN_subject', 'textMapContentTextMapHash': 2}]
    payload = b'owned complete synthetic table payload'
    def parse(exe, meta, raw):
        calls.append(True)
        assert exe == native.read_bytes() and meta == metadata.read_bytes() and raw == payload
        proof = {'schema': 'genshin-original-manual-table-v1', 'rows': len(rows),
            'payload_bytes': len(payload), 'payload_sha256': hashlib.sha256(payload).hexdigest(),
            'canonical_sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'contract_sha256': 'a' * 64, 'method_sha256s': ['b' * 64],
            'strict_eof': True, 'source_kind': 'original-publisher'}
        return rows, proof
    monkeypatch.setattr(excel, 'read_manual', parse)
    identity = asset_identity(excel.MANUAL_PATH)
    def make():
        value = object.__new__(source.Source)
        value.directory, value.publisher, value.build = directory, directory / 'sophon', build()
        value.stamp = 'sophon-' + source.identity(value.build)
        value.native_input = native, info(native)
        value.catalog = DesignCatalog(catalog((identity,)))
        value.objects = lambda package: Objects({identity: payload})
        value.manual_rows, value.manual_receipt = None, None
        return value
    return make, rows, calls, metadata


def test_normal_source_table_api_reopens_owned_cache_and_repairs_invalid_proof(tmp_path, monkeypatch):
    make, expected, calls, _ = manual_source(tmp_path, monkeypatch)
    first = make()
    assert first.file('ExcelBinOutput/ManualTextMapConfigData.json') == expected
    assert len(calls) == 1 and first.manual_receipt['owner']['metadata']['bytes'] == 1024
    assert make().manual() == expected and len(calls) == 1
    cached, = first.directory.glob('manual-*.private-json')
    broken = json.loads(cached.read_bytes()); broken['proof']['method_sha256s'] = ['moving-branch']
    cached.write_text(json.dumps(broken))
    assert make().manual() == expected and len(calls) == 2
    assert json.loads(cached.read_bytes())['proof']['method_sha256s'] == ['b' * 64]


def test_changed_original_metadata_cannot_reuse_a_previous_table_or_destroy_it(tmp_path, monkeypatch):
    from backend import genshin_original_excel as excel
    make, expected, calls, metadata = manual_source(tmp_path, monkeypatch)
    previous = make(); assert previous.manual() == expected
    cache, = previous.directory.glob('manual-*.private-json'); held = cache.read_bytes()
    metadata.write_bytes(b'changed original metadata fixture')
    monkeypatch.setattr(excel, 'read_manual', lambda *args: (_ for _ in ()).throw(ValueError('unsupported new native shape')))
    current = make()
    with pytest.raises(ValueError, match='new native shape'): current.manual()
    assert current.manual_rows is None and current.manual_receipt is None
    assert cache.read_bytes() == held and previous.manual() == expected
