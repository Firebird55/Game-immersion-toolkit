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
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.game_tools import download
from backend.nte_toolchain import DEPENDENCIES, PREFIX, SCHEMA

INPUTS = {
    'UEExtractor.dll': {
        'url': 'https://github.com/SolicenTEAM/UEExtractor/releases/download/v.1.0.8.7/UEExtractor.zip',
        'sha256': 'e89ffece53cc11970d08f6d0a683b67ca58882e8c51fb99de07923175eb96660',
        'format': 'zip', 'member': 'UEExtractor.dll', 'version': '1.0.8.7',
        'source': 'https://github.com/SolicenTEAM/UEExtractor/tree/1dff3554320d530efff26a827819f0e011f1b892',
        'embedded_parser_source': 'https://github.com/FabianFG/CUE4Parse/tree/6409f38e09e2a21aa839cd77b4515bca6c66f280',
        'license': 'MIT; embedded parser Apache-2.0; transitive assembly inventory pending'},
    'oodle-data-shared.dll': {
        'url': 'https://github.com/WorkingRobot/OodleUE/releases/download/2026-01-25-1223/clang-cl-x64-release.zip',
        'sha256': '2c7b9350b1a396690ef233fc79f945b62453e7f9b026645e00b75a2d8569f283',
        'format': 'zip', 'member': 'bin/oodle-data-shared.dll', 'version': '2026-01-25-1223',
        'source': 'https://github.com/WorkingRobot/OodleUE/tree/9bd4cc1e644f2890785b970cc09b96ea488be4e6',
        'license': 'Supplier references Unreal Engine EULA; redistribution grant not established'},
    'zlib-ng2.dll': {
        'url': 'https://github.com/NotOfficer/Zlib-ng.NET/releases/download/1.0.0/zlib-ng2.dll.gz',
        'sha256': 'e11f814f64821c482fb81c05fb20d9e5a3be0feb0e2f8fd9480d1f341163e2c1',
        'format': 'gzip', 'version': '1.0.0',
        'source': 'https://github.com/NotOfficer/Zlib-ng.NET/tree/52175d749e2a00ddf9b10610197c27b2c1d65658',
        'license': 'Wrapper MIT; exact zlib-ng native build and notice closure pending'},
}
NOTICES = {
    'UEEXTRACTOR-LICENSE.txt': ('https://raw.githubusercontent.com/SolicenTEAM/UEExtractor/1dff3554320d530efff26a827819f0e011f1b892/LICENSE', 'fb300b505be778c50066cd4fd897aec164e1bd7eaef31634d810ae2882555811'),
    'CUE4PARSE-LICENSE.txt': ('https://raw.githubusercontent.com/FabianFG/CUE4Parse/6409f38e09e2a21aa839cd77b4515bca6c66f280/LICENSE', 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'),
    'OODLE-SUPPLIER-README.md': ('https://raw.githubusercontent.com/WorkingRobot/OodleUE/9bd4cc1e644f2890785b970cc09b96ea488be4e6/README.md', '62f115a674411924f6690d0be4fb63e12d6fcf3a4de958ff352e3082f8bc2a42'),
    'ZLIB-WRAPPER-LICENSE.txt': ('https://raw.githubusercontent.com/NotOfficer/Zlib-ng.NET/52175d749e2a00ddf9b10610197c27b2c1d65658/LICENSE', 'deac1ca63a9ec0afe45533534e85e912bf8083a201f47ee24e0d335f386566d2'),
}
NOTICE = '''# NTE archive dependency evidence

These exact supplier binaries are collected for private native evaluation.
UEExtractor incorporates CUE4Parse and other managed libraries. The included
top-level MIT and Apache notices do not cover every embedded assembly. Its full
transitive source, version and notice inventory remains required before release.

WorkingRobot/OodleUE says its files are Epic/RAD intellectual property subject
to the Unreal Engine EULA. Its release archive supplies no license notice. This
collection does not assert a redistribution grant. Close that grant for the
exact native bytes, or replace this decoder before public distribution.

The Zlib-ng.NET wrapper's MIT license does not establish the exact native DLL's
source/build and zlib-ng notice closure. Those remain required before release.

All source URLs, supplier archive hashes, selected binary hashes and available
notice hashes are retained in dependencies.json and the outer resource receipt.
No game files, archive keys, recordings, user paths or account state are included.
'''


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


def build(output: Path):
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
    files['notices/DEPENDENCIES.md'] = NOTICE.encode()
    identities = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = {'schema': SCHEMA, 'platform': 'win-x64', 'files': identities,
                'components': INPUTS, 'rights_review': 'pending', 'native_acceptance': 'pending'}
    files['dependencies.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    receipt = {'schema': 'toolkit-native-resources-v1', 'platform': 'win-x64',
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'source_inputs': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ('scripts/build-nte-toolchain.py', 'backend/nte_toolchain.py')},
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
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({'platform': result['platform'], 'files': len(result['files']),
                      'rights_review': result['rights_review'], 'native_acceptance': result['native_acceptance']}))
