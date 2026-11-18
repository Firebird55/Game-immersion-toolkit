"""Build owned bounded JNI transport with pinned Capstone, using only NDK clang.

No game input is compiled, loaded or executed. The authenticated source archive,
fixed C source list and owned transport are the complete software recipe.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(path):
    with path.open('rb') as source: return hashlib.file_digest(source, 'sha256').hexdigest()


def source_tree(archive, destination, policy):
    _no_links(archive); _no_links(destination)
    if archive.stat().st_size != policy['bytes'] or sha(archive) != policy['sha256']:
        raise ValueError('The original decoder source archive differs from its pinned receipt')
    expected, total = {}, 0
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if (not path.parts or path.is_absolute() or path.as_posix() != member.name.rstrip('/')
                    or any(part in {'', '.', '..'} or ':' in part or '\\' in part for part in path.parts)
                    or not (member.isdir() or member.isfile())):
                raise ValueError('Unsafe decoder source archive member')
            if member.isdir(): continue
            total += member.size
            if len(expected) >= 4096 or total > 128 * 1024**2 or member.name.casefold() in expected:
                raise ValueError('Decoder source archive exceeds its closed input limit')
            raw = source.extractfile(member).read()
            target = destination.joinpath(*path.parts); _no_links(target)
            expected[member.name.casefold()] = hashlib.sha256(raw).hexdigest()
            if target.exists():
                if not target.is_file() or sha(target) != expected[member.name.casefold()]:
                    raise ValueError('An extracted decoder source changed')
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output: output.write(raw)
    actual = set()
    for target in destination.rglob('*'):
        _no_links(target)
        if target.is_file(): actual.add(target.relative_to(destination).as_posix().casefold())
    if actual != set(expected):
        raise ValueError('Unexpected files in the closed decoder source tree')
    return destination / policy['root']


def build(work, archive, ndk, ndk_archive, *, download=False):
    lock_path = ROOT / 'packaging/android/native-decoders.json'
    policy = json.loads(lock_path.read_text())
    work, archive, ndk = (Path(value).absolute() for value in (work, archive, ndk))
    for path in (work, archive, ndk): _no_links(path)
    work.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        if not download: raise ValueError('Acquire the pinned original decoder source archive first')
        archive.parent.mkdir(parents=True, exist_ok=True)
        pending = archive.with_suffix('.pending')
        try:
            with urllib.request.urlopen(policy['capstone']['source'], timeout=60) as response, pending.open('xb') as output:
                count = 0
                while block := response.read(min(1024**2, policy['capstone']['bytes'] + 1 - count)):
                    count += len(block)
                    if count > policy['capstone']['bytes']: raise ValueError('Decoder source exceeds its pinned size')
                    output.write(block)
            if pending.stat().st_size != policy['capstone']['bytes'] or sha(pending) != policy['capstone']['sha256']:
                raise ValueError('Decoder source download differs from its pinned receipt')
            os.replace(pending, archive)
        finally: pending.unlink(missing_ok=True)
    properties = (ndk / 'source.properties').read_text()
    if 'Pkg.Revision = ' + policy['ndk'] not in properties.splitlines():
        raise ValueError('Use the exact original Android NDK revision')
    prebuilt = ndk / 'toolchains/llvm/prebuilt' / ('windows-x86_64' if os.name == 'nt' else 'linux-x86_64')
    compiler = prebuilt / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
    readelf = prebuilt / 'bin' / ('llvm-readelf.exe' if os.name == 'nt' else 'llvm-readelf')
    source = source_tree(archive, work / 'source', policy['capstone'])
    shim = ROOT / 'packaging/android/app/src/main/cpp/x64_decoder.c'
    compiler_policy = json.loads((ROOT / 'packaging/android/python-dependencies.json').read_text())
    recipe = {'policy_sha256': sha(lock_path), 'transport_sha256': sha(shim),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': policy['capstone']['sha256'],
        'ndk_policy_sha256': hashlib.sha256(canonical(compiler_policy['ndk'])).hexdigest()}
    # Reuse exact previously built software bits, not a relabelled foreign .so.
    cached = work / 'assets/native-decoder-manifest.json'
    receipt_path = work / 'build-receipt.json'
    if cached.is_file() and receipt_path.is_file():
        manifest = json.loads(cached.read_text()); receipt = json.loads(receipt_path.read_text())
        if manifest.get('recipe') == recipe and receipt.get('recipe') == recipe:
            verify_bundle(work)
            if receipt.get('compiler_sha256') != sha(compiler) or receipt.get('manifest_sha256') != sha(cached):
                raise ValueError('The cached decoder compiler/manifest receipt changed')
            return manifest
    spec = importlib.util.spec_from_file_location('toolkit_python_dependency_builder', ROOT / 'scripts/build-android-python-dependencies.py')
    dependency_builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(dependency_builder)
    ndk_inventory = dependency_builder.verify_ndk(ndk, Path(ndk_archive).absolute(), compiler_policy['ndk'])
    libraries = {}
    spec = importlib.util.spec_from_file_location('toolkit_apk_audit', ROOT / 'scripts/verify-android-apk.py')
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    for abi, target in policy['abis'].items():
        output = work / 'jniLibs' / abi / policy['library']; _no_links(output); output.parent.mkdir(parents=True, exist_ok=True)
        flags = ['-target', target + str(policy['api']), '--sysroot=' + str(prebuilt / 'sysroot'),
            '-std=c99', '-O2', '-fPIC', '-shared', '-fvisibility=hidden', '-fno-ident',
            '-ffile-prefix-map=' + str(source) + '=/capstone-src',
            '-ffile-prefix-map=' + str(ROOT) + '=/toolkit-src',
            '-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384',
            '-Wl,--build-id=sha1', '-Wl,-soname,' + policy['library'],
            '-I' + str(source / 'include'), '-I' + str(source)]
        flags += ['-D' + value for value in policy['capstone']['definitions']]
        flags += [str(source / value) for value in policy['capstone']['sources']]
        flags += [str(shim), '-lm', '-ldl', '-o', str(output)]
        subprocess.run([str(compiler), *flags], check=True, cwd=work, timeout=600)
        proof = audit.native(output.read_bytes(), abi)
        dynamic = subprocess.run([str(readelf), '-d', str(output)], check=True, capture_output=True, text=True).stdout
        import re
        needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic)
        if not needed or set(needed) - {'libm.so', 'libdl.so', 'libc.so'}:
            raise ValueError('The decoder linked an undeclared platform dependency')
        libraries[abi] = {**proof, 'bytes': output.stat().st_size, 'needed': needed,
            'entry': 'lib/' + abi + '/' + policy['library']}
    licenses = {}
    for index, name in enumerate(policy['capstone']['licenses']):
        original = work / 'source' / name
        relative = 'native-decoder-licenses/' + str(index) + '-' + original.name
        destination = work / 'assets' / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        licenses[relative] = {'bytes': destination.stat().st_size, 'sha256': sha(destination)}
    # Recheck software inputs after compilation; no edited source or original
    # game binary can be substituted behind a successful source download.
    source_tree(archive, work / 'source', policy['capstone'])
    if recipe['transport_sha256'] != sha(shim) or recipe['builder_sha256'] != sha(Path(__file__)):
        raise ValueError('Decoder build recipe changed during compilation')
    manifest = {'schema': 'toolkit-android-native-decoders-v1', 'version': policy['capstone']['version'],
        'source': policy['capstone']['source'], 'source_sha256': policy['capstone']['sha256'],
        'recipe': recipe, 'ndk': policy['ndk'], 'ndk_archive_sha256': compiler_policy['ndk']['sha256'],
        'ndk_inventory_sha256': ndk_inventory, 'api': policy['api'], 'library': policy['library'],
        'libraries': libraries, 'licenses': licenses, 'original_client_execution': False}
    (work / 'assets/native-decoder-manifest.json').write_bytes(canonical(manifest))
    (work / 'build-receipt.json').write_bytes(canonical({'manifest_sha256': sha(work / 'assets/native-decoder-manifest.json'),
        'compiler_sha256': sha(compiler), 'recipe': recipe}))
    return manifest


def verify_bundle(work):
    work = Path(work).absolute(); _no_links(work)
    policy = json.loads((ROOT / 'packaging/android/native-decoders.json').read_text())
    manifest_path = work / 'assets/native-decoder-manifest.json'; _no_links(manifest_path)
    if manifest_path.stat().st_size > 65536: raise ValueError('Decoder manifest exceeds its bound')
    manifest = json.loads(manifest_path.read_text())
    recipe = {'policy_sha256': sha(ROOT / 'packaging/android/native-decoders.json'),
        'transport_sha256': sha(ROOT / 'packaging/android/app/src/main/cpp/x64_decoder.c'),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': policy['capstone']['sha256'],
        'ndk_policy_sha256': hashlib.sha256(canonical(json.loads((ROOT / 'packaging/android/python-dependencies.json').read_text())['ndk'])).hexdigest()}
    compiler_policy = json.loads((ROOT / 'packaging/android/python-dependencies.json').read_text())
    if (manifest.get('recipe') != recipe or manifest.get('source_sha256') != policy['capstone']['sha256']
            or manifest.get('schema') != 'toolkit-android-native-decoders-v1'
            or manifest.get('ndk') != policy['ndk'] or manifest.get('api') != policy['api']
            or manifest.get('ndk_archive_sha256') != compiler_policy['ndk']['sha256']
            or not isinstance(manifest.get('ndk_inventory_sha256'), str) or len(manifest['ndk_inventory_sha256']) != 64
            or manifest.get('library') != policy['library'] or manifest.get('original_client_execution') is not False
            or set(manifest.get('libraries', {})) != set(policy['abis'])):
        raise ValueError('The native decoder software closure does not match its owned recipe')
    expected = {'assets/native-decoder-manifest.json'}
    for abi, receipt in manifest['libraries'].items():
        name = 'jniLibs/' + abi + '/' + policy['library']; path = work / name; _no_links(path)
        if (not path.is_file() or path.stat().st_size != receipt['bytes'] or receipt['bytes'] > 16 * 1024**2
                or sha(path) != receipt['sha256'] or receipt['entry'] != 'lib/' + abi + '/' + policy['library']
                or receipt['minimum_load_alignment'] < policy['load_alignment']):
            raise ValueError('The actual native decoder differs from its software receipt')
        expected.add(name)
    expected_licenses = {'native-decoder-licenses/' + str(index) + '-' + Path(name).name
        for index, name in enumerate(policy['capstone']['licenses'])}
    if set(manifest.get('licenses', {})) != expected_licenses: raise ValueError('Decoder notices are incomplete')
    for name, receipt in manifest['licenses'].items():
        path = work / 'assets' / name; _no_links(path)
        if not path.is_file() or path.stat().st_size != receipt['bytes'] or receipt['bytes'] > 65536 or sha(path) != receipt['sha256']:
            raise ValueError('An original decoder notice is missing or changed')
        expected.add('assets/' + name)
    actual = set()
    for tree in ('assets', 'jniLibs'):
        for path in (work / tree).rglob('*'):
            _no_links(path)
            if path.is_file(): actual.add(path.relative_to(work).as_posix())
    if actual != expected: raise ValueError('Unexpected software files in the native decoder bundle')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--ndk-root', type=Path)
    parser.add_argument('--ndk-archive', type=Path)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        result = verify_bundle(args.work_dir)
    else:
        if not all((args.source_archive, args.ndk_root, args.ndk_archive)): parser.error('Supply exact source and original NDK inputs.')
        result = build(args.work_dir, args.source_archive, args.ndk_root, args.ndk_archive, download=args.download)
    print(json.dumps({'schema': result['schema'], 'source_sha256': result['source_sha256'], 'libraries': result['libraries']}))
