"""Record observed diagnostic build inputs; this grants no redistribution approval.

Run with the exact Windows interpreter provisioned from the supplied archive.
Wheel hashes identify the local wheelhouse. Installed hashes identify the actual
build files; observation is deliberately distinct from native/license review.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

from closure import ROOT, ClosureError, digest, normalized


def record(evidence, python_artifact, python_source, build_id, source):
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise ClosureError('Observe diagnostic inputs on the Windows x64 build host.')
    archive = evidence / python_artifact
    if not archive.is_file() or not python_source.startswith('https://'):
        raise ClosureError('Supply the actual provisioned Python archive and HTTPS supplier URL.')
    components = []
    licenses_root = evidence / 'licenses'
    licenses_root.mkdir(exist_ok=True)

    def notice(source_file, component, relative):
        destination = licenses_root / component / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
        return {'path': destination.relative_to(evidence).as_posix(), 'sha256': digest(destination)}

    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise ClosureError('The Python supplier license file is missing; do not infer it.')
    components.append({'name': 'cpython', 'version': platform.python_version(), 'source': python_source,
        'architecture': 'win-amd64', 'review_status': 'observed-diagnostic', 'native_closure': 'unverified',
        'license_expression': 'PSF-2.0; incorporated terms require review',
        'artifact': {'path': python_artifact, 'sha256': digest(archive)},
        'licenses': [notice(python_license, 'cpython', 'LICENSE.txt')],
        'installed_files': [{'path': path.relative_to(Path(sys.base_prefix)).as_posix(), 'sha256': digest(path)}
            for path in sorted(Path(sys.base_prefix).glob('*')) if path.is_file() and path.suffix.lower() in {'.exe', '.dll'}]})
    for wheel in sorted((evidence / 'wheelhouse').glob('*.whl')):
        with zipfile.ZipFile(wheel) as package:
            info = [name for name in package.namelist() if name.endswith('.dist-info/METADATA')]
            if len(info) != 1:
                raise ClosureError('A wheel has ambiguous package identity.')
            package_metadata = BytesParser().parsebytes(package.read(info[0]))
        name, version = package_metadata['Name'], package_metadata['Version']
        installed = metadata.distribution(name)
        if installed.version != version:
            raise ClosureError('Installed distribution differs from wheelhouse: ' + name)
        licenses, files = [], []
        for member in installed.files or ():
            path = Path(installed.locate_file(member)).resolve()
            if not path.is_file() or path.suffix == '.pyc':
                continue
            # Entry scripts can be outside an environment's package directory,
            # but remain inside sys.prefix on the supported Windows build host.
            if Path(sys.prefix).resolve() not in path.parents:
                raise ClosureError('Installed packaging file escapes the build environment: ' + name)
            relative = path.relative_to(Path(sys.prefix)).as_posix()
            files.append({'path': relative, 'sha256': digest(path)})
            if path.name.lower().startswith(('license', 'copying', 'notice')):
                licenses.append(notice(path, normalized(name), relative))
        if not licenses:
            raise ClosureError('Actual installed license/notice files are missing: ' + name)
        components.append({'name': name, 'version': version, 'source': f'https://pypi.org/project/{name}/{version}/',
            'architecture': 'win-amd64' if 'win_amd64' in wheel.name else 'any',
            'review_status': 'observed-diagnostic', 'native_closure': 'unverified',
            'license_expression': package_metadata.get('License-Expression') or package_metadata.get('License') or 'observed notices; review pending',
            'artifact': {'path': wheel.relative_to(evidence).as_posix(), 'sha256': digest(wheel)},
            'licenses': licenses, 'installed_files': files})
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    return {'schema': 'proxy-runtime-build-inputs-v1', 'profile': 'diagnostic', 'source_commit': commit,
        'build_id': build_id, 'python_executable_sha256': digest(sys.executable), 'components': components,
        'resources': [], 'gates': {}, 'supplier_acceptance': 'unverified',
        'status': 'observed diagnostic input only; full R19 closure and Windows 11 25H2 acceptance incomplete'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--python-artifact', required=True)
    parser.add_argument('--python-source', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        value = record(args.evidence.resolve(), args.python_artifact, args.python_source, args.build_id, args.source.resolve())
        args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    except (ClosureError, OSError, ValueError, metadata.PackageNotFoundError) as error:
        print('Diagnostic input observation blocked: ' + str(error), file=sys.stderr)
        return 2
    print('Observed exact diagnostic inputs; supplier/native/redistribution acceptance remains unverified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
