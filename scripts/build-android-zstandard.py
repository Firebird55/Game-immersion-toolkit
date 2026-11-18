"""Build the pinned unmodified Zstandard C backend for real Android CPython.

This standalone software cohort does not mutate the maintained core wheelhouse
or construct an APK. Android runtime acceptance remains a separate requirement.
"""
import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(path):
    with path.open('rb') as source: return hashlib.file_digest(source, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def original_notices(source, policy):
    result = {name: (source / name).read_bytes() for name in policy['licenses']}
    # Preserve the complete original embedded copyright/permission blocks in
    # the upstream amalgamation, including its bundled xxHash notices.
    raw = (source / policy['embedded_notice_source']).read_bytes()
    notices = sorted(set(block for block in re.findall(rb'/\*.*?\*/', raw, re.S)
                         if b'copyright' in block.lower()))
    if not notices or sum(map(len, notices)) > 1024**2:
        raise ValueError('The original embedded Zstandard notices were not found within their bound')
    result['embedded-original-notices.txt'] = b'\n\n'.join(notices) + b'\n'
    return result


def verify_wheels(work, source, receipt):
    dependencies = load_script('toolkit_zstd_verify_inputs', 'build-android-python-dependencies.py')
    policy = json.loads((ROOT / 'packaging/android/zstandard-native.json').read_text())
    pins = json.loads(dependencies.POLICY.read_text())
    if set(receipt['abis']) != set(pins['targets']):
        raise ValueError('Both actual Android Python ABIs are required')
    dist = 'zstandard-' + policy['version'] + '.dist-info/'
    notices = original_notices(source, policy)
    expected = {*policy['pure_members'], policy['native_member'], dist + 'METADATA', dist + 'WHEEL', dist + 'RECORD',
                *(dist + 'licenses/' + name for name in notices)}
    for abi, row in receipt['abis'].items():
        name = 'zstandard-' + policy['version'] + '-cp312-cp312-android_' + str(policy['api']) + '_' + abi.replace('-', '_') + '.whl'
        path = work / 'wheelhouse' / name;_no_links(path)
        if row['wheel'] != name or path.stat().st_size != row['wheel_bytes'] or sha(path) != row['wheel_sha256']:
            raise ValueError('A compiled Zstandard wheel changed')
        with zipfile.ZipFile(path) as wheel:
            if len(wheel.namelist()) != len(expected) or set(wheel.namelist()) != expected or wheel.testzip() is not None:
                raise ValueError('The Zstandard software namespace differs from its closed recipe')
            raw = wheel.read(policy['native_member'])
            if hashlib.sha256(raw).hexdigest() != row['native_sha256'] or len(raw) != row['native_bytes']:
                raise ValueError('The actual C backend differs from its compiled receipt')
            if dependencies.elf_contract(raw, pins['targets'][abi]['elf_machine']) != row['elf']:
                raise ValueError('The actual C backend ABI differs')
            if wheel.read(dist + 'METADATA') != (source / 'PKG-INFO').read_bytes():
                raise ValueError('The original Zstandard package metadata changed')
            expected_tag = 'cp312-cp312-android_' + str(policy['api']) + '_' + abi.replace('-', '_')
            if ('Tag: ' + expected_tag + '\n').encode() not in wheel.read(dist + 'WHEEL'):
                raise ValueError('The actual Android wheel tag changed')
            records = list(csv.reader(io.StringIO(wheel.read(dist + 'RECORD').decode())))
            if len(records) != len(expected) or {row[0] for row in records} != expected:
                raise ValueError('The wheel record inventory changed')
            for member, digest, size in records:
                if member == dist + 'RECORD':
                    if digest or size: raise ValueError('Invalid wheel self-record')
                else:
                    body = wheel.read(member)
                    encoded = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip('=')
                    if digest != 'sha256=' + encoded or size != str(len(body)):
                        raise ValueError('A wheel member differs from its actual record')
            for member in policy['pure_members']:
                if wheel.read(member) != (source / member).read_bytes():
                    raise ValueError('An original Python Zstandard member changed')
            for member, raw in notices.items():
                if wheel.read(dist + 'licenses/' + member) != raw:
                    raise ValueError('An original complete Zstandard notice changed')


def build(work, source_archive, ndk_root, ndk_archive, python_archives):
    work, source_archive, ndk_root, ndk_archive, python_archives = (
        Path(value).absolute() for value in (work, source_archive, ndk_root, ndk_archive, python_archives))
    for path in (work, source_archive, ndk_root, ndk_archive, python_archives): _no_links(path)
    policy_path = ROOT / 'packaging/android/zstandard-native.json'
    policy = json.loads(policy_path.read_text())
    if (policy.get('schema') != 'toolkit-android-zstandard-recipe-v1' or policy.get('expected_backend') != 'cext'
            or any(policy.get(name) is not False for name in ('system_zstd', 'cffi', 'rust', 'legacy_format', 'original_game_code'))):
        raise ValueError('Only the reviewed bundled C backend is supported')
    dependencies = load_script('toolkit_zstd_python_inputs', 'build-android-python-dependencies.py')
    unpacker = load_script('toolkit_zstd_source_inputs', 'build-android-data-decoders.py')
    pins = json.loads(dependencies.POLICY.read_text())
    if policy['ndk'] != pins['ndk_revision'] or policy['python_target'] != pins['python_target']:
        raise ValueError('Zstandard must use the same exact Android CPython and NDK suppliers')
    source = unpacker.source_tree(source_archive, work / 'source', policy)
    ndk_inventory = dependencies.verify_ndk(ndk_root, ndk_archive, pins['ndk'])
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler = ndk_root / 'toolchains/llvm/prebuilt' / host / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
    readelf = compiler.with_name('llvm-readelf.exe' if os.name == 'nt' else 'llvm-readelf')
    for path in (compiler, readelf): _no_links(path)
    notices = original_notices(source, policy)
    recipe = {'policy_sha256': sha(policy_path), 'builder_sha256': sha(Path(__file__)),
        'source_sha256': sha(source_archive), 'compiler_sha256': sha(compiler),
        'python_input_policy_sha256': sha(dependencies.POLICY),
        'supplier_helper_sha256': sha(ROOT / 'scripts/build-android-python-dependencies.py'),
        'source_helper_sha256': sha(ROOT / 'scripts/build-android-data-decoders.py')}
    output = work / 'wheelhouse';output.mkdir(parents=True, exist_ok=True)
    results = {}
    for abi, pin in pins['targets'].items():
        archive = dependencies.acquire(python_archives, pin, download=False)
        target = work / 'python-target' / abi
        _no_links(target)
        if target.exists():
            for path in target.rglob('*'): _no_links(path)
        dependencies.unpack_target(archive, target)
        native = work / 'native' / abi / 'backend_c.cpython-312.so'
        _no_links(native);native.parent.mkdir(parents=True, exist_ok=True)
        flags = ['-target', pin['rust_target'] + str(policy['api']), '-std=c99', '-O2', '-DNDEBUG', '-fPIC', '-shared',
            '-fvisibility=hidden', '-fno-ident', '-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384',
            '-Wl,-z,defs',
            '-Wl,-soname,backend_c.cpython-312.so', '-ffile-prefix-map=' + str(work) + '=/android-zstandard',
            '-ffile-prefix-map=' + str(ROOT) + '=/toolkit-source', '-I' + str(target / 'include/python3.12')]
        flags += ['-I' + str(source / name) for name in policy['include_directories']]
        flags += ['-D' + value for value in policy['definitions']]
        flags += [str(source / name) for name in policy['source_files']]
        flags += ['-L' + str(target / 'jniLibs' / abi), '-lpython3.12', '-lm', '-ldl', '-o', str(native)]
        subprocess.run([str(compiler), *flags], cwd=work, check=True, timeout=600)
        raw = native.read_bytes()
        contract = dependencies.elf_contract(raw, pin['elf_machine'])
        symbols = subprocess.run([str(readelf), '--dyn-syms', str(native)], check=True, capture_output=True, text=True).stdout
        if not re.search(r'\bGLOBAL\b[^\n]*\bPyInit_backend_c\b', symbols):
            raise ValueError('The actual Python C extension entrypoint is absent')
        dist = 'zstandard-' + policy['version'] + '.dist-info/'
        tag = 'cp312-cp312-android_' + str(policy['api']) + '_' + abi.replace('-', '_')
        files = {name: (source / name).read_bytes() for name in policy['pure_members']}
        files[policy['native_member']] = raw
        files[dist + 'METADATA'] = (source / 'PKG-INFO').read_bytes()
        files[dist + 'WHEEL'] = ('Wheel-Version: 1.0\nGenerator: toolkit-owned-android-zstandard\n'
            'Root-Is-Purelib: false\nTag: ' + tag + '\n').encode()
        files.update({dist + 'licenses/' + name: value for name, value in notices.items()})
        wheel = dependencies.package_wheel(files, dist, output / ('zstandard-' + policy['version'] + '-' + tag + '.whl'))
        results[abi] = {'wheel': wheel.name, 'wheel_sha256': sha(wheel), 'wheel_bytes': wheel.stat().st_size,
            'native_sha256': sha(native), 'native_bytes': len(raw), 'elf': contract,
            'python_target_sha256': pin['sha256'], 'python_init_export': 'PyInit_backend_c',
            'notices': {name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)} for name, value in notices.items()}}
    unpacker.source_tree(source_archive, work / 'source', policy)
    if recipe['policy_sha256'] != sha(policy_path) or recipe['builder_sha256'] != sha(Path(__file__)):
        raise ValueError('The software recipe changed during compilation')
    receipt = {'schema': 'toolkit-android-zstandard-build-v1', 'version': policy['version'], 'recipe': recipe,
        'ndk_archive_sha256': pins['ndk']['sha256'], 'ndk_inventory_sha256': ndk_inventory,
        'abis': results, 'backend': 'cext', 'system_zstd': False, 'cffi': False, 'rust': False,
        'android_execution': 'not-established-by-host-build', 'original_game_code': False}
    verify_wheels(work, source, receipt)
    (output / 'zstandard-build-receipt.json').write_bytes(canonical(receipt))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work-dir', 'source-archive', 'ndk-root', 'ndk-archive', 'python-archives'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.work_dir, args.source_archive, args.ndk_root, args.ndk_archive, args.python_archives)
    print(json.dumps({'version': result['version'], 'abis': result['abis'], 'android_execution': result['android_execution']}))
