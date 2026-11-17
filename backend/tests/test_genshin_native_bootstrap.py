"""Authored PE/x64 fixtures; no original game bytes, keys or localized text."""
import hashlib
import json
from pathlib import Path
import platform
import struct
import sys
from types import SimpleNamespace

import pytest

from backend import genshin_native_x64 as native
from backend import genshin_native_metadata as metadata
from backend import genshin_native_expression as expression


WINDOWS_AMD64 = sys.platform == 'win32' and platform.machine().lower() in {'amd64', 'x86_64'}
requires_decoder = pytest.mark.skipif(not WINDOWS_AMD64, reason='Explicit Windows amd64 decoder closure')


def toy_image(*, duplicate=False, initializer=True):
    raw, base, pe = bytearray(0xe00), 0x180000000, 0x80
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, pe)
    raw[pe:pe + 4] = b'PE\0\0'
    struct.pack_into('<HH', raw, pe + 4, 0x8664, 3)
    struct.pack_into('<H', raw, pe + 20, 240)
    optional = pe + 24
    struct.pack_into('<H', raw, optional, 0x20b)
    struct.pack_into('<Q', raw, optional + 24, base)
    struct.pack_into('<I', raw, optional + 108, 16)
    struct.pack_into('<II', raw, optional + 136, 0x3000, 24 if duplicate else 12)
    sections = [(b'.text', 0x1000, 0x200, 0x200, 0x60000020),
                (b'.rdata', 0x2000, 0x400, 0x800, 0x40000040),
                (b'.pdata', 0x3000, 0xc00, 0x200, 0x40000040)]
    for ordinal, (name, rva, offset, size, flags) in enumerate(sections):
        at = optional + 240 + 40 * ordinal
        struct.pack_into('<8sIIII', raw, at, name, size, rva, size, offset)
        struct.pack_into('<I', raw, at + 36, flags)
    for ordinal in range(2 if duplicate else 1):
        rva, target = 0x1000 + 0x20 * ordinal, 0x2000 + 0x300 * ordinal
        raw[0x400 + 0x300 * ordinal:0x404 + 0x300 * ordinal] = b'MHY\0'
        code = (b'\x48\x8d\x05' + struct.pack('<i', target - rva - 7)
                + b'\x48\x89\x05' + struct.pack('<i', 0x2700 - rva - 14) + b'\xc3')
        if not initializer:
            code = b'\x90' * (len(code) - 1) + b'\xc3'
        raw[0x200 + 0x20 * ordinal:0x200 + 0x20 * ordinal + len(code)] = code
        struct.pack_into('<III', raw, 0xc00 + 12 * ordinal, rva, rva + len(code), 0x2708)
    return bytes(raw)


@pytest.mark.parametrize('change', ['truncated', 'wrong-machine', 'bad-section', 'bad-method'])
def test_original_pe_bounds_reject_incomplete_or_conflicting_input(change):
    raw = bytearray(toy_image())
    if change == 'truncated':
        raw = raw[:-1]
    elif change == 'wrong-machine':
        struct.pack_into('<H', raw, 0x84, 0x14c)
    elif change == 'bad-section':
        struct.pack_into('<I', raw, 0x98 + 240 + 40 + 12, 0x1000)
    else:
        struct.pack_into('<I', raw, 0xc04, 0x999999)
    with pytest.raises(ValueError):
        native.Image(bytes(raw))


def test_image_never_reads_unmapped_virtual_or_guessed_method_bytes():
    image = native.Image(toy_image())
    assert image.base == 0x180000000
    with pytest.raises(ValueError):
        image.offset(0x2800)
    with pytest.raises(ValueError):
        image.window(0x1001)


@requires_decoder
def test_header_owner_comes_from_native_reference_and_store_not_magic():
    image = native.Image(toy_image())
    # The file header differs from the native-owned header, as supported by the
    # original format. The embedded header is owned by its actual initializer.
    external = b'MHY\0' + b'\x39' * metadata.HEADER_SIZE
    owner = metadata.header_owner(image, external)
    assert owner.header_rva == 0x2000 and owner.global_rva == 0x2700
    assert owner.initializer_rva == 0x1000
    assert owner.initializer_sha256 == hashlib.sha256(image.window(0x1000)).hexdigest()
    with pytest.raises(ValueError):
        metadata.header_owner(native.Image(toy_image(initializer=False)), external)
    with pytest.raises(ValueError):
        metadata.header_owner(native.Image(toy_image(duplicate=True)), external)


@requires_decoder
@pytest.mark.parametrize('code,name,bits,expected,terminal', [
    ('bb1100000090c3', 'ebx', 32, 17, ()),
    ('bb2100000090c3', 'ebx', 32, 33, ()),
    ('85c97407bb11000000eb05bb2200000090c3', 'ebx', 32, None, ()),
    ('85c97407bb11000000eb05e8f00f000090c3', 'ebx', 32, 17, (0x2000,)),
    ('ba11000000e8f60f000090c3', 'edx', 32, None, ()),
    ('bb11000000e8f60f000090c3', 'ebx', 32, 17, ()),
    ('ba11223344b25590c3', 'edx', 32, 0x44332255, ()),
    ('b25590c3', 'dl', 8, 0x55, ()),
    ('b25590c3', 'edx', 32, None, ()),
    ('b844332211b45590c3', 'eax', 32, 0x11225544, ()),
    ('c744243011000000e8f30f00008b54243090c3', 'edx', 32, None, ()),
    ('bb1100000083c30185c975f990c3', 'ebx', 32, None, ()),
    ('bb1100000085c975fc90c3', 'ebx', 32, 17, ()),
    ('ba11000000f7e190c3', 'edx', 32, None, ()),
])
def test_changed_operands_ambiguity_calls_partial_registers_and_loops(code, name, bits, expected, terminal):
    instructions = list(native.decoder().disasm(bytes.fromhex(code), 0x1000))
    point = next(ins.address for ins in instructions if ins.mnemonic == 'nop')
    analysis = native.Constants(instructions, terminal)
    if expected is None:
        with pytest.raises(ValueError):
            analysis.value_before(point, name, bits)
    else:
        assert analysis.value_before(point, name, bits) == expected


@requires_decoder
def test_merged_native_definition_paths_remain_explicit():
    instructions = list(native.decoder().disasm(bytes.fromhex('85c97407bb11000000eb05bb2200000090c3'), 0x1000))
    point = next(ins.address for ins in instructions if ins.mnemonic == 'nop')
    assert len(native.Definitions(instructions).before(point, 'ebx')) == 2
    with pytest.raises(ValueError):
        native.Constants([])


def test_host_boundary_and_tampered_decoder_reject_before_library_import(tmp_path, monkeypatch):
    native.decoder.cache_clear()
    monkeypatch.setattr(native.platform, 'machine', lambda: 'arm64')
    with pytest.raises(ValueError, match='Windows amd64'):
        native.decoder()
    monkeypatch.setattr(native.sys, 'platform', 'win32')
    monkeypatch.setattr(native.platform, 'machine', lambda: 'AMD64')
    monkeypatch.delenv('LIBCAPSTONE_PATH', raising=False)
    package = tmp_path / 'capstone'
    (package / 'lib').mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'lib/capstone.dll').write_bytes(b'authored invalid decoder')
    distribution = SimpleNamespace(version='5.0.7', locate_file=lambda name: tmp_path / name)
    monkeypatch.setattr(native.importlib.metadata, 'distribution', lambda name: distribution)
    monkeypatch.setattr(native.importlib.util, 'find_spec', lambda name: SimpleNamespace(origin=package / '__init__.py'))
    monkeypatch.setattr(native.importlib, 'import_module', lambda name: pytest.fail('Unverified native library imported'))
    with pytest.raises(ValueError, match='decoder or its complete notice differs'):
        native.decoder()
    native.decoder.cache_clear()


def test_decoder_closure_contains_full_notice_and_exact_native_dependency():
    root = Path(__file__).resolve().parents[2]
    receipt = json.loads((root / 'packaging/native-codecs/genshin-capstone-5.0.7-windows-amd64.json').read_text())
    assert receipt['host'] == 'windows-amd64' and receipt['version'] == native.DECODER_VERSION
    assert receipt['all_wheel_members_sha256'][receipt['native_member']] == native.DECODER_DLL_SHA256
    notice = (root / receipt['retained_license']).read_bytes()
    assert hashlib.sha256(notice).hexdigest() == native.DECODER_NOTICE_SHA256
    assert b'Redistribution and use in source and binary forms' in notice


@requires_decoder
def test_native_table_address_has_exact_owned_stride_and_field():
    instructions = list(native.decoder().disasm(bytes.fromhex('488d14498b4cd00483f133'), 0x1000))
    registers, fields = expression.extract(instructions, 'rax', 24, {4: 4}, image_base=0x1000, index_limit=1000)
    assert fields == [{'read_rva': 4, 'index_register': 'rcx', 'field_offset': 4,
                      'field_width_bytes': 4, 'stride': 24}]
    assert expression.evaluate(registers['rcx'], {'rcx': 12}, {4: 17}) == 34
    with pytest.raises(ValueError):
        expression.extract(instructions, 'rax', 26, {4: 4}, image_base=0x1000, index_limit=1000)
    with pytest.raises(ValueError):
        expression.extract(instructions, 'rax', 24, {8: 4}, image_base=0x1000, index_limit=1000)


@requires_decoder
@pytest.mark.parametrize('code', ['480fafc98b4cc804', '8bd08b4c8a04'])
def test_nonlinear_or_truncated_table_pointers_cannot_be_sample_fitted(code):
    instructions = list(native.decoder().disasm(bytes.fromhex(code), 0x1000))
    with pytest.raises(ValueError):
        expression.extract(instructions, 'rax', 8, {4: 4}, image_base=0x1000, index_limit=1000)


def test_unsupported_expression_and_wrapping_index_are_rejected():
    with pytest.raises(ValueError):
        expression.evaluate(('unknown', 32, ('constant', 17)), {})
    with pytest.raises(ValueError, match='index can wrap'):
        expression._affine(('cast', 32, ('imul', 64, ('input', 'index'), ('constant', 1 << 30))), 10)


@requires_decoder
@pytest.mark.parametrize('code,expected', [
    ('488b05000000004889c28b8a88000000c3', True),
    ('488b05000000004889c2e8000000008b8a88000000c3', False),
    ('488b05000000004889c285c974034831d28b8a88000000c3', False),
])
def test_header_pointer_requires_every_reaching_definition(code, expected):
    seq = list(native.decoder().disasm(bytes.fromhex(code), 0x1000))
    read = next(i for i in seq if i.mnemonic == 'mov' and i.operands[1].type == native.CS_OP_MEM
                and i.operands[1].mem.disp == 0x88)
    assert metadata.owns_global_pointer(SimpleNamespace(base=0x1000), seq, read,
                                       read.operands[1].mem, 7) is expected


def test_complete_usage_boundary_and_strict_literal_text():
    from backend.genshin_native_usage import Usages
    from backend.genshin_native_literals import Literals
    header = bytes(metadata.HEADER_SIZE)
    # Two authored usage lists, including the last list and its sentinel.
    body = struct.pack('<III', 0, 1, 2) + struct.pack('<IIII', 5 << 29, 9, (5 << 29) | 1, 10)
    table_at = len(body)
    raw = [b'An authored path', b'\xff']
    body += struct.pack('<III', 0, len(raw[0]), sum(map(len, raw)))
    data_at = len(body)
    encoded = bytearray()
    for index, value in enumerate(raw):
        key = index + 17
        for pos in range(0, len(value), 8):
            block = value[pos:pos + 8]
            encoded.extend((int.from_bytes(block.ljust(8, b'\0'), 'little') ^ key).to_bytes(8, 'little')[:len(block)])
            key += 31
    view = SimpleNamespace(metadata=header + body + encoded)
    profile = {'count': {'count': 2}, 'list_header': {'body_offset': 0},
               'pair_header': {'body_offset': 12}, 'first': ('field', 0), 'next': ('field', 4),
               'pair_index': 'index', 'source': ('field', 0), 'slot': ('field', 4)}
    usages = Usages(view, profile)
    assert usages.entries(1) == ((5, 1, 10),)
    literal_profile = {'table': {'body_offset': table_at}, 'data': {'body_offset': data_at},
                       'table_expression': ('field', 0),
                       'seed': {'expression': ('add', 64, ('input', 'index'), ('constant', 17)), 'step': 31}}
    literals = Literals(view, usages, literal_profile)
    assert literals.text(0) == raw[0].decode()
    assert literals.invalid_utf8 == (1,)
    with pytest.raises(ValueError, match='strict UTF-8'):
        literals.text(1)
    with pytest.raises(ValueError):
        Literals(SimpleNamespace(metadata=view.metadata[:-1]), usages, literal_profile)
    with pytest.raises(ValueError):
        Literals(view, SimpleNamespace(pairs=((5, 0, 9), (5, 2, 10))), literal_profile)
    with pytest.raises(ValueError):
        Usages(SimpleNamespace(metadata=header + struct.pack('<III', 0, 2, 1) + body[12:]), profile)
    with pytest.raises(ValueError):
        Usages(SimpleNamespace(metadata=header + body[:20]), profile)


@requires_decoder
def test_only_explicit_bounded_dispatch_edges_reach_native_cases():
    seq = list(native.decoder().disasm(bytes.fromhex('bb11000000ffe090c3'), 0x1000))
    jump = next(i for i in seq if i.mnemonic == 'jmp')
    point = next(i.address for i in seq if i.mnemonic == 'nop')
    with pytest.raises(ValueError, match='unreachable'):
        native.Constants(seq).value_before(point, 'ebx', 32)
    supplied = {jump.address: (point,)}
    assert native.Constants(seq, jump_targets=supplied).value_before(point, 'ebx', 32) == 17
    assert native.Definitions(seq, jump_targets=supplied).before(point, 'ebx') == frozenset({0x1000})
    with pytest.raises(ValueError, match='jump-table edges'):
        native.Constants(seq, jump_targets={jump.address: (point + 999,)})
    with pytest.raises(ValueError, match='jump-table edges'):
        native.Constants(seq, jump_targets={0x1000: (point,)})


@requires_decoder
@pytest.mark.parametrize('code,bits,mode,offset,expected', [
    ('8b54082083c211895610c3', 32, 'scalar', 7, (('add', 17),)),
    ('8b54082083c221895610c3', 32, 'scalar', 7, (('add', 33),)),
    ('0fb75408206683c2116685d27400c3', 16, 'length', None, (('add', 17),)),
    ('8b54082085ff740583c211eb0383c222895610c3', 32, 'scalar', 15, None),
])
def test_native_stream_word_follows_changed_operands_and_rejects_conflicting_paths(code, bits, mode, offset, expected):
    from backend.genshin_native_words import Context
    raw = bytes.fromhex(code)
    seq = list(native.decoder().disasm(raw, 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    context = Context(image, 0)
    if expected is None:
        with pytest.raises(ValueError, match='missing or ambiguous'):
            context.operations(0, bits, mode, offset)
    else:
        assert context.operations(0, bits, mode, offset) == expected


@requires_decoder
@pytest.mark.parametrize('operand', [17, 33])
def test_owned_dictionary_call_argument_follows_current_word_operations(operand):
    from backend.genshin_native_words import Context
    raw = bytes.fromhex('488b5408204883c2') + bytes([operand]) + bytes.fromhex('e800000000c3')
    seq = list(native.decoder().disasm(raw, 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq, window=lambda rva: raw)
    context = Context(image, 0)
    assert context.operations(0, 64, 'argument', 9, argument='rdx') == (('add', operand),)
    with pytest.raises(ValueError):
        context.operations(0, 64, 'argument', 9, argument='r8')
    with pytest.raises(ValueError):
        context.operations(0, 64, 'argument', 14, argument='rdx')
    with pytest.raises(ValueError):
        context.operations(0, 64, 'argument', 9)


@requires_decoder
@pytest.mark.parametrize('key', [17, 33])
def test_original_UInt64_scalar_preserves_high_bits_and_post_store_arithmetic(key):
    from backend.genshin_native_contracts import Contracts
    from backend.genshin_original_dialogue import decode_original
    raw = bytes.fromhex('4889ce0fb65c0820f6c301740e488b5408204889561048837610') + bytes([key]) + b'\xc3'
    seq = list(native.decoder().disasm(raw, 0x1000))
    fields = [{'name': '_identity', 'authored_offset_word': 16, 'type': {'kind': 11}}]
    view = SimpleNamespace(image=SimpleNamespace(base=0x1000, instructions=lambda rva: seq),
                           field_offsets=lambda definition: fields)
    contract = Contracts(view, 1).record(0, 0)
    assert decode_original(b'\x01' + struct.pack('<Q', 0x12345678abcdef01), contract) == {'identity': 0x12345678abcdef01 ^ key}
    partial = bytes.fromhex('4889ce0fb65c0820f6c301740d488b54082048895610837610') + bytes([key]) + b'\xc3'
    seq[:] = native.decoder().disasm(partial, 0x1000)
    with pytest.raises(ValueError, match='partial post-store'):
        Contracts(view, 1).record(0, 0)


@requires_decoder
def test_only_actual_owned_typed_tail_reader_can_own_array_field():
    from backend.genshin_native_fields import ordered_fields
    from backend.genshin_native_words import Context
    prefix = bytes.fromhex('4889ce4889d70fb65c0820f6c301740c488d56104889f9')
    target = 0x200
    raw = prefix + b'\xe9' + struct.pack('<i', target - len(prefix) - 5) + b'\xc3'
    seq = list(native.decoder().disasm(raw, 0x1000))
    context = Context(SimpleNamespace(base=0x1000, instructions=lambda rva: seq), 0)
    fields = [{'name': '_children', 'authored_offset_word': 16, 'type': {'kind': 29}}]
    _, rows = ordered_fields(context, fields, {target})
    assert len(rows) == 1 and rows[0]['offset'] == 16
    with pytest.raises(ValueError, match='no owned field input'):
        ordered_fields(context, fields)


@requires_decoder
@pytest.mark.parametrize('constant', [16, 17, 33])
def test_presence_flags_follow_constant_xor_with_header_in_other_register(constant):
    from backend.genshin_native_contracts import Contracts
    from backend.genshin_original_dialogue import decode_original
    raw = (bytes.fromhex('4889ce488b5c0820ba') + struct.pack('<I', constant)
           + bytes.fromhex('4831daf6c20174078b540820895610c3'))
    seq = list(native.decoder().disasm(raw, 0x1000))
    fields = [{'name': '_id', 'authored_offset_word': 16, 'type': {'kind': 9}}]
    view = SimpleNamespace(image=SimpleNamespace(base=0x1000, instructions=lambda rva: seq),
                           field_offsets=lambda definition: fields)
    contract = Contracts(view, 1).record(0, 0)
    flag = 1 ^ (constant & 1)
    assert decode_original(struct.pack('<QI', flag, 55), contract) == {'id': 55}
    assert decode_original(struct.pack('<Q', flag ^ 1), contract) == {'id': 0}


@requires_decoder
@pytest.mark.parametrize('branch,header', [('74', 3), ('75', 0)])
def test_native_contract_uses_authored_order_and_presence_polarity(branch, header):
    from backend.genshin_native_contracts import Contracts
    from backend.genshin_original_dialogue import decode_original
    raw = bytes.fromhex('4889ce0fb65c0820f6c301' + branch + '078b540820895614f6c302' + branch + '078b540820895610c3')
    seq = list(native.decoder().disasm(raw, 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    fields = [{'name': '_id', 'authored_offset_word': 0x10, 'type': {'kind': 9}},
              {'name': '_other', 'authored_offset_word': 0x14, 'type': {'kind': 9}}]
    view = SimpleNamespace(image=image, field_offsets=lambda definition: fields)
    contract = Contracts(view, 1).record(0, 0)
    payload = bytes([header]) + struct.pack('<II', 17, 33)
    assert decode_original(payload, contract) == {'other': 17, 'id': 33}
    with pytest.raises(ValueError):
        decode_original(payload[:-1], contract)
    with pytest.raises(ValueError):
        decode_original(payload + b'\0', contract)


@requires_decoder
def test_word_length_can_use_the_original_read_instruction_flags():
    from backend.genshin_native_words import Context
    seq = list(native.decoder().disasm(bytes.fromhex('66bf110066037c0820890e7400c3'), 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    assert Context(image, 0).operations(4, 16, 'length') == (('add', 17),)


@requires_decoder
@pytest.mark.parametrize('amount,words,expected', [(4, [17, 33], {'other': 17, 'id': 33}),
                                                  (5, [33], {'other': 0, 'id': 33})])
def test_raw_header_alias_survives_changed_native_decode_parameters(amount, words, expected):
    from backend.genshin_native_contracts import Contracts
    from backend.genshin_original_dialogue import decode_original
    raw = bytes.fromhex('4889ce0fb65c082089df80c3') + bytes([amount]) + bytes.fromhex('f6c30174078b540820895614f7c70200000074078b540820895610c3')
    seq = list(native.decoder().disasm(raw, 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    fields = [{'name': '_id', 'authored_offset_word': 0x10, 'type': {'kind': 9}},
              {'name': '_other', 'authored_offset_word': 0x14, 'type': {'kind': 9}}]
    view = SimpleNamespace(image=image, field_offsets=lambda definition: fields)
    contract = Contracts(view, 1).record(0, 0)
    assert contract.flags.operations == (('add', amount),)
    assert contract.fields[1].raw_flag
    payload = b'\3' + struct.pack('<' + 'I' * len(words), *words)
    assert decode_original(payload, contract) == expected


@requires_decoder
def test_authored_scalar_includes_native_in_place_transformation_after_first_store():
    from backend.genshin_native_contracts import Contracts
    from backend.genshin_original_dialogue import decode_original
    raw = bytes.fromhex('4889ce0fb65c0820f6c301740e8b54082089561081761033000000c3')
    seq = list(native.decoder().disasm(raw, 0x1000))
    image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq)
    view = SimpleNamespace(image=image, field_offsets=lambda definition: [
        {'name': '_id', 'authored_offset_word': 0x10, 'type': {'kind': 9}}])
    contract = Contracts(view, 1).record(0, 0)
    assert decode_original(b'\1' + struct.pack('<I', 17), contract) == {'id': 34}


@requires_decoder
@pytest.mark.parametrize('second_offset,valid', [(0x188, True), (0x190, False)])
def test_semantic_field_aliases_accept_only_agreeing_branch_sources(second_offset, valid):
    from backend.genshin_native_words import Context
    from backend.genshin_native_voice import _field_load
    base, global_address = 0x1000, 0x4000
    raw = bytes.fromhex('488b05') + struct.pack('<i', global_address - (base + 7))
    raw += bytes.fromhex('85c97409488bb888010000eb07')
    raw += bytes.fromhex('488bb8') + struct.pack('<I', second_offset)
    raw += bytes.fromhex('4889f990c3')
    seq = list(native.decoder().disasm(raw, base))
    context = Context(SimpleNamespace(base=base, instructions=lambda rva: seq), 0)
    point = next(i.address for i in seq if i.mnemonic == 'nop')
    if valid:
        assert _field_load(context, native.Definitions(seq), point, 'rcx', 8).operands[1].mem.disp == 0x188
    else:
        with pytest.raises(ValueError, match='authored source'):
            _field_load(context, native.Definitions(seq), point, 'rcx', 8)


@requires_decoder
def test_native_event_input_is_preserved_through_only_abi_safe_registers():
    from backend.genshin_native_words import Context
    from backend.genshin_native_voice import _value_origin
    for code, valid in [('448be1e8001000004489e090c3', True), ('8bd1e8001000008bc290c3', False)]:
        seq = list(native.decoder().disasm(bytes.fromhex(code), 0x1000))
        image = SimpleNamespace(base=0x1000, instructions=lambda rva: seq,
                                window=lambda rva: (_ for _ in ()).throw(ValueError('No owned callee')))
        context = Context(image, 0)
        point = next(i.address for i in seq if i.mnemonic == 'nop')
        if valid:
            assert _value_origin(context, native.Definitions(seq), point, 'rax') == ('input', 'rcx')
        else:
            with pytest.raises(ValueError):
                _value_origin(context, native.Definitions(seq), point, 'rax')
