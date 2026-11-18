"""Authored BLB3 representations, checked against the pinned managed helper.

All parameter bytes are generated here; no game keys/assets are test inputs.
The independent encoder uses inverse permutations and field matrix operations.
Committed whole-file hashes freeze its representations and the C# output; this
prevents a simultaneous encoder/decoder mistake from quietly redefining them.
Set TOOLKIT_GI_BLB_ORACLE_LAYOUT to an existing closed resource layout to rerun
the differential oracle. It must pass the ordinary full prebuilt-reader gate;
tests never build/download a helper or consult an installed game.
"""
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from backend import genshin_blb_portable as portable


def multiply(a, b):
    value = 0
    for _ in range(8):
        if b & 1:
            value ^= a
        a = ((a << 1) ^ (0x11b if a & 128 else 0)) & 255
        b >>= 1
    return value


def parameters(variant=0):
    exp, log = bytearray(256), bytearray(256)
    value = 1
    for i in range(255):
        exp[i] = value; log[value] = i; value = multiply(value, 3)
    exp[255] = 1
    return {'GF256Exp': bytes(exp), 'GF256Log': bytes(log),
        'Blb3AESSBox': bytes(i ^ ((i * (5 + 2 * variant) + 17) & 255) for i in range(256)),
        'Blb3AESShift': bytes((i * 5 + variant) % 16 for i in range(16)),
        'Blb3RC4Key': bytes((i * (7 + 2 * variant) + 11) & 255 for i in range(256)),
        'Blb3SBox': bytes((i * (3 + 2 * bank) + bank * 19 + variant) & 255
                         for bank in range(4) for i in range(256)),
        'Blb3ShiftRow': bytes((i * 5 + row * 3 + variant) % 16 + row * 16
                              for row in range(3) for i in range(16)),
        'Blb3Key': bytes((i * 27 + variant * 13) & 255 for i in range(8)),
        'Blb3Mul': bytes(i + 2 + variant for i in range(8))}


def parameter_json(p):
    return json.dumps({name: base64.b64encode(raw).decode() for name, raw in p.items()}).encode()


def inverse_permutation(values):
    assert len(set(values)) == len(values)
    return [values.index(i) for i in range(len(values))]


def roundkeys(p, key):
    # Word recurrence, rather than the port's offset-by-offset implementation.
    old = [key[i] for i in p['Blb3AESShift']]
    result = [old]
    power = 1
    for _ in range(10):
        new = []
        for word, subindex in enumerate((7, 11, 15, 3)):
            first = old[4 * word] ^ old[subindex] ^ p['Blb3AESSBox'][old[subindex]]
            if word == 0:
                first ^= power
            new.append(first)
            for offset in range(1, 4):
                new.append(new[-1] ^ old[4 * word + offset])
        result.append(new); old = new; power = multiply(power, 2)
    return result


def unencrypt(raw, p, key):
    state = list(raw)
    keys = roundkeys(p, key)
    inverse_sub = inverse_permutation([i ^ p['Blb3AESSBox'][i] for i in range(256)])
    inverse_shift = inverse_permutation([0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11])
    matrix = ((14, 11, 13, 9), (9, 14, 11, 13), (13, 9, 14, 11), (11, 13, 9, 14))
    for number in range(10, -1, -1):
        state = [value ^ keys[number][(i % 4) * 4 + i // 4] for i, value in enumerate(state)]
        if number == 0:
            break
        if number != 10:
            state = [multiply(row[0], state[off]) ^ multiply(row[1], state[off + 1])
                     ^ multiply(row[2], state[off + 2]) ^ multiply(row[3], state[off + 3])
                     for off in range(0, 16, 4) for row in matrix]
        state = [inverse_sub[state[i]] for i in inverse_shift]
    return bytes(state)


def encode_prefix(raw, p, key, stats):
    if len(raw) < 16:
        stats['short'] += 1
        return bytes(value ^ key[i] for i, value in enumerate(raw))
    if len(raw) == 16:
        stats['exact16'] += 1
    state = bytearray(raw)
    for row in range(3):
        previous = bytearray(16)
        for j in range(16):
            box = list(p['Blb3SBox'][(j % 4) * 256:(j % 4 + 1) * 256])
            product = box.index(state[j] ^ p['Blb3Key'][j % 8])
            source = next(x for x in range(256) if multiply(x, p['Blb3Mul'][j % 8]) == product)
            stats['gf_zero' if source == 0 else 'gf_nonzero'] += 1
            previous[p['Blb3ShiftRow'][row * 16 + j] % 16] = source
        state[:16] = previous
    # Undo tail with its immutable seed bytes; arithmetic wraps in byte space.
    s = list(p['Blb3RC4Key']); j = 0
    for i in range(256):
        j = (j + s[i] + state[i % 8]) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    for at in range(16, len(state)):
        i = (i + 1) % 256; j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        value = s[(s[i] + s[j]) % 256]
        mode = state[i % 8 + 8] % 3
        stats['mode' + str(mode)] += 1
        original = state[at]
        if mode == 0:
            state[at] ^= value
        elif mode == 1:
            stats['subtract_wrap'] += original + value > 255
            state[at] = (original + value) % 256
        else:
            stats['add_wrap'] += original - value < 0
            state[at] = (original - value) % 256
    state[:16] = unencrypt(state[:16], p, key)
    for i in range(16):
        state[i] ^= key[i]
    return bytes(state)


def representation(variant=0, *, lengths=(1, 15, 16, 17, 127, 128, 129, 256, 65539), mutate=None):
    p = parameters(variant)
    key = bytes((i * 13 + variant * 7) % 256 for i in range(16))
    size = max(192, 64 + 4 * len(lengths))
    header = bytearray((i * 29 + 3) % 256 for i in range(size))
    total = 28 + size + sum(lengths)
    struct.pack_into('<i', header, 0, total)
    struct.pack_into('<ii', header, 24, len(lengths), 1)
    struct.pack_into('<q', header, 32, 24)
    end = 0
    for i, length in enumerate(lengths):
        end += length; struct.pack_into('<i', header, 56 + i * 4, end)
    if mutate:
        mutate(header)
    prefix = b'Blb\x03' + struct.pack('<i', size) + bytes(4) + key
    plain = [bytes((i * 23 + n * 31 + variant) % 256 for i in range(length))
             for n, length in enumerate(lengths)]
    stats = Counter()
    def encode(raw):
        return encode_prefix(raw[:128], p, key, stats) + raw[128:]
    return prefix + encode(header) + b''.join(map(encode, plain)), prefix + header + b''.join(plain), p, stats


# Filled only from whole decoded output accepted by the existing verified C# helper.
GOLDEN = {
    0: ('8a05fc5b403053c25194b4c1bbe306279a8d9c03d380a3a61a4ea5943df96fa8',
        'f482d532b3f60cd4a019b212ef607e8cad16d85a5ff5fc5ca71658a5711b28fa'),
    1: ('e8f2b39f4807c60186ed3e7519870c516dc58a94d7dff2f52c303110f5804823',
        'f41eab055647c1398696e8edc1670e165dc665b17fda8b5551cb579562a84f55'),
}


@pytest.mark.parametrize('variant', [0, 1])
def test_authored_representation_and_managed_golden_parity(tmp_path, variant):
    raw, expected, p, stats = representation(variant)
    assert hashlib.sha256(raw).hexdigest() == GOLDEN[variant][0]
    assert hashlib.sha256(expected).hexdigest() == GOLDEN[variant][1]
    source, params, target = (tmp_path / name for name in ('source', 'parameters', 'target'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    portable.decode_file(source, params, target)
    assert target.read_bytes() == expected
    assert stats['short'] == 2 and stats['exact16'] == 1
    assert all(stats[name] > 0 for name in ('mode0', 'mode1', 'mode2', 'subtract_wrap', 'add_wrap', 'gf_zero', 'gf_nonzero'))


def test_optional_verified_managed_differential_oracle(tmp_path):
    root = os.environ.get('TOOLKIT_GI_BLB_ORACLE_LAYOUT')
    if root is None:
        pytest.skip('No explicit existing verified managed oracle layout supplied.')
    from backend.prebuilt_readers import prebuilt_reader
    from backend.genshin_blb import Helper
    root = Path(root)
    manifest = json.loads((root / 'helpers/genshin/helper-manifest.json').read_bytes())
    resources = {p.relative_to(root).as_posix(): {} for p in (root / 'helpers/genshin').rglob('*') if p.is_file()}
    layout = SimpleNamespace(mode='bundle', resource_root=root, resources=resources,
        source_commit=manifest['source_commit'], resource=lambda name: root / name)
    reader = prebuilt_reader('genshin', layout=layout)
    helper = Helper((str(reader.executable),), reader.source_identity)
    for variant in (0, 1):
        raw, expected, p, _ = representation(variant)
        source, params, decoded = (tmp_path / (name + str(variant)) for name in ('source', 'params', 'managed'))
        source.write_bytes(raw); params.write_bytes(parameter_json(p))
        helper.decode(source, params, decoded, work=tmp_path)
        assert decoded.read_bytes() == expected
        assert hashlib.sha256(decoded.read_bytes()).hexdigest() == GOLDEN[variant][1]


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'extra', 'bad-base64', 'wrong-size', 'bad-shift', 'null', 'too-large'])
def test_parameter_contract_is_closed_and_bounded(change):
    raw = parameter_json(parameters())
    rows = json.loads(raw)
    if change == 'duplicate': raw = raw[:-1] + b',"GF256Exp":"AA=="}'
    elif change == 'missing': rows.pop('Blb3Key')
    elif change == 'extra': rows['code'] = 'execute()'
    elif change == 'bad-base64': rows['Blb3Key'] = '***'
    elif change == 'wrong-size': rows['Blb3Key'] = 'AA=='
    elif change == 'bad-shift': rows['Blb3AESShift'] = base64.b64encode(bytes([255]) * 16).decode()
    elif change == 'null': rows['Blb3Mul'] = None
    else: raw = b' ' * (32 * 1024 + 1)
    if change not in ('duplicate', 'too-large'):
        raw = json.dumps(rows).encode()
    with pytest.raises(ValueError):
        portable.parse_parameters(raw)


@pytest.mark.parametrize('change', ['total', 'zero-count', 'large-count', 'negative-count', 'negative-table',
    'huge-table', 'early-table', 'table-overflow', 'zero-end', 'negative-end', 'descending-end', 'end-overflow', 'end-short'])
def test_corrupt_decoded_framing_is_rejected_before_creating_output(tmp_path, change):
    def mutate(head):
        field = {'total': (0, '<i', 999), 'zero-count': (24, '<i', 0), 'large-count': (24, '<i', 8193),
            'negative-count': (24, '<i', -1), 'negative-table': (32, '<q', -33),
            'huge-table': (32, '<q', 2**63 - 1), 'early-table': (32, '<q', 23),
            'table-overflow': (32, '<q', len(head) - 32), 'zero-end': (56, '<i', 0),
            'negative-end': (56, '<i', -1), 'descending-end': (60, '<i', 1),
            'end-overflow': (56, '<i', 2**31 - 1), 'end-short': (88, '<i', 66227)}[change]
        struct.pack_into(field[1], head, field[0], field[2])
    raw, _, p, _ = representation(mutate=mutate)
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    with pytest.raises(ValueError):
        portable.decode_file(source, params, output)
    assert not output.exists()


@pytest.mark.parametrize('change', ['magic', 'small-header', 'huge-header', 'negative-header', 'truncated', 'trailing'])
def test_raw_container_bounds_and_eof_are_exact(tmp_path, change):
    raw, _, p, _ = representation()
    raw = bytearray(raw)
    if change == 'magic': raw[0] = 0
    elif change == 'small-header': struct.pack_into('<i', raw, 4, 55)
    elif change == 'huge-header': struct.pack_into('<i', raw, 4, 1024**2 + 1)
    elif change == 'negative-header': struct.pack_into('<i', raw, 4, -1)
    elif change == 'truncated': raw = raw[:-1]
    else: raw += b'x'
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    with pytest.raises(ValueError):
        portable.decode_file(source, params, output)
    assert not output.exists()


def test_existing_output_work_budget_and_cancellation_retain_prior_files(tmp_path):
    raw, _, p, _ = representation()
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    output.write_bytes(b'previous')
    with pytest.raises(ValueError): portable.decode_file(source, params, output)
    assert output.read_bytes() == b'previous'
    output.unlink()
    for budget in (0, True, 9, 8194):
        with pytest.raises(ValueError): portable.decode_file(source, params, output, transform_budget=budget)
        assert not output.exists()
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 5: raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        portable.decode_file(source, params, output, check_cancel=cancel)
    assert not output.exists()
    assert source.read_bytes() == raw
    with pytest.raises(ValueError): portable.decode_file(source, params, source)
    assert source.read_bytes() == raw


def test_streaming_copy_preserves_long_block_suffix_and_limits_work(tmp_path):
    raw, expected, p, _ = representation(lengths=(256 * 1024 + 3,))
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
    portable.decode_file(source, params, output, transform_budget=2, check_cancel=cancel)
    assert output.read_bytes() == expected
    assert calls == 7  # header, block, four bounded suffix reads, completion


def test_maximum_block_inventory_and_exact_transform_budget(tmp_path):
    raw, expected, p, _ = representation(lengths=(1,) * 8192)
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    portable.decode_file(source, params, output, transform_budget=8193)
    assert output.read_bytes() == expected


def test_minimum_and_maximum_package_limits_precede_header_work(tmp_path, monkeypatch):
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    params.write_bytes(parameter_json(parameters()))
    source.write_bytes(bytes(83))
    with pytest.raises(ValueError): portable.decode_file(source, params, output)
    raw, _, _, _ = representation()
    source.write_bytes(raw)
    monkeypatch.setattr(portable, 'MAX_PACKAGE', len(raw) - 1)
    with pytest.raises(ValueError): portable.decode_file(source, params, output)
    assert not output.exists()


def test_read_budget_and_midstream_failure_remove_only_new_partial_output(tmp_path, monkeypatch):
    raw, _, p, _ = representation(lengths=(256 * 1024 + 3,))
    source, params, output = (tmp_path / n for n in ('source', 'parameters', 'output'))
    source.write_bytes(raw); params.write_bytes(parameter_json(p))
    original_open = Path.open
    reads = []
    class Reader:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def seek(self, *args): return self.stream.seek(*args)
        def tell(self): return self.stream.tell()
        def read(self, size):
            reads.append(size)
            assert 0 < size <= portable.MAX_HEADER
            return b'' if len(reads) == 5 else self.stream.read(size)
    def wrapped(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return Reader(stream) if path == source and args == ('rb',) else stream
    monkeypatch.setattr(Path, 'open', wrapped)
    with pytest.raises(ValueError): portable.decode_file(source, params, output)
    assert reads == [28, 192, 128, 64 * 1024, 64 * 1024]
    assert not output.exists() and source.stat().st_size == len(raw)
