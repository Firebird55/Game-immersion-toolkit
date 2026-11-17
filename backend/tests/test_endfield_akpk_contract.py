"""Whole independently encoded containers gate source-owned candidate fields."""
from dataclasses import replace
import hashlib
import struct
from types import SimpleNamespace as NS
import zlib

import pytest

from backend.endfield_akpk_contract import Candidate, transform_candidate
from backend.endfield_akpk_controls import validate
from backend.endfield_vfs import IndexParameters
from backend.tests.test_endfield_vfs import PARAMETERS, package, index, encrypt


def declaration(payload):
    original = index(len(payload), encrypted=False, name='default_owned_banks.pck')
    body = bytearray(encrypt(original[12:], original[:12]))
    at = body.index(bytes(32))
    body[at:at + 32] = bytes.fromhex('a' * 32 + hashlib.md5(payload).hexdigest())
    body[-4:] = struct.pack('<I', zlib.crc32(body[:-4]))
    return original[:12] + encrypt(bytes(body), original[:12])


def common():
    return IndexParameters(PARAMETERS.key, PARAMETERS.directories)


def test_full_authored_package_and_every_bank_gate_candidate_acceptance():
    # The existing fixture encodes all key words with an independent scalar
    # algorithm, not the reader's vector transform or a copied native body.
    payload = package()
    parameters, proof = validate(Candidate(5, 7), common(), declaration(payload), 102,
                                 'default_owned_banks.pck', payload)
    assert parameters == PARAMETERS and proof['complete_banks'] == 1
    assert proof['complete_bank_sections'] == 4 and proof['media_entries'] == 3
    assert proof['original_file_md5'] == hashlib.md5(payload).hexdigest()
    assert proof['media_playback_verified'] is False
    assert 'multiplier' not in proof and 'xor_constant' not in proof
    assert repr(Candidate(5, 7)) == 'Candidate()'


@pytest.mark.parametrize('kind', ['multiplier', 'xor', 'index_crc', 'file_hash', 'wrong_owner', 'missing_owner', 'plain_header', 'different_bank'])
def test_failed_control_never_returns_usable_audio_parameters(kind):
    payload = package()
    original_index = declaration(payload)
    candidate, name = Candidate(5, 7), 'default_owned_banks.pck'
    if kind == 'multiplier':
        candidate = replace(candidate, multiplier=9)
    elif kind == 'xor':
        candidate = replace(candidate, xor_constant=11)
    elif kind == 'index_crc':
        original_index = original_index[:-1] + bytes([original_index[-1] ^ 1])
    elif kind == 'file_hash':
        payload = payload[:-1] + bytes([payload[-1] ^ 1])
    elif kind == 'wrong_owner':
        name = 'different_banks.pck'
    elif kind == 'missing_owner':
        common_params = IndexParameters(PARAMETERS.key, {1: '00000001'})
        with pytest.raises(ValueError):
            validate(candidate, common_params, original_index, 102, name, payload)
        return
    elif kind == 'plain_header':
        payload = package(encrypted_header=False)
        original_index = declaration(payload)
    elif kind == 'different_bank':
        # A correctly MD5-bound new file still has to pass complete internal
        # bank sections; content identity does not imply format validity.
        payload = package(bad_bank=True)
        original_index = declaration(payload)
    with pytest.raises(ValueError):
        validate(candidate, common(), original_index, 102, name, payload)


def owned_fields(multiplier=5, mask=7):
    def operand(kind, *, size=4, value=None):
        return NS(type=kind, size=size, imm=value)
    def row(name, *values):
        return NS(mnemonic=name, operands=values)
    register = operand(1)
    result = []
    for _ in range(3):
        result += [row('xor', register, operand(2, value=mask))]
        result += [row('imul', register, register, operand(2, value=multiplier)) for _ in range(4)]
        result += [row('shr', register, operand(2, value=value)) for value in (8, 16, 24)]
    result += [row('xor', operand(3, size=size), operand(1, size=size)) for size in (4, 1, 1)]
    result += [row('xorps', register, register) for _ in range(5)]
    return result


@pytest.mark.parametrize('multiplier,mask', [(5, 7), (17, 0), (0x10203, 0x4050607)])
def test_authored_master_rotation_comes_from_all_current_owned_paths(multiplier, mask):
    assert transform_candidate(owned_fields(multiplier, mask)) == Candidate(multiplier, mask)


@pytest.mark.parametrize('change', ['one_round', 'one_mask', 'byte_order', 'wrong_output', 'different_round_count', 'extra_call'])
def test_divergent_or_changed_original_round_contract_is_not_a_candidate(change):
    rows = owned_fields()
    if change == 'one_round':
        rows[2].operands[2].imm = 19
    elif change == 'one_mask':
        rows[8].operands[1].imm = 9
    elif change == 'byte_order':
        rows[5].operands[1].imm = 7
    elif change == 'wrong_output':
        rows[-6].operands[0].size = 2
    elif change == 'different_round_count':
        del rows[2]
    elif change == 'extra_call':
        rows.append(NS(mnemonic='call', operands=[]))
    with pytest.raises(ValueError):
        transform_candidate(rows)
