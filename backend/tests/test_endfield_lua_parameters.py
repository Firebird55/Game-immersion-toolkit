"""Authored Lua-key rotations, typed call ownership and atomic source controls."""
import base64
import copy
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from backend import endfield_lua_contract as contract, endfield_lua_parameters as parameters
from backend.endfield_presentation_source import decode_lua
from backend.tests.endfield_parameter_fixture import (Fixture, instruction, move, register, memory,
                                                       immediate, static_store)
from backend.tests.test_endfield_client_parameters import identity


class LuaFixture(Fixture):
    def __init__(self, *, key=b'owned-lua-key-01', mask='authored Lua mask', order=(1, 5, 3, 2)):
        super().__init__()
        assert len(key) == 16
        self.fields[contract.OWNER] = {'KEYS': 0}
        self.field_types['KEYS'] = ('array', 'System.String')
        encoded = base64.b64encode(bytes((value + mask.encode()[n % len(mask.encode())]) & 255
                                         for n, value in enumerate(key))).decode()
        pieces = ['unused owned fragment'] * 8
        for index, piece in zip(order, (encoded[:6], encoded[6:12], encoded[12:18], encoded[18:-2])):
            pieces[index] = piece
        ctor = []
        for index, value in enumerate(pieces):
            ctor += [move(register('r8'), memory('rip'), literal=value), move(register('edx'), immediate(index)),
                     move(register('rcx'), register('rbx')), instruction('call', immediate(0x700))]
        ctor += static_store(contract.OWNER, 0, register('rbx'))
        getter = [move(register('rcx'), memory('rip'), owner=contract.OWNER),
                  move(register('rax'), memory('rcx', 0xb8)), move(register('rdx'), memory('rax'))]
        registers = ('r14', 'rsi', 'rdi', 'rbx')
        getter += [move(register(name), memory('rdx', 0x20 + index * 8)) for name, index in zip(registers, order)]
        reference = move(register('rax'), memory('rip'))
        reference.method_spec = {'owner': 'Beyond.UnSafeString', 'name': 'Format', 'parameters': 6,
                                 'arguments': ('System.String',) * 5}
        getter += [reference, move(register('r10'), memory('rip'), literal=encoded[-2:]),
                   move(memory('rsp', 0x30), register('rax')), move(memory('rsp', 0x28), register('r10')),
                   move(memory('rsp', 0x20), register('rbx')), move(register('r9'), register('rdi')),
                   move(register('r8'), register('rsi')), move(register('rdx'), register('r14')),
                   move(register('rcx'), memory('rip'), literal='{0}{1}{2}{3}{4}'),
                   instruction('call', immediate(0xa00)), move(register('r8'), memory('rip'), literal=mask),
                   instruction('call', immediate(0x800)), instruction('call', immediate(0x820)),
                   instruction('call', immediate(0x830))]
        self.methods[contract.OWNER, '.cctor'] = ctor
        self.methods[contract.OWNER, 'GetKey'] = getter
        self.names.update({(contract.OWNER, '.cctor'): 0xb00, (contract.OWNER, 'GetKey'): 0xc00,
                           ('System.Text.Encoding', 'GetString'): 0x830})


def derive(fixture, monkeypatch):
    monkeypatch.setattr(contract, 'Owners', fixture.owner_reader)
    monkeypatch.setattr(contract, 'Code', fixture.code_reader)
    return contract.derive(None, None)


@pytest.mark.parametrize('key,mask,order', [
    (b'owned-lua-key-01', 'authored Lua mask', (1, 5, 3, 2)),
    (b'new-key-no-data!', 'x', (7, 2, 0, 4)),
    (b'another-key-2026', 'different-length authored mask', (0, 1, 2, 3)),
])
def test_current_original_fragments_mask_and_selection_can_rotate(key, mask, order, monkeypatch):
    fixture = LuaFixture(key=key, mask=mask, order=order)
    assert derive(fixture, monkeypatch) == key


@pytest.mark.parametrize('change', ['foreign-array', 'missing-fragment', 'wrong-type', 'wrong-format-owner',
                                  'wrong-format-type', 'repeated-format-argument', 'wrong-transform',
                                  'clobbered-fragment', 'wrong-getstring', 'extra-format-caller'])
def test_changed_or_incomplete_original_contract_never_guesses_a_key(change, monkeypatch):
    fixture = LuaFixture()
    getter = fixture.methods[contract.OWNER, 'GetKey']
    if change == 'foreign-array':
        getter[0].owner = 'Authored.OtherClass'
    elif change == 'missing-fragment':
        del fixture.methods[contract.OWNER, '.cctor'][8:12]
    elif change == 'wrong-type':
        fixture.field_types['KEYS'] = 'System.String'
    elif change.startswith('wrong-format'):
        reference = next(row for row in getter if hasattr(row, 'method_spec'))
        if change == 'wrong-format-owner':
            reference.method_spec['owner'] = 'Authored.OtherFormatter'
        else:
            reference.method_spec['arguments'] = ('System.Int32',) * 5
    elif change == 'repeated-format-argument':
        next(row for row in getter if row.literal == '{0}{1}{2}{3}{4}').literal = '{0}{1}{2}{3}{3}'
    elif change == 'wrong-transform':
        fixture.methods['Fixture.PrivateTransform', 'ChangedName'][3].op_str = 'eax, edx'
    elif change == 'clobbered-fragment':
        getter.insert(7, move(register('r14'), immediate(7)))
    elif change == 'wrong-getstring':
        fixture.names['System.Text.Encoding', 'GetString'] = 0xdead
    else:
        getter.extend(copy.deepcopy(getter[7:17]))
    with pytest.raises((ValueError, AssertionError, KeyError)):
        derive(fixture, monkeypatch)


def encrypted_source(key, text='local authored = "synthetic source control"\nreturn authored'):
    # Reference encoder for owned test data only; no game ciphertext is stored.
    raw = text.encode()
    values = list(struct.unpack('<' + 'I' * ((len(raw) + 3) // 4), raw.ljust((len(raw) + 3) // 4 * 4, b'\0')))
    values.append(len(raw))
    keys, count, mask, delta = struct.unpack('<4I', key), len(values), 0xffffffff, 0x9e3779b9
    total, z = 0, values[-1]
    for _ in range(6 + 52 // count):
        total = (total + delta) & mask
        e = total >> 2 & 3
        for position in range(count):
            y = values[(position + 1) % count]
            mix = (((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^
                   ((total ^ y) + (keys[(position & 3) ^ e] ^ z))) & mask
            values[position] = (values[position] + mix) & mask
            z = values[position]
    return base64.b64encode(struct.pack('<' + 'I' * count, *values)), text


def test_complete_original_controls_activate_once_and_remain_available_offline(tmp_path):
    client, key, digest = identity(), b'owned-lua-key-01', 'a' * 64
    original, decoded = encrypted_source(key)
    controls = {hashlib.md5(original).hexdigest(): (original, decoded)}
    assert decode_lua(original, key) == decoded
    parameters.activate(tmp_path, client, key, digest, controls, recheck=lambda: client)
    assert parameters._active(tmp_path, client)[0] == key
    parameters.activate(tmp_path, client, key, digest, controls,
                        recheck=lambda: pytest.fail('An unchanged complete witness must work offline'))
    assert parameters.candidate(tmp_path, client) == key


@pytest.mark.parametrize('change', ['changed-key', 'bad-original-md5', 'invented-plaintext', 'changed-client'])
def test_failed_updates_keep_the_original_complete_key_witness(tmp_path, change):
    client, key = identity(), b'owned-lua-key-01'
    original, decoded = encrypted_source(key)
    file_hash = hashlib.md5(original).hexdigest()
    controls = {file_hash: (original, decoded)}
    parameters.activate(tmp_path, client, key, 'a' * 64, controls, recheck=lambda: client)
    path, changed = parameters._path(tmp_path, client), copy.deepcopy(client)
    accepted = path.read_bytes()
    changed['game_files_md5'] = 'c' * 32
    if change == 'changed-key':
        key = b'new-key-no-data!'
    elif change == 'bad-original-md5':
        controls = {'f' * 32: (original, decoded)}
    elif change == 'invented-plaintext':
        controls[file_hash] = original, 'local fabricated = "not this source"'
    with pytest.raises((ValueError, UnicodeError)):
        parameters.activate(tmp_path, client, key, 'b' * 64, controls,
                            recheck=lambda: changed if change == 'changed-client' else client)
    assert path.read_bytes() == accepted
    assert not parameters._path(tmp_path, changed).exists()


def test_generic_method_usage_reads_actual_owned_spec_and_type_arguments():
    from backend.endfield_client_metadata import Owners
    raw = bytearray(4096)
    registration = 256
    struct.pack_into('<2Q', raw, registration - 16, 1, 1536)
    struct.pack_into('<3i', raw, 1536, 0, -1, 0)
    struct.pack_into('<2Q', raw, registration - 64, 1, 1600)
    struct.pack_into('<Q', raw, 1600, 1640)
    struct.pack_into('<I', raw, 1640, 5)
    struct.pack_into('<Q', raw, 1648, 1700)
    for n in range(5):
        struct.pack_into('<Q', raw, 1700 + n * 8, 1800)
    raw[1810] = 0xe
    struct.pack_into('<Q', raw, 500, (6 << 29) | 1)
    reader = Owners.__new__(Owners)
    reader.registration = registration
    reader.image = SimpleNamespace(data_read=lambda at, size: bytes(raw[at:at + size]),
                                   q=lambda at: struct.unpack_from('<Q', raw, at)[0])
    reader.metadata = SimpleNamespace(methods=struct.pack('<6I4H', 0, 0, 0, 0, 0, 0x06000001, 0, 0, 0, 6),
                                     type_name=lambda _: 'Beyond.UnSafeString', string=lambda _: 'Format')
    reference = move(register('rax'), memory('rip', 499))
    assert reader.method_usage(reference) == {'owner': 'Beyond.UnSafeString', 'name': 'Format', 'parameters': 6,
                                              'arguments': ('System.String',) * 5}
    struct.pack_into('<i', raw, 1540, 0)  # A different generic class owner is unsupported.
    with pytest.raises(ValueError):
        reader.method_usage(reference)
    struct.pack_into('<i', raw, 1540, -1)
    struct.pack_into('<I', raw, 1640, 9)
    with pytest.raises(ValueError):
        reader.method_usage(reference)


def test_normal_modern_source_route_does_not_consult_a_community_lua_seed(tmp_path, monkeypatch):
    from backend import endfield_release as release, endfield_metadata, endfield_parameters as common
    client, key = identity(), b'owned-lua-key-01'
    original, decoded = encrypted_source(key)
    file = SimpleNamespace(content_hashes=('unused', hashlib.md5(original).hexdigest()))
    monkeypatch.setattr(release, 'descriptor', lambda *_: {'client': client})
    monkeypatch.setattr(parameters, 'candidate', lambda *_: key)
    monkeypatch.setattr(common, '_active', lambda *_: (None, {'validated_indices': {'17': 'a' * 64}}))
    monkeypatch.setattr(release, '_whole', lambda *_: original)
    monkeypatch.setattr(release, 'latest_client', lambda *_: ({}, client))
    monkeypatch.setattr(endfield_metadata, 'cache_root', lambda *_: pytest.fail('Modern Lua must use its original client'))
    assert parameters.scripts(tmp_path, 'authored-stamp', {'role': ('owned-base', file)}) == {'role': decoded}
    assert parameters._active(tmp_path, client)[0] == key
    monkeypatch.setattr(release, 'latest_client', lambda *_: pytest.fail('Existing identical source must work offline'))
    assert parameters.scripts(tmp_path, 'authored-stamp', {'role': ('owned-base', file)}) == {'role': decoded}
    monkeypatch.setattr(common, '_active', lambda *_: None)
    with pytest.raises(ValueError, match='index is not validated'):
        parameters.scripts(tmp_path, 'authored-stamp', {'role': ('owned-base', file)})


def test_legacy_descriptor_retains_its_original_lua_provenance(tmp_path, monkeypatch):
    from backend import endfield_release as release, endfield_metadata
    key = b'owned-lua-key-01'
    original, decoded = encrypted_source(key)
    file = SimpleNamespace(content_hashes=('unused', hashlib.md5(original).hexdigest()))
    (tmp_path / 'Keys.cs').write_text('XxteaKey = Encoding.UTF8.GetBytes("' + key.decode() + '")')
    monkeypatch.setattr(release, 'descriptor', lambda *_: {'version': 'old'})
    monkeypatch.setattr(endfield_metadata, 'cache_root', lambda *_: tmp_path)
    monkeypatch.setattr(release, '_whole', lambda *_: original)
    monkeypatch.setattr(parameters, 'candidate', lambda *_: pytest.fail('Old descriptor must not adopt a new native recipe'))
    assert parameters.scripts(tmp_path, 'old', {'role': ('owned-base', file)}) == {'role': decoded}
