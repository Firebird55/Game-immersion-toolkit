"""Build-host-only collection of a pinned Node runtime and owned grammar reader.

No npm or compiler is invoked. Output is an immutable resource input directory,
not an installer or a complete desktop/native acceptance claim.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.game_tools import download
from backend.node_tools import ACORN_FILES, ACORN_VERSION, ARCHIVES, ENTRY, NODE_VERSION

ACORN_URL = 'https://registry.npmjs.org/acorn/-/acorn-8.18.0.tgz'
ACORN_INTEGRITY = 'lGq+9yr1/GuAWaVYIHRjvvySG5/4VfKIvC8EWxStPdcDh/Ka7FG3twP6v4d5BkravUilhIAsG4Qj83t02LWUPQ=='
NODE_SOURCE_SHA256 = '4f5379796280cdaeb0c2f358fd04b6a16cc4fb7dfa83b5a8c91a9d963b435231'


def selected_members(data: bytes, names: set[str], *, zipped=False) -> dict[str, bytes]:
    result = {}
    if zipped:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                if member.filename in names:
                    if member.filename in result or member.file_size > 150 * 1024 * 1024 or (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe or duplicate selected archive member')
                    result[member.filename] = archive.read(member)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
            for member in archive:
                if member.name in names:
                    if member.name in result or not member.isfile() or member.size > 150 * 1024 * 1024:
                        raise ValueError('Unsafe or duplicate selected archive member')
                    result[member.name] = archive.extractfile(member).read()
    if result.keys() != names:
        raise ValueError('Runtime archive is missing required files')
    return result


def build(output: Path, target: str, *, archive_cache: Path | None = None) -> dict:
    if target not in ARCHIVES or output.exists():
        raise ValueError('Choose a supported platform and a fresh resource output folder')
    suffix, archive_sha = ARCHIVES[target]
    prefix = f'node-v{NODE_VERSION}-{target}'
    url = f'https://nodejs.org/dist/v{NODE_VERSION}/{prefix}.{suffix}'
    archive = archive_cache.read_bytes() if archive_cache else download(url, limit=100 * 1024 * 1024)
    if hashlib.sha256(archive).hexdigest() != archive_sha:
        raise ValueError('Node archive checksum mismatch')
    executable = 'node.exe' if target.startswith('win-') else 'node'
    source_binary = prefix + ('/node.exe' if target.startswith('win-') else '/bin/node')
    source_license = prefix + '/LICENSE'
    node = selected_members(archive, {source_binary, source_license}, zipped=suffix == 'zip')
    parser_archive = download(ACORN_URL, limit=4 * 1024 * 1024)
    if base64.b64encode(hashlib.sha512(parser_archive).digest()).decode() != ACORN_INTEGRITY:
        raise ValueError('Acorn archive checksum mismatch')
    parser = selected_members(parser_archive, {'package/' + name for name in ACORN_FILES})
    parsed = json.loads(parser['package/package.json'])
    if parsed.get('name') != 'acorn' or parsed.get('version') != ACORN_VERSION or parsed.get('license') != 'MIT':
        raise ValueError('Acorn identity or license differs')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip())
    files = {'toolchains/node/' + executable: node[source_binary], 'toolchains/node/LICENSE': node[source_license],
             ENTRY: (ROOT / ENTRY).read_bytes(), 'toolchains/node/TOOLKIT-LICENSE': (ROOT / 'LICENSE').read_bytes(),
             **{'backend/node_modules/acorn/' + name: parser['package/' + name] for name in ACORN_FILES}}
    runtime = {'schema': 'toolkit-node-runtime-v1', 'platform': target, 'version': NODE_VERSION,
               'executable': executable, 'archive_sha256': archive_sha,
               'executable_sha256': hashlib.sha256(node[source_binary]).hexdigest()}
    files['toolchains/node/runtime.json'] = (json.dumps(runtime, indent=2) + '\n').encode()
    evidence = {'schema': 'toolkit-native-resources-v1', 'source_commit': commit, 'source_dirty': dirty,
                'source_inputs': {ENTRY: hashlib.sha256(files[ENTRY]).hexdigest()}, 'platform': target,
                'components': {'node': {'version': NODE_VERSION, 'url': url, 'archive_sha256': archive_sha,
                    'source_url': f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}.tar.xz',
                    'source_archive_sha256': NODE_SOURCE_SHA256, 'license': 'MIT and included third-party notices'},
                    'acorn': {'version': ACORN_VERSION, 'url': ACORN_URL, 'sha512': ACORN_INTEGRITY, 'license': 'MIT'}},
                'rights_review': 'pending', 'native_acceptance': 'pending',
                'files': [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(files.items())]}
    output.mkdir(parents=True)
    for name, data in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        if name == 'toolchains/node/node':
            destination.chmod(0o755)
    (output / 'resource-manifest.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', choices=tuple(ARCHIVES), required=True)
    parser.add_argument('--node-archive', type=Path)
    options = parser.parse_args()
    result = build(options.output, options.platform, archive_cache=options.node_archive)
    print(json.dumps({'platform': result['platform'], 'files': len(result['files']), 'native_acceptance': 'pending'}))
