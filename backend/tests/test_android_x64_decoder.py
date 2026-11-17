"""Pinned Windows CAPI reference for the bounded Android wire contract.

These host tests do not execute an Android ELF or establish APK acceptance.
"""
import copy
import json
import os

import pytest

from backend.android_x64_decoder import PackagedX64Decoder, SOURCE_SHA256
from backend import genshin_native_x64 as original

CODE = [bytes.fromhex(value) for value in (
    '488d05200000004869c007000000c3',
    '48b8f0debc9a7856341248c7c0ffffffffc3',
    '48b81032547698badcfe64488b44cbe0c3',
    'e805000000ebfe7502c3',
    '50534889e54883ec20480fbae0084883c4205b58c3',
)]
ADDRESSES = [0x1000, 0x123456789ABCDE00, 0xFEDCBA9876000000]


def wire(instruction):
    operands = []
    for op in instruction.operands:
        value = {'type': op.type, 'size': op.size, 'access': op.access}
        if op.type == 1: value['reg'] = op.reg
        elif op.type == 2: value['imm'] = op.imm
        else: value['mem'] = {name: getattr(op.mem, name) for name in ('segment', 'base', 'index', 'scale', 'disp')}
        operands.append(value)
    reads, writes = instruction.regs_access()
    return {'address': instruction.address, 'size': instruction.size, 'id': instruction.id,
        'mnemonic': instruction.mnemonic, 'op_str': instruction.op_str, 'bytes': instruction.bytes.hex(),
        'groups': list(instruction.groups), 'regs_read': reads, 'regs_write': writes, 'operands': operands}


class Reference:
    def __init__(self):
        self.decoder = original.decoder()
        from capstone.x86_const import X86_REG_ENDING
        self.proof = {'schema': 'toolkit-x64-capi-v1', 'version': '5.0.7', 'source_sha256': SOURCE_SHA256,
            'abi': 'arm64-v8a', 'pointer_bits': 64, 'api_major': 5, 'api_minor': 0,
            'apk_entry_verified': True, 'licenses_verified': True, 'system_fallback': False,
            'original_client_execution': False, 'library_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64,
            'register_names': [self.decoder.reg_name(value) for value in range(X86_REG_ENDING)]}
    def disassembleX64(self, data, address, count):
        return json.dumps([wire(value) for value in self.decoder.disasm(data, address & (2**64 - 1), count)])


@pytest.mark.skipif(os.name != 'nt', reason='The authenticated reference wheel gate supports Windows amd64')
@pytest.mark.parametrize('data', CODE)
@pytest.mark.parametrize('address', ADDRESSES)
def test_wire_preserves_actual_full_integer_operand_and_register_contract(data, address):
    bridge = Reference(); adapted = PackagedX64Decoder(bridge, bridge.proof)
    expected = [wire(value) for value in bridge.decoder.disasm(data, address)]
    actual = list(adapted.disasm(data, address))
    assert [wire(value) for value in actual] == expected
    for index, value in enumerate(actual):
        for register in range(len(bridge.proof['register_names'])):
            assert value.reg_name(register) == bridge.decoder.reg_name(register)
        assert all(value.group(group) for group in expected[index]['groups'])
    assert not adapted.verified
    assert adapted.verify_contract() == adapted.proof()['authored_contract_sha256']
    with pytest.raises(ValueError): original.install_android_decoder(adapted)


@pytest.mark.skipif(os.name != 'nt', reason='Requires authenticated Windows reference software')
@pytest.mark.parametrize('change', [
    {'source_sha256': 'f' * 64}, {'system_fallback': True}, {'licenses_verified': False},
    {'apk_entry_verified': False}, {'original_client_execution': True}, {'pointer_bits': 32}, {'api_major': 4},
])
def test_unsupported_or_unverified_software_never_enables_provider(change):
    bridge = Reference()
    with pytest.raises(ValueError): PackagedX64Decoder(bridge, {**bridge.proof, **change})


@pytest.mark.skipif(os.name != 'nt', reason='Requires authenticated Windows reference software')
def test_malformed_wire_and_unbounded_inputs_fail_closed(monkeypatch):
    bridge = Reference(); adapted = PackagedX64Decoder(bridge, bridge.proof)
    value = json.loads(bridge.disassembleX64(CODE[0], 0x1000, 0))
    for mutate in (
        lambda v: v[0].update(address=True),
        lambda v: v[0].update(bytes='ff'),
        lambda v: v[0]['operands'][1]['mem'].update(disp=2**64),
        lambda v: v[0].update(regs_write=[100000]),
        lambda v: v[0].update(operands=[{'type': 9}]),
    ):
        changed = copy.deepcopy(value); mutate(changed)
        monkeypatch.setattr(bridge, 'disassembleX64', lambda *_, result=changed: json.dumps(result))
        with pytest.raises(ValueError): list(adapted.disasm(CODE[0], 0x1000))
    for data, address, count in ((b'x' * 65537, 0, 0), (b'x', -1, 0), (b'x', 0, 65537), (b'x', 2**64, 0)):
        with pytest.raises(ValueError): list(adapted.disasm(data, address, count))


def test_arbitrary_provider_or_environment_path_cannot_bypass_windows_gate(monkeypatch):
    with pytest.raises(ValueError): original.install_android_decoder(object())
    original.decoder.cache_clear()
    monkeypatch.setenv('LIBCAPSTONE_PATH', 'untrusted-game-input')
    with pytest.raises(ValueError, match='overridden'): original.decoder()
    original.decoder.cache_clear()
