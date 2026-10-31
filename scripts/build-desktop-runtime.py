"""Build an exact native desktop inventory for subsequent target acceptance.

Construction never grants release eligibility. The unchanged payload is promoted
only after its input closure and native target evidence have been verified.
No dependency or tool is installed by this command.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ACORN_RESOURCES = {'backend/node_modules/acorn/package.json', 'backend/node_modules/acorn/LICENSE',
    'backend/node_modules/acorn/dist/acorn.js'}
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
from backend.desktop_frontend import FrontendBuild, MANIFEST
from backend.runtime_bundle import EXPERIMENT_CHILDREN, MANIFEST_SCHEMA, relative_resource
from closure import FORBIDDEN_NAMES, PRIVATE_PARTS
from record_diagnostic import wheel_metadata
from record_runtime import RESOURCES, verify_python, verify_wheel
from packaging.requirements import Requirement


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build_environment(inputs_path, evidence):
    env = dict(os.environ, PYTHONNOUSERSITE='1', PROXY_RUNTIME_BUILD_INPUTS=str(inputs_path),
               PROXY_RUNTIME_EVIDENCE_ROOT=str(evidence))
    for name in ('PYTHONPATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH',
                 'DYLD_FALLBACK_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(name, None)
    # PyInstaller searches PATH for DLL dependencies. Developer tools can carry
    # same-named, incompatible libraries (for example Poppler's ICU versus the
    # Windows ICU used by Qt). Only the verified interpreter and OS tools belong
    # in this search; package hooks supply the locked wheels' own libraries.
    if sys.platform == 'win32':
        windows = Path(os.environ['SystemRoot'])
        paths = [Path(sys.executable).parent, windows / 'System32', windows]
    else:
        paths = [Path(sys.executable).parent, Path('/usr/bin'), Path('/bin'), Path('/usr/sbin')]
    env['PATH'] = os.pathsep.join(str(path) for path in paths)
    return env


def tree(root):
    result = []
    for path in sorted(root.rglob('*')):
        name = relative_resource(path.relative_to(root).as_posix())
        if path.name.casefold() in FORBIDDEN_NAMES or path.suffix.casefold() in {'.dpapi', '.db', '.sqlite', '.mp3', '.wav', '.pak', '.pck', '.wem', '.bnk'}:
            raise ValueError('Forbidden private artifact in runtime: ' + name)
        owned_acorn = name.removeprefix('_internal/') in ACORN_RESOURCES
        if any(part.casefold() in PRIVATE_PARTS for part in Path(name).parts) and not (owned_acorn or
                path.is_dir() and any(resource.startswith(name.removeprefix('_internal/') + '/') for resource in ACORN_RESOURCES)):
            raise ValueError('Private tree in runtime: ' + name)
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or root.resolve() not in path.resolve().parents or not path.exists():
                raise ValueError('Runtime contains an escaping or broken symbolic link.')
            result.append({'path': name, 'link': target, 'bytes': len(target.encode()),
                'sha256': hashlib.sha256(target.encode()).hexdigest()})
        elif path.is_file():
            if getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Runtime contains a reparse point.')
            result.append({'path': name, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    return result


def source_inputs():
    roots = ['backend', 'scripts', 'packaging', 'assets/fireredvad']
    paths = [ROOT / name for name in ['requirements.txt', 'requirements.lock.txt', 'package.json', 'package-lock.json']]
    for name in roots:
        paths += [p for p in (ROOT / name).rglob('*') if p.is_file() and p.suffix in {'.py', '.ps1', '.mjs', '.json', '.spec', '.txt', '.onnx', '.ark'}
            and not any(part in {'__pycache__', 'node_modules', 'bin', 'obj'} for part in p.relative_to(ROOT).parts)]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def extra_resources(root, destination):
    manifest = json.loads((root / 'resource-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'toolkit-native-resources-v1':
        raise ValueError('Unknown native resource manifest.')
    expected = {}
    for item in manifest.get('files', []):
        name = relative_resource(item['path'])
        if name.casefold() in expected:
            raise ValueError('Duplicate native resource path.')
        path = root / name
        if any(p.is_symlink() or (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
                for p in (path, *path.parents)):
            raise ValueError('Native resources cannot traverse links.')
        if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Native resource bytes differ from the manifest.')
        expected[name.casefold()] = name
    actual = {p.relative_to(root).as_posix().casefold() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected) | {'resource-manifest.json'} or not expected:
        raise ValueError('Native resource inventory is not closed.')
    for name in expected.values():
        target = destination / name
        if target.exists():
            raise ValueError('Native resource collides with a base resource.')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        shutil.copymode(root / name, target)
    return manifest


def build(frontend_root, output, wheelhouse=None, resources_root=None, *, profile='runtime', python_archive=None):
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Desktop candidates require Python 3.12.')
    if profile not in {'runtime', 'runtime-experiment'}:
        raise ValueError('Unsupported desktop construction profile.')
    if output.exists():
        raise ValueError('Choose a fresh output directory; previous candidates are preserved.')
    for path in (output, *output.parents):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Candidate output cannot traverse links or reparse points.')
    if frontend_root == output or frontend_root in output.parents or output in frontend_root.parents:
        raise ValueError('Candidate output cannot overlap the frontend input.')
    frontend = FrontendBuild(frontend_root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    if frontend.value['source_commit'] != commit or frontend.value['version'] != package['version']:
        raise ValueError('Build the desktop frontend from the current source identity first.')
    before = source_inputs()
    python_supplier = None
    if python_archive:
        pin = json.loads((ROOT / 'packaging/runtime-bundle/python-supplier.json').read_text())
        if platform.python_version() != pin['version'] or sys.platform != 'win32':
            raise ValueError('Python supplier pin does not match this native build target.')
        installed_python = verify_python(python_archive, Path(sys.base_prefix), pin)
        python_supplier = {**pin, 'installed_files': installed_python}
    components = []
    for lock in ['requirements.lock.txt', 'packaging/desktop/build-requirements.lock.txt']:
        for line in (ROOT / lock).read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            installed = metadata.distribution(requirement.name)
            if installed.version not in requirement.specifier:
                raise ValueError('Installed dependency differs from the lock: ' + requirement.name)
            components.append({'name': requirement.name, 'version': installed.version,
                'source': f'https://pypi.org/project/{requirement.name}/{installed.version}/',
                'license_expression': installed.metadata.get('License-Expression') or 'see exact retained notices',
                'architecture': platform.machine(), 'rights_review': 'pending-exact-output'})
    if wheelhouse:
        wheels = {}
        for wheel in sorted(wheelhouse.glob('*.whl')):
            verify_wheel(wheel)
            with zipfile.ZipFile(wheel) as archive:
                info = wheel_metadata(archive)
            wheels[info['Name'].lower().replace('_', '-')] = (info['Version'], digest(wheel))
        for item in components:
            entry = wheels.get(item['name'].lower().replace('_', '-'))
            if not entry or entry[0] != item['version']:
                raise ValueError('Exact wheelhouse input missing: ' + item['name'])
            item['artifact_sha256'] = entry[1]
    output.mkdir(parents=True)
    evidence = output / 'inputs'
    evidence.mkdir()
    shutil.copytree(frontend.root, evidence / 'desktop')
    for name in RESOURCES:
        destination = evidence / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    native_resources = []
    for resource_input in resources_root or []:
        native_resources.append(extra_resources(resource_input, evidence))
    resources = [{'path': p.relative_to(evidence).as_posix(), 'sha256': digest(p)}
        for p in sorted(evidence.rglob('*')) if p.is_file()]
    source_hash = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    identity = {'profile': profile, 'version': package['version'], 'source_commit': commit,
        'build_id': 'desktop-' + source_hash[:20]}
    inputs = {'schema': 'proxy-desktop-observed-build-v1', **identity, 'resources': resources,
        'source_inputs': before, 'python_version': platform.python_version(),
        'python_executable_sha256': digest(sys.executable), 'components': components,
        'python_supplier': python_supplier,
        'native_resources': native_resources,
        'r19_complete': False, 'redistribution_review': 'pending-exact-output'}
    inputs_path = output / 'OBSERVED-INPUTS.json'
    inputs_path.write_text(json.dumps(inputs, indent=2) + '\n')
    env = build_environment(inputs_path, evidence)
    subprocess.run([sys.executable, '-B', '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--distpath', str(output / 'runtime'), '--workpath', str(output / 'build'),
        str(ROOT / 'packaging/runtime-bundle/runtime.spec')], cwd=ROOT, env=env, check=True)
    if source_inputs() != before:
        raise ValueError('Source changed during the candidate build; retained output is invalid and must not be packaged.')
    runtime = output / 'runtime/GameImmersionToolkit'
    manifest = {'schema': MANIFEST_SCHEMA, **identity, 'resources': {item['path']: item['sha256'] for item in resources},
        'children': list(EXPERIMENT_CHILDREN), 'r19_complete': False, 'storage_epoch': 1, 'host_protocol': 1}
    (runtime / '_internal/runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    asr = output / 'runtime/GameImmersionToolkitAsr'
    target = runtime / 'asr'
    if output.resolve() not in asr.resolve().parents or output.resolve() not in target.resolve().parents:
        raise ValueError('ASR move escaped the owned candidate directory.')
    asr.rename(target)
    (runtime / 'asr/_internal/runtime-manifest.json').write_text(json.dumps({**manifest, 'children': ['asr'], 'resources': {}}, indent=2) + '\n')
    for name in ['LICENSE', 'NOTICE.md', 'THIRD_PARTY_NOTICES.md']:
        shutil.copyfile(ROOT / name, runtime / name)
    notices = runtime / 'THIRD_PARTY'
    for component in components:
        distribution = metadata.distribution(component['name'])
        destination = notices / component['name']
        destination.mkdir(parents=True)
        # Retain complete actual files, including vendored native notices. A
        # metadata label is not promoted to an approval by this observer.
        for file in distribution.files or []:
            name = Path(str(file)).name.casefold()
            if name.startswith(('license', 'copying', 'notice')) or name == 'metadata':
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    suffix = hashlib.sha256(str(file).encode()).hexdigest()[:10]
                    shutil.copyfile(path, destination / (suffix + '-' + path.name))
    python_license = Path(sys.base_prefix) / ('LICENSE.txt' if sys.platform == 'win32' else 'LICENSE')
    if python_license.is_file():
        shutil.copyfile(python_license, notices / 'CPython-LICENSE.txt')
    files = tree(runtime)
    proof = {'schema': 'proxy-runtime-candidate-v1', **identity, 'repository': 'Firebird55/Game-immersion-toolkit',
        'r19_complete': False, 'redistribution_review': 'pending-exact-output', 'native_acceptance': 'unavailable',
        'signing': 'not-established', 'source_inputs_sha256': source_hash, 'components': components,
        'native_resources': native_resources, 'python_supplier': python_supplier,
        'python_version': platform.python_version(), 'python_executable_sha256': digest(sys.executable),
        'release_eligible': False, 'storage_epoch': 1, 'host_protocol': 1,
        'files': files, 'directories': sorted(p.relative_to(runtime).as_posix() for p in runtime.rglob('*') if p.is_dir() and not p.is_symlink())}
    (output / 'CANDIDATE-PROVENANCE.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'build_id': identity['build_id'], 'files': len(files), 'bytes': sum(p['bytes'] for p in files),
        'r19_complete': False, 'release_eligible': False}))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--resources-root', type=Path, action='append', default=[])
    parser.add_argument('--profile', choices=['runtime', 'runtime-experiment'], default='runtime')
    parser.add_argument('--python-archive', type=Path,
        help='Verify the provisioned Windows interpreter byte-for-byte against its pinned supplier archive.')
    args = parser.parse_args()
    try:
        build(args.frontend_root.absolute(), args.output.absolute(), args.wheelhouse, args.resources_root,
            profile=args.profile, python_archive=args.python_archive)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Observed desktop build failed: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
