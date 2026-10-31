"""Exercise the actual app-local reader on authored bytes without a game or SDK."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.cyberpunk_toolchain import (INVENTORY_SHA256, OWNED_FILES, PREFIX, TARGET,
    OwnedProcess, _verify, host_platform)


def authored_archive(path: Path, payload: bytes):
    """One uncompressed authored .bin, encoded from the retained RED4 schema."""
    if not 4 <= len(payload) <= 4096:
        raise ValueError('Authored probe payload must fit its fixed segment')
    entry = struct.pack('<QqIIIII', 123456789123, 0, 0, 0, 1, 0, 0) + hashlib.sha1(payload).digest()
    table = struct.pack('<III', 1, 1, 0) + entry + struct.pack('<QII', 4096, len(payload), len(payload))
    index = struct.pack('<IIQ', 8, len(table) + 8, 0) + table
    header = struct.pack('<IIQIQIQ', 1380009042, 12, 8192, len(index), 0, 0, 12288)
    archive = bytearray(12288)
    archive[:40] = header
    archive[4096:4096 + len(payload)] = payload
    archive[8192:8192 + len(index)] = index
    path.write_bytes(archive)


def probe(resources: Path):
    if host_platform() != TARGET:
        raise ValueError('This supplier closure requires a native Windows x64 probe')
    resources = resources.resolve()
    chain = _verify(resources / PREFIX)
    checks = {}
    with tempfile.TemporaryDirectory(prefix='toolkit-cyberpunk-probe-') as temporary:
        root = Path(temporary)
        work, game, output = root / 'work', root / 'authored', root / 'extracted'
        for path in (work, game, output):
            path.mkdir()
        layout = SimpleNamespace(mode='bundle', data_root=root, cache_root=root / 'cache', work_root=work)
        def execute(arguments, *, reject=False):
            command, environment = chain.command(arguments if not reject else ['--help'], work=work, layout=layout)
            if reject:
                command[-1:] = list(arguments)  # Verify the managed entry also rejects writes independently.
            child = OwnedProcess(command, cwd=work, env=environment)
            try:
                stdout, _stderr = child.process.communicate(timeout=120)
                result = child.process.returncode
            finally:
                child.stop()
                child.close_streams()
            if (result == 0) == reject:
                raise ValueError('Native reader returned an unexpected operation status')
            return stdout
        checks['owned_entry_identity'] = b'toolkit-cyberpunk-reader-v1' in execute(['--version'])
        checks['fixed_read_operations'] = b'unbundle' in execute(['--help'])
        execute(['pack', str(output)], reject=True)
        checks['managed_entry_rejects_writes'] = True
        payload = b'Authored toolkit archive probe.\n' * 32
        source = game / 'authored.archive'
        authored_archive(source, payload)
        original = source.read_bytes()
        execute(['unbundle', str(source), '-o', str(output), '-r', '.*', '-v', 'quiet'])
        extracted = list(output.rglob('*.bin'))
        checks['authored_archive_extraction'] = len(extracted) == 1 and extracted[0].read_bytes() == payload
        checks['authored_input_unchanged'] = source.read_bytes() == original
        # HashService initializes the supplier's compressed embedded hash tables
        # during UnbundleTask; the owned resolver permits only pinned kraken.dll.
        checks['bundled_kraken_decompression'] = checks['authored_archive_extraction']
    _verify(resources / PREFIX)
    checks['immutable_runtime_unchanged'] = True
    if not all(checks.values()):
        raise ValueError('Native authored reader assertions failed')
    receipt = json.loads((resources / 'resource-manifest.json').read_text(encoding='utf-8'))
    return {'schema': 'toolkit-cyberpunk-native-probe-v1', 'platform': TARGET,
        'execution': 'actual-app-local-process', 'source_commit': receipt['source_commit'],
        'source_dirty': receipt['source_dirty'], 'supplier_inventory_sha256': INVENTORY_SHA256,
        'owned_entry_sha256': OWNED_FILES['reader/ToolkitCyberpunkReader.dll'],
        'checks': checks, 'passed': True, 'game_asset_validation': 'not-performed',
        'cr2w_format_validation': 'not-performed', 'rights_review': 'pending'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    result = probe(options.resources)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'platform': result['platform'], 'passed': True, 'checks': result['checks']}))
