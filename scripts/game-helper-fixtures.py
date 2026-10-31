"""Small independently authored inputs for private prebuilt-reader probes.

No game file, archive constant, recording or publisher-derived table is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def murmur32(data, seed=0xffffffff):
    def rotate(value, bits):
        return ((value << bits) | (value >> (32 - bits))) & 0xffffffff
    value = seed
    complete = len(data) // 4 * 4
    for offset in range(0, complete, 4):
        block = struct.unpack_from('<I', data, offset)[0]
        block = rotate(block * 0xcc9e2d51 & 0xffffffff, 15) * 0x1b873593 & 0xffffffff
        value = rotate(value ^ block, 13)
        value = (value * 5 + 0xe6546b64) & 0xffffffff
    tail = int.from_bytes(data[complete:], 'little')
    if len(data) != complete:
        value ^= rotate(tail * 0xcc9e2d51 & 0xffffffff, 15) * 0x1b873593 & 0xffffffff
    value ^= len(data); value ^= value >> 16
    value = value * 0x85ebca6b & 0xffffffff; value ^= value >> 13
    value = value * 0xc2b2ae35 & 0xffffffff; value ^= value >> 16
    return value


def fixture(root):
    if root.exists():
        raise ValueError('Fixture requires a new owned directory.')
    root.mkdir(parents=True)
    project = root / 'projects'; project.mkdir()
    selected = 'natives/owned/one.bin'
    (project / 'Owned.list').write_text(selected + '\n', encoding='ascii')
    payloads = [(selected, bytes(range(256))), ('natives/owned/unselected.bin', b'authored unselected resource')]
    table, body = b'', b''
    for name, data in payloads:
        lower, upper = (murmur32(value.encode('utf-16le')) for value in (name.lower(), name.upper()))
        table += struct.pack('<IIqqqqQ', lower, upper, 16 + 48 * len(payloads) + len(body), len(data), len(data), 0, 0)
        body += data
    (root / 'owned.pak').write_bytes(struct.pack('<IBBhII', 0x414b504b, 4, 0, 0, len(payloads), 0) + table + body)
    (root / 'oversized.pak').write_bytes(struct.pack('<IBBhII', 0x414b504b, 4, 0, 0, 2000001, 0))
    # Deliberately no encrypted/VFS/voice data. Endfield's missing-pack and
    # malformed-request handling can run without invoking a real installation.
    (root / 'endfield/StreamingAssets/VFS').mkdir(parents=True)
    (root / 'expected.json').write_text(json.dumps({'schema': 'proxy-owned-game-helper-fixture-v1',
        'selected': selected, 'selected_sha256': hashlib.sha256(payloads[0][1]).hexdigest(),
        'unselected': payloads[1][0], 'game_files': False}) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    fixture(parser.parse_args().output)
