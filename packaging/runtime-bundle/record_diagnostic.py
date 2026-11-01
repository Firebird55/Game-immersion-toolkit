"""Record observed diagnostic build inputs; this grants no redistribution approval.

Run with the exact Windows interpreter provisioned from the supplied archive.
Wheel hashes identify the local wheelhouse. Installed hashes identify the actual
build files; observation is deliberately distinct from native/license review.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email import policy
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

from closure import ROOT, ClosureError, digest, normalized


def wheel_metadata(package):
    # A wheel can contain vendored distributions with their own nested metadata
    # (e.g. setuptools). Only the wheel's top-level dist-info identifies it.
    info = [name for name in package.namelist()
            if name.count('/') == 1 and '\\' not in name
            and name.endswith('.dist-info/METADATA') and not name.startswith('.dist-info/')]
    if len(info) != 1:
        # Count archive entries, not a set: a duplicate of the same top-level
        # name is ambiguous too and must not be silently selected by ZipFile.
        raise ClosureError('A wheel has missing or ambiguous top-level package identity.')
    # Wheel metadata is UTF-8. compat32 can return non-serializable Header
    # objects for incorporated license text containing non-ASCII names.
    return BytesParser(policy=policy.default).parsebytes(package.read(info[0]))


def record(evidence, python_artifact, python_source, build_id, source, frontend_root=None, *, metadata_notices=False):
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
            package_metadata = wheel_metadata(package)
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
            if path.name.lower().startswith(('license', 'licence', 'copying', 'notice')):
                licenses.append(notice(path, normalized(name), relative))
        if not licenses:
            if not metadata_notices:
                raise ClosureError('Actual installed license/notice files are missing: ' + name)
            # Preserve the complete actual metadata, without promoting a short
            # license label (or missing text) into redistribution permission.
            member = next(item for item in installed.files if str(item).endswith('.dist-info/METADATA'))
            licenses.append(notice(Path(installed.locate_file(member)), normalized(name), 'METADATA'))
        components.append({'name': name, 'version': version, 'source': f'https://pypi.org/project/{name}/{version}/',
            'architecture': 'win-amd64' if 'win_amd64' in wheel.name else 'any',
            'review_status': 'observed-diagnostic', 'native_closure': 'unverified',
            'license_expression': package_metadata.get('License-Expression') or package_metadata.get('License') or 'observed notices; review pending',
            'artifact': {'path': wheel.relative_to(evidence).as_posix(), 'sha256': digest(wheel)},
            'licenses': licenses, 'installed_files': files,
            'notice_review': 'pending; metadata alone may not contain complete terms'})
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    resources = []
    if frontend_root is not None:
        from backend.desktop_frontend import FrontendBuild, MANIFEST
        frontend = FrontendBuild(frontend_root)
        if (frontend.value['source_commit'] != commit
                or frontend.value['version'] != json.loads((source / 'package.json').read_text(encoding='utf-8'))['version']
                or frontend.value['lock_sha256'] != digest(source / 'package-lock.json')):
            raise ClosureError('Frontend bytes must come from this exact source commit, package version and lock.')
        target = evidence / 'desktop'
        shutil.copytree(frontend.root, target)  # Existing evidence is never replaced.
        for name in (*frontend.files, MANIFEST):
            path = target / name
            resources.append({'path': 'desktop/' + name, 'sha256': digest(path),
                'version': frontend.build_id, 'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + commit,
                'license_expression': 'Observed application/font/dependency notices; exact-output redistribution review pending'})
    return {'schema': 'proxy-runtime-build-inputs-v1', 'profile': 'frontend-experiment' if frontend_root else 'diagnostic', 'source_commit': commit,
        'build_id': build_id, 'python_executable_sha256': digest(sys.executable), 'components': components,
        'resources': resources, 'gates': {}, 'supplier_acceptance': 'unverified',
        'status': 'observed diagnostic input only; full R19 closure and Windows 11 25H2 acceptance incomplete'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--python-artifact', required=True)
    parser.add_argument('--python-source', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--frontend-root', type=Path)
    args = parser.parse_args()
    try:
        value = record(args.evidence.resolve(), args.python_artifact, args.python_source, args.build_id, args.source.resolve(), args.frontend_root)
        args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    except (ClosureError, OSError, ValueError, metadata.PackageNotFoundError) as error:
        print('Diagnostic input observation blocked: ' + str(error), file=sys.stderr)
        return 2
    print('Observed exact diagnostic inputs; supplier/native/redistribution acceptance remains unverified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
