"""Offline evidence gate and quarantined onedir manifest writer.

No downloads, package installs, game probing, or license inference occur here.
Reviewed exact inputs are supplied privately by the Windows build operator.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.runtime_bundle import CHILD_TARGETS, EXPERIMENT_CHILDREN, MANIFEST_SCHEMA, relative_resource

GATES = ('python-supplier', 'python-native', 'javascript-native', 'models',
         'vgmstream', 'ffmpeg', 'copyleft', 'game-helper-rights', 'compiler-free-helpers',
         'native-dll-isolation', 'frontend-equivalence', 'supervised-update')
FORBIDDEN_NAMES = {'oneocr.dll', 'oneocr.onemodel', 'oo2core_7_win64.dll',
                   'model.int8.onnx', 'tokens.txt', 'accounts.dpapi', 'key.dpapi'}
PRIVATE_PARTS = {'data', 'work', 'output', 'diagnostics', 'persona5-charsets', '.git', '.venv', 'node_modules'}
SHA = re.compile(r'[a-f0-9]{64}')


class ClosureError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_file(root, entry):
    if not isinstance(entry, dict) or not SHA.fullmatch(str(entry.get('sha256', ''))):
        raise ClosureError('Every evidence file needs its exact SHA-256.')
    name = relative_resource(entry.get('path', ''))
    path = root / name
    if path.is_symlink() or not path.is_file() or root.resolve() not in path.resolve().parents:
        raise ClosureError('Evidence file is missing or escapes its root: ' + name)
    if digest(path) != entry['sha256']:
        raise ClosureError('Evidence checksum mismatch: ' + name)
    return path


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def validate_inputs(value, source, evidence, *, check_host=True):
    if value.get('schema') != 'proxy-runtime-build-inputs-v1' or value.get('profile') not in {'diagnostic', 'frontend-experiment', 'runtime-experiment', 'runtime'}:
        raise ClosureError('Unsupported build-input schema or profile.')
    if not re.fullmatch(r'[a-f0-9]{40}', str(value.get('source_commit', ''))):
        raise ClosureError('An exact source commit is required.')
    if not isinstance(value.get('build_id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value['build_id']):
        raise ClosureError('A portable build identity is required.')
    components = value.get('components')
    if not isinstance(components, list) or not components:
        raise ClosureError('Reviewed Python and packaging artifacts are missing; no unpinned build is allowed.')
    names = set()
    for component in components:
        name = normalized(str(component.get('name', '')))
        if not name or name in names or not re.fullmatch(r'\d+\.\d+(?:\.\d+)*(?:[a-zA-Z0-9.+-]*)', str(component.get('version', ''))):
            raise ClosureError('Component identities must have unique names and exact versions.')
        names.add(name)
        diagnostic_observation = (value['profile'] in {'diagnostic', 'frontend-experiment'}
            and component.get('review_status') == 'observed-diagnostic'
            and component.get('native_closure') == 'unverified')
        diagnostic_observation |= (value['profile'] == 'runtime-experiment'
            and component.get('review_status') == 'observed-experiment'
            and component.get('native_closure') == 'unverified')
        if ((component.get('review_status') != 'approved' and not diagnostic_observation)
                or component.get('architecture') not in {'win-amd64', 'win32', 'any'}
                or not str(component.get('source', '')).startswith('https://')
                or not component.get('license_expression')
                or (component.get('native_closure') != 'reviewed' and not diagnostic_observation)):
            raise ClosureError('Source, license, architecture and native review are required: ' + name)
        checked_file(evidence, component.get('artifact'))
        licenses = component.get('licenses')
        if not isinstance(licenses, list) or not licenses:
            raise ClosureError('Complete hashed license/notice evidence is required: ' + name)
        for notice in licenses:
            checked_file(evidence, notice)
        installed = component.get('installed_files')
        if not isinstance(installed, list) or not installed:
            raise ClosureError('Exact installed build files must be bound to reviewed artifact bytes: ' + name)
        if check_host:
            prefix = Path(sys.base_prefix if name == 'cpython' else sys.prefix)
            for item in installed:
                checked_file(prefix, item)
            if name != 'cpython' and metadata.version(component['name']) != component['version']:
                raise ClosureError('Installed packaging/runtime version differs: ' + name)
    required = {'cpython', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools'}
    if not required <= names:
        raise ClosureError('Python/PyInstaller build closure is incomplete: ' + ', '.join(sorted(required - names)))
    python = next(item for item in components if normalized(item['name']) == 'cpython')
    if not python['version'].startswith('3.12.') or python['architecture'] != 'win-amd64':
        raise ClosureError('A reviewed maintained CPython 3.12 Windows x64 distribution is required.')
    if check_host:
        if sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'} or platform.architecture()[0] != '64bit':
            raise ClosureError('Build on Windows x64; cross-building from another platform is unsupported.')
        if platform.python_version() != python['version'] or digest(sys.executable) != value.get('python_executable_sha256'):
            raise ClosureError('The selected interpreter does not match the reviewed executable/version.')
        commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
        if commit != value['source_commit'] or dirty.strip():
            raise ClosureError('Build input must match a clean source commit.')
    if value['profile'] in {'runtime', 'runtime-experiment'}:
        gates = value.get('gates', {})
        if value['profile'] == 'runtime' and any(gates.get(name) != 'approved' for name in GATES):
            raise ClosureError('Full runtime closure remains incomplete; use an explicitly diagnostic candidate.')
        lock_names = set()
        for line in (source / 'requirements.lock.txt').read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                match = re.fullmatch(r'([^=]+)==([^; ]+)(?:; .*)?', line)
                if not match:
                    raise ClosureError('Unsupported Python lock syntax.')
                name, version = normalized(match[1]), match[2]
                lock_names.add(name)
                if not any(normalized(item['name']) == name and item['version'] == version for item in components):
                    raise ClosureError('Runtime wheel/version evidence is missing: ' + name)
        # Test packages remain build-only; their evidence still identifies the
        # exact provisioned environment, without collecting them in the spec.
    resources = value.get('resources', [])
    if not isinstance(resources, list):
        raise ClosureError('Resource evidence must be a file list.')
    for resource in resources:
        name = relative_resource(resource.get('path', ''))
        if Path(name).name.lower() in FORBIDDEN_NAMES or any(part.lower() in PRIVATE_PARTS for part in Path(name).parts):
            raise ClosureError('Private or proprietary resources must never be collected.')
        checked_file(evidence if value['profile'] in {'frontend-experiment', 'runtime-experiment'} else source, resource)
        if not resource.get('license_expression') or not resource.get('source') or not resource.get('version'):
            raise ClosureError('Resource source/version/license evidence is incomplete: ' + name)
    if value['profile'] in {'frontend-experiment', 'runtime-experiment'}:
        from backend.desktop_frontend import FrontendBuild, MANIFEST
        frontend = FrontendBuild(evidence / 'desktop')
        expected = {'desktop/' + name: digest(evidence / 'desktop' / name) for name in (*frontend.files, MANIFEST)}
        package = json.loads((source / 'package.json').read_text(encoding='utf-8'))
        if (frontend.value['source_commit'] != value['source_commit']
                or frontend.value['version'] != package['version']
                or frontend.value['lock_sha256'] != digest(source / 'package-lock.json')
                or {item['path']: item['sha256'] for item in resources if item['path'].startswith('desktop/')} != expected
                or len({item['path'] for item in resources}) != len(resources)
                or (value['profile'] == 'frontend-experiment' and len(resources) != len(expected))):
            raise ClosureError('Frontend candidate must collect exactly the verified public desktop tree, version and lock from this commit.')
    if value['profile'] == 'runtime-experiment':
        from record_runtime import RESOURCES, verified_nte, verified_codec, codec_identity
        helper = verified_nte(evidence, resources, value['source_commit'], source)
        codec = verified_codec(evidence, resources, value['source_commit'], source)
        codec_names = {'codecs/xiph-flac/' + name for name in (*codec.manifest['files'], 'codec-manifest.json')}
        helper_names = {'helpers/nte/' + name for name in (*helper.manifest['files'], 'helper-manifest.json')}
        helper_identity = {'nte': {'build_id': helper.manifest['build_id'], 'source_identity': helper.source_identity,
            'manifest_sha256': digest(evidence / 'helpers/nte/helper-manifest.json'), 'game_execution_approved': False}}
        pin = json.loads((source / 'packaging/runtime-bundle/python-supplier.json').read_text())
        if (value.get('python_supplier') != pin or python['version'] != pin['version']
                or python['artifact']['sha256'] != pin['sha256'] or python['source'] != pin['url']
                or value.get('runtime_lock_sha256') != digest(source / 'requirements.lock.txt')
                or value.get('helpers') != helper_identity
                or value.get('codecs') != codec_identity(codec)
                or {item['path'] for item in resources} != set(RESOURCES) | set(expected) | helper_names | codec_names):
            raise ClosureError('Integrated experiment supplier, lock or exact resource closure differs.')
        for resource in resources:
            if not resource['path'].startswith(('desktop/', 'helpers/', 'codecs/')) and digest(source / resource['path']) != resource['sha256']:
                raise ClosureError('Experimental resource differs from source.')
    if value['profile'] == 'runtime':
        required_resources = {'package.json', 'public/mobile-capture/games-data.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
            'assets/fireredvad/fireredvad_vad.onnx', 'assets/fireredvad/cmvn.ark',
            'assets/fireredvad/LICENSE', 'assets/fireredvad/NOTICE.md', 'assets/fireredvad/PROVENANCE.json'}
        if not required_resources <= {item['path'] for item in resources}:
            raise ClosureError('Full runtime resource/model/notice collection is incomplete.')
        raise ClosureError('Full runtime profile is not enabled: prebuilt helpers, host/update artifacts and exact collected-file closure remain incomplete.')
    return value


def inventory_output(folder):
    """Reject known prohibited files even for a quarantined diagnostic build."""
    result = []
    seen = set()
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ClosureError('Bundle links/reparse points are prohibited.')
        name = path.relative_to(folder).as_posix()
        relative_resource(name)
        folded = name.casefold()
        if folded in seen:
            raise ClosureError('Case-aliased bundle file names are prohibited.')
        seen.add(folded)
        if path.name.lower() in FORBIDDEN_NAMES or path.suffix.lower() in {'.dpapi', '.db', '.sqlite', '.mp3', '.wav', '.pak', '.pck', '.wem', '.bnk'}:
            raise ClosureError('Prohibited private/proprietary artifact: ' + name)
        if any(part.lower() in PRIVATE_PARTS for part in Path(name).parts):
            raise ClosureError('Private trees must never be collected: ' + name)
        if not path.is_file():
            continue
        result.append({'path': name, 'sha256': digest(path), 'bytes': path.stat().st_size})
    return result


def write_candidate(value, source, evidence, output):
    resources = {entry['path']: entry['sha256'] for entry in value.get('resources', [])}
    package = json.loads((source / 'package.json').read_text())
    runtime = value['profile'] in {'runtime', 'runtime-experiment'}
    manifest = {'schema': MANIFEST_SCHEMA, 'profile': value['profile'], 'version': package['version'],
        'source_commit': value['source_commit'], 'build_id': value['build_id'], 'resources': resources,
        'children': list(EXPERIMENT_CHILDREN) if value['profile'] == 'runtime-experiment' else list(CHILD_TARGETS) if runtime else ['frontend'] if value['profile'] == 'frontend-experiment' else [], 'r19_complete': False}
    internal = output / 'ProxyTranscriptRuntime' / '_internal'
    internal.mkdir(parents=True, exist_ok=True)
    (internal / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if runtime:
        asr = output / 'ProxyTranscriptAsr'
        target = output / 'ProxyTranscriptRuntime/asr'
        if target.exists():
            raise ClosureError('ASR target already exists; use a fresh output directory.')
        asr.rename(target)
        helper = {**manifest, 'children': ['asr'], 'resources': {}}
        (target / '_internal/runtime-manifest.json').write_text(json.dumps(helper, indent=2) + '\n', encoding='utf-8')
    # Full notices are copied from reviewed evidence, not inferred from package
    # labels. This folder is still quarantined until exact output review.
    import shutil
    notices = output / 'ProxyTranscriptRuntime/THIRD_PARTY'
    for component in value['components']:
        home = notices / normalized(component['name'])
        home.mkdir(parents=True, exist_ok=True)
        for notice in component['licenses']:
            path = checked_file(evidence, notice)
            target = home / notice['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    files = inventory_output(output / 'ProxyTranscriptRuntime')
    directories = sorted(path.relative_to(output / 'ProxyTranscriptRuntime').as_posix()
        for path in (output / 'ProxyTranscriptRuntime').rglob('*') if path.is_dir())
    proof = {'schema': 'proxy-runtime-candidate-v1', 'repository': 'Firebird55/Game-immersion-toolkit',
        'source_commit': value['source_commit'], 'version': package['version'], 'build_id': value['build_id'],
        'profile': value['profile'], 'r19_complete': False, 'redistribution_review': 'pending-exact-output',
        'native_acceptance': 'unavailable', 'signing': 'not-established', 'files': files, 'directories': directories,
        'components': [{key: item[key] for key in ('name', 'version', 'source', 'architecture', 'license_expression')}
                       for item in value['components']]}
    (output / 'CANDIDATE-PROVENANCE.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    if value['profile'] == 'runtime-experiment':
        # Public review metadata has only logical names and digests. Raw
        # receipts, installed host paths and complete license text stay private.
        inventory = {'schema': 'proxy-r19-runtime-inventory-v1', 'source_commit': value['source_commit'],
            'profile': value['profile'], 'build_id': value['build_id'], 'files': files, 'directories': directories,
            'file_count': len(files), 'bytes': sum(item['bytes'] for item in files),
            'components': [{'name': item['name'], 'version': item['version'],
                'architecture': item['architecture'], 'source': item['source'],
                'artifact_sha256': item['artifact']['sha256'],
                'notice_sha256': [notice['sha256'] for notice in item['licenses']],
                'rights_review': 'pending-exact-output'} for item in value['components']],
            'helpers': value.get('helpers', {}),
            'codecs': value.get('codecs', {}),
            'gates': {name: 'pending' for name in GATES}, 'r19_complete': False,
            'native_windows_11_acceptance': 'unavailable', 'installer': 'not-built'}
        (output / 'RUNTIME-INVENTORY.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('preflight', 'finalize'))
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        value = validate_inputs(json.loads(args.inputs.read_text(encoding='utf-8')), args.source.resolve(), args.evidence.resolve())
        if args.action == 'finalize':
            if args.output is None:
                raise ClosureError('Finalization requires an output directory.')
            write_candidate(value, args.source.resolve(), args.evidence.resolve(), args.output.resolve())
        print('Reviewed input gate passed; candidate remains quarantined and R19 acceptance incomplete.')
    except (ClosureError, OSError, ValueError, metadata.PackageNotFoundError) as error:
        print('Runtime build blocked: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
