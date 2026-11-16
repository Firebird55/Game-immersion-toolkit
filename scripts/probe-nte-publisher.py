"""Exercise the real owned managed range stream with authored reflection types.

The fixture is not an Unreal parser or a native game acceptance claim. It
checks multi-request reads, seek/clone isolation, source errors and URI refusal.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nte_publisher_stream import Broker
from backend.preparation_errors import PreparationFailure


def probe(application, tools, context, destination, *, launcher=()):
    destination.mkdir(parents=True, exist_ok=True)
    cache = destination / 'publisher-cache'
    cache.mkdir()
    payload = bytes(range(256)) * 16385
    source_calls = []
    toc = json.dumps({'schema': 'proxy-owned-publisher-stream-v1', 'member': 'Owned/publisher-member',
        'offset': 64, 'size': len(payload) - 128,
        'sha256': hashlib.sha256(payload[64:-64]).hexdigest(),
        'prefix': payload[:8].hex(), 'suffix': payload[-8:].hex()}).encode()
    (cache / 'complete.ucas').write_bytes(payload)
    def source(at, size):
        source_calls.append((at, size))
        return payload[at:at + size]
    container = SimpleNamespace(raw=toc, paths={}, root=cache, region='nte-global', branch='PC_150',
        ucas=SimpleNamespace(size=len(payload), digest=hashlib.md5(payload).hexdigest()), read_stored=source)
    containers = {'Paks/global.utoc': container, 'Paks/pakchunk1-Windows.utoc': container}
    environment = {name: os.environ[name] for name in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP') if name in os.environ}
    environment.update(PATH=os.pathsep.join((str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32'),
        os.environ.get('WINDIR', 'C:/Windows'))), DOTNET_MULTILEVEL_LOOKUP='0',
        DOTNET_ROOT=str(destination / 'absent-system-dotnet'))
    # Source-development verification may provide an explicit SDK launcher.
    # Hosted native acceptance leaves launcher empty and executes its app-local helper.
    def run(label, broker, change=lambda d: d):
        request = change({'archive_metadata': '0x' + '0' * 64, 'publisher_streams': broker.descriptors})
        output = destination / label
        result = subprocess.run([*map(str, launcher), str(application), 'inventory', str(context), str(tools), str(output)],
            input=json.dumps(request).encode(), capture_output=True, timeout=30, cwd=destination, env=environment,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode, output
    with Broker(containers) as broker:
        code, output = run('publisher-inventory', broker)
        assert code == 0 and json.loads((output / 'inventory.json').read_bytes()) == ['Owned/publisher-member']
        assert not broker.failures and any(n == 4 * 1024**2 for _, n in source_calls)
        assert len(source_calls) >= 3 and all(n <= 4 * 1024**2 for _, n in source_calls)
        def wrong_host(request):
            request['publisher_streams'][0]['toc_url'] = request['publisher_streams'][0]['toc_url'].replace('127.0.0.1', 'localhost')
            return request
        assert run('publisher-bad-host', broker, wrong_host)[0] != 0
    def refused(at, size):
        raise PreparationFailure('unsupported_game_format', 'Authored block failure')
    container.read_stored = refused
    with Broker(containers) as broker:
        assert run('publisher-corrupt-source', broker)[0] != 0
        assert broker.failures
    print('Owned NTE publisher stream transport passed; no game assets were used.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('application', 'tools', 'context', 'destination'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    probe(args.application.resolve(), args.tools.resolve(), args.context.resolve(), args.destination.resolve())
