"""Collect exact NTE dependencies on the build host; never run downloaded code.

The output can be tested privately with the self-contained owned bridge. Its
receipt records unresolved supplier/source obligations and is not release
approval. The desktop runtime does not perform any of these downloads.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.game_tools import download
from backend.nte_toolchain import DEPENDENCIES, PREFIX, SCHEMA

MANAGED_COMPONENTS = ROOT / 'packaging/game-readers/managed-components.json'

INPUTS = {
    'UEExtractor.dll': {
        'url': 'https://github.com/SolicenTEAM/UEExtractor/releases/download/v.1.0.8.7/UEExtractor.zip',
        'sha256': 'e89ffece53cc11970d08f6d0a683b67ca58882e8c51fb99de07923175eb96660',
        'format': 'zip', 'member': 'UEExtractor.dll', 'version': '1.0.8.7',
        'source': 'https://github.com/SolicenTEAM/UEExtractor/tree/1dff3554320d530efff26a827819f0e011f1b892',
        'embedded_parser_source': 'https://github.com/FabianFG/CUE4Parse/tree/6409f38e09e2a21aa839cd77b4515bca6c66f280',
        'license': 'MIT; embedded parser Apache-2.0; see MANAGED-COMPONENTS.json and complete notices'},

}
NOTICES = {
    'UEEXTRACTOR-LICENSE.txt': ('https://raw.githubusercontent.com/SolicenTEAM/UEExtractor/1dff3554320d530efff26a827819f0e011f1b892/LICENSE', 'fb300b505be778c50066cd4fd897aec164e1bd7eaef31634d810ae2882555811'),
    'CUE4PARSE-LICENSE.txt': ('https://raw.githubusercontent.com/FabianFG/CUE4Parse/6409f38e09e2a21aa839cd77b4515bca6c66f280/LICENSE', 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'),
}
NOTICE = '''# NTE archive dependency evidence

UEExtractor incorporates CUE4Parse and 29 other managed assemblies. The attached
MANAGED-COMPONENTS.json records each embedded assembly hash, version, supplier
package hash, exact matching package member, source reference and notice hashes.
The collector verifies all 29 package members against the observed embedded
assembly hashes before including their complete license/notice texts. CUE4Parse
is a custom supplier build; its informational version and supplier submodule
identify the source revision. Its complete NOTICE also covers incorporated code.

The owned bridge initializes CUE4Parse directly and retains its embedded
managed Oodle and Zlib defaults. The supplier wrapper constructor and its
external native-code downloaders are never invoked. External OodleUE and
Zlib-ng DLLs are no longer collected or accepted by the runtime inventory.
Managed wrappers with optional native entry points remain embedded supplier
bytes, but the bounded archive operations do not load their external libraries.
No native codecs or compiler are acquired by the runtime.

All source URLs, supplier archive hashes, selected binary hashes and available
notice hashes are retained in dependencies.json and the outer resource receipt.
No game files, archive keys, recordings, user paths or account state are included.
'''


def managed_notices(specification=None):
    """Collect inert notices and verify the exact embedded/package identities.

    These packages are evidence inputs, not installed runtime dependencies. No
    package code is executed, restored, or copied into the application.
    """
    specification = specification or json.loads(MANAGED_COMPONENTS.read_text(encoding='utf-8'))
    components = specification.get('components', [])
    if (specification.get('schema') != 'toolkit-ue-managed-components-v1'
            or specification.get('supplier_sha256') != DEPENDENCIES['UEExtractor.dll']
            or len(components) != 30 or len({item['name'] for item in components}) != 30):
        raise ValueError('Incomplete embedded managed-assembly inventory')
    files = {}
    for item in components:
        name = item['name']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not item.get('notices'):
            raise ValueError('A managed assembly lacks its full notices')
        package = None
        if item.get('package'):
            package = verified(item['url'], item['package_sha256'], limit=64 * 1024 * 1024)
            members = item['matching_members']
            if len(members) != 1:
                raise ValueError('A managed assembly must have one exact package identity')
            assembly = extract(package, {'format': 'zip', 'member': members[0]})
            if hashlib.sha256(assembly).hexdigest() != item['sha256']:
                raise ValueError('The package assembly differs from the embedded supplier identity')
        elif name != 'CUE4Parse':
            raise ValueError('Unknown custom managed assembly')
        for number, notice in enumerate(item['notices'], 1):
            if notice['kind'] == 'package' and package is not None:
                data = extract(package, {'format': 'zip', 'member': notice['member']})
            elif notice['kind'] == 'url':
                data = verified(notice['url'], notice['sha256'], limit=512 * 1024)
            else:
                raise ValueError('Unknown managed notice source')
            if len(data) > 512 * 1024 or hashlib.sha256(data).hexdigest() != notice['sha256']:
                raise ValueError('A managed notice differs from its pinned identity')
            data.decode('utf-8-sig')
            files[f'notices/{name}-{number:02d}.txt'] = data
    files['notices/MANAGED-COMPONENTS.json'] = (json.dumps(specification, indent=2) + '\n').encode()
    return files


def verified(url, digest, *, limit):
    data = download(url, limit=limit)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('A dependency download differs from its pinned supplier identity')
    return data


def extract(data, specification):
    if specification['format'] == 'gzip':
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            result = stream.read(32 * 1024 * 1024 + 1)
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            matches = [entry for entry in archive.infolist() if entry.filename == specification['member']]
            if (len(matches) != 1 or matches[0].file_size > 32 * 1024 * 1024
                    or (matches[0].external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe or absent selected dependency member')
            result = archive.read(matches[0])
    if len(result) > 32 * 1024 * 1024:
        raise ValueError('The selected dependency exceeds its bound')
    return result


def build(output: Path, *, platform="win-x64"):
    if platform not in {"win-x64", "linux-x64", "darwin-arm64"}:
        raise ValueError("Unsupported managed reader target platform")
    if output.exists():
        raise ValueError('Choose a fresh dependency resource output folder')
    files = {}
    for name, specification in INPUTS.items():
        data = extract(verified(specification['url'], specification['sha256'], limit=64 * 1024 * 1024), specification)
        if hashlib.sha256(data).hexdigest() != DEPENDENCIES[name]:
            raise ValueError('The selected dependency differs from its exact runtime pin')
        files[name] = data
    for name, (url, digest) in NOTICES.items():
        files['notices/' + name] = verified(url, digest, limit=256 * 1024)
    files.update(managed_notices())
    files['notices/DEPENDENCIES.md'] = NOTICE.encode()
    identities = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = {'schema': SCHEMA, 'platform': platform, 'files': identities,
                'components': INPUTS, 'rights_review': 'pending', 'native_acceptance': 'pending'}
    files['dependencies.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    receipt = {'schema': 'toolkit-native-resources-v1', 'platform': platform,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'source_inputs': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ('scripts/build-nte-toolchain.py', 'backend/nte_toolchain.py',
                                       'packaging/game-readers/managed-components.json')},
        'components': INPUTS, 'rights_review': 'pending', 'native_acceptance': 'pending',
        'files': [{'path': PREFIX + name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())]}
    output.mkdir(parents=True)
    for name, data in files.items():
        target = output / PREFIX / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / 'resource-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', choices=('win-x64', 'linux-x64', 'darwin-arm64'), default='win-x64')
    args = parser.parse_args()
    result = build(args.output, platform=args.platform)
    print(json.dumps({'platform': result['platform'], 'files': len(result['files']),
                      'rights_review': result['rights_review'], 'native_acceptance': result['native_acceptance']}))
