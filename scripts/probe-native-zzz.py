"""Run bundled ZZZ modules/decoder on authored inputs without games or compilers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.prebuilt_node_reader import production_zzz_reader, _no_links
from backend.runtime_bundle import RuntimeLayout, relative_resource
from backend.node_tools import host_platform

PROGRAM = r"""
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {pathToFileURL} from 'node:url';
const root=process.argv[2];
const reader=await import(pathToFileURL(root+'/upstream/galgame-perform.mjs'));
const {decompress}=await import(pathToFileURL(root+'/dependencies/ooz/index.js'));
const {sceneBundleRangesFromCatalog}=await import(pathToFileURL(root+'/scripts/scene-catalog.mjs'));
assert.equal(reader.xxHash64('hello'),0x26c7827d889f6da3n);
assert.throws(()=>reader.unpackMhyFile(Buffer.from('authored invalid header'),0),/invalid mhy1 signature/);
const packed=Uint8Array.from([0x8c,0x06,0x07,0xff,0xff,0x41]);
assert.deepEqual(Buffer.from(decompress(packed,4096)),Buffer.alloc(4096,0x41));
assert.throws(()=>decompress(Uint8Array.from([255,255,255,255,255,255]),4096));
// One authored scene catalog and exact dependency mapping, in the legacy gzip schema.
const raw=Buffer.alloc(150);
raw.writeUInt32LE(1,8);raw.writeUInt32LE(2,12);raw.writeUInt32LE(2,16);
raw.writeUInt32LE(52,20);raw.writeBigUInt64LE(64n,28);raw.writeBigUInt64LE(82n,36);raw.writeBigUInt64LE(138n,44);
raw.writeUInt32LE(0,52);raw.writeBigUInt64LE(42n,56);
raw.writeUInt32LE(100,65);raw.writeUInt32LE(200,74);
raw.writeUInt32LE(0,82);raw.writeUInt32LE(500,102);raw.writeUInt32LE(50,106);
raw.writeUInt32LE(1,110);raw.writeUInt32LE(700,130);raw.writeUInt32LE(60,134);
raw.writeUInt32LE(1,138);raw.writeUInt32LE(1,142);raw.writeUInt32LE(0,146);
assert.deepEqual(sceneBundleRangesFromCatalog(gzipSync(raw),new Set([42n])),{
 matchedHashes:[42n],ranges:[{block:'Blocks/100.blk',offset:500,size:50},{block:'Blocks/200.blk',offset:700,size:60}]});
console.log(JSON.stringify({checks:['compiled-reader-import','xxhash64-known-vector','invalid-archive-refusal',
 'kraken-compressed-fill-quantum','invalid-kraken-refusal','authored-scene-catalog']}));
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_resources(root: Path):
    _no_links(root)
    path = root / 'resource-manifest.json'
    _no_links(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema') != 'toolkit-native-resources-v1' or value.get('source_dirty') is not False:
        raise ValueError('Native probe requires resources from a clean source checkpoint')
    files = {}
    for row in value['files']:
        name = relative_resource(row['path'])
        candidate = root / name
        _no_links(candidate)
        if name in files or candidate.stat().st_size != row['bytes'] or digest(candidate.read_bytes()) != row['sha256']:
            raise ValueError('Native probe resource differs')
        files[name] = candidate
    return value, files


def probe(zzz_resources: Path, node_resources: Path):
    zzz, zzz_files = read_resources(zzz_resources)
    node, node_files = read_resources(node_resources)
    if zzz['platform'] != host_platform() or node['platform'] != host_platform():
        raise ValueError('Native probe must run on the artifact platform')
    if zzz_files.keys() & node_files.keys():
        raise ValueError('Native resource inputs overlap')
    with tempfile.TemporaryDirectory(prefix='toolkit-zzz-probe-') as temporary:
        # Hosted Windows can expose its temp directory through an 8.3 alias;
        # macOS also aliases /var. Derive owned paths from the actual directory.
        work = Path(temporary).resolve(strict=True)
        app, resources, private = work / 'app', work / 'app/resources', work / 'private'
        resources.mkdir(parents=True)
        inventory = {}
        for name, source in {**zzz_files, **node_files}.items():
            destination = resources / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            inventory[name] = digest(destination.read_bytes())
        layout = RuntimeLayout(mode='bundle', profile='runtime', application_root=app, resource_root=resources,
            data_root=private / 'data', settings_root=private, cache_root=private / 'cache',
            tool_root=private / 'tools', work_root=private / 'work', state_root=private / 'state',
            default_export_root=private / 'exports', source_commit=zzz['source_commit'], resources=inventory)
        helper = production_zzz_reader(layout=layout)
        before = {name: digest(path.read_bytes()) for name, path in {**zzz_files, **node_files}.items()}
        authored = layout.work_root / 'authored'; authored.mkdir(parents=True)
        program = authored / 'probe.mjs'; program.write_text(PROGRAM, encoding='utf-8')
        result = subprocess.run([str(helper.executable), str(program), str(helper.root)], cwd=authored,
            env=helper.environment(), capture_output=True, timeout=60)
        if result.returncode:
            raise ValueError('Native ZZZ authored module/decoder checks failed')
        checks = json.loads(result.stdout)['checks']
        # Run the real entrypoints with an intentionally empty authored install.
        # They must reach schema errors through prebuilt modules, with no TS/npm.
        game = work / 'authored-game'; game.mkdir()
        (authored / 'PerformTemplateTb.json').write_text('{}')
        for mode, expected in [('dialogue', b'No matching scene paths'), ('cinematic', b'Installed cinematic resource catalog was not found')]:
            result = subprocess.run(helper.command(mode, game_data=game, work=authored), cwd=authored,
                env=helper.environment(), capture_output=True, timeout=60)
            if result.returncode == 0 or expected not in result.stderr or b'ERR_MODULE_NOT_FOUND' in result.stderr:
                raise ValueError('Native ZZZ entrypoint did not reach its expected authored format refusal')
            checks.append(mode + '-compiler-free-entrypoint')
        if any(path.suffix in {'.ts', '.mjs'} and path != program for path in authored.iterdir()):
            raise ValueError('Native ZZZ generated runtime code in private work')
        after = {name: digest(path.read_bytes()) for name, path in {**zzz_files, **node_files}.items()}
        if before != after:
            raise ValueError('Native ZZZ probe changed immutable inputs')
        checks.append('immutable-resources-preserved')
        return {'schema': 'toolkit-native-zzz-probe-v1', 'platform': host_platform(), 'source_commit': zzz['source_commit'],
            'reader_build_id': helper.identity, 'zzz_resources_sha256': digest((zzz_resources / 'resource-manifest.json').read_bytes()),
            'node_resources_sha256': digest((node_resources / 'resource-manifest.json').read_bytes()),
            'probe_source_sha256': digest(Path(__file__).read_bytes()), 'checks': checks, 'status': 'pass',
            'installed_game_validation': 'not-part-of-authored-probe'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zzz-resources', type=Path, required=True)
    parser.add_argument('--node-resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.zzz_resources.absolute(), args.node_resources.absolute())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'platform': result['platform']}))
