"""Derive VFS candidates from authored owners, assignments and direct calls.

This is a bounded recognizer for the evidenced IL2CPP/x64 contract. It does not
interpret arbitrary instructions. Original index validation decides whether a
derived candidate may be activated. No current game key or label list is stored.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import struct

from .endfield_client_code import Code, calls, direct, literal_moves, reg
from .endfield_client_metadata import Owners
from .endfield_client_source import check

VFS = 'Beyond.VFS.VirtualFileSystem'
DEFINE = 'Beyond.VFS.VFSDefine'


@dataclass(frozen=True)
class Candidate:
    key: bytes
    directories: dict[int, str]
    protocol: int


def _stores(owners, rows, owner):
    """Only stores through that exact original class's static-field pointer."""
    result = {}
    for n, ins in enumerate(rows):
        if ins.mnemonic != 'mov' or len(ins.operands) != 2 or ins.operands[0].type != 3:
            continue
        memory = ins.operands[0].mem
        if memory.index:
            continue
        for at in range(max(0, n - 4), n):
            load = rows[at]
            if load.mnemonic != 'mov' or len(load.operands) != 2 or load.operands[0].type != 1 or load.operands[1].type != 3:
                continue
            if load.operands[0].reg != memory.base or load.operands[1].mem.disp != 0xb8:
                continue
            if any(row.operands and row.operands[0].type == 1 and row.operands[0].reg == memory.base and
                   row.mnemonic not in {'cmp', 'test'} for row in rows[at + 1:n]):
                continue
            class_register = load.operands[1].mem.base
            if any(prior.mnemonic == 'mov' and prior.operands[0].type == 1 and
                   prior.operands[0].reg == class_register and owners.is_owner_usage(prior, owner)
                   for prior in rows[max(0, at - 2):at]):
                check(memory.disp not in result, 'Duplicate original parameter assignment.')
                result[memory.disp] = (n, ins.operands[1])
                break
    return result


def _literal_before(owners, rows, at, destination, distance=8):
    values = [(n, value) for n, value in literal_moves(owners, rows[max(0, at - distance):at], destination)]
    check(len(values) == 1, 'Original caller literal is missing or ambiguous.')
    return values[0][1]['text']


def _immediate(rows, name):
    values = [row.operands[1].imm for row in rows if row.mnemonic == 'mov' and len(row.operands) == 2
              and reg(row, row.operands[0]) == name and row.operands[1].type == 2]
    check(len(values) == 1)
    return values[0]


def _fragments(owners, code):
    check(owners.field_type(VFS, 'CHACHA_KEY') == 'System.String' and
          owners.field_type(VFS, 'CHACHA_KEYS') == ('array', 'System.String'))
    rows = code.linear(owners.method(VFS, '.cctor', 0))
    stores = _stores(owners, rows, VFS)
    delimiter_at, delimiter_operand = stores[owners.field(VFS, 'CHACHA_KEY')['offset']]
    check(delimiter_operand.type == 1)
    delimiter = _literal_before(owners, rows, delimiter_at, rows[delimiter_at].reg_name(delimiter_operand.reg))
    array_at, array_operand = stores[owners.field(VFS, 'CHACHA_KEYS')['offset']]
    check(array_operand.type == 1)
    array_register = array_operand.reg
    entries, setters = {}, set()
    for at, pointer in calls(rows[:array_at]):
        window = rows[max(0, at - 5):at]
        arguments = [row for row in window if row.mnemonic == 'mov' and len(row.operands) == 2 and
                     reg(row, row.operands[0]) == 'rcx' and row.operands[1].type == 1]
        alias_window = rows[max(0, at - 10):at]
        aliases = [n for n, row in enumerate(alias_window) if row.mnemonic == 'mov' and
                   len(row.operands) == 2 and row.operands[0].type == 1 and
                   row.operands[0].reg == array_register and reg(row, row.operands[1]) == 'rax']
        returned_array = any(not any(row.mnemonic == 'call' for row in alias_window[n + 1:]) for n in aliases)
        if not any(row.operands[1].reg == array_register or
                   reg(row, row.operands[1]) == 'rax' and returned_array for row in arguments):
            continue
        values = literal_moves(owners, window, 'r8')
        if not values:
            continue
        check(len(values) == 1)
        indices = [0 for row in window if row.mnemonic == 'xor' and row.op_str == 'edx, edx']
        indices += [row.operands[1].imm for row in window if row.mnemonic == 'mov' and
                    reg(row, row.operands[0]) == 'edx' and row.operands[1].type == 2]
        check(len(indices) == 1 and 0 <= indices[0] < 128 and indices[0] not in entries)
        entries[indices[0]] = values[0][1]['text']
        setters.add(pointer)
    check(1 <= len(entries) <= 128 and set(entries) == set(range(len(entries))) and len(setters) == 1,
          'Incomplete original key-fragment array.')
    return delimiter, entries


def _selected_fragments(owners, rows):
    array_offset = owners.field(VFS, 'CHACHA_KEYS')['offset']
    selected = []
    for n, ins in enumerate(rows):
        if ins.mnemonic != 'mov' or len(ins.operands) != 2 or ins.operands[1].type != 3:
            continue
        memory = ins.operands[1].mem
        if memory.index or memory.disp < 0x20 or (memory.disp - 0x20) % 8:
            continue
        preceding = rows[max(0, n - 12):n]
        loads = [at for at, row in enumerate(preceding) if row.mnemonic == 'mov' and
                 len(row.operands) == 2 and row.operands[0].type == 1 and
                 row.operands[0].reg == memory.base and row.operands[1].type == 3 and
                 row.operands[1].mem.disp == array_offset]
        if not loads:
            continue
        at = loads[-1]
        if any(row.operands and row.operands[0].type == 1 and
               row.operands[0].reg == memory.base and row.mnemonic not in {'cmp', 'test'}
               for row in preceding[at + 1:]):
            continue
        # Bind the field access back to the same static VFS class.
        if any(owners.is_owner_usage(row, VFS) for row in preceding[max(0, at - 3):at]):
            selected.append((memory.disp - 0x20) // 8)
    check(1 <= len(selected) <= 128)
    return selected


def _key(owners, code):
    delimiter, fragments = _fragments(owners, code)
    rows = code.linear(owners.method(VFS, 'GetCommonChachaKeyBs', 1))
    selected = _selected_fragments(owners, rows)
    check(all(index in fragments for index in selected))
    candidates = []
    for at, target in calls(rows):
        window = rows[max(0, at - 12):at]
        values = literal_moves(owners, window, 'r8')
        if len(values) == 1 and not any(row.mnemonic == 'call' for row in window[values[0][0] + 1:]):
            candidates.append((target, values[0][1]['text']))
    check(len(candidates) == 1, 'Original common-key call contract is ambiguous.')
    pointer, mask = candidates[0]
    method = owners.method_at(pointer, 3)
    transform = code.linear(method)
    targets = {target for _, target in calls(transform)}
    check(owners.method('System.Convert', 'TryFromBase64Chars', 3)['pointer'] in targets and
          owners.method('System.Text.Encoding', 'get_UTF8', 0)['pointer'] in targets)
    # Recognize the original modulo/subtract-byte path, including its generic
    # mask-length division; a changed operation is unsupported, never guessed.
    operations = [(row.mnemonic, row.op_str) for row in transform]
    check(any(name == 'idiv' for name, _ in operations) and
          any(name == 'sub' and value == 'eax, ecx' for name, value in operations) and
          any(name == 'add' and value == 'eax, 0x100' for name, value in operations) and
          any(name == 'and' and value == 'eax, 0x800000ff' for name, value in operations),
          'The original key conversion contract changed.')
    mask_bytes = mask.encode('utf-8')
    check(0 < len(mask_bytes) <= 4096)
    encoded = ''.join(fragments[index] for index in selected) + delimiter
    decoded = base64.b64decode(encoded, validate=True)
    check(len(decoded) == 32)
    return bytes((value - mask_bytes[index % len(mask_bytes)]) & 255 for index, value in enumerate(decoded))


def _map(owners, code):
    check(owners.field_type(DEFINE, 's_vfsTypeNameMap') == (
        'generic', 'System.Collections.Generic.Dictionary`2', ('Beyond.VFS.EVFSBlockType', 'System.String')))
    check(all(owners.field_type(DEFINE, name) == 'System.Int32' for name in ('VFS_PROTO_VERSION', 'KEY_LEN')))
    rows = code.linear(owners.method(DEFINE, '.cctor', 0))
    stores = _stores(owners, rows, DEFINE)
    map_at, register = stores[owners.field(DEFINE, 's_vfsTypeNameMap')['offset']]
    check(register.type == 1)
    result, setters = {}, set()
    for at, pointer in calls(rows[:map_at]):
        window = rows[max(0, at - 5):at]
        if not any(row.mnemonic == 'mov' and len(row.operands) == 2 and
                   reg(row, row.operands[0]) == 'rcx' and row.operands[1].type == 1 and
                   row.operands[1].reg == register.reg for row in window):
            continue
        values = literal_moves(owners, window, 'r8')
        if not values:
            continue
        check(len(values) == 1)
        key = _immediate(window, 'dl')
        check(0 <= key <= 255 and key not in result)
        text = values[0][1]['text']
        check(0 < len(text.encode('utf-8')) <= 256 and '\0' not in text)
        result[key] = text
        setters.add(pointer)
    check(1 <= len(result) <= 256 and len(setters) == 1, 'Incomplete original VFS type map.')
    protocol = stores[owners.field(DEFINE, 'VFS_PROTO_VERSION')['offset']][1]
    key_length = stores[owners.field(DEFINE, 'KEY_LEN')['offset']][1]
    check(protocol.type == key_length.type == 2 and protocol.imm == 3 and key_length.imm == 32)
    return result, protocol.imm


def _hash_contract(owners, code):
    rows = code.linear(owners.method(DEFINE, 'GetVFSBlockHashDir', 1))
    wrapper = owners.called(rows, 'Beyond.Cryptor.Crc32Utils', 'XXHash64', 1)
    wrapper_rows = code.linear(wrapper)
    check(owners.method('System.Text.Encoding', 'get_UTF8', 0)['pointer'] in {p for _, p in calls(wrapper_rows)})
    owners.called(wrapper_rows, 'Unity.Collections.xxHash3', 'Hash64', 2)
    helper = owners.called(rows, DEFINE, 'GetVFSBlockHashFileName', 1)
    check(wrapper['pointer'] in {p for _, p in calls(rows)} and
          any(row.mnemonic == 'jmp' and direct(row) == helper['pointer'] for row in rows) and
          any(row.mnemonic == 'shr' and row.op_str == 'rcx, 0x20' for row in rows) and
          any(row.mnemonic == 'xor' and row.op_str == 'ecx, eax' for row in rows))
    rows = code.linear(helper)
    formatter = owners.called(rows, 'Beyond.Byte.ByteHelper', 'GetHexString', 3)
    check(formatter['pointer'] in {p for _, p in calls(rows)} and
          all(any(row.mnemonic == 'shr' and row.operands[1].type == 2 and row.operands[1].imm == shift
                  for row in rows) for shift in (8, 16, 24)))
    rows = code.linear(formatter)
    # The original loop emits high and low nibbles using 0x30 / 0x37. This is
    # stronger than treating a GetHexString method name as formatting evidence.
    constants = {operand.imm for row in rows for operand in row.operands if operand.type == 2}
    check({0x30, 0x37, 0xa, 0xf, 4} <= constants and
          any(row.mnemonic == 'cmovae' for row in rows) and
          any(row.mnemonic == 'mov' and row.operands[0].type == 3 and
              row.operands[0].size == 2 for row in rows))


def derive(metadata, image):
    owners, code = Owners(metadata, image), Code(image)
    key = _key(owners, code)
    labels, protocol = _map(owners, code)
    _hash_contract(owners, code)
    # A fixed software implementation; the hashes' INPUTS are always current
    # original strings. No directory IDs or game key bytes are distributed.
    from .endfield_xxhash import hash64
    directories = {}
    for block, text in labels.items():
        value = hash64(text.encode('utf-8'))
        directories[block] = struct.pack('<I', (value >> 32) ^ (value & 0xffffffff)).hex().upper()
    check(len(set(directories.values())) == len(directories), 'Original VFS directory collision.')
    return Candidate(key, directories, protocol)
