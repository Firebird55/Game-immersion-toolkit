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
import zlib

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


def authored_cr2w():
    """Encode an owned localization entry using the retained RED4 v195 schema.

    Two chunks exercise JsonResource's handle, the localization entry array,
    UInt64 key and both CString variants. No supplier/game fixture is copied.
    """
    names = ['', 'JsonResource', 'root', 'handle:ISerializable',
             'localizationPersistenceOnScreenEntries', 'entries',
             'array:localizationPersistenceOnScreenEntry', 'primaryKey', 'Uint64',
             'secondaryKey', 'String', 'femaleVariant', 'maleVariant']
    def name_hash(text):
        value = 0xcbf29ce484222325
        for byte in text.encode('utf-8'):
            value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
        return ((value >> 32) ^ value) & 0xffffffff if text else 0
    strings, name_table = bytearray(), bytearray()
    for name in names:
        name_table += struct.pack('<II', len(strings), name_hash(name))
        strings += name.encode('utf-8') + b'\0'
    def prop(name, kind, payload):
        return struct.pack('<HHI', names.index(name), names.index(kind), len(payload) + 4) + payload
    def text(value):
        payload = value.encode('utf-8')
        if not 0 < len(payload) < 64:
            raise ValueError('Authored string must fit the one-byte signed VLQ fixture')
        return bytes([len(payload) | 0x80]) + payload
    entry = (b'\0' + prop('primaryKey', 'Uint64', struct.pack('<Q', 12345))
             + prop('secondaryKey', 'String', text('toolkit_authored'))
             + prop('femaleVariant', 'String', text('Authored female dialogue.'))
             + prop('maleVariant', 'String', text('Authored male dialogue.')) + b'\0\0')
    chunks = [b'\0' + prop('root', 'handle:ISerializable', struct.pack('<I', 2)) + b'\0\0',
              b'\0' + prop('entries', 'array:localizationPersistenceOnScreenEntry',
                           struct.pack('<I', 1) + entry) + b'\0\0']
    exports = bytearray()
    offset = 160 + len(strings) + len(name_table) + 48
    for name, chunk in zip(('JsonResource', 'localizationPersistenceOnScreenEntries'), chunks):
        exports += struct.pack('<HHIIIII', names.index(name), 0, 0, len(chunk), offset, 0, zlib.crc32(chunk))
        offset += len(chunk)
    tables = [(160, len(strings), zlib.crc32(strings)),
              (160 + len(strings), len(names), zlib.crc32(name_table)), (0, 0, 0), (0, 0, 0),
              (160 + len(strings) + len(name_table), 2, zlib.crc32(exports))] + [(0, 0, 0)] * 5
    header = b'CR2W' + struct.pack('<IIQIIIII', 195, 0, 0, 0, offset, offset, 0, 2)
    # Header CRC is not consulted by the reader; table/chunk CRCs are populated.
    return header + b''.join(struct.pack('<III', *row) for row in tables) + strings + name_table + exports + b''.join(chunks)


def assert_authored_cr2w_output(value):
    """Exit zero alone is insufficient: supplier Cr2wTask can swallow errors."""
    try:
        root = value['Data']['RootChunk']
        collection = root['root']['Data']
        entry, = collection['entries']
        expected = {'$type': 'localizationPersistenceOnScreenEntry',
                    'primaryKey': '12345', 'secondaryKey': 'toolkit_authored',
                    'femaleVariant': 'Authored female dialogue.', 'maleVariant': 'Authored male dialogue.'}
        valid = (value['Header']['DataType'] == 'CR2W' and value['Data']['Version'] == 195
                 and root['$type'] == 'JsonResource'
                 and collection['$type'] == 'localizationPersistenceOnScreenEntries' and entry == expected)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('Native CR2W conversion did not preserve the authored localization entry')


def probe(resources: Path):
    if host_platform() != TARGET:
        raise ValueError('This supplier closure requires a native Windows x64 probe')
    resources = resources.resolve()
    chain = _verify(resources / PREFIX)
    checks = {}
    with tempfile.TemporaryDirectory(prefix='toolkit-cyberpunk-probe-') as temporary:
        # Hosted Windows TEMP may use a short-name/junction spelling. Match the
        # production guard's canonical output paths without relaxing ownership.
        root = Path(temporary).resolve()
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
        converted = root / 'authored-resources'
        converted.mkdir()
        resource = converted / 'onscreens.json'
        cr2w = authored_cr2w()
        resource.write_bytes(cr2w)
        execute(['cr2w', '-s', str(converted), '-v', 'quiet'])
        serialized = converted / 'onscreens.json.json'
        if not serialized.is_file() or not 0 < serialized.stat().st_size < 16 * 1024:
            raise ValueError('Native CR2W conversion did not produce bounded JSON')
        assert_authored_cr2w_output(json.loads(serialized.read_text(encoding='utf-8')))
        checks['authored_cr2w_localization_serialization'] = True
        checks['authored_cr2w_input_unchanged'] = resource.read_bytes() == cr2w
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
        'cr2w_format_validation': 'authored-localization-resource', 'rights_review': 'pending'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    result = probe(options.resources)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'platform': result['platform'], 'passed': True, 'checks': result['checks']}))
