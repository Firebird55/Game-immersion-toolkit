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


def validate_python_notice_delivery(component, source, evidence):
    """Notice-only completeness, never native ownership or rights approval."""
    from record_runtime import expected_python_notice_records
    pin = json.loads((source / 'packaging/runtime-bundle/python-supplier.json').read_text())
    expected = expected_python_notice_records(source, pin)
    for notice in expected:
        if notice not in component['licenses']:
            raise ClosureError('Runtime Python supplier notice delivery is missing or source-invalid.')
        if checked_file(evidence, notice).stat().st_size != notice['bytes']:
            raise ClosureError('Runtime Python supplier notice length differs from source.')


def validate_flatbuffers_notice_delivery(component, source, evidence):
    """Exact source-notice delivery, without promoting component rights."""
    from record_runtime import expected_flatbuffers_notice_records
    for notice in expected_flatbuffers_notice_records(evidence, source, component):
        if notice not in component['licenses']:
            raise ClosureError('Runtime Flatbuffers source notice delivery is missing or source-invalid.')
        if checked_file(evidence, notice).stat().st_size != notice['bytes']:
            raise ClosureError('Runtime Flatbuffers source notice length differs from source.')


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
    if value['profile'] in {'runtime-experiment', 'runtime'}:
        validate_python_notice_delivery(python, source, evidence)
        flatbuffers = next((item for item in components if normalized(item['name']) == 'flatbuffers'), None)
        if flatbuffers is None:
            raise ClosureError('The locked Flatbuffers source-notice component is missing.')
        validate_flatbuffers_notice_delivery(flatbuffers, source, evidence)
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


def validate_codec_output(value, source, evidence, output):
    """Reject unintended codec copies before publishing any candidate metadata."""
    from record_runtime import verified_codec
    from backend.prebuilt_readers import _no_links
    codec = verified_codec(evidence, value.get('resources', []), value['source_commit'], source)
    expected = {'ProxyTranscriptRuntime/_internal/codecs/xiph-flac/' + name: codec.manifest['files'][name]
        for name in ('flac.exe', 'FLAC.dll')}
    actual = set()
    for path in output.rglob('*'):
        if path.name.casefold() not in {'flac.exe', 'flac.dll'}:
            continue
        name = path.relative_to(output).as_posix()
        if name not in expected:
            raise ClosureError('Codec output contains an extra or misplaced native file.')
        _no_links(path.absolute())
        entry = expected[name]
        if not path.is_file() or path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ClosureError('Codec output differs from its verified native input.')
        actual.add(name)
    if actual != set(expected):
        raise ClosureError('Codec output is missing its exact isolated native files.')


def validate_native_collection(value, evidence, output, files, input_manifest):
    """Bind observed real TOC inputs to the existing output inventory, not rights."""
    from record_runtime import (NativeCollectionError, NATIVE_SOURCE_INPUTS, NATIVE_GENERATED,
        native_headers, native_pending, native_path, native_file_identity, native_supplier_index,
        native_system_directory, native_source_record, native_sorted_owners)
    from native_ownership import _relative, _sha
    try:
        headers = native_headers(value)
        path = native_path(output / NATIVE_SOURCE_INPUTS)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise NativeCollectionError('invalid-snapshot')
        raw = path.read_bytes()
        def unique(items):
            result = {}
            for key, item in items:
                if key in result:
                    raise NativeCollectionError('invalid-snapshot')
                result[key] = item
            return result
        snapshot = json.loads(raw, object_pairs_hook=unique)
        expected = {'schema': 'proxy-r19-native-collection-inputs-v1', **headers, **native_pending(),
            'raw_paths_published': False, 'raw_toc_published': False}
        if (set(snapshot) != set(expected) | {'build_inputs', 'records'}
                or any(type(snapshot[key]) is not type(item) or snapshot[key] != item for key, item in expected.items())
                or not isinstance(snapshot['records'], list) or not 2 <= len(snapshot['records']) <= 20000
                or input_manifest is None):
            raise NativeCollectionError('invalid-snapshot')
        manifest = native_path(input_manifest)
        if (native_file_identity(manifest) != snapshot['build_inputs']
                or json.loads(manifest.read_bytes()) != value):
            raise NativeCollectionError('source-changed')
        index = native_supplier_index(value, evidence)
        system = native_system_directory()
        observed, folded = {}, set()
        for record in snapshot['records']:
            if not isinstance(record, dict) or set(record) != {'path', 'process', 'processing', 'bytes', 'sha256', 'source'}:
                raise NativeCollectionError('invalid-snapshot')
            name = _relative(record['path']); checksum = _sha(record['sha256'])
            if (name.casefold() in folded or record['process'] not in NATIVE_GENERATED
                    or type(record['bytes']) is not int or record['bytes'] < 0
                    or Path(name).suffix.lower() not in {'.exe', '.dll', '.pyd'}):
                raise NativeCollectionError('invalid-snapshot')
            folded.add(name.casefold())
            identity = {'bytes': record['bytes'], 'sha256': checksum}
            source_record = record['source']
            if not isinstance(source_record, dict):
                raise NativeCollectionError('invalid-snapshot')
            if record['processing'] == 'pyinstaller-generated-executable':
                if (name != NATIVE_GENERATED[record['process']] or
                        source_record != {'role': 'generated-processing-observed', 'internals_provenance': 'unverified'}):
                    raise NativeCollectionError('invalid-snapshot')
            else:
                prefix = ('asr/' if record['process'] == 'asr' else '') + '_internal/'
                if (not name.startswith(prefix) or record['processing'] not in {'analysis-native', 'explicit-native-resource'}):
                    raise NativeCollectionError('invalid-snapshot')
                if source_record.get('role') == 'declared-supplier-observed':
                    candidates = [entry for entry in index.values()
                        if native_sorted_owners(entry['owners']) == source_record.get('resolved_inputs')]
                    if len(candidates) != 1:
                        raise NativeCollectionError('unbound-supplier-member')
                    origin = candidates[0]['path']
                elif source_record.get('role') == 'windows-system-observed':
                    origin = system / _relative(source_record.get('system_member', ''))
                else:
                    raise NativeCollectionError('other-host-unresolved')
                _origin, current, rebuilt = native_source_record(origin, index, system)
                if current != identity or rebuilt != source_record:
                    raise NativeCollectionError('source-changed')
                if (record['processing'] == 'explicit-native-resource' and
                        (source_record['role'] != 'declared-supplier-observed' or
                         not any(item['kind'] == 'resource' for item in source_record['resolved_inputs']))):
                    raise NativeCollectionError('unbound-supplier-member')
            observed[name] = record
        native = {entry['path']: entry for entry in files if Path(entry['path']).suffix.lower() in {'.dll', '.exe', '.pyd'}}
        if set(native) != set(observed) or not set(NATIVE_GENERATED.values()) <= set(observed):
            raise NativeCollectionError('missing-source')
        for name, entry in native.items():
            expected_identity = {key: observed[name][key] for key in ('bytes', 'sha256')}
            if {key: entry[key] for key in expected_identity} != expected_identity:
                raise NativeCollectionError('unexpected-transformation')
            if native_file_identity(output / 'ProxyTranscriptRuntime' / name) != expected_identity:
                raise NativeCollectionError('output-mismatch')
        return {'schema': 'proxy-r19-native-collection-v1', **headers, **native_pending(),
            'input_snapshot': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
            'build_inputs': snapshot['build_inputs'], 'records': [observed[name] for name in sorted(observed)],
            'scope': 'Observed TOC/source/output bytes only; generated internals, incorporated code, rights and native acceptance remain unverified',
            'raw_paths_published': False, 'raw_toc_published': False}
    except Exception as error:
        from record_runtime import native_failure
        native_failure(value, output, 'finalize', error)
        raise NativeCollectionError(error.code if isinstance(error, NativeCollectionError) else 'invalid-snapshot') from None


def _native_image_diagnostic(error):
    """Revalidate finite parser labels; never serialize exception attributes."""
    from native_images import NativeImageError
    unavailable = {'status': 'unavailable'}
    if type(error) is not NativeImageError:
        return unavailable
    selected = error.__dict__.get('selected')
    context = error.__dict__.get('context')
    if (type(selected) is not dict or len(selected) != 4 or set(selected) != {'ordinal', 'count', 'tree', 'role'}
            or type(selected['ordinal']) is not int or type(selected['count']) is not int
            or not 2 <= selected['count'] <= 20000 or not 1 <= selected['ordinal'] <= selected['count']
            or type(selected['tree']) is not str or len(selected['tree']) > 4 or selected['tree'] not in {'main', 'asr'}
            or type(selected['role']) is not str or len(selected['role']) > 15
            or selected['role'] not in {'runtime-primary', 'asr-primary', 'helper', 'other-native'}
            or selected['role'] == 'runtime-primary' and selected['tree'] != 'main'
            or selected['role'] == 'asr-primary' and selected['tree'] != 'asr'):
        return unavailable
    imports = None
    if context is not None:
        phases = {'directory': {'directory-layout'},
            'descriptor': {'directory-too-short', 'descriptor-range', 'entry-limit', 'delay-attributes'},
            'pointer': {'required-pointer-missing', 'pointer-range'},
            'name': {'name-range', 'name-empty-or-unterminated', 'name-non-ascii', 'name-format'},
            'duplicate': {'duplicate-module-name'}, 'termination': {'missing-terminator'}}
        if (type(context) is not dict or len(context) != 3 or set(context) != {'import_table', 'import_phase', 'import_reason'}
                or any(type(context[key]) is not str or len(context[key]) > 32 for key in context)
                or context['import_table'] not in {'normal', 'delay'}
                or context['import_phase'] not in phases
                or context['import_reason'] not in phases[context['import_phase']]
                or context['import_reason'] == 'delay-attributes' and context['import_table'] != 'delay'):
            return unavailable
        mapping_reasons = {'directory-layout', 'descriptor-range', 'pointer-range', 'name-range'}
        allowed_codes = {'malformed-pe', 'ambiguous-rva'} if context['import_reason'] in mapping_reasons else {'invalid-import'}
        if error.__dict__.get('code') not in allowed_codes:
            return unavailable
        imports = {key: context[key] for key in ('import_table', 'import_phase', 'import_reason')}
    elif error.__dict__.get('code') == 'invalid-import':
        return unavailable
    return {'status': 'available', 'selected_native': {key: selected[key] for key in ('ordinal', 'count', 'tree', 'role')},
        'imports': imports}


def validate_native_images(value, output, inventory):
    """Mandatory static image review, independent of native-source attribution.

    Only complete parser observations reach the success sidecar. Failure
    metadata contains fixed fields/codes, never an exception or import spelling.
    Neither outcome authorizes production execution or redistribution.
    """
    from native_images import CODES, NativeImageError, review_native_images
    from record_runtime import native_headers, native_pending, native_path, write_native_json
    headers = {'source_commit': None, 'build_id': None, 'profile': 'runtime-experiment'}
    try:
        headers = native_headers(value)
        if any(inventory.get(key) != item for key, item in headers.items()):
            raise NativeImageError('invalid-inventory')
        output = native_path(output, directory=True)
        report = review_native_images(inventory, output / 'RUNTIME-INVENTORY.json', output / 'ProxyTranscriptRuntime')
        if any(report.get(key) != item for key, item in headers.items()):
            raise NativeImageError('invalid-inventory')
        write_native_json(output, 'NATIVE-IMAGES.json', report)
        return report
    except Exception as error:
        code = error.__dict__.get('code') if type(error) is NativeImageError else None
        code = code if isinstance(code, str) and code in CODES else 'observation-failed'
        diagnostic = {'status': 'unavailable'}
        if code != 'observation-failed':
            try:
                diagnostic = _native_image_diagnostic(error)
            except Exception:
                pass  # An unusable diagnostic cannot bypass or expose refusal.
        failure = {'schema': 'proxy-r19-native-images-failure-v1', **headers, **native_pending(),
            'status': 'failed', 'phase': 'finalize', 'failure_code': code,
            'diagnostic': diagnostic,
            'raw_paths_published': False, 'raw_exceptions_published': False, 'raw_imports_published': False}
        try:
            write_native_json(output, 'NATIVE-IMAGES-FAILED.json', failure)
        except Exception:
            pass  # A failed metadata channel cannot convert refusal into success.
        raise ClosureError('Native image review blocked: ' + code + '.') from None


def write_candidate(value, source, evidence, output, *, input_manifest=None):
    resources = {entry['path']: entry['sha256'] for entry in value.get('resources', [])}
    package = json.loads((source / 'package.json').read_text())
    runtime = value['profile'] in {'runtime', 'runtime-experiment'}
    if runtime:
        validate_codec_output(value, source, evidence, output)
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
    native_collection = None
    if value['profile'] == 'runtime-experiment':
        native_collection = validate_native_collection(value, evidence, output, files, input_manifest)
    ownership = None
    if value['profile'] == 'runtime-experiment':
        from native_ownership import native_input_ownership
        ownership = native_input_ownership(value['components'], value.get('resources', []), files)
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
            'native_input_ownership': ownership,
            'gates': {name: 'pending' for name in GATES}, 'r19_complete': False,
            'native_windows_11_acceptance': 'unavailable', 'installer': 'not-built'}
        (output / 'RUNTIME-INVENTORY.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
        from record_runtime import NATIVE_SOURCE_FINAL, write_native_json
        native_collection['inventory_sha256'] = digest(output / 'RUNTIME-INVENTORY.json')
        try:
            write_native_json(output, NATIVE_SOURCE_FINAL, native_collection)
        except Exception as error:
            from record_runtime import native_failure, NativeCollectionError
            native_failure(value, output, 'finalize', error)
            raise NativeCollectionError('observation-failed') from None
        validate_native_images(value, output, inventory)


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
            write_candidate(value, args.source.resolve(), args.evidence.resolve(), args.output.resolve(),
                input_manifest=args.inputs.absolute())
        print('Reviewed input gate passed; candidate remains quarantined and R19 acceptance incomplete.')
    except (ClosureError, OSError, ValueError, metadata.PackageNotFoundError) as error:
        print('Runtime build blocked: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
