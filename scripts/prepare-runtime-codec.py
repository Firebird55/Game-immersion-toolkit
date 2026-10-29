"""BUILD HOST ONLY: verify one supplied wheel and prepare a quarantined codec.

No pip installation, compilation or game/account access. Only pinned upstream
notices may be downloaded; binaries and raw evidence are never public artifacts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile
import stat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.prebuilt_codecs import PINNED_FILES, POLICY, SCHEMA, SOURCE_INPUTS, identity
from backend.prebuilt_readers import _no_links, _x64_image
from backend.runtime_bundle import relative_resource


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(wheel, output, source=ROOT):
    wheel, output = Path(wheel).absolute(), Path(output).absolute()
    _no_links(wheel); _no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh codec output directory; existing artifacts are preserved.')
    pin = json.loads((source / 'packaging/codecs/ffmpeg-flac.json').read_text())
    if wheel.name != pin['archive']['filename'] or digest(wheel.read_bytes()) != pin['archive']['sha256']:
        raise ValueError('Codec archive differs from its exact PyPI artifact pin.')
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        seen = set()
        for item in archive.infolist():
            name = relative_resource(item.filename.rstrip('/'))
            if name.casefold() in seen or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Codec archive contains aliases or links.')
            seen.add(name.casefold())
        files['ffmpeg.exe'] = archive.read(pin['executable']['member'])
        files['notices/IMAGEIO-LICENSE.txt'] = archive.read(pin['wrapper_notice']['member'])
    _x64_image(files['ffmpeg.exe'])
    if len(files['ffmpeg.exe']) != pin['executable']['bytes']:
        raise ValueError('Codec executable size differs.')
    for name, entry in pin['upstream_notices'].items():
        relative_resource(name)
        with urllib.request.urlopen(entry['source'], timeout=30) as response:
            data = response.read(128 * 1024 + 1)
        if len(data) > 128 * 1024 or digest(data) != entry['sha256']:
            raise ValueError('An exact upstream codec notice differs.')
        files['notices/' + name] = data
    if {name: digest(data) for name, data in files.items()} != PINNED_FILES:
        raise ValueError('Codec payload/notice hashes differ from the fixed runtime policy.')
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip())
    inputs = {name: digest((source / name).read_bytes()) for name in SOURCE_INPUTS}
    # All archive/notices/path validation precedes the first destination write.
    _no_links(output)
    output.mkdir(parents=True)
    inventory = {}
    for name, data in sorted(files.items()):
        target = output / name; target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        inventory[name] = {'bytes': len(data), 'sha256': digest(data)}
    manifest = {'schema': SCHEMA, 'kind': pin['kind'], 'platform': pin['platform'], 'version': pin['version'],
        'source_commit': commit, 'source_dirty': dirty, 'source_inputs': inputs,
        'archive_sha256': pin['archive']['sha256'], 'entry': 'ffmpeg.exe', 'policy': POLICY,
        'build_id': identity(inventory), 'files': inventory, 'production_execution_allowed': False,
        'redistribution_review': 'pending-exact-output', 'source_delivery_review': 'open', 'servicing_review': 'open',
        'review_notes': {name: pin[name] for name in ('source_delivery_review', 'servicing_review')},
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
    (output / 'codec-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.wheel, args.output)
    print('Exact codec prepared for bounded decode in runtime-experiment; rights, servicing and Windows 11 gates remain open.')


if __name__ == '__main__':
    main()
