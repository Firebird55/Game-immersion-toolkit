"""Build the desktop core's pinned Python dependencies for Android.

Build-host tooling only. APKs contain the resulting wheels, not this compiler,
an installer, or a downloader. Game preparation/native game readers are separate.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'packaging/android/python-dependencies.json'
MAX_INPUT = 64 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def acquire(directory, pin, *, download=False):
    name = pin.get('artifact') or pin['source'].rsplit('/', 1)[1]
    if Path(name).name != name or ':' in name:
        raise ValueError('Invalid software input name')
    target = directory / name
    if not target.exists():
        if not download:
            raise ValueError('A pinned software input is missing: ' + name)
        pending = target.with_suffix(target.suffix + '.pending')
        with urllib.request.urlopen(pin['source'], timeout=60) as source, pending.open('xb') as output:
            total = 0
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > MAX_INPUT:
                    raise ValueError('Oversized software input')
                output.write(block)
        pending.replace(target)
    if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_INPUT:
        raise ValueError('Invalid software input')
    raw = target.read_bytes()
    if sha(raw) != pin['sha256'] or ('bytes' in pin and len(raw) != pin['bytes']):
        raise ValueError('Software checksum mismatch: ' + name)
    return target


def safe_name(name):
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or '\\' in name or ':' in name
            or any(part in ('', '.', '..') for part in name.rstrip('/').split('/'))):
        raise ValueError('Unsafe source member')
    return path


def unpack_tar(path, destination):
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        if (len(members) > 30000 or sum(member.size for member in members) > 128 * 1024 * 1024
                or any(not (member.isdir() or member.isfile()) for member in members)):
            raise ValueError('Unsupported source archive')
        names = [safe_name(member.name).as_posix().casefold() for member in members]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate source member')
        archive.extractall(destination, filter='data')


def unpack_target(path, destination):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [safe_name(entry.filename).as_posix().casefold() for entry in entries]
        if (len(entries) > 10000 or len(names) != len(set(names))
                or sum(entry.file_size for entry in entries) > 128 * 1024 * 1024
                or any((entry.external_attr >> 16) & 0o170000 == 0o120000 for entry in entries)):
            raise ValueError('Unsupported Python target archive')
        archive.extractall(destination)


def verify_ndk(ndk, archive, pin):
    """Bind the actual compiler/sysroot files to the official archive, not a label."""
    if not archive.is_file() or archive.stat().st_size != pin['size']:
        raise ValueError('Supply the checksum-pinned original NDK archive')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != pin['sha256']:
        raise ValueError('NDK supplier archive checksum mismatch')
    inventory = {}
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    prefix = 'toolchains/llvm/prebuilt/' + host + '/'
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name = safe_name(entry.filename)
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            if entry.is_dir() or not (relative.startswith(prefix) or relative == 'source.properties'):
                continue
            path = ndk.joinpath(*PurePosixPath(relative).parts)
            if not path.is_file() or path.is_symlink() or path.stat().st_size != entry.file_size:
                raise ValueError('NDK compiler inventory is incomplete')
            with source.open(entry) as stream:
                expected = hashlib.file_digest(stream, 'sha256').hexdigest()
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected:
                raise ValueError('NDK compiler or sysroot differs from the original archive')
            inventory[relative] = actual
    if not any(name.endswith('/clang.exe' if os.name == 'nt' else '/clang') for name in inventory):
        raise ValueError('Original NDK archive does not contain the build-host compiler')
    return sha(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode())


def elf_contract(data, machine):
    """Verify ABI, Android dependencies and page alignment, without loading code."""
    if (len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01'
            or struct.unpack_from('<HH', data, 16) != (3, machine)):
        raise ValueError('Wrong native Python ABI')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or not 1 <= count <= 64 or offset + size * count > len(data):
        raise ValueError('Invalid native program headers')
    loads, dynamic = [], None
    for index in range(count):
        kind, flags, start, address, _, length, memory, alignment = struct.unpack_from('<IIQQQQQQ', data, offset + index * size)
        if start + length > len(data) or length > memory:
            raise ValueError('Truncated native segment')
        if kind == 1:
            if alignment < 16384 or alignment & (alignment - 1) or start % alignment != address % alignment:
                raise ValueError('Native segment lacks 16-KiB alignment')
            loads.append((address, address + length, start))
        if kind == 2:
            if dynamic is not None or length % 16:
                raise ValueError('Invalid native dynamic table')
            dynamic = start, length
    if not loads or dynamic is None:
        raise ValueError('Missing native dynamic segments')
    needed, strings, string_size, ended = [], None, None, False
    start, length = dynamic
    for at in range(start, start + length, 16):
        kind, value = struct.unpack_from('<qQ', data, at)
        if kind == 0:
            ended = True
            break
        if kind == 1:
            needed.append(value)
        elif kind == 5:
            strings = value
        elif kind == 10:
            string_size = value
    mappings = [(file + strings - first) for first, end, file in loads
                if strings is not None and first <= strings < end]
    if not ended or len(mappings) != 1 or not string_size or mappings[0] + string_size > len(data):
        raise ValueError('Invalid native dependency names')
    table = data[mappings[0]:mappings[0] + string_size]
    dependencies = []
    for entry in needed:
        if entry >= len(table) or (end := table.find(b'\0', entry)) < 0:
            raise ValueError('Truncated native dependency name')
        dependencies.append(table[entry:end].decode('ascii'))
    if set(dependencies) != {'libpython3.12.so', 'libc.so', 'libm.so', 'libdl.so'} or len(dependencies) != 4:
        raise ValueError('Unexpected native runtime dependency')
    return {'elf_machine': machine, 'page_alignment': 16384, 'needed': sorted(dependencies)}


def crate_notices(source, cargo_home):
    """Every cached locked crate contributes its original license documents."""
    result, inventory = {}, {}
    lock = tomllib.loads((source / 'Cargo.lock').read_text())
    for package in lock['package']:
        if not package.get('checksum'):
            continue
        name = package['name'] + '-' + package['version']
        archives = list((cargo_home / 'registry/cache').glob('*/' + name + '.crate'))
        if not archives:
            continue  # Unselected platform-only dependency; no compiled input.
        if len(archives) != 1 or sha(archives[0].read_bytes()) != package['checksum']:
            raise ValueError('Locked crate checksum mismatch')
        with tarfile.open(archives[0], 'r:gz') as archive:
            notices = [entry for entry in archive.getmembers() if entry.isfile()
                       and len(PurePosixPath(entry.name).parts) == 2
                       and any(term in PurePosixPath(entry.name).name.lower()
                               for term in ('license', 'licence', 'copying', 'notice', 'copyright'))]
            if not notices or any(entry.size > 1024 * 1024 for entry in notices):
                raise ValueError('A compiled crate has no bounded license documents')
            for entry in notices:
                result['rust/' + safe_name(entry.name).as_posix()] = archive.extractfile(entry).read()
        inventory[name] = package['checksum']
    if not inventory:
        raise ValueError('Missing locked Rust source inventory')
    result['rust/locked-sources.json'] = (json.dumps(inventory, sort_keys=True, indent=2) + '\n').encode()
    return result


def native_wheel(source, native, output, abi, notices):
    tag = 'cp312-cp312-android_24_' + abi.replace('-', '_')
    dist = 'pydantic_core-2.50.1.dist-info/'
    files = {path.relative_to(source / 'python').as_posix(): path.read_bytes()
             for path in (source / 'python/pydantic_core').rglob('*') if path.is_file()
             and (path.suffix in ('.py', '.pyi') or path.name == 'py.typed')}
    files.update({'pydantic_core/_pydantic_core.cpython-312.so': native,
                  dist + 'METADATA': (source / 'PKG-INFO').read_bytes(),
                  dist + 'WHEEL': f'Wheel-Version: 1.0\nGenerator: toolkit-android-python\nRoot-Is-Purelib: false\nTag: {tag}\n'.encode(),
                  dist + 'licenses/LICENSE': (source / 'LICENSE').read_bytes()})
    files.update({dist + 'licenses/' + name: raw for name, raw in notices.items()})
    return package_wheel(files, dist, output / ('pydantic_core-2.50.1-' + tag + '.whl'))


def package_wheel(files, dist, target):
    records = io.StringIO(newline='')
    writer = csv.writer(records, lineterminator='\n')
    for name, raw in sorted(files.items()):
        writer.writerow((name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='), len(raw)))
    writer.writerow((dist + 'RECORD', '', ''))
    files[dist + 'RECORD'] = records.getvalue().encode()
    pending = target.with_suffix('.whl.pending')
    with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), raw)
    pending.replace(target)
    return target


def rapidfuzz_native(source, pure_wheel, work, output, ndk, target, abi, environment):
    """Build upstream C++ modules; never substitute a second matching algorithm."""
    cmake = shutil.which('cmake')
    if not cmake:
        raise ValueError('CMake 3.24 or later is a build-host prerequisite')
    version = subprocess.check_output([cmake, '--version'], text=True).splitlines()[0].split()[-1]
    minimum = tuple(int(part) for part in json.loads(POLICY.read_text())['cmake_minimum'].split('.'))
    if tuple(int(part) for part in version.split('.')[:2]) < minimum:
        raise ValueError('CMake 3.24 or later is a build-host prerequisite')
    directory = work / 'rapidfuzz-native' / abi
    directory.mkdir(parents=True, exist_ok=True)
    python = work / 'python-target' / abi
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
    # The official Chaquopy libpython has no SONAME. CMake must link -lpython,
    # otherwise its imported target records a build-host path in DT_NEEDED.
    hook = work / 'rapidfuzz-native' / 'python-import.cmake'
    hook.write_text('cmake_language(DEFER CALL set_property TARGET Python::Module PROPERTY IMPORTED_NO_SONAME TRUE)\n'
                    'cmake_language(DEFER CALL set_property TARGET Python::Module PROPERTY IMPORTED_NO_SONAME_RELEASE TRUE)\n')
    flags = '-g0 -ffile-prefix-map=' + work.as_posix() + '=/build/android-python'
    command = [cmake, '-S', str(source), '-B', str(directory), '-G', 'MinGW Makefiles' if os.name == 'nt' else 'Unix Makefiles',
        '-DCMAKE_TOOLCHAIN_FILE=' + (ndk / 'build/cmake/android.toolchain.cmake').as_posix(),
        '-DANDROID_ABI=' + abi, '-DANDROID_PLATFORM=android-24', '-DANDROID_STL=c++_static',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PROJECT_INCLUDE=' + hook.as_posix(),
        '-DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON', '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF',
        '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF', '-DCMAKE_DISABLE_FIND_PACKAGE_Taskflow=ON',
        '-DCMAKE_DISABLE_FIND_PACKAGE_rapidfuzz=ON', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON',
        '-DPython_EXECUTABLE=' + Path(sys.executable).as_posix(),
        '-DPython_INCLUDE_DIR=' + (python / 'include/python3.12').as_posix(),
        '-DPython_LIBRARY=' + (python / 'jniLibs' / abi / 'libpython3.12.so').as_posix(),
        '-DCMAKE_C_FLAGS=' + flags, '-DCMAKE_CXX_FLAGS=' + flags,
        '-DCMAKE_MODULE_LINKER_FLAGS=-Wl,-z,max-page-size=16384',
        '-DCMAKE_INSTALL_PREFIX=' + (directory / 'install').as_posix()]
    if os.name == 'nt':
        command.append('-DCMAKE_MAKE_PROGRAM=' + (ndk / 'prebuilt/windows-x86_64/bin/make.exe').as_posix())
    run(command, environment=environment, directory=work, log=work / ('rapidfuzz-' + abi + '-configure.log'))
    run([cmake, '--build', str(directory), '--parallel', '2'], environment=environment,
        directory=work, log=work / ('rapidfuzz-' + abi + '-native.log'))
    run([cmake, '--install', str(directory)], environment=environment,
        directory=work, log=work / ('rapidfuzz-' + abi + '-install.log'))
    modules, proof = {}, {}
    for file in sorted((directory / 'install/rapidfuzz').rglob('*.so')):
        subprocess.run([str(compiler / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')),
                        '--strip-unneeded', str(file)], env=environment, check=True)
        relative = file.relative_to(directory / 'install')
        # FindPython uses the build interpreter for metadata. Normalize its
        # filename suffix only after verifying the actual target ELF bytes.
        name = relative.with_name(relative.name.split('.')[0] + '.so').as_posix()
        raw = file.read_bytes()
        contract = elf_contract(raw, target['elf_machine'])
        if name in modules:
            raise ValueError('Duplicate native RapidFuzz module')
        modules[name] = raw;proof[name] = {**contract, 'sha256': sha(raw)}
    required = {'rapidfuzz/' + name + '.so' for name in ('utils_cpp', 'fuzz_cpp', 'process_cpp_impl',
        'distance/_initialize_cpp', 'distance/metrics_cpp')}
    if not required <= set(modules) or len(modules) != (8 if abi == 'x86_64' else 5):
        raise ValueError('Incomplete upstream native RapidFuzz modules')
    with zipfile.ZipFile(pure_wheel) as archive:
        files = {name: archive.read(name) for name in archive.namelist()
                 if not name.endswith(('.dist-info/RECORD', '.dist-info/WHEEL'))}
    dist = next(name.rsplit('/', 1)[0] + '/' for name in files if name.endswith('.dist-info/METADATA'))
    tag = 'cp312-cp312-android_24_' + abi.replace('-', '_')
    files.update(modules)
    files[dist + 'WHEEL'] = f'Wheel-Version: 1.0\nGenerator: toolkit-original-android-source\nRoot-Is-Purelib: false\nTag: {tag}\n'.encode()
    for name in ('taskflow', 'rapidfuzz-cpp'):
        files[dist + 'licenses/' + name + '/LICENSE'] = (source / 'extern' / name / 'LICENSE').read_bytes()
    wheel = package_wheel(files, dist, output / ('rapidfuzz-3.14.6-' + tag + '.whl'))
    return {'wheel': wheel.name, 'sha256': sha(wheel.read_bytes()), 'modules': proof,
            'cmake_version': version, 'cmake_binary_sha256': sha(Path(cmake).read_bytes())}


def run(command, *, environment, directory, log):
    with log.open('w', encoding='utf-8') as output:
        subprocess.run(command, env=environment, cwd=directory, stdout=output, stderr=subprocess.STDOUT, check=True)


def build(work, output, ndk, *, download=False, abis=None):
    pins = json.loads(POLICY.read_text())
    work, output, ndk = (Path(path).absolute() for path in (work, output, ndk))
    work.mkdir(parents=True, exist_ok=True); output.mkdir(parents=True, exist_ok=True)
    if not all(path.is_dir() and not path.is_symlink() for path in (work, output, ndk)):
        raise ValueError('Choose ordinary private build directories')
    if ('Pkg.Revision = ' + pins['ndk_revision']) not in (ndk / 'source.properties').read_text():
        raise ValueError('Wrong Android NDK revision')
    ndk_proof = verify_ndk(ndk, work / pins['ndk']['source'].rsplit('/', 1)[1], pins['ndk'])
    cargo, rustc = shutil.which('cargo'), shutil.which('rustc')
    if not cargo or not rustc or subprocess.check_output([rustc, '--version'], text=True).split()[1] != pins['rust_version']:
        raise ValueError('The pinned Rust build toolchain is required')
    cargo_home = Path(os.environ['CARGO_HOME']).absolute()
    environment = dict(os.environ, CARGO_TARGET_DIR=str(work / 'cargo-target'), SOURCE_DATE_EPOCH='315532800', PYTHONDONTWRITEBYTECODE='1')
    build_tools = work / 'build-python-pinned'
    for name, pin in pins['build_tools'].items():
        unpack_target(acquire(work, {'artifact': name, **pin}, download=download), build_tools)
    environment['PYTHONPATH'] = str(build_tools)
    for name, pin in pins['wheels'].items():
        target = acquire(work, {'artifact': name, **pin}, download=download)
        if target.resolve() != (output / name).resolve():
            shutil.copyfile(target, output / name)
    for name, pin in pins['sources'].items():
        archive = acquire(work, pin, download=download)
        unpack_tar(archive, work / 'source')
    source = work / 'source/pydantic_core-2.50.1'
    if sha((source / 'Cargo.lock').read_bytes()) != pins['sources']['pydantic_core']['cargo_lock_sha256']:
        raise ValueError('Changed native dependency lock')
    run([cargo, 'fetch', '--locked', '--manifest-path', str(source / 'Cargo.toml'),
         *[argument for abi in (abis or pins['targets']) for argument in ('--target', pins['targets'][abi]['rust_target'])]],
        environment=environment, directory=work, log=work / 'cargo-fetch.log')
    notices = crate_notices(source, cargo_home)
    native_results = {}
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler_root = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
    for abi in abis or pins['targets']:
        pin = pins['targets'][abi]
        archive = acquire(work, pin, download=download)
        target = work / 'python-target' / abi
        unpack_target(archive, target)
        lib = target / 'jniLibs' / abi
        config = work / ('pyo3-' + abi + '.txt')
        config.write_text('\n'.join(('implementation=CPython', 'version=3.12', 'shared=true', 'abi3=false',
            'lib_name=python3.12', 'lib_dir=' + lib.as_posix(), 'pointer_width=64',
            'build_flags=', 'suppress_build_script_link_lines=false')) + '\n')
        triple = pin['rust_target']
        compiler = compiler_root / (triple + '24-clang' + ('.cmd' if os.name == 'nt' else ''))
        if not compiler.is_file():
            raise ValueError('The requested Android compiler is missing')
        current = dict(environment, PYO3_CONFIG_FILE=str(config),
                       RUSTFLAGS='-C link-arg=-Wl,-z,max-page-size=16384 --remap-path-prefix=' + work.as_posix() + '=/build/android-python')
        current['CARGO_TARGET_' + triple.upper().replace('-', '_') + '_LINKER'] = str(compiler)
        run([cargo, 'build', '--release', '--locked', '--offline', '--features', 'pyo3/extension-module',
             '--lib', '--target', triple, '--manifest-path', str(source / 'Cargo.toml')],
            environment=current, directory=work, log=work / ('pydantic-' + abi + '-build.log'))
        native = (work / 'cargo-target' / triple / 'release/lib_pydantic_core.so').read_bytes()
        proof = elf_contract(native, pin['elf_machine'])
        wheel = native_wheel(source, native, output, abi, notices)
        native_results[abi] = {**proof, 'wheel': wheel.name, 'sha256': sha(wheel.read_bytes()),
                              'native_sha256': sha(native), 'python_target_sha256': pin['sha256']}
    # Same upstream Python algorithms; do not implement a second fuzzy matcher.
    run([sys.executable, '-c', 'import sys;from scikit_build_core.build import build_wheel;'
         'build_wheel(sys.argv[1],config_settings={"wheel.cmake":"false"})', str(output)],
        environment=dict(environment, RAPIDFUZZ_BUILD_EXTENSION='0'),
        directory=work / 'source/rapidfuzz-3.14.6', log=work / 'rapidfuzz-build.log')
    rapid = output / 'rapidfuzz-3.14.6-py3-none-any.whl'
    with zipfile.ZipFile(rapid) as archive:
        if any(name.endswith(('.so', '.pyd', '.dll')) for name in archive.namelist()):
            raise ValueError('RapidFuzz must use the same upstream portable Python implementation')
    rapid_native = {abi: rapidfuzz_native(work / 'source/rapidfuzz-3.14.6', rapid, work,
        output, ndk, pins['targets'][abi], abi, environment) for abi in abis or pins['targets']}
    requirements = output / 'requirements-android.lock.txt'
    requirements.write_text('\n'.join(pins['runtime_requirements']) + '\n')
    result = {'schema': 'toolkit-android-python-wheels-v1', 'policy_sha256': sha(POLICY.read_bytes()),
              'python': pins['python'], 'rust_version': pins['rust_version'], 'ndk_revision': pins['ndk_revision'],
              'ndk_compiler_inventory_sha256': ndk_proof,
              'native': native_results, 'rapidfuzz_native': rapid_native,
              'files': {path.name: sha(path.read_bytes()) for path in sorted(output.glob('*.whl'))},
              'target_runtime_acceptance': 'not-established-by-cross-compilation'}
    (output / 'python-wheels-receipt.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--ndk-root', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--abi', action='append', choices=('arm64-v8a', 'x86_64'))
    args = parser.parse_args()
    build(args.work_dir, args.wheelhouse, args.ndk_root, download=args.download, abis=args.abi)
