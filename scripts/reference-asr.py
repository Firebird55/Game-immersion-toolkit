"""Private build-host experiment; never selected by a production runtime profile.

Download-free preparation and evidence collection for the separately identified
TTS-disabled sherpa binding. Raw archives/build logs/inventories stay private.
"""
import argparse
import base64
import csv
import hashlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'packaging/asr/sherpa-reference.json'
CMAKE_TOOL_POLICY = 'packaging/build-tools/cmake-4.4.5-windows-x64.json'
SOURCE_FILES = (MANIFEST, 'packaging/asr/tts-off-python-symbols.patch',
                'packaging/asr/SHERPA-LICENSE.txt', 'packaging/asr/SHERPA-PATCH-NOTICE.txt',
                'scripts/reference-asr.py', 'scripts/build-reference-asr.ps1',
                'scripts/probe-reference-asr.py',
                'packaging/runtime-bundle/python-supplier.json',
                CMAKE_TOOL_POLICY, 'scripts/pinned-build-cmake.py',
                'backend/windows_preparation_process.py', 'LICENSE')

BUILD_PHASES = frozenset({'build-preflight', 'source-validation', 'toolchain-validation',
    'vs-installation-origin', 'tool-root-schema', 'tool-root-filesystem',
    'python-interpreter-origin', 'python-supplier-bytes', 'cmake-version-review',
    'cmake-pinned-input', 'final-cmake-pinned-input',
    'toolchain-seal', 'probe-dependency-preparation', 'build-environment', 'cmake-configure',
    'build-graph-review', 'native-build', 'native-output-review', 'candidate-assembly',
    'probe-decode', 'probe-wrong-shape', 'probe-corrupt', 'final-source-review',
    'final-candidate-review', 'final-toolchain-review', 'source-commit-review', 'success-receipt'})
PHASE_LOGS = {'cmake-configure': 'configure.log', 'native-build': 'build.log',
    'probe-decode': 'probe-decode.log', 'probe-wrong-shape': 'probe-wrong-shape.log',
    'probe-corrupt': 'probe-corrupt.log'}
# Only these fixed public code labels may leave private compiler/MSBuild logs.
# Unrecognized errors produce a category, never the unknown token or message.
KNOWN_BUILD_CODES = frozenset({'C1001', 'C1010', 'C1083', 'C1189', 'C1900', 'C2001',
    'C2011', 'C2027', 'C2039', 'C2061', 'C2065', 'C2079', 'C2084', 'C2100', 'C2131',
    'C2143', 'C2146', 'C2171', 'C2198', 'C2248', 'C2338', 'C2440', 'C2491', 'C2512',
    'C2530', 'C2660', 'C2664', 'C2665', 'C2672', 'C2678', 'C2872', 'C3646', 'C3861',
    'C4996', 'D8016', 'D8021', 'D8022', 'LNK1104', 'LNK1107', 'LNK1112', 'LNK1120',
    'LNK1181', 'LNK1257', 'LNK2001', 'LNK2005', 'LNK2019', 'LNK2038',
    'MSB1009', 'MSB1011', 'MSB3073', 'MSB3644', 'MSB4018', 'MSB4019', 'MSB4057',
    'MSB6003', 'MSB6006', 'MSB8020', 'MSB8036'})
_BUILD_PHASE = 'build-preflight'
_BUILD_SOURCE_COMMIT = None
_BUILD_CMAKE_OBSERVATION = None


def build_phase(value):
    global _BUILD_PHASE
    if value not in BUILD_PHASES:
        raise ValueError('Unknown private ASR build phase.')
    _BUILD_PHASE = value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate evidence key.')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_json)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def no_links(path):
    for item in (path, *path.parents):
        if (item.is_symlink() or getattr(item, 'is_junction', lambda: False)()
                or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)):
            raise ValueError('Links and reparse points are not experiment inputs.')


def safe_name(name):
    if (not name or '\\' in name or ':' in name or PurePosixPath(name).is_absolute()
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or any(p in {'', '.', '..'} or p.endswith((' ', '.'))
                   or re.match(r'^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)', p, re.I)
                   for p in name.split('/'))):
        raise ValueError('Non-canonical experiment input path.')
    return name


def attributes(data):
    return {'bytes': len(data), 'sha256': sha(data)}


def inventory(root):
    no_links(root)
    result = {}
    for path in sorted(root.rglob('*')):
        no_links(path)
        name = safe_name(path.relative_to(root).as_posix())
        if path.is_file():
            result[name] = attributes(path.read_bytes())
        elif not path.is_dir():
            raise ValueError('Non-regular experiment input.')
    return result


def pin():
    value = read_json(ROOT / MANIFEST)
    if (value['schema'] != 'proxy-r19-asr-source-reference-v1'
            or value.get('cmake_build_tool_policy') != CMAKE_TOOL_POLICY
            or value['gates'] != {'production_execution_allowed': False,
                'runtime_collection_allowed': False, 'redistribution_review': 'pending-exact-output',
                'native_windows_11_acceptance': 'unavailable',
                'trained_model_acceptance': 'not-requested-no-asr-model-weights', 'r19_complete': False}):
        raise ValueError('ASR experiment identity or pending gates differ.')
    return value


def archive_files(path, item):
    """Validate before writing; main source deliberately omits unrelated links.

    Whole original archives are retained privately and bound by exact hash. Every
    archive name is canonical; every selected entry must be a regular file/dir.
    No general link exemption or arbitrary archive is accepted.
    """
    no_links(path)
    if attributes(path.read_bytes()) != {'bytes': item['bytes'], 'sha256': item['sha256']}:
        raise ValueError('An exact source/dependency archive is missing or changed.')
    result, aliases, spelling, total = {}, set(), {}, 0
    archive = zipfile.ZipFile(path) if path.suffix == '.zip' else tarfile.open(path)
    with archive:
        members = archive.infolist() if isinstance(archive, zipfile.ZipFile) else archive.getmembers()
        if len(members) > 20000:
            raise ValueError('Source/dependency archive is too large.')
        for member in members:
            is_zip = isinstance(member, zipfile.ZipInfo)
            raw_name = member.filename if is_zip else member.name
            name = safe_name(raw_name.rstrip('/'))
            parts = name.split('/', 1)
            if parts[0] != item['archive_root']:
                raise ValueError('Source/dependency archive root differs.')
            relative = parts[1] if len(parts) == 2 else ''
            selected = not item['selected_prefixes'] or any(
                relative == p or relative.startswith(p + '/') for p in item['selected_prefixes'])
            if not selected or not relative:
                continue
            for n in range(1, len(relative.split('/')) + 1):
                prefix = '/'.join(relative.split('/')[:n])
                previous = spelling.setdefault(prefix.casefold(), prefix)
                if previous != prefix:
                    raise ValueError('Case-aliased source/dependency directory.')
            if relative.casefold() in aliases:
                raise ValueError('Duplicate or case-aliased source/dependency entry.')
            aliases.add(relative.casefold())
            if is_zip:
                mode = member.external_attr >> 16
                directory, regular = member.is_dir(), stat.S_IFMT(mode) in (0, stat.S_IFREG)
                size = member.file_size
            else:
                directory, regular, size = member.isdir(), member.isfile(), member.size
            if directory:
                continue
            if not regular or size > 32 * 1024 * 1024:
                raise ValueError('Selected source/dependency entry is not a bounded regular file.')
            total += size
            if total > 160 * 1024 * 1024:
                raise ValueError('Selected source/dependency bytes exceed the experiment bound.')
            data = archive.read(member) if is_zip else archive.extractfile(member).read()
            if len(data) != size:
                raise ValueError('Truncated source/dependency entry.')
            result[relative] = data
    if not result:
        raise ValueError('Empty source/dependency archive.')
    # Also reject file/directory aliases before creating anything.
    names = {name.casefold() for name in result}
    if any('/'.join(name.split('/')[:n]).casefold() in names
           for name in result for n in range(1, len(name.split('/')))):
        raise ValueError('Source/dependency file is used as a directory.')
    if any(attributes(result.get(name, b'')) != expected for name, expected in item['notices'].items()):
        raise ValueError('Source/dependency notice bytes differ.')
    return result


def patched_source(data, patch_pin):
    patch = ROOT / patch_pin['file']
    if sha(patch.read_bytes()) != patch_pin['sha256'] or sha(data) != patch_pin['before_sha256']:
        raise ValueError('TTS-off patch or its exact upstream base differs.')
    # Apply only the two recorded additions; no external patch program/config.
    result = data.replace(b'  /* Define "empty" TTS symbols */\n',
        b'  /* Define "empty" TTS symbols */\n  m.attr("GenerationConfig") = py::none();\n')
    result = result.replace(b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n',
        b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n'
        b'  m.attr("OfflineTtsSupertonicModelConfig") = py::none();\n')
    if sha(result) != patch_pin['after_sha256']:
        raise ValueError('TTS-off patch result differs.')
    return result


def verify_patch_notices(policy):
    upstream = next(i for i in policy['inputs'] if i['name'] == 'sherpa-onnx')
    if (policy['patch_notices'][policy['patch']['license_file']] != upstream['notices']['LICENSE']
            or any(attributes((ROOT / name).read_bytes()) != expected
                   for name, expected in policy['patch_notices'].items())):
        raise ValueError('Public patch attribution or complete original Apache license differs.')


def prepare(inputs, output):
    policy = pin()
    inputs, output = Path(inputs).absolute(), Path(output).absolute()
    no_links(inputs); no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh private ASR experiment directory.')
    verify_patch_notices(policy)
    prepared = {item['name']: archive_files(inputs / item['filename'], item)
                for item in policy['inputs']}
    prepared['sherpa-onnx'][policy['patch']['target']] = patched_source(
        prepared['sherpa-onnx'][policy['patch']['target']], policy['patch'])
    source_inputs = {name: attributes((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    # All source/archive/notice/patch checks finish before the first output write.
    output.mkdir(parents=True)
    for item in policy['inputs']:
        shutil.copyfile(inputs / item['filename'], output / item['filename'])
        for name, data in prepared[item['name']].items():
            dest = output / 'sources' / item['name'] / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        for name in item['notices']:
            dest = output / 'notices' / item['name'] / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(prepared[item['name']][name])
    for name in SOURCE_FILES:
        dest = output / 'recipes' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    expected = inventory(output / 'sources')
    write_json(output / 'PRIVATE-SOURCE-INVENTORY.json', expected)
    receipt = {'schema': policy['schema'], 'identity': policy['identity'],
        'manifest_sha256': sha((ROOT / MANIFEST).read_bytes()), 'source_inputs': source_inputs,
        'source_inventory_sha256': sha(canonical(expected)), 'source_file_count': len(expected),
        'input_archives': {i['name']: {'sha256': i['sha256'], 'bytes': i['bytes'],
            'kind': i['kind'], 'url': i['url']} for i in policy['inputs']},
        'patch': policy['patch'], 'patch_notices': policy['patch_notices'],
        'configuration': policy['cmake'], 'gates': policy['gates'],
        'python_supplier_pin': read_json(ROOT / policy['python_supplier_manifest']),
        'numpy_probe_dependency_pin': policy['numpy'],
        'cmake_build_tool_policy': policy['cmake_build_tool_policy'],
        'status': 'prepared-not-built', 'rights_approval': False}
    write_json(output / 'PREPARED.json', receipt)
    return receipt


def verify_sources(output):
    policy, output = pin(), Path(output).absolute()
    receipt = read_json(output / 'PREPARED.json')
    verify_patch_notices(policy)
    expected = read_json(output / 'PRIVATE-SOURCE-INVENTORY.json')
    source_inputs = {n: attributes((ROOT / n).read_bytes()) for n in SOURCE_FILES}
    if (receipt['manifest_sha256'] != sha((ROOT / MANIFEST).read_bytes())
            or receipt['source_inputs'] != source_inputs
            or inventory(output / 'recipes') != source_inputs
            or receipt.get('cmake_build_tool_policy') != policy['cmake_build_tool_policy']
            or receipt['source_inventory_sha256'] != sha(canonical(expected))
            or inventory(output / 'sources') != expected or receipt['gates'] != policy['gates']):
        raise ValueError('Prepared ASR source, recipes or gates changed.')
    for item in policy['inputs']:
        archive = output / item['filename']; no_links(archive)
        if attributes(archive.read_bytes()) != {'bytes': item['bytes'], 'sha256': item['sha256']}:
            raise ValueError('Retained exact input archive changed.')
        for name, expected_notice in item['notices'].items():
            notice = output / 'notices' / item['name'] / name; no_links(notice)
            if attributes(notice.read_bytes()) != expected_notice:
                raise ValueError('Retained input notice changed.')
    return receipt


def cmake_arguments(output, python):
    output, python = Path(output).absolute(), Path(python).absolute()
    verify_sources(output)
    args = [f'-D{key}={value}' for key, value in pin()['cmake'].items()]
    args += [f'-DFETCHCONTENT_SOURCE_DIR_{item["fetchcontent_name"].upper()}=' +
             (output / 'sources' / item['name']).as_posix()
             for item in pin()['inputs'] if item['fetchcontent_name']]
    args += [f'-DPython_EXECUTABLE={python.as_posix()}', f'-DPYTHON_EXECUTABLE={python.as_posix()}',
             f'-DPython_ROOT_DIR={python.parent.as_posix()}',
             f'-DPython_INCLUDE_DIR={(python.parent / "include").as_posix()}',
             f'-DPython_LIBRARY={(python.parent / "libs/python312.lib").as_posix()}',
             '-DPython_FIND_REGISTRY=NEVER', '-DCMAKE_FIND_USE_CMAKE_ENVIRONMENT_PATH=OFF',
             '-DCMAKE_FIND_USE_SYSTEM_ENVIRONMENT_PATH=OFF',
             '-DCMAKE_PREFIX_PATH=', '-DCMAKE_TOOLCHAIN_FILE=', '-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=']
    return args


def verify_trace(path, output):
    """Require the exact selected FetchContent set, no undeclared downloads.

    CMake trace/logs remain private. This bounded source-graph check does not
    claim an OS network sandbox or blanket absence of runtime LoadLibrary.
    """
    output = Path(output).absolute()
    expected = {i['fetchcontent_name'] for i in pin()['inputs'] if i['fetchcontent_name']}
    declared, populated = set(), set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        command, args = event.get('cmd', '').casefold(), event.get('args', [])
        if not command:
            continue
        if command == 'file' and args and args[0].casefold() in {'download', 'upload'}:
            raise ValueError('The ASR build attempted an undeclared network transfer.')
        if command == 'fetchcontent_declare' and args:
            name = args[0].casefold()
            if name not in expected:
                raise ValueError('The ASR build declared an unreviewed source dependency.')
            declared.add(name)
        if command in {'fetchcontent_populate', 'fetchcontent_makeavailable'} and args:
            name = args[0].casefold()
            if name not in expected:
                raise ValueError('The ASR build populated an unreviewed source dependency.')
            populated.add(name)
        if command == 'execute_process' and any(re.search(r'(?i)(?:https?://|(?:^|[/\\])(?:curl|wget)(?:\.exe)?$)', str(a)) for a in args):
            raise ValueError('The ASR build attempted an unreviewed downloader.')
    if declared != expected or populated != expected:
        raise ValueError('The observed ASR source dependency graph differs.')
    return {'declared': sorted(declared), 'populated': sorted(populated),
            'no_undeclared_fetch_observed': True, 'network_sandbox': False}


def verify_cache(path, output):
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([^#/:][^:]*):[^=]+=(.*)', line)
        if match:
            if match[1] in values: raise ValueError('Duplicate CMake cache observation.')
            values[match[1]] = match[2]
    if any(values.get(key) != expected for key, expected in pin()['cmake'].items()):
        raise ValueError('The observed ASR configuration differs from the fixed recipe.')
    for item in pin()['inputs']:
        name = item['fetchcontent_name']
        if name and Path(values.get('FETCHCONTENT_SOURCE_DIR_' + name.upper(), '')).resolve() != (output / 'sources' / item['name']).resolve():
            raise ValueError('The observed ASR source override differs from its exact prepared input.')


def validate_tool_root_schema(roots):
    required = {'vc', 'vc-auxiliary', 'msbuild', 'sdk-include', 'sdk-lib', 'sdk-bin', 'cmake', 'python'}
    if (not isinstance(roots, dict) or not required <= set(roots)
            or set(roots) - required - {'netfx-include', 'netfx-lib'}):
        raise ValueError('Incomplete explicit toolchain roots.')
    # Check all JSON value types before constructing even the first Path. A
    # PowerShell command-discovery array must never become an implicit choice.
    if any(not isinstance(value, str) or not value.strip()
           or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in roots.values()):
        raise ValueError('Every explicit tool root must be one directory string.')


def validate_tool_roots(roots):
    validate_tool_root_schema(roots)
    for value in roots.values():
        path = Path(value)
        no_links(path)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError('Every explicit tool root must be one existing absolute directory.')


def numeric_version(value):
    return value if isinstance(value, str) and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4}', value) else None


def safe_cmake_observation():
    """Project only bounded values, including if a caller alters private state."""
    value = _BUILD_CMAKE_OBSERVATION
    if not isinstance(value, dict):
        return None
    result = {'expected_version': numeric_version(value.get('expected_version')),
        'observed_version': numeric_version(value.get('observed_version')), 'executable': None}
    executable = value.get('executable')
    if (isinstance(executable, dict) and type(executable.get('bytes')) is int
            and 0 < executable['bytes'] <= 512 * 1024 * 1024
            and isinstance(executable.get('sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', executable['sha256'])):
        result['executable'] = {'bytes': executable['bytes'], 'sha256': executable['sha256']}
    return result


def observe_cmake_version(executable, expected):
    global _BUILD_CMAKE_OBSERVATION
    _BUILD_CMAKE_OBSERVATION = {'expected_version': numeric_version(expected),
        'observed_version': None, 'executable': None}
    no_links(executable)
    if not executable.is_file() or numeric_version(expected) is None:
        raise ValueError('The explicit CMake executable or numeric version constraint is unavailable.')
    _BUILD_CMAKE_OBSERVATION['executable'] = attributes(executable.read_bytes())
    output = subprocess.check_output([str(executable), '--version'], text=True,
        stderr=subprocess.STDOUT, timeout=30)
    first = output.splitlines()[0] if output.splitlines() else ''
    match = re.fullmatch(r'cmake version ([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4})', first)
    if match:
        _BUILD_CMAKE_OBSERVATION['observed_version'] = match[1]
    if first != 'cmake version ' + expected:
        raise ValueError('The required CMake version is unavailable.')
    if attributes(executable.read_bytes()) != _BUILD_CMAKE_OBSERVATION['executable']:
        raise ValueError('The observed CMake executable changed during its version query.')
    return safe_cmake_observation()


def verify_pinned_cmake(root, payload):
    """Reuse the common exact ZIP/tree verifier; no native execution or fallback."""
    if root is None:
        raise ValueError('The separate verified CMake container is required.')
    spec = importlib.util.spec_from_file_location('r19_shared_pinned_cmake', ROOT / 'scripts/pinned-build-cmake.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if module.POLICY.resolve() != (ROOT / pin()['cmake_build_tool_policy']).resolve():
        raise ValueError('The shared CMake verifier policy differs from the ASR source binding.')
    supplier = module.policy()
    if supplier['version'] != pin()['toolchain']['cmake_version']:
        raise ValueError('The pinned build tool differs from the ASR version constraint.')
    receipt = module.verify(Path(root))
    if Path(payload).resolve() != module.payload_root(root).resolve():
        raise ValueError('The selected CMake payload is outside the verified container.')
    return receipt


def seal_toolchain(roots):
    """Hash exact bytes under explicitly selected tool roots; keep file list private."""
    validate_tool_roots(roots)
    values = {name: inventory(Path(path).absolute()) for name, path in sorted(roots.items())}
    if any(not files for files in values.values()):
        raise ValueError('An explicit toolchain root is empty.')
    return values


def toolchain_summary(value):
    return {name: {'sha256': sha(canonical(files)), 'file_count': len(files),
                   'bytes': sum(f['bytes'] for f in files.values())}
            for name, files in value.items()}


def python_files(archive):
    supplier = read_json(ROOT / pin()['python_supplier_manifest'])
    archive = Path(archive).absolute(); no_links(archive)
    return archive_files(archive, {'bytes': archive.stat().st_size,
        'sha256': supplier['sha256'], 'archive_root': 'python',
        'selected_prefixes': [], 'notices': {}})


def prepare_python(archive, output):
    """Extract only the exact existing supplier pin; not supplier approval."""
    output = Path(output).absolute(); no_links(output)
    if output.exists():
        raise ValueError('A fresh separate Python directory is required.')
    files = python_files(archive)
    for name, data in files.items():
        dest = output / 'python' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return output / 'python' / 'python.exe'


def verify_python(inputs, root):
    supplier = read_json(ROOT / pin()['python_supplier_manifest'])
    expected = {name: attributes(data) for name, data in python_files(Path(inputs) / supplier['archive']).items()}
    if inventory(Path(root)) != expected:
        raise ValueError('The actual build/probe Python differs from the exact supplier archive.')


def prepare_numpy(inputs, output):
    item = pin()['numpy']
    wheel = Path(inputs) / item['filename']
    no_links(wheel); no_links(output)
    if output.exists() or attributes(wheel.read_bytes()) != {'bytes': item['bytes'], 'sha256': item['sha256']}:
        raise ValueError('Exact separate NumPy probe dependency required.')
    files, aliases = {}, set()
    with zipfile.ZipFile(wheel) as archive:
        if (len(archive.infolist()) > 2000
                or sum(m.file_size for m in archive.infolist()) > 256 * 1024 * 1024):
            raise ValueError('NumPy probe wheel exceeds the bounded inventory.')
        for member in archive.infolist():
            name = safe_name(member.filename.rstrip('/'))
            if name.casefold() in aliases or member.file_size > 64 * 1024 * 1024:
                raise ValueError('Unsupported NumPy probe wheel inventory.')
            aliases.add(name.casefold())
            if member.is_dir():
                continue
            if stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError('Non-regular NumPy probe wheel entry.')
            files[name] = archive.read(member)
    if sum(map(len, files.values())) > 256 * 1024 * 1024 or len(files) > 2000:
        raise ValueError('NumPy probe wheel exceeds the bounded inventory.')
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return inventory(output)


def pe_evidence(data):
    """Read normal/delay imports and named exports without executing native code."""
    def u16(p): return struct.unpack_from('<H', data, p)[0]
    def u32(p): return struct.unpack_from('<I', data, p)[0]
    def u64(p): return struct.unpack_from('<Q', data, p)[0]
    pe = u32(60)
    opt = pe + 24
    if data[:2] != b'MZ' or data[pe:pe + 4] != b'PE\0\0' or u16(pe + 4) != 0x8664 or u16(opt) != 0x20b:
        raise ValueError('An x64 PE32+ artifact is required.')
    sections = [(u32(opt + u16(pe + 20) + n * 40 + 12),
                 max(u32(opt + u16(pe + 20) + n * 40 + 8), u32(opt + u16(pe + 20) + n * 40 + 16)),
                 u32(opt + u16(pe + 20) + n * 40 + 20)) for n in range(u16(pe + 6))]
    def offset(rva):
        for va, size, raw in sections:
            if va <= rva < va + size and raw + rva - va < len(data):
                return raw + rva - va
        raise ValueError('Unmapped PE address.')
    def string(rva):
        start = offset(rva)
        end = data.index(0, start, min(len(data), start + 1024))
        result = data[start:end].decode('ascii')
        if any(ord(c) < 32 or ord(c) > 126 for c in result):
            raise ValueError('Invalid PE name.')
        return result
    result = {}
    for label, index, stride in [('imports', 1, 20), ('delay_imports', 13, 32)]:
        rva, size = u32(opt + 112 + index * 8), u32(opt + 116 + index * 8)
        names = []
        if rva:
            for n in range(min(size // stride, 256)):
                p = offset(rva) + n * stride
                if not any(data[p:p + stride]): break
                addr = u32(p + 12) if index == 1 else u32(p + 4) - (0 if u32(p) & 1 else u64(opt + 24))
                names.append(string(addr))
        result[label] = sorted(names)
    export_rva = u32(opt + 112)
    exports = []
    if export_rva:
        table = offset(export_rva)
        count = u32(table + 24)
        if count > 10000: raise ValueError('Unbounded PE export inventory.')
        names = offset(u32(table + 32))
        exports = [string(u32(names + n * 4)) for n in range(count)]
    result['exports'] = sorted(exports)
    return result


def validate_native(evidence):
    imports = evidence['imports'] + evidence['delay_imports']
    allowed = {'advapi32.dll', 'kernel32.dll', 'ntdll.dll', 'ole32.dll', 'oleaut32.dll',
        'user32.dll', 'ws2_32.dll', 'bcrypt.dll', 'crypt32.dll', 'secur32.dll',
        'shell32.dll', 'shlwapi.dll', 'version.dll', 'python312.dll', 'onnxruntime.dll'}
    if (not {'python312.dll', 'onnxruntime.dll'} <= {n.casefold() for n in imports}
            or any(n.casefold() not in allowed and not re.fullmatch(r'api-ms-win-[a-z0-9-]+\.dll', n.casefold()) for n in imports)
            or 'PyInit__sherpa_onnx' not in evidence['exports']
            or any(any(c in n for c in '/\\:') for n in imports + evidence['exports'])
            or any(re.search(r'espeak|piper|phonemiz', n, re.I) for n in imports + evidence['exports'])):
        raise ValueError('The isolated ASR binding native dependency/export scope differs.')


def make_wheel(output, pyd):
    policy = pin()
    source = output / 'sources/sherpa-onnx/sherpa-onnx/python/sherpa_onnx'
    target = output / 'candidate'
    target.mkdir()
    for path in source.rglob('*.py'):
        dest = target / 'sherpa_onnx' / path.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    init = target / 'sherpa_onnx/__init__.py'
    with init.open('a', encoding='utf-8') as f:
        f.write('\n# Separate unpublished reference identity; upstream Python sources retained.\n'
                '__version__ = "1.13.8+proxy.r19.asr1"\n')
    lib = target / 'sherpa_onnx/lib'
    lib.mkdir(exist_ok=True)
    shutil.copyfile(pyd, lib / pyd.name)
    shutil.copyfile(output / 'sources/onnxruntime/lib/onnxruntime.dll', lib / 'onnxruntime.dll')
    dist = target / 'proxy_r19_sherpa_asr_reference-1.13.8+proxy.r19.asr1.dist-info'
    dist.mkdir()
    (dist / 'WHEEL').write_text('Wheel-Version: 1.0\nGenerator: proxy-r19-private-reference\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n', encoding='utf-8')
    (dist / 'METADATA').write_text('Metadata-Version: 2.1\nName: proxy-r19-sherpa-asr-reference\nVersion: 1.13.8+proxy.r19.asr1\nSummary: Unapproved private TTS-disabled source experiment\nRequires-Dist: numpy==1.26.4\n', encoding='utf-8')
    shutil.copytree(output / 'notices', dist / 'notices')
    shutil.copyfile(ROOT / 'LICENSE', dist / 'notices/PROJECT-LICENSE.txt')
    shutil.copyfile(ROOT / policy['patch']['file'], dist / 'notices/TTS-OFF-MODIFICATION.patch')
    for name in policy['patch_notices']:
        shutil.copyfile(ROOT / name, dist / 'notices' / Path(name).name)
    record = io.StringIO(newline='')
    writer = csv.writer(record)
    for name in sorted(inventory(target)):
        data = (target / name).read_bytes()
        writer.writerow([name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data))])
    writer.writerow([dist.name + '/RECORD', '', ''])
    (dist / 'RECORD').write_text(record.getvalue(), encoding='utf-8')
    wheel = output / 'private-wheelhouse/proxy_r19_sherpa_asr_reference-1.13.8+proxy.r19.asr1-cp312-cp312-win_amd64.whl'
    wheel.parent.mkdir()
    with zipfile.ZipFile(wheel, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(inventory(target)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (target / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    return wheel


def process_owner():
    spec = importlib.util.spec_from_file_location('asr_owned_windows_process', ROOT / 'backend/windows_preparation_process.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.WindowsPreparationProcess()


def run_private(command, log, env, cwd, timeout):
    # Existing stdlib bootstrap joins the retained kill-on-close Win32 job
    # before spawning. Timeout cleanup addresses only this owned subtree.
    owner, process = process_owner(), None
    try:
        with log.open('wb') as handle:
            try:
                process = subprocess.Popen(owner.command([str(v) for v in command]),
                    stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                    cwd=cwd, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
                code = process.wait(timeout=timeout)
            finally:
                if process and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                owner.terminate(timeout=10)
    finally:
        owner.close()
    if code:
        raise ValueError('A private ASR build/probe command failed.')


def known_log_diagnostics(output, phase):
    """Return fixed labels only; never serialize a line, match text or raw log."""
    if phase not in PHASE_LOGS:
        return {'known_codes': [], 'categories': []}
    path = output / 'private-logs' / PHASE_LOGS[phase]
    try:
        no_links(path)
        # The bounded tail covers final tool summaries without copying a raw
        # log into memory/output as an artifact. Missing logs are explicit.
        with path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 2 * 1024 * 1024))
            content = handle.read(2 * 1024 * 1024).decode('utf-8', errors='replace')
    except (OSError, ValueError):
        return {'known_codes': [], 'categories': ['private-log-unavailable']}
    tokens = set(re.findall(r'\b(?:fatal\s+)?error\s+((?:C|D|LNK|MSB)[0-9]{4})\b', content, re.I))
    tokens = {token.upper() for token in tokens}
    categories = set()
    if any(t.startswith(('C', 'D', 'LNK')) for t in tokens): categories.add('compiler-or-linker-error')
    if any(t.startswith('MSB') for t in tokens): categories.add('msbuild-error')
    if tokens - KNOWN_BUILD_CODES: categories.add('unclassified-tool-error')
    if re.search(r'(?im)^CMake Error(?:\s|:)', content): categories.add('cmake-error')
    if re.search(r'Configuring incomplete, errors occurred', content, re.I): categories.add('cmake-configure-incomplete')
    if re.search(r'CMake Generate step failed', content, re.I): categories.add('cmake-generate-failed')
    if re.search(r'could not (?:create named generator|find any instance of Visual Studio)', content, re.I):
        categories.add('cmake-generator-unavailable')
    if re.search(r'is not able to compile a simple test program', content, re.I): categories.add('cmake-compiler-test-failed')
    if 'Native ASR reference probe failed;' in content: categories.add('native-probe-failed')
    if '[ONNXRuntimeError]' in content: categories.add('onnx-native-error')
    return {'known_codes': sorted(tokens & KNOWN_BUILD_CODES), 'categories': sorted(categories)}


def failed_build_receipt(output, phase, error):
    """Write only to this prepared attempt; a failure is never an ASR success."""
    output = Path(output).absolute()
    if phase not in BUILD_PHASES:
        raise ValueError('Unknown private ASR build phase.')
    no_links(output)
    policy = pin()
    prepared = read_json(output / 'PREPARED.json')
    if (prepared.get('schema') != policy['schema'] or prepared.get('identity') != policy['identity']
            or prepared.get('gates') != policy['gates']):
        raise ValueError('Failure diagnostics require this explicit prepared ASR attempt.')
    if isinstance(error, subprocess.TimeoutExpired):
        category = 'owned-process-timeout'
    elif isinstance(error, OSError):
        category = 'io-or-cleanup-unconfirmed'
    elif isinstance(error, subprocess.SubprocessError) or phase in PHASE_LOGS:
        category = 'private-command-failed'
    elif isinstance(error, (ValueError, KeyError, struct.error)):
        category = 'input-or-output-validation-rejected'
    else:
        category = 'unexpected-operation-failed'
    # Do not serialize exception text, command args, environment, model output,
    # source/tool paths, private log names or unrecognized compiler tokens.
    receipt = {'schema': 'proxy-r19-asr-source-failure-v1', 'identity': policy['identity'],
        'status': 'failed', 'phase': phase, 'failure_category': category,
        'diagnostics': known_log_diagnostics(output, phase),
        'cmake_observation': safe_cmake_observation(),
        'source_commit': _BUILD_SOURCE_COMMIT if isinstance(_BUILD_SOURCE_COMMIT, str)
            and re.fullmatch('[0-9a-f]{40}', _BUILD_SOURCE_COMMIT) else None,
        'manifest_sha256': sha((ROOT / MANIFEST).read_bytes()),
        'native_reference_probes_passed': False, 'success_receipt_for_this_attempt': False,
        'rights_approval': False, 'gates': policy['gates']}
    path = output / 'ASR-FAILURE.json'; no_links(path)
    # A retry must choose a fresh attempt; preserve any previous failure record.
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


def publish_success_receipt(output, receipt):
    policy = pin()
    if (receipt.get('schema') != policy['schema'] or receipt.get('identity') != policy['identity']
            or receipt.get('status') != 'native-reference-probes-passed'
            or receipt.get('gates') != policy['gates'] or receipt.get('rights_approval') is not False):
        raise ValueError('A failed or unapproved result cannot become an ASR success receipt.')
    target = output / 'ASR-RECEIPT.json'
    pending = output / 'PRIVATE-ASR-RECEIPT.pending.json'
    no_links(target); no_links(pending)
    if target.exists():
        raise ValueError('Preserve the existing ASR result and choose a fresh attempt.')
    with pending.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    # No visible success file if serialization/close fails. This is the final
    # commit point; the caller performs no subsequent fallible work.
    pending.rename(target)


def reject_parent_imports(output):
    for directory in (output, *output.parents):
        for name in ('Directory.Build.props', 'Directory.Build.targets', 'Directory.Build.rsp', 'MSBuild.rsp'):
            if (directory / name).exists():
                raise ValueError('An ambient parent MSBuild import/response file would affect the experiment.')


def build(output, tool_roots, vs_root, inputs, cmake_root=None):
    global _BUILD_SOURCE_COMMIT, _BUILD_CMAKE_OBSERVATION
    build_phase('build-preflight')
    _BUILD_SOURCE_COMMIT = None
    _BUILD_CMAKE_OBSERVATION = None
    try:
        return _build(output, tool_roots, vs_root, inputs, cmake_root)
    except Exception as error:
        try:
            failure = failed_build_receipt(output, _BUILD_PHASE, error)
        except Exception:
            # Invalid/unprepared caller paths cannot gain a diagnostic write.
            print('ASR reference failure metadata unavailable; no success claimed.', file=sys.stderr)
        else:
            print('ASR reference failed in ' + failure['phase'] + ' (' + failure['failure_category'] + ').', file=sys.stderr)
        raise


def _build(output, tool_roots, vs_root, inputs, cmake_root):
    global _BUILD_SOURCE_COMMIT
    output, vs_root = Path(output).absolute(), Path(vs_root).absolute()
    build_phase('source-validation')
    receipt, policy = verify_sources(output), pin()
    if (output / 'ASR-RECEIPT.json').exists() or (output / 'ASR-FAILURE.json').exists():
        raise ValueError('Choose a fresh prepared ASR attempt; existing results are preserved.')
    build_phase('toolchain-validation')
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or sys.version_info[:3] != (3, 12, 16):
        raise ValueError('The exact separate Windows x64 Python supplier is required.')
    source_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if (not re.fullmatch('[0-9a-f]{40}', source_commit)
            or subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()):
        raise ValueError('A clean candidate source commit is required before native building.')
    _BUILD_SOURCE_COMMIT = source_commit
    build_phase('vs-installation-origin')
    no_links(vs_root)
    build_phase('tool-root-schema')
    roots = read_json(Path(tool_roots))
    validate_tool_root_schema(roots)
    build_phase('tool-root-filesystem')
    validate_tool_roots(roots)
    build_phase('python-interpreter-origin')
    if Path(roots['python']).resolve() != Path(sys.prefix).resolve():
        raise ValueError('The sealed Python root is not this interpreter.')
    build_phase('python-supplier-bytes')
    verify_python(inputs, roots['python'])
    build_phase('tool-root-filesystem')
    for path in roots.values(): no_links(Path(path))
    cmake = Path(roots['cmake']) / 'bin/cmake.exe'
    build_phase('cmake-pinned-input')
    cmake_supplier = verify_pinned_cmake(cmake_root, roots['cmake'])
    build_phase('cmake-version-review')
    observe_cmake_version(cmake, policy['toolchain']['cmake_version'])
    build_phase('toolchain-seal')
    initial = seal_toolchain(roots)
    write_json(output / 'PRIVATE-TOOLCHAIN-INVENTORY.json', initial)
    build_phase('probe-dependency-preparation')
    numpy_files = prepare_numpy(inputs, output / 'probe-dependencies')
    build_phase('build-environment')
    logs = output / 'private-logs'; logs.mkdir()
    build_root = output / 'build'
    env = {k: v for k, v in os.environ.items() if k.casefold() in {
        'systemroot', 'windir', 'comspec', 'processor_architecture', 'number_of_processors',
        'programfiles', 'programfiles(x86)', 'programw6432', 'temp', 'tmp'}}
    env.update({'PATH': os.pathsep.join([str(cmake.parent), str(Path(sys.executable).parent),
        str(Path(os.environ['SystemRoot']) / 'System32'),
        str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0')]),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
        'HOME': str(output / 'empty-home'), 'USERPROFILE': str(output / 'empty-home'),
        'APPDATA': str(output / 'empty-home/AppData/Roaming'),
        'LOCALAPPDATA': str(output / 'empty-home/AppData/Local')})
    (output / 'empty-home').mkdir()
    user_props = output / 'empty-home/MSBuild'; user_props.mkdir()
    targets = list(Path(roots['msbuild']).glob('Microsoft/VC/v*/Microsoft.Cpp.Default.props'))
    if len(targets) != 1:
        raise ValueError('A unique sealed VC target directory is required; do not fall back to registry paths.')
    build_properties = {'ImportDirectoryBuildProps': 'false', 'ImportDirectoryBuildTargets': 'false',
        'UserRootDir': user_props.as_posix() + '/', 'MSBuildUserExtensionsPath': user_props.as_posix() + '/',
        'VCTargetsPath': targets[0].parent.as_posix() + '/'}
    for when in ('Before', 'After'):
        for kind in ('CommonProps', 'CommonTargets', 'CppDefaultProps', 'CppProps', 'CppTargets'):
            build_properties['ImportUserLocationsByWildcard' + when + 'Microsoft' + kind] = 'false'
    env.update(build_properties)
    env['MSBUILDDISABLENODEREUSE'] = '1'
    reject_parent_imports(output)
    configure = [cmake, '-S', output / 'sources/sherpa-onnx', '-B', build_root,
        '-G', policy['toolchain']['generator'], '-A', 'x64',
        '-T', 'host=x64,version=' + policy['toolchain']['vc_tools_version'],
        '-DCMAKE_GENERATOR_INSTANCE=' + str(vs_root),
        '-DCMAKE_SYSTEM_VERSION=' + policy['toolchain']['windows_sdk_version'],
        '--trace-expand', '--trace-format=json-v1', '--trace-redirect=' + str(output / 'PRIVATE-CMAKE-TRACE.jsonl')]
    configure += cmake_arguments(output, sys.executable)
    configure += ['-DCMAKE_VS_GLOBALS=' + ';'.join(k + '=' + v for k, v in build_properties.items())]
    map_option = '/INCREMENTAL:NO /Brepro /MAP:' + (output / 'PRIVATE-BINDING.map').as_posix()
    configure += ['-DCMAKE_MODULE_LINKER_FLAGS_RELEASE=' + map_option,
                  '-DCMAKE_SHARED_LINKER_FLAGS_RELEASE=' + map_option]
    print('Configuring the distinct ASR source experiment; raw paths/logs remain private.', flush=True)
    build_phase('cmake-configure')
    run_private(configure, logs / 'configure.log', env, output, 600)
    build_phase('build-graph-review')
    graph = verify_trace(output / 'PRIVATE-CMAKE-TRACE.jsonl', output)
    verify_cache(build_root / 'CMakeCache.txt', output)
    for language in ('C', 'CXX'):
        compilers = list(build_root.glob('CMakeFiles/**/CMake' + language + 'Compiler.cmake'))
        if len(compilers) != 1:
            raise ValueError('A unique selected compiler observation is required.')
        observed = compilers[0].read_text()
        compiler = re.search(r'set\(CMAKE_' + language + r'_COMPILER "([^"]+)"\)', observed)
        if (('set(CMAKE_' + language + '_COMPILER_VERSION "' + policy['toolchain']['compiler_version'] + '")') not in observed
                or not compiler or not Path(compiler[1]).resolve().is_relative_to(Path(roots['vc']).resolve())):
            raise ValueError('The observed compiler version or sealed tool origin differs.')
    projects = list(build_root.rglob('*.vcxproj'))
    if not projects or any(re.search(r'espeak|piper|phonemiz', p.name, re.I) for p in projects):
        raise ValueError('Unexpected TTS/native project in the ASR build graph.')
    compiled = [str((p.parent / html.unescape(v)).resolve()) for p in projects
                for v in re.findall(r'<ClCompile Include="([^"]+)"', p.read_text(encoding='utf-8-sig'))]
    if (not any(v.endswith('offline-sense-voice-model.cc') for v in compiled)
            or any(re.search(r'espeak|piper|phonemiz|offline-tts', v, re.I) for v in compiled)):
        raise ValueError('The actual ASR compilation input scope differs.')
    if any(not Path(v).is_relative_to(output) for v in compiled):
        raise ValueError('A compilation unit is outside the prepared/build output.')
    verify_sources(output)
    print('Building the binding with the sealed source graph; no production collection.', flush=True)
    build_phase('native-build')
    run_private([cmake, '--build', build_root, '--config', 'Release', '--target', '_sherpa_onnx', '--parallel', '2',
                 '--', '/nodeReuse:false', '/noAutoResponse'],
                logs / 'build.log', env, output, 1800)
    build_phase('native-output-review')
    outputs = list((build_root / 'lib/Release').glob('_sherpa_onnx*.pyd'))
    if len(outputs) != 1 or outputs[0].name != '_sherpa_onnx.cp312-win_amd64.pyd':
        raise ValueError('A unique rebuilt Python binding was not produced.')
    pyd = outputs[0]
    native_binding = attributes(pyd.read_bytes())
    native = pe_evidence(pyd.read_bytes())
    validate_native(native)
    link_map = (output / 'PRIVATE-BINDING.map').read_text(encoding='utf-8', errors='replace')
    if not link_map or re.search(r'espeak|piper|phonemiz', link_map, re.I):
        raise ValueError('Unexpected phonemizer in the actual binding link map.')
    build_phase('candidate-assembly')
    wheel = make_wheel(output, pyd)
    wheel_bytes = attributes(wheel.read_bytes())
    candidate_files = inventory(output / 'candidate')
    spec = importlib.util.spec_from_file_location('owned_asr_fixture', ROOT / 'scripts/probe-reference-asr.py')
    fixture_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture_module)
    fixtures = fixture_module.fixtures(output / 'owned-fixtures')
    probes = []
    for case in ('decode', 'wrong-shape', 'corrupt'):
        build_phase('probe-' + case)
        report = output / ('PRIVATE-PROBE-' + case + '.json')
        run_private([sys.executable, '-I', '-B', ROOT / 'scripts/probe-reference-asr.py',
            '--package', output / 'candidate', '--numpy', output / 'probe-dependencies',
            '--fixtures', output / 'owned-fixtures', '--case', case, '--report', report],
            logs / ('probe-' + case + '.log'), env, output / 'empty-home', 90)
        result = read_json(report)
        if (result['onnx_dll_sha256'] != sha((output / 'sources/onnxruntime/lib/onnxruntime.dll').read_bytes())
                or result['binding_filename'] != pyd.name or result['binding_sha256'] != native_binding['sha256']):
            raise ValueError('Native probe DLL bytes differ from the exact ONNX input.')
        probes.append(result)
    build_phase('final-source-review')
    verify_sources(output)
    reject_parent_imports(output)
    build_phase('final-candidate-review')
    if (inventory(output / 'candidate') != candidate_files
            or inventory(output / 'probe-dependencies') != numpy_files
            or attributes(pyd.read_bytes()) != native_binding
            or attributes(wheel.read_bytes()) != wheel_bytes):
        raise ValueError('An actual candidate/native/probe input changed during execution.')
    build_phase('final-toolchain-review')
    if seal_toolchain(roots) != initial:
        raise ValueError('Compiler, SDK, CMake, MSBuild or Python bytes changed during the experiment.')
    build_phase('final-cmake-pinned-input')
    if verify_pinned_cmake(cmake_root, roots['cmake']) != cmake_supplier:
        raise ValueError('The exact CMake input/tree receipt changed during the experiment.')
    build_phase('source-commit-review')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()
    if commit != source_commit or dirty:
        raise ValueError('A clean candidate source commit is required for the final receipt.')
    receipt.update({'status': 'native-reference-probes-passed', 'source_commit': commit,
        'toolchain_constraints': policy['toolchain'], 'toolchain_observed_bytes': toolchain_summary(initial),
        'pinned_cmake': cmake_supplier,
        'source_graph': graph, 'native_binding': native_binding,
        'native_pe': native, 'link_map_sha256': sha((output / 'PRIVATE-BINDING.map').read_bytes()),
        'no_espeak_link_input_observed': True, 'private_wheel': wheel_bytes,
        'owned_fixtures': fixtures, 'native_probes': probes,
        'trained_model': False, 'speech_recognition_accuracy_verified': False,
        'onnx_native_source_crt_review': 'pending-exact-inputs',
        'windows_11_acceptance': 'unavailable', 'rights_approval': False})
    build_phase('success-receipt')
    print('Owned native format/API probes passed; all production/rights/Windows11 gates remain open.', flush=True)
    publish_success_receipt(output, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--inputs', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify-sources')
    check.add_argument('--output', type=Path, required=True)
    python = sub.add_parser('prepare-python')
    python.add_argument('--archive', type=Path, required=True)
    python.add_argument('--output', type=Path, required=True)
    native = sub.add_parser('build')
    native.add_argument('--output', type=Path, required=True)
    native.add_argument('--inputs', type=Path, required=True)
    native.add_argument('--tool-roots', type=Path, required=True)
    native.add_argument('--vs-root', type=Path, required=True)
    native.add_argument('--cmake-root', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.inputs, args.output)
        print('ASR reference inputs prepared; no native build or rights acceptance claimed.')
    elif args.command == 'verify-sources':
        verify_sources(args.output)
        print('Exact ASR prepared source/recipe bytes verified.')
    elif args.command == 'prepare-python':
        prepare_python(args.archive, args.output)
        print('Exact separate Python supplier prepared; supplier rights review remains open.')
    else:
        build(args.output, args.tool_roots, args.vs_root, args.inputs, args.cmake_root)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Raw source/build/tool locations are private, including exception text.
        print('ASR reference operation failed; inspect the private build-host inputs.', file=sys.stderr)
        sys.exit(1)
