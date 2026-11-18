"""Build pinned XXH3 + owned JNI with the existing authenticated Android NDK.

No download, package installation, Python extension, game code or APK build.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links


def sha(path):
    _no_links(path)
    with path.open('rb') as source: return hashlib.file_digest(source, 'sha256').hexdigest()


def script(name):
    spec = importlib.util.spec_from_file_location('hash_' + name, ROOT/'scripts'/(name+'.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


def selected_source(archive, destination, policy):
    _no_links(archive); _no_links(destination)
    if archive.stat().st_size != policy['bytes'] or sha(archive) != policy['sha256']:
        raise ValueError('The original XXH3 archive differs from its pinned receipt')
    if set(policy['members']) != {'deps/xxhash/xxhash.h', 'deps/xxhash/LICENSE', 'LICENSE'}:
        raise ValueError('Review the selected original XXH3 source subset')
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 256 or len({row.name for row in members}) != len(members):
            raise ValueError('Unexpected original XXH3 archive inventory')
        for name, digest in policy['members'].items():
            original = source.getmember(policy['root']+'/'+name)
            if not original.isfile() or not 1 <= original.size <= 512*1024:
                raise ValueError('Unsafe original XXH3 source member')
            raw = source.extractfile(original).read()
            if len(raw) != original.size or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('An original XXH3 source member changed')
            target = destination/name; _no_links(target)
            if target.exists():
                if not target.is_file() or sha(target) != digest: raise ValueError('An extracted XXH3 member changed')
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output: output.write(raw)
    actual = set()
    for path in destination.rglob('*'):
        _no_links(path)
        if path.is_file(): actual.add(path.relative_to(destination).as_posix())
    if actual != set(policy['members']): raise ValueError('Unexpected files in the selected XXH3 source tree')
    return destination


def recipe():
    names = ('scripts/build-android-publisher-hash.py', 'scripts/build-android-python-dependencies.py',
        'packaging/android/publisher-hash-native.json', 'packaging/android/app/src/main/cpp/publisher_hash.c',
        'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/PublisherHash.java',
        'backend/android_publisher_hash.py', 'packaging/android/publisher-hash-authored-vectors.json')
    return {name: sha(ROOT/name) for name in names}


def build(work, archive, ndk, ndk_archive):
    work, archive, ndk, ndk_archive = map(lambda value: Path(value).absolute(), (work, archive, ndk, ndk_archive))
    for path in (work, archive, ndk, ndk_archive): _no_links(path)
    policy = json.loads((ROOT/'packaging/android/publisher-hash-native.json').read_text())
    if (policy['schema'] != 'toolkit-android-publisher-hash-recipe-v1' or policy['contract'] != 'toolkit-publisher-hash-v1'
            or policy['max_bytes'] != 4096 or policy['seed'] != 0 or policy['custom_secret'] is not False
            or policy['original_client_execution'] is not False or policy['cpython'] is not False
            or policy['source']['xxhash_version'] != '0.8.4' or policy['api'] != 24
            or policy['abis'] != {'arm64-v8a':'aarch64-linux-android', 'x86_64':'x86_64-linux-android'}):
        raise ValueError('Review the bounded publisher hash recipe')
    source = selected_source(archive, work/'source', policy['source'])
    inputs = script('build-android-python-dependencies'); pins = json.loads(inputs.POLICY.read_text())
    if policy['ndk'] != pins['ndk_revision']: raise ValueError('Use the authenticated existing Android compiler')
    inventory = inputs.verify_ndk(ndk, ndk_archive, pins['ndk'])
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler = ndk/'toolchains/llvm/prebuilt'/host/'bin'/('clang.exe' if os.name == 'nt' else 'clang')
    readelf = compiler.with_name('llvm-readelf.exe' if os.name == 'nt' else 'llvm-readelf')
    identity = recipe(); libraries = {}; audit = script('verify-android-apk')
    expected_exports = {'toolkit_publisher_xxh3_64',
        'Java_io_github_firebird55_gameimmersiontoolkit_PublisherHash_nativeProof',
        'Java_io_github_firebird55_gameimmersiontoolkit_PublisherHash_nativeHash64'}
    for abi, target in policy['abis'].items():
        output = work/'jniLibs'/abi/policy['library']; _no_links(output); output.parent.mkdir(parents=True, exist_ok=True)
        command = [str(compiler), '-target', target+str(policy['api']), '-std=c99', '-O2', '-fPIC', '-shared',
            '-fvisibility=hidden', '-fno-ident', '-Werror', '-Wall', '-Wextra',
            '-Wl,--as-needed', '-Wl,-z,defs', '-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384',
            '-Wl,-soname,'+policy['library'], '-ffile-prefix-map='+str(source)+'=/xxh3-source',
            '-ffile-prefix-map='+str(ROOT)+'=/toolkit-source', '-I'+str(source/'deps/xxhash'),
            str(ROOT/'packaging/android/app/src/main/cpp/publisher_hash.c'), '-o', str(output)]
        subprocess.run(command, cwd=work, check=True, timeout=120)
        raw = output.read_bytes()
        if len(raw) > 1024**2: raise ValueError('The bounded hash library exceeded its software limit')
        elf = audit.native(raw, abi)
        parsed = inputs.elf_contract(raw, pins['targets'][abi]['elf_machine'], expected_dependencies=('libc.so',))
        dynamic = subprocess.run([str(readelf), '-d', str(output)], check=True, capture_output=True, text=True).stdout
        if re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic) != parsed['needed']:
            raise ValueError('The hash library linked an unexpected supplier')
        symbols = subprocess.run([str(readelf), '--dyn-syms', str(output)], check=True, capture_output=True, text=True).stdout
        exports = {line.split()[-1] for line in symbols.splitlines() if re.search(r'\bGLOBAL\s+DEFAULT\b', line) and ' UND ' not in line}
        if exports != expected_exports: raise ValueError('The hash library exposes an unexpected API')
        libraries[abi] = {**elf, 'bytes':len(raw), 'needed':parsed['needed'], 'exports':sorted(exports),
            'entry':'lib/'+abi+'/'+policy['library']}
    licenses = {}
    for filename, original in [('xxhash-LICENSE', 'deps/xxhash/LICENSE'), ('python-xxhash-LICENSE', 'LICENSE')]:
        name = 'publisher-hash-licenses/'+filename; raw = (source/original).read_bytes()
        destination = work/'assets'/name; _no_links(destination); destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw); licenses[name] = {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
    selected_source(archive, source, policy['source'])
    if recipe() != identity: raise ValueError('The hash recipe changed during compilation')
    manifest = {'schema':'toolkit-android-publisher-hash-bundle-v1', 'contract':policy['contract'],
        'source':policy['source']['source'], 'source_sha256':policy['source']['sha256'],
        'header_sha256':policy['source']['members']['deps/xxhash/xxhash.h'], 'version':'0.8.4',
        'recipe':identity, 'source_members':policy['source']['members'], 'library':policy['library'],
        'libraries':libraries, 'licenses':licenses, 'max_bytes':4096, 'seed':0, 'custom_secret':False,
        'original_client_execution':False, 'ndk':policy['ndk'], 'api':policy['api'],
        'ndk_archive_sha256':pins['ndk']['sha256'], 'ndk_inventory_sha256':inventory,
        'compiler_sha256':sha(compiler), 'target_runtime_acceptance':'not-established-by-compilation',
        'apk_delivery':'not-established-without-reviewed-packaging'}
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    (work/'assets/publisher-hash-manifest.json').write_bytes(raw)
    receipt = {'schema':'toolkit-publisher-hash-build-v1', 'manifest_sha256':hashlib.sha256(raw).hexdigest(),
        'libraries':libraries, 'source_sha256':policy['source']['sha256'], 'recipe':identity,
        'android_execution':'not-established', 'release_eligibility':False}
    (work/'hash-build-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work-dir', 'source', 'ndk', 'ndk-archive'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(build(args.work_dir, args.source, args.ndk, args.ndk_archive)))
