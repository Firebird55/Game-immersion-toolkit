"""Authored DATA fixtures; no Android/client execution or runtime ungating."""
from dataclasses import replace
import io
import json
import struct

import pytest

from backend import starrail_android_ir as ir
from backend.android_x64_decoder import Operand, PackagedX64Decoder, SOURCE_SHA256
from backend.android_x64_fixtures import CASES, REGISTER_NAMES


def reg(name): return REGISTER_NAMES.index(name)
def register(name, size=8): return {'type': 1, 'size': size, 'access': 0, 'reg': reg(name)}
def immediate(value, size=8): return {'type': 2, 'size': size, 'access': 0, 'imm': value}
def memory(base, *, index=None, scale=1, disp=0, size=8, segment=None):
    return {'type': 3, 'size': size, 'access': 0, 'mem': {'segment': reg(segment) if segment else 0,
        'base': reg(base) if base else 0, 'index': reg(index) if index else 0, 'scale': scale, 'disp': disp}}


def row(address, code, mnemonic, operands=(), groups=()):
    return {'address': address, 'size': len(bytes.fromhex(code)), 'id': 1, 'mnemonic': mnemonic,
        'op_str': 'untrusted text deliberately ignored', 'bytes': code.replace(' ', ''),
        'operands': list(operands), 'groups': list(groups), 'regs_read': [], 'regs_write': []}


class AuthoredWire:
    def __init__(self, rows): self.rows = {v['address']: v for v in rows}; self.calls = 0
    def disassembleX64(self, data, address, count):
        self.calls += 1; address &= ir.U64
        result, used = [], 0
        while used < len(data) and (not count or len(result) < count):
            value = self.rows.get(address+used)
            if value is None or data[used:used+value['size']].hex() != value['bytes']: break
            result.append(value); used += value['size']
        return json.dumps(result)


def decoder(rows):
    wire = AuthoredWire(rows)
    proof = {'schema': 'toolkit-x64-capi-v1', 'version': '5.0.7', 'source_sha256': SOURCE_SHA256,
        'abi': 'arm64-v8a', 'pointer_bits': 64, 'api_major': 5, 'api_minor': 0,
        'apk_entry_verified': True, 'licenses_verified': True, 'system_fallback': False,
        'original_client_execution': False, 'library_sha256': 'a'*64, 'manifest_sha256': 'b'*64,
        'register_names': list(REGISTER_NAMES)}
    return PackagedX64Decoder(wire, proof)


def helper(rows, monkeypatch):
    value = decoder(rows)
    # Authored transport only. This monkeypatch never exists in production and
    # does not establish the real Java identity/verified APK gate.
    value._verified = True
    monkeypatch.setattr(value, 'require_android', lambda: None)
    return ir.AndroidIR(value)


@pytest.mark.parametrize('case', CASES)
def test_existing_frozen_capi_vectors_have_complete_linear_byte_coverage(case):
    value = decoder(case['instructions']); data = bytes.fromhex(case['hex'])
    result = ir._range(value, data, case['address'], False)
    assert sum(v.size for v in result) == len(data)
    assert [v.address for v in result] == [v['address'] for v in case['instructions']]


@pytest.mark.parametrize('value,expected', [
    (row(0x1000, '48c7c0ffffffff', 'mov', [register('rax'), immediate(-1)]), ['mov', 'rax, 0xffffffffffffffff']),
    (row(0x1000, 'b8ffffffff', 'mov', [register('eax', 4), immediate(-1, 4)]), ['mov', 'eax, 0xffffffff']),
    (row(0x1000, '48b8f0debc9a78563412', 'movabs', [register('rax'), immediate(0x123456789abcdef0)]), ['movabs', 'rax, 0x123456789abcdef0']),
    (row(0x1000, '488d05e0ffffff', 'lea', [register('rax'), memory('rip', disp=-32)]), ['lea', 'rax, [rip - 0x20]']),
    (row(0x1000, '64488b44cbe0', 'mov', [register('rax'), memory('rbx', index='rcx', scale=8, disp=-32, segment='fs')]), ['mov', 'rax, qword ptr fs:[rbx + rcx*8 - 0x20]']),
    (row(0x1000, '660f6fc1', 'movdqa', [register('xmm0', 16), register('xmm1', 16)]), ['movdqa', 'xmm0, xmm1']),
    (row(0x1000, '7500', 'jnz', [immediate(0x1002)], [1, 7]), ['jne', '0x1002']),
    (row(0xfedcba9876000000, 'ebfe', 'jmp', [immediate(0xfedcba9876000000-2**64)], [1, 7]), ['jmp', '0xfedcba9876000000']),
    (row(0x1000, '48a10000000000000000', 'movabs', [register('rax'), memory(None, disp=0)]), ['mov', 'rax, qword ptr [0x0]']),
    (row(0x1000, '4869c007000000', 'imul', [register('rax'), register('rax'), immediate(7)]), ['imul', 'rax, 0x7']),
    (row(0x1000, 'f3aa', 'rep stosb', [memory('rdi', size=1), register('al', 1)]), ['rep stosb', 'byte ptr [rdi]']),
    (row(0x1000, 'f3ac', 'rep lodsb', [register('al', 1), memory('rsi', size=1)]), ['rep lodsb', 'byte ptr [rsi]']),
    (row(0x1000, 'f2ae', 'repne scasb', [register('al', 1), memory('rdi', size=1)]), ['repne scasb', 'byte ptr [rdi]']),
    (row(0x1000, 'f3c3', 'repz ret', groups=[3]), ['rep ret', '']),
    (row(0x1000, '2e488b00', 'mov', [register('rax'), memory('rax', segment='cs')]), ['mov', 'rax, qword ptr [rax]']),
])
def test_structured_operands_preserve_unsigned_width_rip_aliases_and_exact_addresses(value, expected):
    instruction, = decoder([value]).disasm(bytes.fromhex(value['bytes']), value['address'])
    assert ir.normalize(instruction) == [value['address'], *expected]


def test_missing_ir_fields_are_typed_unresolved_not_a_publisher_format_change():
    value = row(0x1000, '90', 'nop'); instruction, = decoder([value]).disasm(b'\x90', 0x1000)
    for changed in (replace(instruction, size=24), replace(instruction, operands=(Operand(3, 3, 0),)),
                    replace(instruction, mnemonic='unknown text extra')):
        with pytest.raises(ir.IRUnavailable) as error: ir.normalize(changed)
        assert error.value.code == 'starrail_ir_contract_unresolved'


def test_unverified_reference_provider_and_metadata_operation_never_enable_a_runtime(monkeypatch):
    with pytest.raises(ir.IRUnavailable): ir.AndroidIR(decoder([]))
    with pytest.raises(ir.IRUnavailable): ir.AndroidIR(object())
    with pytest.raises(ir.IRUnavailable): ir.AndroidIR.from_native(object())
    value = helper([], monkeypatch)
    with pytest.raises(ir.IRUnavailable, match='metadata-reader-not-implemented'):
        value.run('metadata', work='.')


def test_missing_own_source_binding_is_unresolved_and_provider_is_rechecked(tmp_path, monkeypatch):
    value = helper([], monkeypatch)
    value._decoder._verified = False
    with pytest.raises(ir.IRUnavailable, match='verified-Android-provider'):
        value.run('disassemble', work=tmp_path)
    def missing(path): raise OSError('Source is not present in this runtime layout')
    monkeypatch.setattr(ir.metadata, '_hash', missing)
    with pytest.raises(ir.IRUnavailable, match='adapter-source-binding'):
        helper([], monkeypatch)


def test_valid_prefix_with_truncated_or_unsupported_suffix_is_rejected_atomically(tmp_path, monkeypatch):
    source = tmp_path/'input'; source.write_bytes(bytes.fromhex('90 48b8'))
    request = tmp_path/'request'; output = tmp_path/'output'
    request.write_text(json.dumps({'ranges': [{'offset': 0, 'address': 0x1000, 'bytes': 3}]}))
    value = helper([row(0x1000, '90', 'nop')], monkeypatch)
    with pytest.raises(ir.IRInputError): value.run('disassemble', source, request, output, work=tmp_path)
    assert not output.exists() and source.read_bytes() == bytes.fromhex('90 48b8')


@pytest.mark.parametrize('spec', [
    {'offset': True, 'address': 0, 'bytes': 1}, {'offset': 0, 'address': True, 'bytes': 1},
    {'offset': 0, 'address': 0, 'bytes': 65537}, {'offset': 2, 'address': 0, 'bytes': 1},
    {'offset': 0, 'address': ir.U64, 'bytes': 1}, {'offset': 0, 'address': 0, 'bytes': 1, 'unknown': 1},
    {'offset': 0, 'address': 0, 'bytes': 1, 'control_flow': False},
    None,
])
def test_all_range_bounds_are_preflighted_before_any_decode(spec):
    value = decoder([row(0, '90', 'nop')])
    with pytest.raises(ir.IRInputError): ir._ranges(io.BytesIO(b'\x90'), {'ranges': [spec]}, value)
    assert value._native.calls == 0


def test_future_vector_decorators_without_ir_fields_are_unresolved():
    value = row(0x1000, 'c5f8 58c1', 'vaddps', [register('xmm0', 16), register('xmm0', 16), register('xmm1', 16)])
    instruction, = decoder([value]).disasm(bytes.fromhex(value['bytes']), 0x1000)
    with pytest.raises(ir.IRUnavailable, match='vector-encoding-not-represented'):
        ir.normalize(instruction)


def test_aggregate_range_budget_and_duplicate_json_are_rejected_before_decode(tmp_path, monkeypatch):
    value = decoder([])
    spec = {'offset': 0, 'address': 0x1000, 'bytes': 65536}
    with pytest.raises(ir.IRInputError):
        ir._ranges(io.BytesIO(bytes(65536)), {'ranges': [spec]*257}, value)
    assert value._native.calls == 0
    source, request, output = (tmp_path/name for name in ('source', 'request', 'output'))
    source.write_bytes(b'\x90'); request.write_text('{"ranges":[],"ranges":[]}')
    adapter = helper([], monkeypatch)
    with pytest.raises(ir.IRInputError): adapter.run('disassemble', source, request, output, work=tmp_path)
    assert adapter._decoder._native.calls == 0 and not output.exists()
    output.write_bytes(b'previous output')
    with pytest.raises(ir.IRInputError): adapter.run('disassemble', source, request, output, work=tmp_path)
    assert output.read_bytes() == b'previous output'


def switch_fixture():
    address = 0x1000
    data = bytes.fromhex('83f801 7712 488d1514000000 48630482 4801d0 ffe0 c3 c3 c3') + bytes(8) + struct.pack('<ii', -11, -10)
    rows = [row(address, '83f801', 'cmp', [register('eax', 4), immediate(1, 4)]),
        row(address+3, '7712', 'ja', [immediate(address+23)], [1, 7]),
        row(address+5, '488d1514000000', 'lea', [register('rdx'), memory('rip', disp=20)]),
        row(address+12, '48630482', 'movsxd', [register('rax'), memory('rdx', index='rax', scale=4, size=4)]),
        row(address+16, '4801d0', 'add', [register('rax'), register('rdx')]),
        row(address+19, 'ffe0', 'jmp', [register('rax')], [1])]
    rows += [row(address+n, 'c3', 'ret', groups=[3]) for n in (21, 22, 23)]
    return data, rows


def test_guarded_indirect_switch_follows_all_authored_edges_without_decoding_table_bytes():
    data, rows = switch_fixture(); result = ir._range(decoder(rows), data, 0x1000, True)
    assert [v.address for v in result] == [v['address'] for v in rows]


@pytest.mark.parametrize('change', ['bypass', 'overlap', 'unknown-index', 'table-bounds'])
def test_unknown_or_bypassed_switch_and_overlapping_targets_fail_closed(change):
    data, rows = switch_fixture()
    if change == 'bypass': rows[1]['operands'][0]['imm'] = 0x1005
    elif change == 'overlap': data = data[:-8]+struct.pack('<ii', -26, -10)
    elif change == 'unknown-index': rows[3]['operands'][1]['mem']['index'] = reg('rcx')
    else: rows[0]['operands'][1]['imm'] = 255
    with pytest.raises((ir.IRInputError, ir.IRUnavailable)): ir._range(decoder(rows), data, 0x1000, True)


def test_prepared_helper_native_graph_matches_existing_contract_without_a_metadata_dump(tmp_path, monkeypatch):
    from backend.tests.test_starrail_native_graph import fixture
    prepared, expected = fixture(tmp_path)
    base, first, second = expected['image_base'], expected['entry_rva'], 0x20000000
    rows = [row(base+first, 'e9'+struct.pack('<i', second-first-5).hex(), 'jmp', [immediate(base+second)], [1, 7]),
        row(base+second, '7503', 'jne', [immediate(base+second+5)], [1, 7]),
        row(base+second+2, '90', 'nop'), row(base+second+3, 'c3', 'ret', groups=[3]),
        row(base+second+5, '90', 'nop'), row(base+second+6, 'c3', 'ret', groups=[3])]
    prepared = replace(prepared, helper=helper(rows, monkeypatch))
    assert prepared.native_graph(first) == expected
    assert (prepared.outputs/'dump.cs').read_text() == 'previous complete metadata'
    assert not list(tmp_path.glob('native-graph-*'))


@pytest.mark.parametrize('kind', ['call', 'indirect-call'])
def test_native_graph_records_calls_as_opaque_edges(tmp_path, monkeypatch, kind):
    from backend.tests.test_starrail_native_graph import probe
    code = bytes.fromhex('e8fbffffffc3' if kind == 'call' else 'ffd0c3')
    source = tmp_path/'input'; source.write_bytes(probe.native_pe([(0x1000, code)]))
    first = row(0x180001000, code[:-1].hex(), 'call',
        [immediate(0x180001000)] if kind == 'call' else [register('rax')], [2])
    value = helper([first, row(first['address']+first['size'], 'c3', 'ret', groups=[3])], monkeypatch)
    request, output = tmp_path/'request', tmp_path/'output'; request.write_text('{"entry_rva":4096}')
    value.run('native-graph', source, request, output, work=tmp_path)
    result = json.loads(output.read_bytes())
    assert result['calls'] == [[first['address'], 'direct' if kind == 'call' else 'indirect', first['address'] if kind == 'call' else None]]
    assert len(result['instructions']) == 2


class TrackedSource(io.BytesIO):
    def __init__(self, data): super().__init__(data); self.reads = []
    def read(self, length=-1):
        self.reads.append((self.tell(), length)); return super().read(length)


@pytest.mark.parametrize('limit', ['regions', 'bytes'])
def test_graph_limits_are_checked_before_reading_the_next_code_region(limit):
    from backend.tests.test_starrail_native_graph import probe
    count = 17 if limit == 'regions' else 2
    starts = [0x1000+n*0x10000 for n in range(count)]; regions, rows = [], []
    for n, start in enumerate(starts):
        target = starts[n+1] if n+1<count else None
        code = b'\xe9'+struct.pack('<i', target-start-5) if target else b'\xc3'
        if limit == 'bytes' and n == 0: code += bytes(32768-len(code))
        regions.append((start, code))
        rows.append(row(0x180000000+start, code[:5].hex() if target else 'c3', 'jmp' if target else 'ret',
                        [immediate(0x180000000+target)] if target else [], [1, 7] if target else [3]))
    source = TrackedSource(probe.native_pe(regions))
    with pytest.raises(ir.IRInputError): ir._graph(source, starts[0], decoder(rows))
    header = (0x80+24+240+(count+1)*40+511)&~511
    next_offset = header+sum((len(code)+511)&~511 for _, code in regions[:-1])
    assert not any(offset == next_offset and length == len(regions[-1][1]) for offset, length in source.reads)


@pytest.mark.parametrize('kind', ['indirect', 'trap', 'no-return', 'unterminated', 'interior-owner'])
def test_unsupported_or_incomplete_native_graph_never_publishes_output(tmp_path, monkeypatch, kind):
    from backend.tests.test_starrail_native_graph import probe
    base, start = 0x180000000, 0x1000
    code = {'indirect': 'ffe0', 'trap': 'cc', 'no-return': 'ebfe', 'unterminated': '90',
            'interior-owner': 'e9fc0f0000'}[kind]
    op = {'indirect': 'jmp', 'trap': 'int3', 'no-return': 'jmp', 'unterminated': 'nop',
          'interior-owner': 'jmp'}[kind]
    groups = {'indirect': [1], 'trap': [4], 'no-return': [1, 7], 'unterminated': [], 'interior-owner': [1, 7]}[kind]
    operands = ([register('rax')] if kind == 'indirect' else [immediate(base+start)] if kind == 'no-return'
                else [immediate(base+0x2001)] if kind == 'interior-owner' else [])
    regions = [(start, bytes.fromhex(code))] + ([(0x2000, b'\x90\xc3')] if kind == 'interior-owner' else [])
    source = tmp_path/'source'; source.write_bytes(probe.native_pe(regions))
    adapter = helper([row(base+start, code, op, operands, groups)], monkeypatch)
    request, output = tmp_path/'request', tmp_path/'output'; request.write_text('{"entry_rva":4096}')
    with pytest.raises((ir.IRInputError, ir.IRUnavailable)):
        adapter.run('native-graph', source, request, output, work=tmp_path)
    assert not output.exists()


def test_unsorted_original_function_table_fails_before_any_code_decode():
    from backend.tests.test_starrail_native_graph import probe
    value = decoder([])
    with pytest.raises(ir.IRInputError):
        ir._graph(io.BytesIO(probe.native_pe([(0x2000, b'\xc3'), (0x1000, b'\xc3')])), 0x1000, value)
    assert value._native.calls == 0
