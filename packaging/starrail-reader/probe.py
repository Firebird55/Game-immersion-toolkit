"""Exercise a built metadata apphost with authored data, never game files."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--work-root', required=True, type=Path)
    options = parser.parse_args()
    probe(options.executable, options.work_root)
