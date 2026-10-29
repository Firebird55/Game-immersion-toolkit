"""Observe a complete experimental environment, never approve redistribution.

The supplier archive and every installed wheel payload are compared byte for
byte before PyInstaller runs. No installer, account, game or user profile is read.
"""
import argparse
from importlib import metadata
import json
from pathlib import Path
import sys
import tarfile
import zipfile

from closure import ROOT, ClosureError, checked_file, digest, normalized
from record_diagnostic import record, wheel_metadata

RESOURCES = (
    'package.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'public/mobile-capture/games-data.json',
    'assets/fireredvad/fireredvad_vad.onnx', 'assets/fireredvad/cmvn.ark',
    'assets/fireredvad/LICENSE', 'assets/fireredvad/NOTICE.md', 'assets/fireredvad/PROVENANCE.json',
    'scripts/check-capture-readiness.py', 'scripts/select-game-folders.ps1',
    'scripts/select-export-folder.ps1', 'scripts/endfield-reader-sources.json',
)


def verify_python(archive, prefix, pin):
    if digest(archive) != pin['sha256']:
        raise ClosureError('Python supplier archive differs from the exact observed pin.')
    files, seen = [], set()
    with tarfile.open(archive) as package:
        for member in package:
            from backend.runtime_bundle import relative_resource
            name = relative_resource(member.name.rstrip('/'))
            if name == 'python' and member.isdir():
                continue
            if name.casefold() in seen or not (member.isfile() or member.isdir()) or not name.startswith('python/'):
                raise ClosureError('Python archive contains aliases, links or unexpected roots.')
            seen.add(name.casefold())
            relative = name[len('python/'):]
            # pip is build-only and is changed when preparing the wheelhouse.
            if not member.isfile() or relative.endswith('.pyc') or relative.startswith('Lib/site-packages/') or relative.startswith('Scripts/'):
                continue
            path = prefix / relative
            import hashlib
            expected = hashlib.file_digest(package.extractfile(member), 'sha256').hexdigest()
            if not path.is_file() or path.is_symlink() or digest(path) != expected:
                raise ClosureError('Provisioned Python differs from the supplier archive: ' + relative)
            files.append({'path': relative, 'sha256': expected})
    if not files or not any(item['path'] == 'python312.dll' for item in files):
        raise ClosureError('Windows Python shared runtime is missing.')
    return files


def verify_wheel(wheel):
    with zipfile.ZipFile(wheel) as package:
        info = wheel_metadata(package)
        distribution = metadata.distribution(info['Name'])
        seen = set()
        for member in package.infolist():
            from backend.runtime_bundle import relative_resource
            name = relative_resource(member.filename.rstrip('/'))
            if name.casefold() in seen:
                raise ClosureError('Wheel contains aliased or duplicated files.')
            seen.add(name.casefold())
            if member.is_dir():
                continue
            # Windows entry scripts have installer-rewritten shebangs. They
            # are build-only; no scripts/SDK/compiler enter the frozen tree.
            data_path = None
            if '.data/' in name:
                group, _, rest = name.partition('.data/')
                category, _, tail = rest.partition('/')
                if category == 'scripts':
                    continue
                if category == 'data':
                    # sherpa-onnx-core installs its duplicate command-line DLLs
                    # in prefix/Scripts; these stay build-only, but are verified.
                    relative_resource(tail)
                    data_path = Path(sys.prefix) / tail
                elif category not in {'purelib', 'platlib'}:
                    raise ClosureError('Unreviewed wheel installation scheme: ' + group)
                name = tail
            path = (data_path or Path(distribution.locate_file(name))).resolve()
            if Path(sys.prefix).resolve() not in path.parents or not path.is_file() or path.is_symlink() or path.read_bytes() != package.read(member):
                raise ClosureError('Installed wheel payload differs from archive: ' + info['Name'])


def observe(evidence, frontend, build_id, source=ROOT):
    import shutil
    pin = json.loads((source / 'packaging/runtime-bundle/python-supplier.json').read_text())
    installed_python = verify_python(evidence / pin['archive'], Path(sys.base_prefix), pin)
    for wheel in sorted((evidence / 'wheelhouse').glob('*.whl')):
        verify_wheel(wheel)
    value = record(evidence, pin['archive'], pin['url'], build_id, source, frontend, metadata_notices=True)
    value['profile'] = 'runtime-experiment'
    for item in value['components']:
        item['review_status'] = 'observed-experiment'
    python = value['components'][0]
    if python['version'] != pin['version']:
        raise ClosureError('Interpreter version differs from the pinned supplier.')
    python['installed_files'] = installed_python
    value['python_supplier'] = pin
    value['runtime_lock_sha256'] = digest(source / 'requirements.lock.txt')
    for name in RESOURCES:
        original = source / name
        destination = evidence / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        value['resources'].append({'path': name, 'sha256': digest(original), 'version': value['source_commit'],
            'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + value['source_commit'],
            'license_expression': 'Observed source/model notices; exact-output review pending'})
    model = json.loads((source / 'assets/fireredvad/PROVENANCE.json').read_text())
    for item in model['files']:
        checked_file(source / 'assets/fireredvad', {'path': item['file'], 'sha256': item['sha256']})
    value['status'] = 'Quarantined integrated runtime experiment; rights, Windows 11 and full R19 acceptance remain open'
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--frontend-root', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = observe(args.evidence.resolve(), args.frontend_root.resolve(), args.build_id)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
