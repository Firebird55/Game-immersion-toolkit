"""Exercise a built metadata apphost with authored data, never game files."""
import argparse
import json
from pathlib import Path
import subprocess
import struct
import tempfile


def native_pe(regions, *, executable=True):
    """Authored x64 PE/function-table data; none of its bytes are executed."""
    count = len(regions) + 1
    header_size = (0x80 + 24 + 240 + count * 40 + 511) & ~511
    data = bytearray(header_size); data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 0x80)
    struct.pack_into('<4sHHIIIHH', data, 0x80, b'PE\0\0', 0x8664, count, 0, 0, 0, 240, 0)
    optional = 0x80 + 24
    struct.pack_into('<H', data, optional, 0x20b)
    struct.pack_into('<Q', data, optional + 24, 0x180000000)
    struct.pack_into('<I', data, optional + 108, 16)
    pdata_rva = 0x70000000
    struct.pack_into('<II', data, optional + 136, pdata_rva, len(regions) * 12)
    for i, (rva, code) in enumerate(regions):
        offset = len(data); size = (len(code) + 511) & ~511
        row = optional + 240 + i * 40
        struct.pack_into('<8sIIIIIIHHI', data, row, b'.text', len(code), rva, size, offset, 0, 0, 0, 0,
                         0x60000020 if executable else 0x40000040)
        data.extend(code); data.extend(b'\0' * (size - len(code)))
    pdata = bytearray(512)
    for i, (rva, code) in enumerate(regions):
        struct.pack_into('<III', pdata, i * 12, rva, rva + len(code), pdata_rva + len(regions) * 12 + i * 4)
        pdata[len(regions) * 12 + i * 4] = 1  # UNWIND_INFO version 1, no unwind operations.
    if len(regions) * 16 > len(pdata):
        raise ValueError('The authored fixture is bounded.')
    struct.pack_into('<8sIIIIIIHHI', data, optional + 240 + len(regions) * 40,
                     b'.pdata', len(pdata), pdata_rva, len(pdata), len(data), 0, 0, 0, 0, 0x40000040)
    data.extend(pdata)
    return bytes(data)


def graph_probe(executable, root):
    source, request, output = (root / name for name in ('authored-pe.bin', 'graph-request.json', 'graph-output.json'))
    first, second, base = 0x1000, 0x20000000, 0x180000000
    jump = lambda start, target: b'\xe9' + struct.pack('<i', target - start - 5)
    request.write_text(json.dumps({'entry_rva': first}))
    def run():
        return subprocess.run([str(executable), 'native-graph', str(source), str(request), str(output)],
                              capture_output=True, timeout=30)
    source.write_bytes(native_pe([(first, jump(first, second)),
        (second, bytes.fromhex('7503 90 c3 ff 90 c3 48b8'))]))
    if run().returncode:
        raise ValueError('The PE-owned cross-region graph probe failed.')
    value = json.loads(output.read_text())
    expected = [base + first, *(base + second + n for n in (0, 2, 3, 5, 6))]
    if (value['schema'] != 'proxy-starrail-native-graph-v1' or [r[0] for r in value['instructions']] != expected
            or {r['rva'] for r in value['regions']} != {first, second}
            or dict(value['edges'])[base + second] != [base + second + 2, base + second + 5]
            or value['returns'] != [base + second + 3, base + second + 6]):
        raise ValueError('The cross-region graph lost an original entry or branch.')
    before = output.read_bytes()
    if run().returncode == 0 or output.read_bytes() != before:
        raise ValueError('A graph operation replaced an existing result.')
    output.unlink()
    # Calls remain opaque external edges, including an indirect call. The
    # indirect-branch rejection below is a different control-flow contract.
    called = 0x60000000
    code = b'\xe8' + struct.pack('<i', called - second - 5) + bytes.fromhex('ffd0 c3')
    source.write_bytes(native_pe([(first, jump(first, second)), (second, code)]))
    if run().returncode:
        raise ValueError('The graph followed an external call.')
    value = json.loads(output.read_text())
    if value['calls'] != [[base + second, 'direct', base + called], [base + second + 5, 'indirect', None]]:
        raise ValueError('The graph changed its external-call contract.')
    output.unlink()
    bad_images = [
        native_pe([(first, b'\xff\xe0')]),  # Unknown indirect branch.
        native_pe([(first, bytes.fromhex('7401 48b80100000000000000 c3'))]),  # Overlapping reachable instructions.
        native_pe([(first, b'\x90')]),  # Fallthrough outside the original owner.
        native_pe([(first, b'\xc3')], executable=False),
        native_pe([(first, jump(first, second + 1)), (second, b'\x90\xc3')]),  # Unproved new-region entry.
        native_pe([(first, jump(first, second) + b'\xcc' * (32768 - 5)), (second, b'\xc3')]),
        native_pe([(first + i * 0x10000, jump(first + i * 0x10000, first + (i + 1) * 0x10000)
                    if i < 16 else b'\xc3') for i in range(17)]),
    ]
    for image in bad_images:
        source.write_bytes(image)
        if run().returncode == 0 or output.exists():
            raise ValueError('The graph accepted uncertain flow or exceeded its PE bounds.')
    source.write_bytes(native_pe([(first, b'\x90\xc3')]))
    for malformed in ['{"entry_rva":-1}', '{"entry_rva":4097}', '{"entry_rva":4096,"unknown":0}',
                      '{"entry_rva":4096,"entry_rva":4096}']:
        request.write_text(malformed)
        if run().returncode == 0 or output.exists():
            raise ValueError('The graph accepted an unproved entry or malformed request.')


def probe(executable, work_root):
    executable = Path(executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='starrail-authored-', dir=work_root) as temporary:
        root = Path(temporary)
        source = root / 'authored-data.bin'
        # One read/store join, relative call, RIP displacement, mask, return and
        # prefixed string copy. Bytes are authored x64 fixture data, not code run.
        source.write_bytes(bytes.fromhex('488b05f0ffffff e800000000 48894720 48b88877665544332211 85c0 0f48c1 f3a4 c3'))
        request, output = root / 'request.json', root / 'output.json'
        payload = {'ranges': [{'offset': 0, 'address': 4096, 'bytes': source.stat().st_size}]}
        request.write_text(json.dumps(payload))
        def run():
            return subprocess.run([str(executable), 'disassemble', str(source), str(request), str(output)],
                                  capture_output=True, timeout=30)
        result = run()
        if result.returncode:
            raise ValueError('The authored disassembly probe failed.')
        rows = json.loads(output.read_text())[0]
        if rows != [[4096, 'mov', 'rax, qword ptr [rip - 0x10]'],
                    [4103, 'call', '0x100c'], [4108, 'mov', 'qword ptr [rdi + 0x20], rax'],
                    [4112, 'movabs', 'rax, 0x1122334455667788'], [4122, 'test', 'eax, eax'],
                    [4124, 'cmovs', 'eax, ecx'], [4127, 'rep movsb', 'byte ptr [rdi], byte ptr [rsi]'],
                    [4129, 'ret', '']]:
            raise ValueError('The managed decoder operand contract changed.')
        # Existing results survive; malformed later ranges publish no output.
        before = output.read_bytes()
        if run().returncode == 0 or output.read_bytes() != before:
            raise ValueError('The helper overwrote an existing result.')
        output.unlink()
        for bad in [{'offset': -1, 'address': 1, 'bytes': 1},
                    {'offset': 0, 'address': 1, 'bytes': 65537},
                    {'offset': 0, 'address': 2**64 - 1, 'bytes': 2},
                    {'offset': 0, 'address': 1, 'bytes': 1, 'unknown': 1}]:
            request.write_text(json.dumps({'ranges': [payload['ranges'][0], bad]}))
            if run().returncode == 0 or output.exists():
                raise ValueError('The helper accepted malformed range bounds.')
        request.write_text('{"ranges":[],"ranges":[]}')
        if run().returncode == 0 or output.exists():
            raise ValueError('The helper accepted duplicate request fields.')
        # A truncated instruction cannot be silently dropped by a linear decoder.
        source.write_bytes(b'\x48\xb8')
        request.write_text(json.dumps({'ranges': [{'offset': 0, 'address': 1, 'bytes': 2}]}))
        if run().returncode == 0 or output.exists():
            raise ValueError('The helper accepted truncated native data.')
        # Static control flow follows both conditional paths and skips bytes
        # proven unreachable after return/jump. No native instruction is run.
        source.write_bytes(bytes.fromhex('7403 90 c3 ff b801000000 c3 48b8'))
        payload = {'ranges': [{'offset': 0, 'address': 4096, 'bytes': source.stat().st_size, 'control_flow': True}]}
        request.write_text(json.dumps(payload))
        if run().returncode or [row[0] for row in json.loads(output.read_text())[0]] != [4096, 4098, 4099, 4101, 4106]:
            raise ValueError('The static control-flow decoder did not preserve both reachable branches.')
        output.unlink()
        for bad in ['ffe0', '7405c3', '740148b80100000000000000c3', '90']:
            source.write_bytes(bytes.fromhex(bad)); payload['ranges'][0]['bytes'] = source.stat().st_size
            request.write_text(json.dumps(payload))
            if run().returncode == 0 or output.exists():
                raise ValueError('The static decoder accepted indirect, external conditional, overlapping or unterminated flow.')
        switch = (bytes.fromhex('83f801 771c 488d0d') + struct.pack('<i', 24)
                  + bytes.fromhex('48630481 4801c8 ffe0 b805000000 c3 b809000000 c3 31c0 c3')
                  + struct.pack('<ii', -15, -9) + bytes.fromhex('48b8'))
        source.write_bytes(switch); payload['ranges'][0]['bytes'] = len(switch)
        request.write_text(json.dumps(payload))
        if run().returncode or len(json.loads(output.read_text())[0]) != 12:
            raise ValueError('The bounded static switch decoder did not preserve every authored edge.')
        output.unlink()
        # An extra path jumping past the unsigned guard cannot authorize the
        # switch, even when another path already decoded its instructions.
        source.write_bytes(b'\x74\x05' + switch); payload['ranges'][0]['bytes'] = len(switch) + 2
        request.write_text(json.dumps(payload))
        if run().returncode == 0 or output.exists():
            raise ValueError('A branch bypassed the original switch bound.')
        graph_probe(executable, root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--work-root', required=True, type=Path)
    options = parser.parse_args()
    probe(options.executable, options.work_root)
