"""BUILD HOST ONLY: bind the selected Xiph build/source kit to this runtime.

No download, compiler, installer, broad FFmpeg fallback or acceptance override.
The producer's standalone candidate stays unapproved; this explicit collector
permits only the manifest-bound operation in runtime-experiment.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.prebuilt_codecs import (ARCHIVE_SHA256, PINNED_FILES, POLICY, SCHEMA,
    SOURCE_INPUTS, SOURCE_REVIEW, SERVICING_REVIEW, SOURCE_KIT_SHA256, identity)
from backend.prebuilt_readers import _no_links, _unique_json

KIT_INPUTS = {'packaging/codecs/flac-reference.json', 'scripts/build-reference-codec.ps1',
              'scripts/reference-codec.py', 'LICENSE', 'packaging/codecs/FLAC-BUILD-RECIPES-LICENSE.txt'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(reference, output, source=ROOT):
    reference, output = Path(reference).absolute(), Path(output).absolute()
    _no_links(reference); _no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh output directory; existing artifacts are preserved.')
    candidate = reference / 'candidate'
    for path in (candidate, *candidate.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()): raise ValueError('Non-regular codec input.')
    receipt_path = reference / 'CODEC-CANDIDATE.json'; _no_links(receipt_path)
    receipt = json.loads(receipt_path.read_bytes(), object_pairs_hook=_unique_json)
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip())
    pin = json.loads((source / 'packaging/codecs/flac-reference.json').read_text())
    if (dirty or receipt.get('schema') != 'proxy-r19-reference-codec-v1'
            or receipt.get('source_commit') != commit or receipt.get('version') != '1.5.0'
            or receipt.get('platform') != 'win-x64' or receipt.get('upstream_source_sha256') != ARCHIVE_SHA256
            or receipt.get('upstream_commit') != pin['source']['commit']
            or receipt.get('source_archive_sha256') != SOURCE_KIT_SHA256
            or receipt.get('configuration') != pin['cmake'] or receipt.get('source_patches') != []
            or receipt.get('production_execution_allowed') is not False or receipt.get('runtime_collection_allowed') is not False
            or receipt.get('native_windows_11_acceptance') != 'unavailable' or receipt.get('r19_complete') is not False):
        raise ValueError('Selected source-build identity, configuration or pending gates differ.')
    names = {path.relative_to(candidate).as_posix() for path in candidate.rglob('*') if path.is_file()}
    directories = {path.relative_to(candidate).as_posix() for path in candidate.rglob('*') if path.is_dir()}
    expected = set(PINNED_FILES) - {'codec-sources.zip'}
    if names != expected or directories != {'notices'} or set(receipt['files']) != expected:
        raise ValueError('Selected codec inventory differs.')
    files = {name: (candidate / name).read_bytes() for name in expected}
    archive = reference / 'codec-sources.zip'; _no_links(archive)
    files['codec-sources.zip'] = archive.read_bytes()
    if {name: digest(data) for name, data in files.items()} != PINNED_FILES:
        raise ValueError('Selected executable, DLL, source kit or notices differ from the verified pins.')
    if receipt['files'] != {name: {'bytes': len(files[name]), 'sha256': digest(files[name])} for name in expected}:
        raise ValueError('Source-build file receipt differs.')
    with zipfile.ZipFile(io.BytesIO(files['codec-sources.zip'])) as kit:
        wanted = KIT_INPUTS | {'inputs/' + pin['source']['filename']}
        if set(kit.namelist()) != wanted or len(kit.namelist()) != len(wanted):
            raise ValueError('Source kit differs from its exact input allowlist.')
        delivered = {name: kit.read(name) for name in wanted}
    if (receipt['source_files'] != {name: {'bytes': len(data), 'sha256': digest(data)} for name, data in delivered.items()}
            or digest(delivered['inputs/' + pin['source']['filename']]) != ARCHIVE_SHA256
            or any(delivered[name] != (source / name).read_bytes() for name in KIT_INPUTS)):
        raise ValueError('Delivered source/recipe differs from the runtime build.')
    inputs = {name: digest((source / name).read_bytes()) for name in SOURCE_INPUTS}
    inventory = {name: {'bytes': len(data), 'sha256': digest(data)} for name, data in sorted(files.items())}
    manifest = {'schema': SCHEMA, 'kind': 'xiph-flac-experiment', 'platform': 'win-x64', 'version': '1.5.0',
        'source_commit': commit, 'source_dirty': False, 'source_inputs': inputs,
        'archive_sha256': ARCHIVE_SHA256, 'entry': 'flac.exe', 'policy': POLICY,
        'build_id': identity(inventory), 'files': inventory, 'production_execution_allowed': False,
        'redistribution_review': 'pending-exact-output', 'source_delivery_review': SOURCE_REVIEW,
        'servicing_review': SERVICING_REVIEW, 'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
    # All input and destination-ancestry checks precede the first write.
    _no_links(output); output.mkdir(parents=True)
    for name, data in files.items():
        path = output / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    (output / 'codec-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.reference_root, args.output)
    print('Exact Xiph runtime-experiment codec prepared; production and Windows 11 gates remain open.')
