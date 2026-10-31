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

}
NOTICES = {
    'UEEXTRACTOR-LICENSE.txt': ('https://raw.githubusercontent.com/SolicenTEAM/UEExtractor/1dff3554320d530efff26a827819f0e011f1b892/LICENSE', 'fb300b505be778c50066cd4fd897aec164e1bd7eaef31634d810ae2882555811'),
    'CUE4PARSE-LICENSE.txt': ('https://raw.githubusercontent.com/FabianFG/CUE4Parse/6409f38e09e2a21aa839cd77b4515bca6c66f280/LICENSE', 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'),
}
NOTICE = '''# NTE archive dependency evidence

These exact supplier binaries are collected for private native evaluation.
UEExtractor incorporates CUE4Parse and other managed libraries. The included
top-level MIT and Apache notices do not cover every embedded assembly. Its full
transitive source, version and notice inventory remains required before release.

The owned bridge initializes CUE4Parse directly and retains its embedded
managed Oodle and Zlib defaults. The supplier wrapper constructor and its
external native-code downloaders are never invoked. External OodleUE and
Zlib-ng DLLs are no longer collected or accepted by the runtime inventory.
The embedded managed dependencies still require full notice/source review.

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
